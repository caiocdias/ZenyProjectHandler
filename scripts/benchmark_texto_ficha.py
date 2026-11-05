"""Recall do texto recuperado por campo da ficha do poste (etapa E05, critério 3).

Uso::

    python -m scripts.benchmark_texto_ficha --rodada RODADA_E03 --pdfs DIR --saida DIR \
        [--tabela ARQ] [--processos N]

Para cada ``RODADA/pdfs/ID/ficha/referencia.json`` acha o PDF de ``DIR`` com o mesmo
``pdf_sha256``, roda o analisador sem OCR e mede quantos valores de campo da referência
(identificador, poste, estruturas, coordenada) aparecem no texto recuperado perto do poste.
Fonte ``base`` = ``TEXTO`` sem ``origem_texto`` (nativo); ``novo`` = todo ``TEXTO`` (nativo mais
contorno de glifo). Grava ``texto-ficha.json`` e ``texto-ficha.md`` em ``--saida``, sem nome de
PDF nem caminho absoluto (o PDF é identificado pelo ID da rodada).

O recall principal (``acertos``) é "presente na página": o valor aparece em algum texto da
página do poste, atribuído ao poste mais próximo (uma ocorrência serve a um valor só).
``acertos_ate_005`` e ``acertos_ate_010`` contam, desses acertos, os que estão a até 0.05 e a
até 0.10 (cumulativo) do centro da caixa do poste, em coordenadas normalizadas da página.

Erro afirmado (``erros_afirmados``): instância sem acerto cujo texto mais próximo do poste (até
0.05 de distância normalizada) tem um token de comprimento igual ±1 e edição de 1 a 2 do
valor, ou um token que contém o valor colado a outros alfanuméricos (fusão de tokens).

Com ``--processos N`` (inteiro >= 1, padrão 1) os PDFs são medidos em até N processos; a saída
mantém a ordem serial. Os campos ``tempo_*`` medem a execução, não a leitura: com mais de um
processo incluem a disputa por CPU.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import dist
from pathlib import Path
from time import perf_counter
from typing import Any, Final, Literal
from uuid import uuid4

from scripts.ficha_poste import carregar_ficha
from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    TabelaGlifos,
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import extrair_modelo_desenho
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.enums import TipoEvidencia
from zeny_project_handler.ports.analysis import (
    ConfiguracaoAnaliseDocumento,
    SolicitacaoAnaliseDocumento,
)
from zeny_project_handler.ports.pdf import ReferenciaFontePdf

CAMPOS: Final = ("identificador", "poste", "estruturas", "coordenada")
FONTES: Final = ("base", "novo")
DISTANCIA_ERRO: Final = 0.05
PROXIMIDADES: Final = (("acertos_ate_005", 0.05), ("acertos_ate_010", 0.10))
CHAVES_RECALL: Final = ("total", "acertos", "erros_afirmados")
CHAVES: Final = (*CHAVES_RECALL, *(chave for chave, _ in PROXIMIDADES))
ESQUEMA: Final = "benchmark-texto-ficha-v1"

Centro = tuple[float, float]
Contagem = dict[str, int]


@dataclass(frozen=True, slots=True)
class TextoMedido:
    texto: str
    centro: Centro
    origem: Literal["nativo", "glifo"]


@dataclass(frozen=True, slots=True)
class _Instancia:
    campo: str
    valor: str
    centro: Centro


def _normalizar(texto: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", texto).upper().split())


def _numero_como_texto(valor: float | int) -> str:
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


def _centro_da_bbox(bbox: Sequence[float]) -> Centro:
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _valores_do_poste(poste: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    pendentes = set(poste.get("pendentes") or ())
    for campo in ("identificador", "poste"):
        if poste.get(campo) is not None and campo not in pendentes:
            yield campo, str(poste[campo])
    if "estruturas" not in pendentes:
        for item in poste.get("estruturas") or ():
            yield "estruturas", str(item)
    coordenada = poste.get("coordenada")
    if coordenada is not None and "coordenada" not in pendentes:
        yield "coordenada", _numero_como_texto(coordenada["leste"])
        yield "coordenada", _numero_como_texto(coordenada["norte"])


def _instancias(referencia: Mapping[str, Any]) -> list[_Instancia]:
    instancias = []
    for poste in referencia["postes"]:
        centro = _centro_da_bbox(poste["bbox"])
        for campo, valor in _valores_do_poste(poste):
            normalizado = _normalizar(valor)
            if normalizado:
                instancias.append(_Instancia(campo, normalizado, centro))
    return instancias


def _padrao(valor: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![0-9A-Z]){re.escape(valor)}(?![0-9A-Z])")


def _distancia_de_edicao(a: str, b: str) -> int:
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        atual = [i]
        for j, cb in enumerate(b, start=1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def _atribuir(
    instancias: Sequence[_Instancia], textos: Sequence[tuple[str, Centro]]
) -> dict[int, tuple[int, tuple[int, int]]]:
    """Instância -> (texto, trecho), por distância crescente; cada ocorrência serve a uma."""
    pares: list[tuple[float, int, int, tuple[int, int]]] = []
    for i, instancia in enumerate(instancias):
        padrao = _padrao(instancia.valor)
        for t, (texto, centro) in enumerate(textos):
            for achado in padrao.finditer(texto):
                pares.append((dist(centro, instancia.centro), i, t, achado.span()))
    pares.sort()
    atribuidos: dict[int, tuple[int, tuple[int, int]]] = {}
    usadas: set[tuple[int, tuple[int, int]]] = set()
    for _, i, t, trecho in pares:
        if i in atribuidos or (t, trecho) in usadas:
            continue
        atribuidos[i] = (t, trecho)
        usadas.add((t, trecho))
    return atribuidos


def _tokens_livres(
    texto: str, consumidos: Sequence[tuple[int, int]]
) -> Iterable[tuple[str, tuple[int, int]]]:
    for achado in re.finditer(r"\S+", texto):
        inicio, fim = achado.span()
        if not any(inicio < c_fim and c_inicio < fim for c_inicio, c_fim in consumidos):
            yield achado.group(), achado.span()


def _parecido(valor: str, token: str) -> bool:
    return abs(len(token) - len(valor)) <= 1 and 1 <= _distancia_de_edicao(valor, token) <= 2


def _fusao(valor: str, token: str) -> bool:
    return token != valor and valor in token


def _erro_afirmado(
    instancia: _Instancia,
    textos: Sequence[tuple[str, Centro]],
    consumidos: Mapping[int, list[tuple[int, int]]],
) -> bool:
    proximos = [
        (dist(centro, instancia.centro), t)
        for t, (_, centro) in enumerate(textos)
        if dist(centro, instancia.centro) <= DISTANCIA_ERRO
    ]
    if not proximos:
        return False
    _, t = min(proximos)
    texto = textos[t][0]
    candidatos = [token for token, _ in _tokens_livres(texto, consumidos.get(t, ()))]
    if " " in instancia.valor:
        candidatos.append(texto)
    return any(_parecido(instancia.valor, c) or _fusao(instancia.valor, c) for c in candidatos)


def _zerado() -> dict[str, Contagem]:
    return {campo: dict.fromkeys(CHAVES, 0) for campo in CAMPOS}


def medir_texto(
    referencia: Mapping[str, Any], textos: Sequence[TextoMedido]
) -> dict[str, dict[str, int]]:
    """Acertos (presentes na página), acertos perto do poste e erros afirmados por campo; uma
    ocorrência de texto serve a uma instância."""
    instancias = _instancias(referencia)
    alvos = [(_normalizar(item.texto), item.centro) for item in textos]
    atribuidos = _atribuir(instancias, alvos)
    consumidos: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for t, trecho in atribuidos.values():
        consumidos[t].append(trecho)
    resultado = _zerado()
    for i, instancia in enumerate(instancias):
        contagem = resultado[instancia.campo]
        contagem["total"] += 1
        if i in atribuidos:
            contagem["acertos"] += 1
            distancia = dist(alvos[atribuidos[i][0]][1], instancia.centro)
            for chave, limite in PROXIMIDADES:
                contagem[chave] += distancia <= limite
        elif _erro_afirmado(instancia, alvos, consumidos):
            contagem["erros_afirmados"] += 1
    return resultado


def recall_texto(
    referencia: Mapping[str, Any], textos: Sequence[TextoMedido]
) -> dict[str, dict[str, int]]:
    """Acertos e erros afirmados por campo (``medir_texto`` sem as contagens de proximidade)."""
    return {
        campo: {chave: contagem[chave] for chave in CHAVES_RECALL}
        for campo, contagem in medir_texto(referencia, textos).items()
    }


def _somar(blocos: Iterable[Mapping[str, Mapping[str, int]]]) -> dict[str, Contagem]:
    soma = _zerado()
    for bloco in blocos:
        for campo, contagem in bloco.items():
            for chave, valor in contagem.items():
                soma[campo][chave] += valor
    return soma


def _com_fonte(
    por_fonte: Iterable[Mapping[str, Mapping[str, Mapping[str, int]]]],
) -> dict[str, dict[str, Contagem]]:
    lista = list(por_fonte)
    return {fonte: _somar(item[fonte] for item in lista) for fonte in FONTES}


def _solicitacao(pdf: Path) -> SolicitacaoAnaliseDocumento:
    inspecao = PyMuPdfReader().inspecionar(pdf)
    projeto_id = uuid4()
    return SolicitacaoAnaliseDocumento(
        projeto_id=projeto_id,
        documento=inspecao.documento,
        fonte=ReferenciaFontePdf(
            documento_id=inspecao.documento.id,
            projeto_id=projeto_id,
            caminho_canonico=pdf,
            sha256=inspecao.documento.sha256,
            tamanho_bytes=inspecao.tamanho_bytes,
            modificado_em_ns=inspecao.modificado_em_ns,
        ),
        execucao_id=uuid4(),
        criada_em=datetime.now(UTC),
        configuracao=ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=False),
    )


def _texto_da_evidencia(evidencia: EvidenciaDocumento) -> TextoMedido | None:
    if evidencia.tipo is not TipoEvidencia.TEXTO or not evidencia.conteudo_bruto:
        return None
    pontos = evidencia.geometria.pontos
    centro = (
        sum(float(p.x) for p in pontos) / len(pontos),
        sum(float(p.y) for p in pontos) / len(pontos),
    )
    de_glifo = dict(evidencia.atributos_extraidos).get("origem_texto") == "contorno_glifo"
    return TextoMedido(evidencia.conteudo_bruto, centro, "glifo" if de_glifo else "nativo")


def _recall_por_pagina(
    referencia: Mapping[str, Any], textos: Mapping[int, Sequence[TextoMedido]]
) -> dict[str, dict[str, int]]:
    paginas = sorted({poste["pagina"] for poste in referencia["postes"]})
    return _somar(
        medir_texto(
            {"postes": [p for p in referencia["postes"] if p["pagina"] == pagina]},
            textos.get(pagina, ()),
        )
        for pagina in paginas
    )


def _tempo(pdf: Path, tabela: TabelaGlifos | None) -> float:
    inicio = perf_counter()
    PyMuPdfDocumentAnalyzer(tabela_glifos=tabela).analisar(_solicitacao(pdf))
    return perf_counter() - inicio


def _medir_pdf(pdf: Path, referencia: Mapping[str, Any], tabela: TabelaGlifos) -> dict[str, Any]:
    # sem a tabela primeiro: a primeira análise do PDF paga a partida a frio (arquivo, fontes),
    # que não pode ser atribuída à leitura de glifos
    sem_glifos = _tempo(pdf, None)
    solicitacao = _solicitacao(pdf)
    numeros = {pagina.id: pagina.numero for pagina in solicitacao.documento.paginas}
    inicio = perf_counter()
    resultado = PyMuPdfDocumentAnalyzer(tabela_glifos=tabela).analisar(solicitacao)
    com_glifos = perf_counter() - inicio
    textos: dict[str, dict[int, list[TextoMedido]]] = {fonte: defaultdict(list) for fonte in FONTES}
    for evidencia in resultado.evidencias:
        medido = _texto_da_evidencia(evidencia)
        if medido is None:
            continue
        pagina = numeros[evidencia.pagina_id]
        textos["novo"][pagina].append(medido)
        if medido.origem == "nativo":
            textos["base"][pagina].append(medido)
    return {
        "familia": extrair_modelo_desenho(pdf).familia.familia,
        "fontes": {fonte: _recall_por_pagina(referencia, textos[fonte]) for fonte in FONTES},
        "tempo_analise_com_glifos_s": round(com_glifos, 3),
        "tempo_analise_sem_glifos_s": round(sem_glifos, 3),
        "tempo_glifos_s": round(max(com_glifos - sem_glifos, 0.0), 3),
    }


def _pdfs_por_sha(diretorio: Path) -> dict[str, Path]:
    return {sha256(p.read_bytes()).hexdigest(): p for p in sorted(diretorio.rglob("*.pdf"))}


def _referencias(rodada: Path) -> list[tuple[str, Path]]:
    return [
        (arquivo.parent.parent.name, arquivo)
        for arquivo in sorted((rodada / "pdfs").glob("*/ficha/referencia.json"))
    ]


def _porcentagem(contagem: Mapping[str, int]) -> str:
    total = contagem["total"]
    return f"{100 * contagem['acertos'] / total:.1f}%" if total else "-"


def _linhas_md(titulo: str, fontes: Mapping[str, Mapping[str, Contagem]]) -> list[str]:
    linhas = [
        f"### {titulo}",
        "",
        "| campo | fonte | acertos | total | recall | ≤ 0.05 | ≤ 0.10 | erros afirmados |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for campo in CAMPOS:
        for fonte in FONTES:
            c = fontes[fonte][campo]
            linhas.append(
                f"| {campo} | {fonte} | {c['acertos']} | {c['total']} | {_porcentagem(c)} "
                f"| {c['acertos_ate_005']} | {c['acertos_ate_010']} | {c['erros_afirmados']} |"
            )
    return [*linhas, ""]


def _markdown(relatorio: Mapping[str, Any]) -> str:
    linhas = [
        "# Recall de texto por campo da ficha",
        "",
        f"Analisador `{relatorio['versao_analisador']}`; tabela de glifos "
        f"`{relatorio['tabela_sha256']}`.",
        "",
        "Recall = valor presente na página (atribuído ao poste mais próximo); as colunas ≤ 0.05 "
        "e ≤ 0.10 contam os acertos a essa distância normalizada do centro do poste.",
        "",
        *_linhas_md("Total", relatorio["total"]),
    ]
    for familia, bloco in relatorio["por_familia"].items():
        linhas += _linhas_md(f"Família {familia}", bloco)
    for pdf_id, bloco in relatorio["por_pdf"].items():
        linhas += _linhas_md(f"PDF {pdf_id} (família {bloco['familia']})", bloco["fontes"])
        linhas += [
            f"Tempo de análise: {bloco['tempo_analise_com_glifos_s']} s com glifos, "
            f"{bloco['tempo_analise_sem_glifos_s']} s sem; leitura de glifos "
            f"{bloco['tempo_glifos_s']} s.",
            "",
        ]
    return "\n".join(linhas)


_TABELA_DO_PROCESSO: TabelaGlifos | None = None


def _iniciar_processo(tabela_arquivo: Path | None) -> None:
    global _TABELA_DO_PROCESSO
    _TABELA_DO_PROCESSO = carregar_tabela_glifos(tabela_arquivo)


def _medir_no_processo(item: tuple[Path, dict[str, Any]]) -> dict[str, Any]:
    if _TABELA_DO_PROCESSO is None:
        raise RuntimeError("processo do pool sem tabela de glifos")
    pdf, referencia = item
    return _medir_pdf(pdf, referencia, _TABELA_DO_PROCESSO)


def _medir_todos(
    itens: Sequence[tuple[Path, dict[str, Any]]],
    tabela: TabelaGlifos,
    tabela_arquivo: Path | None,
    processos: int,
) -> list[dict[str, Any]]:
    if processos <= 1 or len(itens) <= 1:
        return [_medir_pdf(pdf, referencia, tabela) for pdf, referencia in itens]
    with ProcessPoolExecutor(
        max_workers=min(processos, len(itens)),
        initializer=_iniciar_processo,
        initargs=(tabela_arquivo,),
    ) as pool:
        return list(pool.map(_medir_no_processo, itens))


def executar(
    rodada: Path,
    pdfs: Path,
    saida: Path,
    tabela_arquivo: Path | None,
    processos: int = 1,
) -> dict[str, Any]:
    tabela = carregar_tabela_glifos(tabela_arquivo)
    por_sha = _pdfs_por_sha(pdfs)
    ids: list[str] = []
    itens: list[tuple[Path, dict[str, Any]]] = []
    for pdf_id, arquivo in _referencias(rodada):
        referencia = carregar_ficha(arquivo)
        pdf = por_sha.get(referencia["pdf_sha256"])
        if pdf is None:
            raise ValueError(f"PDF da referência {pdf_id} não encontrado em --pdfs (pdf_sha256)")
        ids.append(pdf_id)
        itens.append((pdf, referencia))
    por_pdf = dict(zip(ids, _medir_todos(itens, tabela, tabela_arquivo, processos), strict=True))
    por_familia: dict[str, list[Any]] = defaultdict(list)
    for bloco in por_pdf.values():
        por_familia[bloco["familia"]].append(bloco["fontes"])
    relatorio = {
        "esquema": ESQUEMA,
        "versao_analisador": PyMuPdfDocumentAnalyzer.versao,
        "tabela_sha256": tabela.sha256,
        "total": _com_fonte(bloco["fontes"] for bloco in por_pdf.values()),
        "por_familia": {
            familia: _com_fonte(blocos) for familia, blocos in sorted(por_familia.items())
        },
        "por_pdf": por_pdf,
    }
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "texto-ficha.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (saida / "texto-ficha.md").write_text(_markdown(relatorio), encoding="utf-8")
    return relatorio


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rodada", type=Path, required=True)
    parser.add_argument("--pdfs", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--tabela", type=Path, default=None)
    parser.add_argument("--processos", type=int, default=1)
    opcoes = parser.parse_args(argumentos)
    if opcoes.processos < 1:
        parser.error("--processos precisa ser >= 1")
    executar(opcoes.rodada, opcoes.pdfs, opcoes.saida, opcoes.tabela, opcoes.processos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
