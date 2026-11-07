# mypy: disable-error-code="no-untyped-call"
"""Ataques a `glifos_lidos`: posições em `modelo.caminhos`, grupos mistos, recorte e rotação."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    pdf_texto_contorno,
    pdf_texto_nativo,
    tabela_do_alfabeto,
)

from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import TabelaGlifos
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import ler_texto_glifos
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    pagina_para_gramaticas,
)


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto"))


def _sem(tabela: TabelaGlifos, caractere: str) -> TabelaGlifos:
    return replace(tabela, glifos=tuple(g for g in tabela.glifos if g.caractere != caractere))


def _ler(pdf: Path, tabela: TabelaGlifos) -> tuple[frozenset[int], int, list[str], int]:
    with pymupdf.open(pdf) as documento:
        pagina = pagina_para_gramaticas(documento[0], 0, tabela)
    return (
        pagina.glifos_lidos,
        len(pagina.modelo.caminhos),
        [t.texto for t in pagina.modelo.textos],
        len(pagina.indices_crus),
    )


def test_moldura_antes_do_texto_desloca_as_posicoes(tmp_path: Path, tabela: TabelaGlifos) -> None:
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("CT", (100.0, 100.0), 5.0)])
    with pymupdf.open(contorno) as documento:
        documento[0].draw_rect(pymupdf.Rect(97, 93, 110, 103), color=(0.7, 0.0, 0.0), overlay=False)
        documento.save(tmp_path / "m.pdf")

    lidos, total, textos, _ = _ler(tmp_path / "m.pdf", tabela)

    assert (total, textos) == (3, ["CT"])
    assert lidos == {1, 2}


def test_linha_nao_resolvida_nao_contamina_a_linha_resolvida(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    pdf = pdf_texto_contorno(
        tmp_path / "c.pdf",
        [LinhaTexto("CC", (40.0, 60.0), 5.0), LinhaTexto("CT", (40.0, 120.0), 5.0)],
    )

    lidos, total, textos, _ = _ler(pdf, _sem(tabela, "T"))

    assert (total, textos) == (4, ["CC"])
    assert lidos == {0, 1}


def test_glifo_repetido_e_com_furo_entram_todos(tmp_path: Path, tabela: TabelaGlifos) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("08BCCCC", (40.0, 60.0), 5.0)])

    lidos, total, textos, _ = _ler(pdf, tabela)

    assert textos == ["08BCCCC"]
    assert lidos == set(range(total))
    assert total == 7


@pytest.mark.parametrize("rotacao_pagina", [0, 90, 270], ids=["r0", "r90", "r270"])
def test_rotacao_da_pagina_nao_perde_caminhos_lidos(
    tmp_path: Path, tabela: TabelaGlifos, rotacao_pagina: int
) -> None:
    pdf = pdf_texto_contorno(
        tmp_path / "c.pdf", [LinhaTexto("CT", (100.0, 100.0), 5.0)], rotacao_pagina=rotacao_pagina
    )

    lidos, total, textos, _ = _ler(pdf, tabela)

    assert (total, textos) == (2, ["CT"])
    assert lidos == {0, 1}


def test_pagina_embutida_nao_mistura_posicao_crua_com_posicao_do_modelo(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """`get_drawings` traz `group`: `glifos_lidos` fala de `modelo.caminhos`, não do cru."""
    origem = pdf_texto_contorno(tmp_path / "o.pdf", [LinhaTexto("CT", (30.0, 40.0), 5.0)])
    with pymupdf.open(origem) as fonte, pymupdf.open() as destino:
        base = fonte[0].rect
        pagina = destino.new_page(width=base.width, height=base.height)
        pagina.draw_line((200, 200), (250, 250), color=(0, 0, 0))
        pagina.show_pdf_page(base, fonte, 0)
        destino.save(tmp_path / "r.pdf")

    with pymupdf.open(tmp_path / "r.pdf") as documento:
        pagina_g = pagina_para_gramaticas(documento[0], 0, tabela)
    direto = ler_texto_glifos(pagina_g.modelo.caminhos, tabela)

    assert pagina_g.glifos_lidos == direto.caminhos_lidos
    assert pagina_g.glifos_lidos
    assert pagina_g.glifos_lidos == {1, 2}
    assert pagina_g.indices_crus == (0, 3, 4)
    assert max(pagina_g.glifos_lidos) < len(pagina_g.modelo.caminhos)
    # o traço solto vem antes e nunca é lido como glifo
    assert 0 not in pagina_g.glifos_lidos


def test_texto_nativo_nao_gera_glifos_lidos(tmp_path: Path, tabela: TabelaGlifos) -> None:
    pdf = pdf_texto_nativo(tmp_path / "n.pdf", [LinhaTexto("CT", (100.0, 100.0), 5.0)])

    lidos, _, textos, _ = _ler(pdf, tabela)

    assert textos == ["CT"]
    assert lidos == frozenset()
