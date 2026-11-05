# mypy: disable-error-code="no-untyped-call"
"""Detecção de símbolos contra os símbolos das fichas de referência (E06.1).

Uso::

    python -m scripts.benchmark_simbolos_ficha --rodada RODADA --saida DIR \
        [--metodo atual ...] [--processos N]

Para cada folha de ``RODADA/rodada.json`` lê a referência em ``pdfs/ID/ficha/referencia.json``,
acha o PDF por ``raiz_corpus`` + ``caminho_relativo`` (recusando, antes de qualquer leitura, o
caminho com o componente ``avaliacao-cega``), confere o ``sha256`` contra o da referência e mede
cada método de detecção. Uma rodada cujo próprio diretório tem esse componente é recusada antes de
ler o ``rodada.json``. A guarda é lexical (componentes do caminho, sem ``resolve``): não pega nome
curto 8.3, symlink nem junction para a pasta cega; a proteção real é o protocolo da curadoria.
Grava ``simbolos-ficha.json`` e ``simbolos-ficha.md`` em ``--saida``,
sem caminho absoluto nem nome de PDF: a folha é identificada só pelo ``pdf_id`` da rodada.

O método ``atual`` é a união do runner de benchmark sem raster nem estrutural: detector legado,
estais, transformadores e pacotes declarativos. Essa união não passa por ``reconcile_symbols``, ao
contrário do runner do servidor; por isso o relatório conta as duplicatas por método e classe.

Regras (R-E06.1-2 a R-E06.1-5b do plano):

* dois critérios de casamento, ambos 1-1 e gulosos por (página, classe): ``centro`` (principal; o
  centro da predição na caixa da referência, expandida por ``TOLERANCIA_CENTRO``) e ``iou``
  (diagnóstico; ``geometry_match`` do avaliador E02);
* saem antes do casamento as predições de contexto de legenda ou informativo e as de classe que
  não aparece em nenhuma referência da rodada; dos símbolos de referência, os dos postes com
  ``simbolos`` pendente;
* das predições que sobram, só é FP a que não está fora das regiões anotadas nem perto
  (``RAIO_POSTE_PENDENTE``) de um poste com símbolos pendentes. A precisão é um limite inferior,
  pois a ficha só anota símbolo associado a poste;
* método que falha numa folha fica fora dos totais dele; ``comparacao`` traz os totais de cada
  método restritos às folhas em que todos tiveram sucesso.

Com ``--processos N`` (inteiro >= 1, padrão 1) as folhas são medidas em até ``min(N, folhas, 61)``
processos; a saída mantém a ordem do ``rodada.json`` e o JSON é igual ao serial, salvo ``tempo_s``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations
from pathlib import Path
from time import perf_counter
from typing import Any, Final, Literal, TypedDict

import pymupdf

import scripts.symbol_benchmark_runner as runner
from scripts.curation_round import RodadaError, carregar_rodada
from scripts.ficha_poste import carregar_ficha
from scripts.symbol_benchmark_evaluator import geometry_match
from zeny_project_handler.adapters.analysis import (
    declarative_symbols,
    legacy_symbols,
    pymupdf_guys,
    pymupdf_transformers,
)
from zeny_project_handler.adapters.analysis.drawing_model.family import reconhecer_familia
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import impressao_estrutural

TOLERANCIA_CENTRO: Final = 0.005
RAIO_POSTE_PENDENTE: Final = 0.05
ESQUEMA: Final = "simbolos-ficha-v1"
CONTEXTOS_NAO_DESENHO: Final = frozenset({"legend", "informative"})
COMPONENTE_CEGO: Final = "avaliacao-cega"
MAXIMO_PROCESSOS: Final = 61
LIMITE_ERRO: Final = 300

Registro = dict[str, Any]
Criterio = Literal["centro", "iou"]
CRITERIOS: Final[tuple[Criterio, ...]] = ("centro", "iou")
Caixa = Sequence[float]
Item = Mapping[str, Any]
_TFF: Final = ("tp", "fp", "fn")


class Predicao(TypedDict):
    pagina: int
    classe: str
    bbox: list[float]
    metodo: str
    contexto: str


class ResultadoMetodo(TypedDict):
    predicoes: list[Predicao]
    assinatura: dict[str, str]
    falha: str | None


class _FolhaError(Exception):
    """Falha esperada de uma folha, com mensagem já saneada."""


# --- saneamento -------------------------------------------------------------------------

# Dentro de um caminho do Windows os componentes podem ter espaço; o último pode ter espaço até
# a extensão (nome de PDF com espaços) ou termina no primeiro espaço, se não houver extensão.
_RESTO_WINDOWS = (
    r"(?:[^\\/:*?\"<>|\r\n]+[\\/])*"
    r"(?:[^\\/:*?\"<>|\r\n']*?\.[A-Za-z0-9]{1,5}\b|[^\s\\/:*?\"<>|']*)"
)
_CAMINHO_WINDOWS = re.compile(r"(?:\\\\[?.][\\/])?[A-Za-z]:[\\/]" + _RESTO_WINDOWS)
_CAMINHO_UNC = re.compile(r"\\\\[^\\/\s'\"]+(?:[\\/]" + _RESTO_WINDOWS + ")?")
_CAMINHO_POSIX = re.compile(r"(?<![\w.:])/(?:[\w.\-~]+/)+[\w.\-~]*")
_NOME_PDF = re.compile(r"[^\s'\"\\/]+\.pdf", re.IGNORECASE)


def sanear(texto: str, ocultar: Iterable[str] = ()) -> str:
    """Primeira linha do erro, sem caminho absoluto nem nome de PDF."""
    for trecho in sorted({item for item in ocultar if item}, key=len, reverse=True):
        texto = re.sub(re.escape(trecho), "<oculto>", texto, flags=re.IGNORECASE)
    linha = next((item for item in texto.splitlines() if item.strip()), "")
    for padrao in (_CAMINHO_WINDOWS, _CAMINHO_UNC, _CAMINHO_POSIX, _NOME_PDF):
        linha = padrao.sub("<caminho>", linha)
    return " ".join(linha.split())[:LIMITE_ERRO]


def _falha(erro: str) -> Registro:
    return {"situacao": "falha", "erro": erro}


# --- geometria e casamento --------------------------------------------------------------


def _centro(bbox: Caixa) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _na_caixa(ponto: tuple[float, float], bbox: Caixa, folga: float) -> bool:
    x, y = ponto
    return bool(bbox[0] - folga <= x <= bbox[2] + folga and bbox[1] - folga <= y <= bbox[3] + folga)


def _elegivel(referencia: Mapping[str, Any], predicao: Mapping[str, Any], criterio: str) -> bool:
    if criterio == "centro":
        return _na_caixa(_centro(predicao["bbox"]), referencia["bbox"], TOLERANCIA_CENTRO)
    resultado = geometry_match({"bbox": predicao["bbox"]}, {"bbox": referencia["bbox"]})
    return bool(resultado["eligible"])


def _indices_por_grupo(itens: Sequence[Mapping[str, Any]]) -> dict[tuple[int, str], list[int]]:
    grupos: dict[tuple[int, str], list[int]] = defaultdict(list)
    for indice, item in enumerate(itens):
        grupos[item["pagina"], item["classe"]].append(indice)
    return grupos


def casar(
    referencias: Sequence[Mapping[str, Any]],
    predicoes: Sequence[Mapping[str, Any]],
    criterio: Criterio,
) -> list[tuple[int, int]]:
    """Pares ``(índice da referência, índice da predição)``, 1-1 e gulosos por (página, classe).

    Os pares elegíveis entram por distância de centro, depois índice da referência, depois o da
    predição; cada lado é usado uma vez. A saída vem ordenada por índice da referência.
    """
    por_grupo = _indices_por_grupo(predicoes)
    candidatos: list[tuple[float, int, int]] = []
    for i, referencia in enumerate(referencias):
        centro = _centro(referencia["bbox"])
        for j in por_grupo.get((referencia["pagina"], referencia["classe"]), ()):
            if _elegivel(referencia, predicoes[j], criterio):
                candidatos.append((math.dist(centro, _centro(predicoes[j]["bbox"])), i, j))
    candidatos.sort()
    usadas_referencia: set[int] = set()
    usadas_predicao: set[int] = set()
    pares: list[tuple[int, int]] = []
    for _, i, j in candidatos:
        if i not in usadas_referencia and j not in usadas_predicao:
            usadas_referencia.add(i)
            usadas_predicao.add(j)
            pares.append((i, j))
    return sorted(pares)


# --- avaliação de uma folha -------------------------------------------------------------


def _simbolos_validos(ficha: Mapping[str, Any]) -> list[Registro]:
    return [
        {"pagina": poste["pagina"], "classe": simbolo["classe"], "bbox": simbolo["bbox"]}
        for poste in ficha["postes"]
        if "simbolos" not in poste["pendentes"]
        for simbolo in poste["simbolos"]
    ]


def classes_da_ficha(ficha: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(s["classe"] for poste in ficha["postes"] for s in poste["simbolos"])


def _postes_pendentes(ficha: Mapping[str, Any]) -> list[Registro]:
    return [
        {"pagina": poste["pagina"], "bbox": poste["bbox"]}
        for poste in ficha["postes"]
        if "simbolos" in poste["pendentes"]
    ]


def _regioes(ficha: Mapping[str, Any]) -> list[Registro] | None:
    escopo = ficha["escopo_anotacao"]
    return list(escopo["regioes"]) if escopo["tipo"] == "regional" else None


def _taxa(numerador: int, denominador: int) -> float | None:
    return numerador / denominador if denominador else None


def _contagem(tp: int, fp: int, fn: int) -> Registro:
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precisao": _taxa(tp, tp + fp),
        "recall": _taxa(tp, tp + fn),
    }


def _por_classe(tp: Counter[str], fp: Counter[str], fn: Counter[str]) -> Registro:
    return {
        classe: _contagem(tp[classe], fp[classe], fn[classe])
        for classe in sorted(set(tp) | set(fp) | set(fn))
    }


def _geral(por_classe: Mapping[str, Mapping[str, Any]]) -> Registro:
    return _contagem(*(sum(item[chave] for item in por_classe.values()) for chave in _TFF))


def _no_pagina(
    ponto: tuple[float, float], pagina: int, caixas: Iterable[Mapping[str, Any]], folga: float
) -> bool:
    return any(
        caixa["pagina"] == pagina and _na_caixa(ponto, caixa["bbox"], folga) for caixa in caixas
    )


def _bloco_criterio(
    referencias: Sequence[Registro],
    predicoes: Sequence[Item],
    fora_do_escopo: Mapping[str, int],
    pendentes: Sequence[Registro],
    regioes: Sequence[Registro] | None,
    criterio: Criterio,
) -> Registro:
    pares = casar(referencias, predicoes, criterio)
    casadas_referencia = {i for i, _ in pares}
    casadas_predicao = {j for _, j in pares}
    tp = Counter(referencias[i]["classe"] for i in casadas_referencia)
    fn = Counter(ref["classe"] for i, ref in enumerate(referencias) if i not in casadas_referencia)
    fp: Counter[str] = Counter()
    fora_das_regioes = perto_de_poste_pendente = 0
    for j, predicao in enumerate(predicoes):
        if j in casadas_predicao:
            continue
        centro = _centro(predicao["bbox"])
        pagina = predicao["pagina"]
        if regioes is not None and not _no_pagina(centro, pagina, regioes, 0.0):
            fora_das_regioes += 1
        elif _no_pagina(centro, pagina, pendentes, RAIO_POSTE_PENDENTE):
            perto_de_poste_pendente += 1
        else:
            fp[predicao["classe"]] += 1
    por_classe = _por_classe(tp, fp, fn)
    return {
        "por_classe": por_classe,
        "geral": _geral(por_classe),
        "fora_do_escopo": dict(sorted(fora_do_escopo.items())),
        "fora_das_regioes": fora_das_regioes,
        "perto_de_poste_pendente": perto_de_poste_pendente,
    }


def _duplicatas(predicoes: Sequence[Item]) -> dict[str, int]:
    """Pares de predições da mesma classe e página com o centro de uma na caixa da outra."""
    contagem: Counter[str] = Counter()
    for (_, classe), indices in _indices_por_grupo(predicoes).items():
        for i, j in combinations(indices, 2):
            a, b = predicoes[i]["bbox"], predicoes[j]["bbox"]
            if _na_caixa(_centro(a), b, 0.0) or _na_caixa(_centro(b), a, 0.0):
                contagem[classe] += 1
    return dict(sorted(contagem.items()))


def avaliar_predicoes(
    referencia: Mapping[str, Any],
    predicoes: Sequence[Item],
    classes_avaliadas: Collection[str],
) -> Registro:
    """Contagens de um método numa folha, nos dois critérios (R-E06.1-3)."""
    desenho = [p for p in predicoes if p["contexto"] not in CONTEXTOS_NAO_DESENHO]
    referencias = _simbolos_validos(referencia)
    escopo = set(classes_avaliadas) | {ref["classe"] for ref in referencias}
    no_escopo = [p for p in desenho if p["classe"] in escopo]
    fora_do_escopo = Counter(p["classe"] for p in desenho if p["classe"] not in escopo)
    pendentes = _postes_pendentes(referencia)
    regioes = _regioes(referencia)
    return {
        "predicoes": len(predicoes),
        "contexto_nao_desenho": len(predicoes) - len(desenho),
        "duplicatas": _duplicatas(desenho),
        **{
            criterio: _bloco_criterio(
                referencias, no_escopo, fora_do_escopo, pendentes, regioes, criterio
            )
            for criterio in CRITERIOS
        },
    }


# --- métodos ----------------------------------------------------------------------------


def _falha_do_manifesto(manifesto: Mapping[str, Any]) -> str | None:
    falhas = manifesto.get("failures") or []
    if falhas:
        return str(falhas[0].get("reason") or "falha sem motivo")
    if manifesto.get("status") == "failed":
        return "status failed"
    return None


def _predicao_do_runner(item: Mapping[str, Any]) -> Predicao:
    return {
        "pagina": int(item["page"]),
        "classe": str(item["class_id"]),
        "bbox": [float(valor) for valor in item["bbox"]],
        "metodo": str(item["method_id"]),
        "contexto": str(item["context"]),
    }


def _predicoes_atual(pdf: Path, pdf_id: str) -> ResultadoMetodo:
    """União do runner sem raster nem estrutural (R-E06.1-1)."""
    manifesto, previstas, execucoes = runner.infer_pdf(
        pdf, pdf_id, include_transformers=True, include_guys=True, include_packages=True
    )
    return {
        "predicoes": [_predicao_do_runner(item) for item in previstas],
        "assinatura": {
            str(item["method_id"]): str(item["signature"])
            for item in execucoes
            if item.get("signature")
        },
        "falha": _falha_do_manifesto(manifesto),
    }


def _componente(perfil: Any, **extras: Any) -> Registro:
    return {
        "metodo_id": perfil.metodo_id,
        "versao": perfil.versao,
        "assinatura": perfil.assinatura(),
        "parametros": {chave: None if v is None else str(v) for chave, v in perfil.parametros},
        **extras,
    }


def _assinatura_atual() -> Registro:
    pacotes = declarative_symbols.carregar_pacotes()
    hash_pacotes = runner.package_method_metadata(pacotes)["package_sha256"]
    return {
        "metodo_id": "atual",
        "versao": "uniao-runner-v1",
        "composicao": "legado + estais + transformadores + pacotes; sem raster nem estrutural",
        "reconcile_symbols": False,
        "componentes": [
            _componente(legacy_symbols.perfil_simbolos_legados()),
            _componente(pymupdf_guys.perfil_estais()),
            _componente(pymupdf_transformers.perfil_transformadores()),
            _componente(declarative_symbols.perfil_pacotes(pacotes), package_sha256=hash_pacotes),
        ],
    }


METODOS: Final[dict[str, Callable[[Path, str], ResultadoMetodo]]] = {"atual": _predicoes_atual}
ASSINATURAS: Final[dict[str, Callable[[], Registro]]] = {"atual": _assinatura_atual}


def _medir_metodo(
    nome: str,
    pdf: Path,
    pdf_id: str,
    referencia: Mapping[str, Any],
    classes: Collection[str],
    ocultar: Sequence[str],
) -> Registro:
    inicio = perf_counter()
    try:
        resultado = METODOS[nome](pdf, pdf_id)
    except Exception as erro:
        return _falha(sanear(f"{type(erro).__name__}: {erro}", ocultar))
    tempo = perf_counter() - inicio
    if resultado["falha"]:
        return _falha(sanear(resultado["falha"], ocultar))
    bloco = avaliar_predicoes(referencia, resultado["predicoes"], classes)
    return {"situacao": "ok", "tempo_s": tempo, "assinatura": resultado["assinatura"], **bloco}


def _ocultar_pdf(pdf: Path) -> list[str]:
    return [str(pdf), pdf.as_posix(), pdf.name, str(pdf.parent), pdf.parent.as_posix()]


def medir_pdf(
    pdf: Path,
    referencia: Mapping[str, Any],
    pdf_id: str,
    metodos: Sequence[str],
    *,
    classes_avaliadas: Collection[str] | None = None,
) -> Registro:
    """Uma folha: família (fora do ``tempo_s``) e, por método, os dois critérios.

    ``classes_avaliadas`` são as da rodada inteira; sem elas valem as desta referência.
    """
    classes = classes_da_ficha(referencia) if classes_avaliadas is None else classes_avaliadas
    with pymupdf.open(pdf) as documento:
        familia = reconhecer_familia(impressao_estrutural(documento)).familia
    ocultar = _ocultar_pdf(pdf)
    return {
        "situacao": "ok",
        "familia": familia,
        "simbolos_referencia": len(_simbolos_validos(referencia)),
        "metodos": {
            nome: _medir_metodo(nome, pdf, pdf_id, referencia, classes, ocultar) for nome in metodos
        },
    }


# --- localização do PDF e pool ----------------------------------------------------------


def _componente_equivalente(parte: str) -> str:
    """Nome equivalente no Windows: sem fluxo ``:x``, sem pontos/espaços finais, sem caixa."""
    return parte.split(":", 1)[0].rstrip(". ").casefold()


def _componentes(*caminhos: str) -> set[str]:
    partes: set[str] = set()
    for caminho in caminhos:
        partes.update(_componente_equivalente(parte) for parte in re.split(r"[\\/]+", caminho))
    return partes


def _caminho_cego(*caminhos: str) -> bool:
    return COMPONENTE_CEGO in _componentes(*caminhos)


def localizar_pdf(rodada: Path, raiz_corpus: str, caminho_relativo: str) -> Path:
    """Caminho do PDF; recusa o componente ``avaliacao-cega`` antes de qualquer acesso a disco.

    A guarda é lexical: compara os componentes do diretório da rodada, de ``raiz_corpus`` e de
    ``caminho_relativo``, e os do caminho normalizado dos três (``..`` incluído). Não pega nome
    curto 8.3, symlink nem junction para a pasta cega; a proteção real é o protocolo da curadoria.
    """
    normalizado = os.path.normpath(os.path.join(raiz_corpus, caminho_relativo))
    completo = os.path.normpath(os.path.join(str(rodada), raiz_corpus, caminho_relativo))
    if _caminho_cego(str(rodada), raiz_corpus, caminho_relativo, normalizado, completo):
        raise _FolhaError(f"caminho recusado: componente {COMPONENTE_CEGO}")
    return rodada / raiz_corpus / caminho_relativo


@dataclass(frozen=True, slots=True)
class _Tarefa:
    rodada: Path
    raiz_corpus: str
    entrada: Registro
    referencia: Registro
    metodos: tuple[str, ...]
    classes: frozenset[str]


def _medir_folha(tarefa: _Tarefa) -> Registro:
    caminho_relativo = str(tarefa.entrada["caminho_relativo"])
    ocultar = [str(tarefa.rodada), tarefa.rodada.as_posix(), caminho_relativo]
    try:
        pdf = localizar_pdf(tarefa.rodada, tarefa.raiz_corpus, caminho_relativo)
        if not pdf.is_file():
            raise _FolhaError("PDF não encontrado no corpus da rodada")
        if sha256(pdf.read_bytes()).hexdigest() != tarefa.referencia["pdf_sha256"]:
            raise _FolhaError("sha256 do PDF difere do pdf_sha256 da referência")
        return medir_pdf(
            pdf,
            tarefa.referencia,
            str(tarefa.entrada["pdf_id"]),
            tarefa.metodos,
            classes_avaliadas=tarefa.classes,
        )
    except _FolhaError as erro:
        return _falha(str(erro))
    except Exception as erro:
        return _falha(sanear(f"{type(erro).__name__}: {erro}", ocultar))


def _medir_todas(tarefas: Sequence[_Tarefa], efetivos: int) -> list[Registro]:
    if efetivos <= 1 or len(tarefas) <= 1:
        return [_medir_folha(tarefa) for tarefa in tarefas]
    resultados: list[Registro] = []
    try:
        with ProcessPoolExecutor(max_workers=efetivos) as pool:
            resultados.extend(pool.map(_medir_folha, tarefas))
    except BrokenProcessPool:
        pass
    resultados.extend(
        _falha("processo do pool encerrado antes de medir a folha")
        for _ in tarefas[len(resultados) :]
    )
    return resultados


# --- agregação --------------------------------------------------------------------------


def _somar_contadores(blocos: Iterable[Mapping[str, int]]) -> dict[str, int]:
    soma: Counter[str] = Counter()
    for bloco in blocos:
        soma.update(bloco)
    return dict(sorted(soma.items()))


def _somar_criterio(blocos: Sequence[Mapping[str, Any]]) -> Registro:
    contagens: dict[str, Counter[str]] = {chave: Counter() for chave in _TFF}
    for bloco in blocos:
        for classe, item in bloco["por_classe"].items():
            for chave in _TFF:
                contagens[chave][classe] += item[chave]
    por_classe = _por_classe(*(contagens[chave] for chave in _TFF))
    return {
        "por_classe": por_classe,
        "geral": _geral(por_classe),
        "fora_do_escopo": _somar_contadores(b["fora_do_escopo"] for b in blocos),
        "fora_das_regioes": sum(b["fora_das_regioes"] for b in blocos),
        "perto_de_poste_pendente": sum(b["perto_de_poste_pendente"] for b in blocos),
    }


def _agregar_metodo(blocos: Sequence[Mapping[str, Any]], com_falha: int) -> Registro:
    return {
        "folhas_medidas": len(blocos),
        "folhas_com_falha": com_falha,
        "predicoes": sum(b["predicoes"] for b in blocos),
        "contexto_nao_desenho": sum(b["contexto_nao_desenho"] for b in blocos),
        "duplicatas": _somar_contadores(b["duplicatas"] for b in blocos),
        **{criterio: _somar_criterio([b[criterio] for b in blocos]) for criterio in CRITERIOS},
    }


def _agregar_folhas(folhas: Sequence[Mapping[str, Any]], metodos: Sequence[str]) -> Registro:
    """Totais por método de folhas já medidas (``situacao`` ``ok``)."""
    agregado: Registro = {}
    for nome in metodos:
        blocos = [f["metodos"][nome] for f in folhas]
        ok = [b for b in blocos if b["situacao"] == "ok"]
        agregado[nome] = _agregar_metodo(ok, len(blocos) - len(ok))
    return agregado


def _agregar_total(por_pdf: Mapping[str, Mapping[str, Any]], metodos: Sequence[str]) -> Registro:
    com_referencia = [folha for folha in por_pdf.values() if folha["situacao"] != "sem_referencia"]
    medidas = [folha for folha in com_referencia if folha["situacao"] == "ok"]
    agregado = _agregar_folhas(medidas, metodos)
    for nome in metodos:
        agregado[nome]["folhas_com_falha"] += len(com_referencia) - len(medidas)
    return agregado


def _agregar_comparacao(
    por_pdf: Mapping[str, Mapping[str, Any]], metodos: Sequence[str]
) -> Registro:
    com_referencia = [i for i, f in por_pdf.items() if f["situacao"] != "sem_referencia"]
    comuns = [
        i
        for i in com_referencia
        if por_pdf[i]["situacao"] == "ok"
        and all(por_pdf[i]["metodos"][nome]["situacao"] == "ok" for nome in metodos)
    ]
    agregado = _agregar_folhas([por_pdf[i] for i in comuns], metodos)
    for nome in metodos:
        agregado[nome]["folhas_com_falha"] = len(com_referencia) - len(comuns)
    return {"folhas": comuns, "metodos": agregado}


def _agregar_por_familia(
    por_pdf: Mapping[str, Mapping[str, Any]], metodos: Sequence[str]
) -> Registro:
    grupos: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for folha in por_pdf.values():
        if folha["situacao"] == "ok":
            grupos[folha["familia"]].append(folha)
    return {familia: _agregar_folhas(grupos[familia], metodos) for familia in sorted(grupos)}


# --- relatório --------------------------------------------------------------------------


def _pct(valor: float | None) -> str:
    return "n/d" if valor is None else f"{valor:.1%}"


def _linhas_criterio(criterio: str, bloco: Mapping[str, Any]) -> list[str]:
    linhas = [
        f"**{criterio}**",
        "",
        "| classe | tp | fp | fn | precisão | recall |",
        "|---|---|---|---|---|---|",
    ]
    itens = [*bloco["por_classe"].items(), ("(geral)", bloco["geral"])]
    linhas += [
        f"| {classe} | {i['tp']} | {i['fp']} | {i['fn']} | {_pct(i['precisao'])} "
        f"| {_pct(i['recall'])} |"
        for classe, i in itens
    ]
    return [
        *linhas,
        "",
        f"Fora do escopo: {bloco['fora_do_escopo'] or 'nenhuma'}; "
        f"fora das regiões: {bloco['fora_das_regioes']}; "
        f"perto de poste pendente: {bloco['perto_de_poste_pendente']}.",
        "",
    ]


def _linhas_metodo(titulo: str, bloco: Mapping[str, Any]) -> list[str]:
    linhas = [
        f"#### {titulo}",
        "",
        f"Folhas medidas: {bloco['folhas_medidas']}; com falha: {bloco['folhas_com_falha']}; "
        f"predições: {bloco['predicoes']}; contexto não desenho: {bloco['contexto_nao_desenho']}; "
        f"duplicatas: {bloco['duplicatas'] or 'nenhuma'}.",
        "",
    ]
    for criterio in CRITERIOS:
        linhas += _linhas_criterio(criterio, bloco[criterio])
    return linhas


def _linhas_bloco(titulo: str, por_metodo: Mapping[str, Mapping[str, Any]]) -> list[str]:
    linhas = [f"### {titulo}", ""]
    for nome, bloco in por_metodo.items():
        linhas += _linhas_metodo(nome, bloco)
    return linhas


def _markdown(relatorio: Mapping[str, Any], processos: int, efetivos: int) -> str:
    opcoes = relatorio["opcoes"]
    linhas = [
        "# Símbolos contra as fichas de referência",
        "",
        f"Esquema {relatorio['schema_version']}. Métodos: {', '.join(opcoes['metodos'])}. "
        f"PyMuPDF {opcoes['pymupdf']}.",
        f"Processos: {processos} (efetivos: {efetivos}).",
        f"Classes avaliadas: {', '.join(opcoes['classes_avaliadas']) or 'nenhuma'}.",
        "",
        "- `atual` é a união legado, estais, transformadores e pacotes de `infer_pdf`, sem raster "
        "nem estrutural. Ela não passa por `reconcile_symbols`, ao contrário do runner do "
        "servidor; as duplicatas por método e classe estão contadas.",
        "- Casamento 1-1 guloso por página e classe. `centro` (principal): centro da predição na "
        f"caixa da referência, com tolerância {opcoes['tolerancia_centro']}. `iou` (diagnóstico): "
        "`geometry_match` do avaliador E02.",
        "- A precisão é um limite inferior: a ficha só anota símbolo associado a poste. Não são FP "
        "a predição de legenda ou informativa, de classe fora do escopo, fora das regiões "
        f"anotadas ou perto (raio {opcoes['raio_poste_pendente']}) de poste com símbolos "
        "pendentes.",
        "- `tempo_s` (só em `por_pdf` do JSON) inclui o `tracemalloc` de `infer_pdf`.",
        "",
        "## Total",
        "",
        *_linhas_bloco("Todas as folhas medidas", relatorio["total"]),
        *_linhas_bloco(
            f"Comparação, mesmas folhas ({len(relatorio['comparacao']['folhas'])})",
            relatorio["comparacao"]["metodos"],
        ),
        "## Por família",
        "",
    ]
    for familia, por_metodo in relatorio["por_familia"].items():
        linhas += _linhas_bloco(f"Família {familia}", por_metodo)
    linhas += ["## Folhas", ""]
    for pdf_id, folha in relatorio["por_pdf"].items():
        if folha["situacao"] != "ok":
            linhas.append(f"- {pdf_id}: {folha['situacao']} {folha.get('erro', '')}".rstrip())
            continue
        falhas = [n for n, b in folha["metodos"].items() if b["situacao"] != "ok"]
        resumo = ", ".join(f"{n}: {folha['metodos'][n]['erro']}" for n in falhas)
        linhas.append(
            f"- {pdf_id}: família {folha['familia']}" + (f"; falha: {resumo}" if falhas else "")
        )
    return "\n".join(linhas) + "\n"


# --- orquestração -----------------------------------------------------------------------

_PDF_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _carregar_referencia(rodada: Path, pdf_id: str) -> Registro:
    """Ficha da folha, ``{"situacao": "sem_referencia"}`` ou uma falha saneada."""
    if not _PDF_ID.fullmatch(pdf_id):
        return _falha("pdf_id inválido no rodada.json")
    caminho = rodada / "pdfs" / pdf_id / "ficha" / "referencia.json"
    if not caminho.is_file():
        return {"situacao": "sem_referencia"}
    try:
        ficha = carregar_ficha(caminho)
    except (ValueError, OSError) as erro:
        return _falha(sanear(f"{type(erro).__name__}: {erro}", [str(rodada), rodada.as_posix()]))
    if ficha["tipo"] != "referencia":
        return _falha("a ficha não é do tipo referencia")
    return {"situacao": "ok", "ficha": ficha}


def _opcoes(metodos: Sequence[str], classes: Collection[str]) -> Registro:
    return {
        "metodos": list(metodos),
        "metodos_assinatura": {nome: ASSINATURAS[nome]() for nome in metodos},
        "criterios": list(CRITERIOS),
        "tolerancia_centro": TOLERANCIA_CENTRO,
        "raio_poste_pendente": RAIO_POSTE_PENDENTE,
        "classes_avaliadas": sorted(classes),
        "pymupdf": str(pymupdf.VersionBind),
    }


def medir_simbolos(
    rodada: Path,
    saida: Path,
    *,
    metodos: Sequence[str] = ("atual",),
    processos: int = 1,
) -> Registro:
    """Mede os métodos nas folhas da rodada e grava ``simbolos-ficha.json`` e ``.md``."""
    nomes = tuple(dict.fromkeys(metodos))
    desconhecidos = [nome for nome in nomes if nome not in METODOS or nome not in ASSINATURAS]
    if desconhecidos or not nomes:
        raise ValueError(f"método desconhecido ou ausente: {desconhecidos or 'nenhum'}")
    if processos < 1:
        raise ValueError("processos precisa ser >= 1")
    # Antes de ler o rodada.json ou qualquer referência: rodada dentro da pasta cega não se abre.
    absoluta = str(Path(rodada).absolute())
    if _caminho_cego(absoluta, os.path.normpath(absoluta)):
        raise RodadaError(f"rodada recusada: o diretório tem o componente {COMPONENTE_CEGO}")
    manifesto = carregar_rodada(rodada)
    raiz_corpus = str(manifesto["raiz_corpus"])
    por_pdf: dict[str, Registro] = {}
    com_ficha: list[tuple[Registro, Registro]] = []
    for entrada in manifesto["pdfs"]:
        pdf_id = str(entrada["pdf_id"])
        carregada = _carregar_referencia(rodada, pdf_id)
        por_pdf[pdf_id] = carregada
        if carregada["situacao"] == "ok":
            com_ficha.append((entrada, carregada["ficha"]))
    classes = frozenset().union(*(classes_da_ficha(ficha) for _, ficha in com_ficha))
    tarefas = [
        _Tarefa(rodada, raiz_corpus, entrada, ficha, nomes, classes) for entrada, ficha in com_ficha
    ]
    efetivos = min(processos, len(tarefas), MAXIMO_PROCESSOS)
    medidas = _medir_todas(tarefas, efetivos)
    for tarefa, resultado in zip(tarefas, medidas, strict=True):
        por_pdf[str(tarefa.entrada["pdf_id"])] = resultado
    relatorio: Registro = {
        "schema_version": ESQUEMA,
        "opcoes": _opcoes(nomes, classes),
        "por_pdf": por_pdf,
        "total": _agregar_total(por_pdf, nomes),
        "comparacao": _agregar_comparacao(por_pdf, nomes),
        "por_familia": _agregar_por_familia(por_pdf, nomes),
    }
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "simbolos-ficha.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (saida / "simbolos-ficha.md").write_text(
        _markdown(relatorio, processos, efetivos), encoding="utf-8"
    )
    return relatorio


def _inteiro_positivo(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"não é inteiro: {texto!r}") from None
    if valor < 1:
        raise argparse.ArgumentTypeError("precisa ser >= 1")
    return valor


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rodada", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--metodo", action="append", choices=sorted(METODOS), default=None)
    parser.add_argument("--processos", type=_inteiro_positivo, default=1)
    opcoes = parser.parse_args(argumentos)
    try:
        medir_simbolos(
            opcoes.rodada,
            opcoes.saida,
            metodos=tuple(opcoes.metodo or ("atual",)),
            processos=opcoes.processos,
        )
    except RodadaError as erro:
        parser.exit(1, f"{erro}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
