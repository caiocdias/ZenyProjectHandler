# mypy: disable-error-code="no-untyped-call"
"""Rótulo em contorno real, lido pelo adaptador e casado com a variante CT do pacote real."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    pdf_texto_contorno,
    pdf_texto_nativo,
    tabela_do_alfabeto,
)

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


_LINHA_CT: Final = [LinhaTexto("CT", (100.0, 100.0), 5.0)]
_AZUL: Final = (0.0, 0.0, 1.0)


def _pagina_ct_emoldurado(
    tmp_path: Path,
    tabela: TabelaGlifos,
    *,
    base: Callable[..., Path] = pdf_texto_contorno,
    desenhar: Callable[[Any], None] | None = None,
) -> PaginaGramatica:
    """`CT` (em contorno, ou nativo) com a moldura desenhada por cima, pelo adaptador real."""
    contorno = base(tmp_path / "contorno.pdf", _LINHA_CT)
    with pymupdf.open(contorno) as documento:
        documento[0].draw_rect(pymupdf.Rect(*_MOLDURA), color=(0.7, 0.0, 0.0))
        if desenhar is not None:
            desenhar(documento[0])
        documento.save(tmp_path / "emoldurado.pdf")
    with pymupdf.open(tmp_path / "emoldurado.pdf") as documento:
        return pagina_para_gramaticas(documento[0], 0, tabela)


def _sem_guarda(variante: Variante) -> Variante:
    pacote, dados = variante
    gramatica = {**dados["recognition"]["grammar"], "empty_interior": False}
    return pacote, {**dados, "recognition": {**dados["recognition"], "grammar": gramatica}}


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


def _casa(pagina: PaginaGramatica, variante: Variante) -> bool:
    return len(casar_variantes(pagina, (variante,))) == 1


def _sem_letra(tabela: TabelaGlifos, letra: str) -> TabelaGlifos:
    return replace(tabela, glifos=tuple(g for g in tabela.glifos if g.caractere != letra))


def _marca_ao_lado(pagina: Any) -> None:
    pagina.draw_rect(pymupdf.Rect(105.5, 94.0, 109.5, 102.0), fill=_AZUL, color=None)


def _triangulo_na_caixa_do_rotulo(pagina: Any) -> None:
    pagina.draw_polyline(
        [pymupdf.Point(101.0, 99.5), pymupdf.Point(105.0, 99.5), pymupdf.Point(103.0, 96.5)],
        fill=_AZUL,
        color=None,
        closePath=True,
    )


def test_rotulo_em_contorno_nao_resolvido_nao_casa(
    tmp_path: Path, tabela: TabelaGlifos, variante_ct: Variante
) -> None:
    """Sem a letra na tabela não há texto e o contorno não é pulado: nada casa."""
    pagina = _pagina_ct_emoldurado(tmp_path, _sem_letra(tabela, "T"))

    assert pagina.modelo.textos == ()
    assert pagina.glifos_lidos == frozenset()
    assert not _casa(pagina, variante_ct)


def test_marca_preenchida_ao_lado_do_rotulo_recusa(
    tmp_path: Path, tabela: TabelaGlifos, variante_ct: Variante
) -> None:
    pagina = _pagina_ct_emoldurado(tmp_path, tabela, desenhar=_marca_ao_lado)

    assert [t.texto for t in pagina.modelo.textos] == ["CT"]
    assert not _casa(pagina, variante_ct)
    assert _casa(pagina, _sem_guarda(variante_ct))


@pytest.mark.parametrize("base", [pdf_texto_contorno, pdf_texto_nativo], ids=["contorno", "nativo"])
def test_triangulo_preenchido_na_caixa_do_rotulo_recusa(
    tmp_path: Path, tabela: TabelaGlifos, variante_ct: Variante, base: Callable[..., Path]
) -> None:
    """`negative_examples` da CT: o triângulo de outra cor dentro da caixa do span não é pulado."""
    pagina = _pagina_ct_emoldurado(
        tmp_path, tabela, base=base, desenhar=_triangulo_na_caixa_do_rotulo
    )

    assert [t.texto for t in pagina.modelo.textos] == ["CT"]
    assert not _casa(pagina, variante_ct)
    assert _casa(pagina, _sem_guarda(variante_ct))


def test_rotulo_nativo_igual_ao_contorno(
    tmp_path: Path, tabela: TabelaGlifos, variante_ct: Variante
) -> None:
    for desenhar in (None, _marca_ao_lado):
        resultados = []
        for nome, base in (("c", pdf_texto_contorno), ("n", pdf_texto_nativo)):
            pasta = tmp_path / f"{nome}{desenhar is None}"
            pasta.mkdir()
            pagina = _pagina_ct_emoldurado(pasta, tabela, base=base, desenhar=desenhar)
            resultados.append(
                (
                    [t.texto for t in pagina.modelo.textos],
                    _casa(pagina, variante_ct),
                    _casa(pagina, _sem_guarda(variante_ct)),
                )
            )
        assert resultados[0] == resultados[1]
        assert resultados[0][0] == ["CT"]
        assert resultados[0][1] is (desenhar is None)
