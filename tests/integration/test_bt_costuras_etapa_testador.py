# mypy: disable-error-code="no-untyped-call"
"""Costuras da E06.3.3.1 (haste e BT na mesma pagina) com os pacotes reais."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pymupdf
import pytest
import scripts.diff_simbolos_nucleo_motor as diff
from tests.fixtures.symbol_grammars import rect_diagonal as bt
from tests.fixtures.symbol_grammars import stem_bars as haste
from tests.fixtures.symbol_grammars.rect_diagonal import CASOS_RECT_DIAGONAL
from tests.fixtures.symbol_grammars.stem_bars import CASOS_HASTE
from tests.integration.test_model_symbols_runner import _METODO_NOVO, _fonte, _settings
from tests.unit.test_diff_simbolos_nucleo_motor import _pagina, _recursos, _rodada, _rodar

from zeny_project_handler.adapters.analysis import declarative_symbols
from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import MarcasDaPagina
from zeny_project_handler.adapters.analysis.drawing_model.grammar_rect_diagonal import (
    retangulos_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_stem import hastes_candidatas
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import gasto_por_fase
from zeny_project_handler_server import symbol_execution
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

pytestmark = pytest.mark.integration

_IDS_BT = [identidade for identidade, _ in CASOS_RECT_DIAGONAL]
_IDS_HASTE = [identidade for identidade, _ in CASOS_HASTE]
_CENTROS_HASTE = [(80.0 + 120.0 * (i % 4), 80.0 + 160.0 * (i // 4)) for i in range(8)]
_CENTROS_BT = [(80.0 + 120.0 * i, 420.0) for i in range(4)]


def _desenhar_haste(pagina: pymupdf.Page) -> None:
    for (identidade, _), centro in zip(CASOS_HASTE, _CENTROS_HASTE, strict=True):
        haste.desenhar_positivo(pagina, identidade, centro=centro)


def _desenhar_bt(pagina: pymupdf.Page) -> None:
    for (identidade, _), centro in zip(CASOS_RECT_DIAGONAL, _CENTROS_BT, strict=True):
        bt.desenhar_positivo(pagina, identidade, centro=centro)


def _desenhar_ambos(pagina: pymupdf.Page) -> None:
    _desenhar_haste(pagina)
    _desenhar_bt(pagina)


def _pdf(caminho: Path, desenhar: Callable[[pymupdf.Page], None]) -> Path:
    with pymupdf.open() as documento:
        desenhar(documento.new_page(width=560, height=520))
        documento.save(caminho)
    return caminho


def _pagina_gramatica(desenhar: Callable[[pymupdf.Page], None]) -> PaginaGramatica:
    return bt.pagina_desenhada(desenhar, largura=560.0, altura=520.0)


def _pares(
    casos: Sequence[tuple[str, Mapping[str, Any]]],
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [
        ({"family_id": "autoral"}, {"id": v, "recognition": {"status": "enabled", "grammar": g}})
        for v, g in casos
    ]


def test_runner_com_pacotes_reais_observa_haste_e_bt_na_mesma_pagina_sem_interferencia(
    tmp_path: Path,
) -> None:
    _pdf(tmp_path / "x.pdf", _desenhar_ambos)
    documento, fonte = _fonte(tmp_path / "x.pdf")
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()

    composto = runner.run(documento, fonte)

    do_modelo = [
        o
        for occ in composto.occurrences
        for o in occ.observations
        if o.metodo_assinatura == novo and o.alternativas
    ]
    classes = sorted(str(o.alternativas[0].classe) for o in do_modelo)
    assert classes == sorted(["ATERRAMENTO"] * 4 + ["PARA_RAIOS_MT"] * 4 + ["PARA_RAIOS_BT"] * 4)
    centros = []
    for o in do_modelo:
        if str(o.alternativas[0].classe) != "PARA_RAIOS_BT":
            continue
        xs = [float(x) for p in o.primitivas for x, _ in p.pontos_originais]
        ys = [float(y) for p in o.primitivas for _, y in p.pontos_originais]
        centros.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
    for cx, cy in _CENTROS_BT:
        assert any(abs(x - cx) < 12 and abs(y - cy) < 12 for x, y in centros), (cx, cy)
    com_haste = [
        occ
        for occ in composto.occurrences
        if any(
            o.metodo_assinatura == novo
            and o.alternativas
            and str(o.alternativas[0].classe) in {"ATERRAMENTO", "PARA_RAIOS_MT"}
            for o in occ.observations
        )
    ]
    assert len(com_haste) == 8
    assert all(len({o.metodo_assinatura for o in occ.observations}) >= 2 for occ in com_haste)


def test_pagina_com_as_duas_gramaticas_paga_os_contornos_uma_vez() -> None:
    pagina = _pagina_gramatica(_desenhar_ambos)

    def gasto(funcao: Callable[[Any], object]) -> int:
        contexto = contexto_gramaticas(pagina)
        antes = contexto.orcamento.gasto
        funcao(contexto)
        return int(contexto.orcamento.gasto - antes)

    def contornos(contexto: Any) -> None:
        assert MarcasDaPagina(contexto).contornos is not None

    def os_dois(contexto: Any) -> None:
        marcas = MarcasDaPagina(contexto)
        hastes_candidatas(contexto, marcas=marcas)
        retangulos_candidatos(contexto, marcas=marcas)

    so_hastes = gasto(hastes_candidatas)
    so_retangulos = gasto(retangulos_candidatos)
    pago_pelos_contornos = gasto(contornos)
    compartilhado = gasto(os_dois)

    assert pago_pelos_contornos > 0
    assert compartilhado == so_hastes + so_retangulos - pago_pelos_contornos


def test_gasto_por_fase_das_duas_gramaticas_soma_os_contornos_uma_vez() -> None:
    pagina = _pagina_gramatica(_desenhar_ambos)
    pares_haste, pares_bt = _pares(CASOS_HASTE), _pares(CASOS_RECT_DIAGONAL)

    ambas = gasto_por_fase(pagina, [*pares_haste, *pares_bt])
    so_haste = gasto_por_fase(pagina, pares_haste)
    so_bt = gasto_por_fase(pagina, pares_bt)
    vazio = gasto_por_fase(pagina, [])

    assert ambas.indices == so_haste.indices == so_bt.indices == vazio.indices
    contexto = contexto_gramaticas(pagina)
    antes = contexto.orcamento.gasto
    assert MarcasDaPagina(contexto).contornos is not None
    contornos = contexto.orcamento.gasto - antes
    assert contornos > 0
    assert ambas.gramaticas == so_haste.gramaticas + so_bt.gramaticas - contornos


def test_diff_dos_pacotes_reais_deixa_haste_e_bt_fora_da_comparacao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diff.recursos.cache_clear()
    monkeypatch.setattr(diff, "recursos", lambda: _recursos(declarative_symbols.carregar_pacotes()))
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _pdf(corpus / "folha.pdf", _desenhar_ambos)
    sha = hashlib.sha256((corpus / "folha.pdf").read_bytes()).hexdigest()
    rodada = _rodada(tmp_path, [("b" * 8, "folha.pdf", sha)])
    relatorio = _rodar(rodada, tmp_path / "saida")
    pagina = _pagina(relatorio, "b" * 8)
    for identidade in [*_IDS_HASTE, *_IDS_BT]:
        categorias = pagina["variantes"].get(identidade, {})
        for nome in ("ambos", "so_motor", "so_nucleo", "indice_diverge", "geometria_diverge"):
            assert categorias.get(nome, []) == [], (identidade, nome)
    assert pagina["gasto"] is not None
    monkeypatch.undo()
    diff.recursos.cache_clear()


def test_pacotes_reais_tem_as_quatro_situacoes_de_bt_habilitadas() -> None:
    habilitadas = {
        v["id"]
        for p in declarative_symbols.carregar_pacotes()
        for v in p["variants"]
        if v["recognition"]["status"] == "enabled"
        and v["recognition"].get("grammar", {}).get("kind") == "rect_diagonal"
    }
    assert habilitadas == set(_IDS_BT)


@pytest.mark.parametrize("modulo", ["grammar_marcas", "grammar_rect_diagonal"])
def test_digest_de_cada_modulo_novo_entra_na_assinatura_do_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, modulo: str
) -> None:
    def assinatura(sal: str) -> str:
        def digest(m: Any) -> str:
            return str(m.__name__) + (sal if str(m.__name__).endswith("." + modulo) else "")

        monkeypatch.setattr(symbol_execution, "_module_digest", digest)
        return SymbolCompositionRunner(_settings(tmp_path / "dados")).signature

    assert assinatura("") == assinatura("")
    assert assinatura("") != assinatura("-mudou")
