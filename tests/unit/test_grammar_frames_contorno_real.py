# mypy: disable-error-code="no-untyped-call"
"""Rótulo em contorno real, lido pelo adaptador e casado com a variante CT do pacote real."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.glyphs.fonte_livre import LinhaTexto, pdf_texto_contorno, tabela_do_alfabeto

from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import TabelaGlifos
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import PaginaGramatica
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import casar_variantes
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas

Variante = tuple[Mapping[str, Any], Mapping[str, Any]]

# 13 x 10 pt: em tamanho 5, "C" e "T" têm mais de 6% da área e cabem na caixa interna.
_MOLDURA: Final[Caixa] = (97.0, 93.0, 110.0, 103.0)
_AREA_MARCA: Final = 0.06


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto"))


@pytest.fixture(scope="module")
def variante_ct() -> Variante:
    (pacote,) = (p for p in carregar_pacotes() if p["family_id"] == "family-f02-06")
    (variante,) = (
        v
        for v in pacote["variants"]
        if (gramatica := v["recognition"].get("grammar"))
        and gramatica["kind"] == "label_in_frame"
        and gramatica["label"] == "CT"
        and gramatica.get("empty_interior") is True
    )
    return pacote, variante


def _pagina_ct_emoldurado(tmp_path: Path, tabela: TabelaGlifos) -> PaginaGramatica:
    """`CT` em contorno com a moldura desenhada por cima, pelo adaptador real."""
    contorno = pdf_texto_contorno(
        tmp_path / "contorno.pdf", [LinhaTexto("CT", (100.0, 100.0), 5.0)]
    )
    with pymupdf.open(contorno) as documento:
        documento[0].draw_rect(pymupdf.Rect(*_MOLDURA), color=(0.7, 0.0, 0.0))
        documento.save(tmp_path / "emoldurado.pdf")
    with pymupdf.open(tmp_path / "emoldurado.pdf") as documento:
        return pagina_para_gramaticas(documento[0], 0, tabela)


def _sem_guarda(variante: Variante) -> Variante:
    pacote, dados = variante
    gramatica = {**dados["recognition"]["grammar"], "empty_interior": False}
    return pacote, {**dados, "recognition": {**dados["recognition"], "grammar": gramatica}}


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="I3: o contorno da letra aciona `_marca_de_proposta`; a guarda muda na Task 6.",
)
def test_rotulo_em_contorno_casa(
    tmp_path: Path, tabela: TabelaGlifos, variante_ct: Variante
) -> None:
    pagina = _pagina_ct_emoldurado(tmp_path, tabela)

    casamentos = casar_variantes(pagina, (variante_ct,))

    assert [c.variante["id"] for c in casamentos] == [variante_ct[1]["id"]]
    assert casamentos[0].caixa == pytest.approx(_MOLDURA)


def test_so_a_guarda_de_marca_separa_o_rotulo_da_variante(
    tmp_path: Path, tabela: TabelaGlifos, variante_ct: Variante
) -> None:
    """Premissas de `test_rotulo_em_contorno_casa`: o texto é lido, as letras passam de 6% da
    moldura e, sem `empty_interior`, a mesma gramática casa."""
    pagina = _pagina_ct_emoldurado(tmp_path, tabela)

    assert [(t.texto, t.origem) for t in pagina.modelo.textos] == [("CT", "glifo")]
    area_moldura = (_MOLDURA[2] - _MOLDURA[0]) * (_MOLDURA[3] - _MOLDURA[1])
    letras = [c for c in pagina.modelo.caminhos if c.estilo.preenchimento is not None]
    assert len(letras) == 2
    for letra in letras:
        pontos = [p for sub in letra.subcaminhos for item in sub for p in item.pontos]
        xs, ys = [x for x, _ in pontos], [y for _, y in pontos]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        assert area >= area_moldura * _AREA_MARCA
    assert len(casar_variantes(pagina, (_sem_guarda(variante_ct),))) == 1
