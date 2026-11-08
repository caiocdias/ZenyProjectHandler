"""X de retirada perto do símbolo (R-E06.3.3.2.1-2) e marcas do mesmo contexto (R-3).

O critério medido nas folhas: o cruzamento do X fica a até 1 vez a escala do centro do
pictograma. Os X próprios medidos ficam a até 0,38 vez a escala, e os de vizinho a 1,82 vez ou
mais. As fixtures são relativas à escala e sintéticas.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.paginas import linha, pagina_gramatica
from tests.fixtures.symbol_grammars.rect_diagonal import (
    desenhar_retangulo,
)
from tests.fixtures.symbol_grammars.rect_diagonal import (
    pagina_desenhada as pagina_retangulo,
)
from tests.fixtures.symbol_grammars.stem_bars import (
    DECRESCENTES,
    VERMELHO,
    desenhar_haste,
    pagina_desenhada,
)

from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import (
    MarcasDaPagina,
    tem_x,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_rect_diagonal import (
    RetanguloDiagonal,
    retangulos_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_stem import (
    Haste,
    hastes_candidatas,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa, Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    PaginaGramatica,
    contexto_gramaticas,
)

# O vizinho mais perto medido nas folhas: 1,82 vez a escala do centro do pictograma.
_VIZINHO: Final = 1.85
# Meio braço do X em cada eixo, relativo à escala: braço de 2,97 vezes a escala, dentro do
# máximo de 3 vezes e alcançando a janela do pictograma a partir do vizinho.
_MEIO_BRACO: Final = 1.05

_CENTRO: Final[Ponto] = (100.0, 100.0)
_ESCALA: Final = 8.0
_PICTOGRAMA: Final[Caixa] = (95.0, 95.0, 105.0, 105.0)


def _desenhar_x(pagina: pymupdf.Page, cruzamento: Ponto, escala: float) -> None:
    cx, cy = cruzamento
    meio = escala * _MEIO_BRACO
    for sinal in (1, -1):
        pagina.draw_line(
            (cx - meio, cy - sinal * meio),
            (cx + meio, cy + sinal * meio),
            color=VERMELHO,
            width=0.5,
        )


def _centro(caixa: Caixa) -> Ponto:
    return (caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2


def _deslocado(ponto: Ponto, distancia: float, direcao: float) -> Ponto:
    return ponto[0] + distancia * math.cos(direcao), ponto[1] + distancia * math.sin(direcao)


# --- haste: X de vizinho e X próprio ----------------------------------------------------------


def _haste(
    desenhar_extra: Callable[[pymupdf.Page], object] | None = None, *, x: bool = False
) -> Haste:
    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_haste(pagina, DECRESCENTES, x=x)
        if desenhar_extra is not None:
            desenhar_extra(pagina)

    (haste,) = hastes_candidatas(contexto_gramaticas(pagina_desenhada(desenhar)))
    return haste


@pytest.mark.parametrize("direcao", [0.0, math.pi], ids=["a-direita", "a-esquerda"])
def test_x_de_vizinho_na_faixa_medida_nao_marca_a_haste(direcao: float) -> None:
    sozinha = _haste()
    assert sozinha.pictograma is not None
    escala = sozinha.maior_barra
    cruzamento = _deslocado(_centro(sozinha.pictograma), _VIZINHO * escala, direcao)

    com_vizinho = _haste(lambda p: _desenhar_x(p, cruzamento, escala))

    assert com_vizinho.x is None


def test_x_proprio_marca_a_haste() -> None:
    assert _haste(x=True).x is not None


# --- retângulo com diagonal: X de vizinho e X próprio -----------------------------------------


def _retangulo(
    desenhar_extra: Callable[[pymupdf.Page], object] | None = None, *, x: bool = False
) -> RetanguloDiagonal:
    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_retangulo(pagina, x=x)
        if desenhar_extra is not None:
            desenhar_extra(pagina)

    (achado,) = retangulos_candidatos(contexto_gramaticas(pagina_retangulo(desenhar)))
    return achado


@pytest.mark.parametrize("direcao", [0.0, math.pi / 2], ids=["ao-lado", "abaixo"])
def test_x_de_vizinho_na_faixa_medida_nao_marca_o_retangulo(direcao: float) -> None:
    sozinho = _retangulo()
    # A escala do retângulo é o lado maior do corpo, 8 na fixture.
    escala = 8.0
    cruzamento = _deslocado(_centro(sozinho.caixa), _VIZINHO * escala, direcao)

    com_vizinho = _retangulo(lambda p: _desenhar_x(p, cruzamento, escala))

    assert not com_vizinho.x


def test_x_proprio_marca_o_retangulo() -> None:
    assert _retangulo(x=True).x


# --- borda do critério, direto em `tem_x` -----------------------------------------------------


@pytest.mark.parametrize(
    ("distancia", "marca"),
    [(0.0, True), (0.95, True), (1.05, False), (_VIZINHO, False)],
    ids=["no-centro", "dentro-da-borda", "fora-da-borda", "vizinho"],
)
@pytest.mark.parametrize("direcao", [0.0, math.pi / 2], ids=["horizontal", "vertical"])
def test_cruzamento_na_borda_do_criterio(distancia: float, marca: bool, direcao: float) -> None:
    """Cruzamento a `distancia` vezes a escala do centro do pictograma."""
    cx, cy = _deslocado(_CENTRO, distancia * _ESCALA, direcao)
    meio = _ESCALA * _MEIO_BRACO
    contexto = contexto_gramaticas(
        pagina_gramatica(
            [
                linha((cx - meio, cy - meio), (cx + meio, cy + meio)),
                linha((cx - meio, cy + meio), (cx + meio, cy - meio)),
            ]
        )
    )

    par = tem_x(contexto, _PICTOGRAMA, _ESCALA, math.pi / 2, frozenset())

    assert (par is not None) is marca


def test_x_proprio_perto_vence_o_de_vizinho_na_mesma_janela() -> None:
    """Com um X de vizinho examinado antes, o X perto do centro ainda é o lido."""
    meio = _ESCALA * _MEIO_BRACO
    vx, vy = _deslocado(_CENTRO, _VIZINHO * _ESCALA, 0.0)
    contexto = contexto_gramaticas(
        pagina_gramatica(
            [
                linha((vx - meio, vy - meio), (vx + meio, vy + meio)),
                linha((vx - meio, vy + meio), (vx + meio, vy - meio)),
                linha((92.0, 92.0), (108.0, 108.0)),
                linha((92.0, 108.0), (108.0, 92.0)),
            ]
        )
    )

    par = tem_x(contexto, _PICTOGRAMA, _ESCALA, math.pi / 2, frozenset())

    assert par is not None
    assert {s.caminho for s in par} == {2, 3}


# --- marcas do mesmo contexto -----------------------------------------------------------------


def _contexto_haste() -> ContextoGramatica:
    return contexto_gramaticas(pagina_desenhada(lambda p: desenhar_haste(p, DECRESCENTES)))


def _pagina_retangulo() -> PaginaGramatica:
    return pagina_retangulo(lambda p: desenhar_retangulo(p))


def test_marcas_expoem_o_contexto_so_para_leitura() -> None:
    contexto = _contexto_haste()
    marcas = MarcasDaPagina(contexto)

    assert marcas.contexto is contexto
    with pytest.raises(AttributeError):
        marcas.contexto = _contexto_haste()  # type: ignore[misc]


def test_hastes_recusam_marcas_de_outro_contexto() -> None:
    contexto = _contexto_haste()

    with pytest.raises(ValueError, match="contexto"):
        hastes_candidatas(contexto, marcas=MarcasDaPagina(_contexto_haste()))


def test_retangulos_recusam_marcas_de_outro_contexto() -> None:
    pagina = _pagina_retangulo()
    contexto = contexto_gramaticas(pagina)

    with pytest.raises(ValueError, match="contexto"):
        retangulos_candidatos(contexto, marcas=MarcasDaPagina(contexto_gramaticas(pagina)))


def test_hastes_aceitam_marcas_do_mesmo_contexto() -> None:
    contexto = _contexto_haste()

    assert len(hastes_candidatas(contexto, marcas=MarcasDaPagina(contexto))) == 1


def test_retangulos_aceitam_marcas_do_mesmo_contexto() -> None:
    contexto = contexto_gramaticas(_pagina_retangulo())

    assert len(retangulos_candidatos(contexto, marcas=MarcasDaPagina(contexto))) == 1
