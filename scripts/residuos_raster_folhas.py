# mypy: disable-error-code="no-untyped-call"
"""Resíduos raster por folha, para confirmar ou refutar a H2 (E06.3.2.1).

Uso::

    python -m scripts.residuos_raster_folhas --rodada RODADA --saida DIR \
        [--recortes] [--dpi 200] [--processos N]

Para cada folha de ``RODADA/rodada.json`` acha o PDF por ``raiz_corpus`` + ``caminho_relativo``
(com a guarda do ``avaliacao-cega`` e a conferência de sha do benchmark de símbolos) e, página a
página, lista as imagens compactas sem casamento em cima (``model_symbols.residuos_raster``),
medidas com as variantes habilitadas dos pacotes de hoje. Cruza cada resíduo com as referências
da ficha E03 e lista as referências cujo centro cai sob qualquer imagem, inclusive as grandes,
que ``residuos_raster`` não vê.

Página fora do domínio (fonte de caminhos ou de imagens que falhou, teto de consultas, fonte de
gramática) não vira zero: fica ``fora_dominio`` com o motivo e a folha tem ``total`` nulo. O
``resumo`` conta resíduos, hashes e cruzamentos só das folhas com ``total``; as referências sob
imagem contam em todas as páginas lidas. Grava ``residuos-raster.json`` (esquema
``residuos-raster-v1``) e, com ``--recortes``, um PNG por resíduo, sem caminho absoluto nem nome de
PDF: a folha é identificada só pelo ``pdf_id`` e a rodada, pelo nome do diretório.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Final

import pymupdf

from scripts.curation_round import RodadaError, carregar_rodada
from scripts.simbolos_corpus import (
    FolhaError,
    Registro,
    carregar_referencia,
    localizar_pdf,
    medir_em_paralelo,
    recusar_rodada_cega,
    sanear,
)
from zeny_project_handler.adapters.analysis.declarative_symbols import _enabled, carregar_pacotes
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    TabelaGlifos,
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    FonteGramaticaFalhou,
    PaginaGramatica,
    TetoGramaticasExcedido,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import casar_variantes
from zeny_project_handler.adapters.analysis.model_symbols import residuos_raster
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas

ESQUEMA: Final = "residuos-raster-v1"
ARQUIVO_SAIDA: Final = "residuos-raster.json"
TAMANHO_HASH_CURTO: Final = 12
DPI_PADRAO: Final = 200
MAXIMO_PROCESSOS: Final = 61
CASAS_CAIXA: Final = 6

_FALHAS_DE_FONTE: Final = (
    "modelo.caminhos_falhou",
    "modelo.imagens_falhou",
    "modelo.imagens_anotacao_falhou",
)

Caixa = tuple[float, float, float, float]

# Nomes que os testes trocam por este módulo.
__all__ = [
    "casar_variantes",
    "main",
    "medir_residuos",
    "pagina_para_gramaticas",
]


@dataclass(frozen=True, slots=True)
class _Referencia:
    id: str
    classe: str
    centro: tuple[float, float]


@dataclass(frozen=True, slots=True)
class _Tarefa:
    rodada: Path
    raiz_corpus: str
    entrada: Registro
    recortes: Path | None
    dpi: int


@dataclass(frozen=True, slots=True)
class _Contexto:
    pdf_id: str
    variantes: Sequence[Any]
    tabela: TabelaGlifos
    referencias: Mapping[int, Sequence[_Referencia]]
    recortes: Path | None
    dpi: int


def _referencias_por_pagina(ficha: Mapping[str, Any]) -> dict[int, list[_Referencia]]:
    """Símbolos da ficha por página (1-based), com o centro ainda normalizado."""
    por_pagina: dict[int, list[_Referencia]] = {}
    for poste in ficha["postes"]:
        for simbolo in poste["simbolos"]:
            x0, y0, x1, y1 = simbolo["bbox"]
            centro = ((x0 + x1) / 2, (y0 + y1) / 2)
            referencia = _Referencia(str(simbolo["id"]), str(simbolo["classe"]), centro)
            por_pagina.setdefault(int(poste["pagina"]), []).append(referencia)
    return por_pagina


def _contem(caixa: Caixa, ponto: tuple[float, float]) -> bool:
    return caixa[0] <= ponto[0] <= caixa[2] and caixa[1] <= ponto[1] <= caixa[3]


def _centro_na_pagina(referencia: _Referencia, pagina: PaginaGramatica) -> tuple[float, float]:
    return (
        referencia.centro[0] * pagina.modelo.largura,
        referencia.centro[1] * pagina.modelo.altura,
    )


def _normalizada(caixa: Caixa, pagina: PaginaGramatica) -> list[float]:
    largura, altura = pagina.modelo.largura, pagina.modelo.altura
    escala = (largura, altura, largura, altura)
    return [
        round(valor / divisor, CASAS_CAIXA) for valor, divisor in zip(caixa, escala, strict=True)
    ]


def _gravar_recorte(page: pymupdf.Page, caixa: Caixa, destino: Path, dpi: int) -> None:
    """Recorte pela caixa crua, derrotada como em `model_symbols._observacao`."""
    crua = pymupdf.Rect(caixa) * page.derotation_matrix
    page.get_pixmap(clip=crua, dpi=dpi).save(destino)


def _falha_de_fonte(pagina: PaginaGramatica) -> str | None:
    presentes = [codigo for codigo in _FALHAS_DE_FONTE if codigo in pagina.modelo.diagnosticos]
    return f"fonte_falhou:{','.join(presentes)}" if presentes else None


def _casamentos(pagina: PaginaGramatica, contexto: _Contexto) -> tuple[Any, ...] | str:
    """Casamentos da página ou, se fora do domínio, o motivo."""
    motivo = _falha_de_fonte(pagina)
    if motivo is not None:
        return motivo
    try:
        return casar_variantes(pagina, contexto.variantes)
    except FonteGramaticaFalhou as erro:
        return f"fonte_falhou:{erro.codigo}"
    except TetoGramaticasExcedido:
        return "teto_consultas"


def _referencias_sob_imagem(
    pagina: PaginaGramatica, referencias: Sequence[_Referencia]
) -> list[Registro]:
    caixas = [imagem.bbox for imagem in pagina.modelo.imagens]
    return [
        {"id": referencia.id, "classe": referencia.classe}
        for referencia in referencias
        if any(_contem(caixa, _centro_na_pagina(referencia, pagina)) for caixa in caixas)
    ]


def _residuo(
    page: pymupdf.Page,
    pagina: PaginaGramatica,
    residuo: Any,
    referencias: Sequence[_Referencia],
    nome_recorte: str | None,
    contexto: _Contexto,
) -> Registro:
    sob = [
        referencia.classe
        for referencia in referencias
        if _contem(residuo.caixa, _centro_na_pagina(referencia, pagina))
    ]
    if nome_recorte is not None and contexto.recortes is not None:
        _gravar_recorte(page, residuo.caixa, contexto.recortes / nome_recorte, contexto.dpi)
    return {
        "caixa_normalizada": _normalizada(residuo.caixa, pagina),
        "sha256_curto": residuo.sha256[:TAMANHO_HASH_CURTO],
        "de_anotacao": residuo.de_anotacao,
        "referencias_sob": sob,
        "recorte": nome_recorte,
    }


def _medir_pagina(page: pymupdf.Page, indice: int, contexto: _Contexto) -> Registro:
    pagina = pagina_para_gramaticas(page, indice, contexto.tabela)
    referencias = contexto.referencias.get(indice + 1, ())
    resultado: Registro = {
        "pagina": indice + 1,
        "estado": "fora_dominio",
        "motivo": "",
        "residuos": [],
        "referencias_sob_imagem": _referencias_sob_imagem(pagina, referencias),
    }
    casamentos = _casamentos(pagina, contexto)
    if isinstance(casamentos, str):
        resultado["motivo"] = casamentos
        return resultado
    encontrados = residuos_raster(pagina, casamentos)
    resultado["estado"] = "medida"
    resultado["motivo"] = f"residuo_raster:{len(encontrados)}"
    resultado["residuos"] = [
        _residuo(
            page,
            pagina,
            item,
            referencias,
            f"{contexto.pdf_id}-p{indice + 1}-{numero:03d}-{item.sha256[:TAMANHO_HASH_CURTO]}.png"
            if contexto.recortes is not None
            else None,
            contexto,
        )
        for numero, item in enumerate(encontrados)
    ]
    return resultado


def _confere_sha(pdf: Path, entrada: Mapping[str, Any], ficha: Mapping[str, Any] | None) -> None:
    esperados = {entrada.get("sha256"), None if ficha is None else ficha["pdf_sha256"]}
    esperados.discard(None)
    # os dois shas conhecidos (rodada e referência) precisam bater com o PDF
    if esperados and esperados != {sha256(pdf.read_bytes()).hexdigest()}:
        raise FolhaError("sha256 do PDF difere do da rodada ou da referência")


def _referencia_da_folha(tarefa: _Tarefa, pdf_id: str) -> Registro | None:
    carregada = carregar_referencia(tarefa.rodada, pdf_id)
    if carregada["situacao"] == "falha":
        raise FolhaError(str(carregada["erro"]))
    return carregada.get("ficha")


def _medir_folha(tarefa: _Tarefa) -> Registro:
    pdf_id = str(tarefa.entrada["pdf_id"])
    caminho_relativo = str(tarefa.entrada["caminho_relativo"])
    ocultar = [str(tarefa.rodada), tarefa.rodada.as_posix(), caminho_relativo]
    try:
        ficha = _referencia_da_folha(tarefa, pdf_id)
        pdf = localizar_pdf(tarefa.rodada, tarefa.raiz_corpus, caminho_relativo)
        if not pdf.is_file():
            raise FolhaError("PDF não encontrado no corpus da rodada")
        _confere_sha(pdf, tarefa.entrada, ficha)
        contexto = _Contexto(
            pdf_id,
            _enabled(carregar_pacotes()),
            carregar_tabela_glifos(),
            {} if ficha is None else _referencias_por_pagina(ficha),
            tarefa.recortes,
            tarefa.dpi,
        )
        with pymupdf.open(pdf) as documento:
            paginas = [
                _medir_pagina(documento.load_page(indice), indice, contexto)
                for indice in range(documento.page_count)
            ]
    except FolhaError as erro:
        return {"pdf_id": pdf_id, "paginas": [], "total": None, "erro": sanear(str(erro), ocultar)}
    except Exception as erro:
        texto = sanear(f"{type(erro).__name__}: {erro}", ocultar)
        return {"pdf_id": pdf_id, "paginas": [], "total": None, "erro": texto}
    return {"pdf_id": pdf_id, "paginas": paginas, "total": _total(paginas)}


def _total(paginas: Sequence[Mapping[str, Any]]) -> int | None:
    if any(pagina["estado"] != "medida" for pagina in paginas):
        return None
    return sum(len(pagina["residuos"]) for pagina in paginas)


def _resumo(folhas: Sequence[Mapping[str, Any]]) -> Registro:
    medidas = [folha for folha in folhas if folha["total"] is not None]
    por_hash: Counter[str] = Counter()
    residuos_total = 0
    sobre_referencia = 0
    for folha in medidas:
        itens = [item for pagina in folha["paginas"] for item in pagina["residuos"]]
        residuos_total += len(itens)
        sobre_referencia += sum(1 for item in itens if item["referencias_sob"])
        por_hash.update({item["sha256_curto"] for item in itens})
    sob_imagem = sum(
        len(pagina["referencias_sob_imagem"]) for folha in folhas for pagina in folha["paginas"]
    )
    return {
        "folhas_medidas": len(medidas),
        "folhas_fora_dominio": len(folhas) - len(medidas),
        "residuos": residuos_total,
        "por_hash": dict(sorted(por_hash.items())),
        "sobre_referencia": sobre_referencia,
        "referencias_sob_imagem": sob_imagem,
    }


def _folha_do_pool(tarefa: _Tarefa, resultado: Registro) -> Registro:
    """Folha cujo processo do pool morreu antes de medir: sem páginas e sem total."""
    if resultado.get("situacao") != "falha":
        return resultado
    pdf_id = str(tarefa.entrada["pdf_id"])
    return {"pdf_id": pdf_id, "paginas": [], "total": None, "erro": str(resultado["erro"])}


def medir_residuos(
    rodada: Path,
    saida: Path,
    *,
    recortes: bool = False,
    dpi: int = DPI_PADRAO,
    processos: int = 1,
) -> Registro:
    """Mede as folhas da rodada e grava ``residuos-raster.json`` (e os recortes) em ``saida``."""
    if processos < 1 or dpi < 1:
        raise ValueError("processos e dpi precisam ser >= 1")
    # Antes de ler o rodada.json ou qualquer referência: rodada dentro da pasta cega não se abre.
    recusar_rodada_cega(rodada)
    manifesto = carregar_rodada(rodada)
    raiz_corpus = str(manifesto["raiz_corpus"])
    pasta_recortes = saida if recortes else None
    saida.mkdir(parents=True, exist_ok=True)
    tarefas = [
        _Tarefa(rodada, raiz_corpus, entrada, pasta_recortes, dpi) for entrada in manifesto["pdfs"]
    ]
    efetivos = min(processos, len(tarefas), MAXIMO_PROCESSOS)
    medidas = medir_em_paralelo(_medir_folha, tarefas, efetivos, ProcessPoolExecutor)
    folhas = [_folha_do_pool(t, r) for t, r in zip(tarefas, medidas, strict=True)]
    relatorio: Registro = {
        "esquema": ESQUEMA,
        "rodada": rodada.absolute().name,
        "folhas": folhas,
        "resumo": _resumo(folhas),
    }
    (saida / ARQUIVO_SAIDA).write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
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
    parser.add_argument("--recortes", action="store_true")
    parser.add_argument("--dpi", type=_inteiro_positivo, default=DPI_PADRAO)
    parser.add_argument("--processos", type=_inteiro_positivo, default=1)
    opcoes = parser.parse_args(argumentos)
    try:
        medir_residuos(
            opcoes.rodada,
            opcoes.saida,
            recortes=opcoes.recortes,
            dpi=opcoes.dpi,
            processos=opcoes.processos,
        )
    except RodadaError as erro:
        parser.exit(1, f"{erro}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
