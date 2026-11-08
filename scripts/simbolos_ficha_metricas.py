"""Métricas do benchmark de símbolos: casamento, contadores, avaliação e agregação."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from functools import cache
from itertools import combinations
from pathlib import Path
from typing import Any, Final, Literal

from scripts.simbolos_corpus import Registro
from scripts.symbol_benchmark_evaluator import geometry_match

TOLERANCIA_CENTRO: Final = 0.005
RAIO_POSTE_PENDENTE: Final = 0.05
CONTEXTOS_NAO_DESENHO: Final = frozenset({"legend", "informative"})

Criterio = Literal["centro", "iou"]
CRITERIOS: Final[tuple[Criterio, ...]] = ("centro", "iou")
Caixa = Sequence[float]
Item = Mapping[str, Any]
_TFF: Final = ("tp", "fp", "fn")
INVENTARIO: Final = (
    Path(__file__).resolve().parents[1] / "docs" / "data" / "inventario-simbologia-v1.json"
)
_NAO_DECLARADA: Final = "n/a"
BALDES_SITUACAO: Final = (
    "concordantes",
    "discordantes",
    "sem_situacao_ficha",
    "situacao_nao_declarada",
    "sem_situacao_predita",
)


# --- situação (R-E06.3.3.2.1-4) ---------------------------------------------------------


def normalizar_situacao(texto: str | None) -> str | None:
    """Minúsculas, sem acento, ``_`` como espaço, só o prefixo antes de ``(`` ou ``;``."""
    if texto is None:
        return None
    decomposto = unicodedata.normalize("NFD", str(texto))
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    prefixo = re.split(r"[(;]", sem_acento.lower().replace("_", " "), maxsplit=1)[0]
    return " ".join(prefixo.split()) or None


@cache
def _situacoes_do_inventario() -> dict[str, frozenset[str] | None]:
    inventario = json.loads(INVENTARIO.read_text(encoding="utf-8"))
    resultado: dict[str, frozenset[str] | None] = {}
    for variante in inventario["variants"]:
        normalizadas = {normalizar_situacao(texto) for texto in variante.get("situation") or []}
        declaradas = frozenset(t for t in normalizadas if t is not None and t != _NAO_DECLARADA)
        resultado[str(variante["id"])] = declaradas or None
    return resultado


def situacoes_da_variante(variante_id: str) -> frozenset[str] | None:
    """Situações normalizadas da variante; ``None`` se vazia, "N/A" ou desconhecida."""
    return _situacoes_do_inventario().get(variante_id)


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
        {
            "pagina": poste["pagina"],
            "classe": simbolo["classe"],
            "bbox": simbolo["bbox"],
            "situacao": normalizar_situacao(
                (simbolo.get("atributos_extras") or {}).get("situacao")
            ),
        }
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


def leituras_erradas(
    referencias: Sequence[Mapping[str, Any]],
    predicoes: Sequence[Mapping[str, Any]],
    casadas: Collection[int],
    tolerancia: float,
) -> list[dict[str, Any]]:
    """Predições não casadas cujo centro cai na referência de outra classe (R-E06.3.2-4)."""
    itens: list[dict[str, Any]] = []
    for j, predicao in enumerate(predicoes):
        if j in casadas:
            continue
        centro = _centro(predicao["bbox"])
        for i, referencia in enumerate(referencias):
            if (
                referencia["pagina"] == predicao["pagina"]
                and referencia["classe"] != predicao["classe"]
                and _na_caixa(centro, referencia["bbox"], tolerancia)
            ):
                itens.append(
                    {
                        "classe_predita": predicao["classe"],
                        "classe_referencia": referencia["classe"],
                        "referencia_id": i,
                    }
                )
    return itens


def _bloco_leituras_erradas(itens: list[dict[str, Any]]) -> Registro:
    por_classe = Counter(item["classe_predita"] for item in itens)
    return {"total": len(itens), "por_classe": dict(sorted(por_classe.items())), "itens": itens}


def _balde_situacao(referencia: Mapping[str, Any], predicao: Mapping[str, Any]) -> str:
    situacao = referencia.get("situacao")
    if situacao is None:
        return "sem_situacao_ficha"
    variante = predicao.get("variante")
    if variante is not None and situacoes_da_variante(variante) is None:
        return "situacao_nao_declarada"
    preditas = predicao.get("situacoes_preditas") or frozenset()
    if not preditas:
        return "sem_situacao_predita"
    return "concordantes" if situacao in preditas else "discordantes"


def _concordancia_por_classe(contagens: Mapping[str, Counter[str]]) -> Registro:
    por_classe: Registro = {
        classe: {balde: contagem[balde] for balde in BALDES_SITUACAO}
        for classe, contagem in sorted(contagens.items())
    }
    geral: Registro = {b: sum(item[b] for item in por_classe.values()) for b in BALDES_SITUACAO}
    for item in (*por_classe.values(), geral):
        item["taxa"] = _taxa(item["concordantes"], item["concordantes"] + item["discordantes"])
    return {"por_classe": por_classe, "geral": geral}


def _concordancia_situacao(
    referencias: Sequence[Mapping[str, Any]],
    predicoes: Sequence[Item],
    pares: Sequence[tuple[int, int]],
) -> Registro:
    contagens: dict[str, Counter[str]] = defaultdict(Counter)
    for i, j in pares:
        contagens[referencias[i]["classe"]][_balde_situacao(referencias[i], predicoes[j])] += 1
    return _concordancia_por_classe(contagens)


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
    fora_do_fp = set(casadas_predicao)
    for j, predicao in enumerate(predicoes):
        if j in casadas_predicao:
            continue
        centro = _centro(predicao["bbox"])
        pagina = predicao["pagina"]
        if regioes is not None and not _no_pagina(centro, pagina, regioes, 0.0):
            fora_das_regioes += 1
            fora_do_fp.add(j)
        elif _no_pagina(centro, pagina, pendentes, RAIO_POSTE_PENDENTE):
            perto_de_poste_pendente += 1
            fora_do_fp.add(j)
        else:
            fp[predicao["classe"]] += 1
    por_classe = _por_classe(tp, fp, fn)
    return {
        "por_classe": por_classe,
        "geral": _geral(por_classe),
        "concordancia_situacao": _concordancia_situacao(referencias, predicoes, pares),
        "fora_do_escopo": dict(sorted(fora_do_escopo.items())),
        "fora_das_regioes": fora_das_regioes,
        "perto_de_poste_pendente": perto_de_poste_pendente,
        "leituras_erradas": _bloco_leituras_erradas(
            leituras_erradas(referencias, predicoes, fora_do_fp, TOLERANCIA_CENTRO)
        ),
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


# --- agregação --------------------------------------------------------------------------


def _somar_contadores(blocos: Iterable[Mapping[str, int]]) -> dict[str, int]:
    soma: Counter[str] = Counter()
    for bloco in blocos:
        soma.update(bloco)
    return dict(sorted(soma.items()))


def _somar_concordancia(blocos: Sequence[Mapping[str, Any]]) -> Registro:
    contagens: dict[str, Counter[str]] = defaultdict(Counter)
    for bloco in blocos:
        for classe, item in bloco["por_classe"].items():
            contagens[classe].update({b: item[b] for b in BALDES_SITUACAO})
    return _concordancia_por_classe(contagens)


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
        "concordancia_situacao": _somar_concordancia([b["concordancia_situacao"] for b in blocos]),
        "fora_do_escopo": _somar_contadores(b["fora_do_escopo"] for b in blocos),
        "fora_das_regioes": sum(b["fora_das_regioes"] for b in blocos),
        "perto_de_poste_pendente": sum(b["perto_de_poste_pendente"] for b in blocos),
        "leituras_erradas": _bloco_leituras_erradas(
            [item for b in blocos for item in b["leituras_erradas"]["itens"]]
        ),
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
