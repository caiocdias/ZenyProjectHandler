"""Envolvente desenhada como subcaminho fechado de dezenas de retas (R-E06.3.3.2.1-1).

Desenho autoral: elipses de muitos lados num subcaminho só, como as folhas trazem o oval. Traços
encostados em dois vértices partem a polilinha reconstruída entre as junções (com um só, ela
ainda fecha na junção), e a envolvente sai do subcaminho.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

import pytest
from tests.fixtures.symbol_grammars.paginas import (
    estilo,
    linha,
    pagina_gramatica,
    poligono,
)
from tests.fixtures.symbol_grammars.rect_diagonal import CASOS_RECT_DIAGONAL, CORPO
from tests.fixtures.symbol_grammars.stem_bars import (
    ALTERNADAS,
    CASOS_HASTE,
    DECRESCENTES,
    HASTE,
    LACUNA,
)

from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import (
    Contorno,
    MarcasDaPagina,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caminho,
    Cor,
    ItemCaminho,
    Polilinha,
    Ponto,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    PaginaGramatica,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import casar_variantes

_CENTRO: Final[Ponto] = (100.0, 100.0)
_LADOS: Final = 40
_TODA_A_PAGINA: Final = (0.0, 0.0, 300.0, 300.0)
_VERDE: Final[Cor] = (0.0, 0.5, 0.0)


def _elipse(
    centro: Ponto = _CENTRO, a: float = 10.0, b: float = 7.0, lados: int = _LADOS
) -> list[Ponto]:
    return [
        (
            centro[0] + a * math.cos(2 * math.pi * k / lados),
            centro[1] + b * math.sin(2 * math.pi * k / lados),
        )
        for k in range(lados)
    ]


def _encostado(vertice: Ponto, centro: Ponto, comprimento: float = 3.0) -> Caminho:
    """Traço que sai do vértice para fora, no mesmo estilo: parte a polilinha da elipse."""
    dx, dy = vertice[0] - centro[0], vertice[1] - centro[1]
    norma = math.hypot(dx, dy)
    fim = (vertice[0] + dx / norma * comprimento, vertice[1] + dy / norma * comprimento)
    return linha(vertice, fim)


def _elipse_com_traco(
    centro: Ponto = _CENTRO, a: float = 10.0, b: float = 7.0, tracos: int = 2
) -> list[Caminho]:
    """O oval e `tracos` traços encostados em vértices distintos."""
    vertices = _elipse(centro, a, b)
    encostados = [
        _encostado(vertices[_LADOS // 8 + k * _LADOS // 2], centro) for k in range(tracos)
    ]
    return [poligono(vertices), *encostados]


def _contornos(caminhos: Sequence[Caminho]) -> tuple[ContextoGramatica, list[Contorno], int]:
    contexto = contexto_gramaticas(pagina_gramatica(caminhos))
    antes = contexto.orcamento.gasto
    contornos = MarcasDaPagina(contexto).contornos
    gasto = contexto.orcamento.gasto - antes
    return contexto, list(contornos.consultar(_TODA_A_PAGINA)), gasto


def _polilinhas_fechadas(contexto: ContextoGramatica) -> list[Polilinha]:
    return [p for p in contexto.pagina.modelo.primitivas if isinstance(p, Polilinha) and p.fechada]


# --- o subcaminho vira contorno ---------------------------------------------------------------


@pytest.mark.parametrize("tracos", [1, 2], ids=["um-traco", "dois-tracos"])
def test_subcaminho_eliptico_com_traco_encostado_vira_um_contorno(tracos: int) -> None:
    contexto, contornos, _ = _contornos(_elipse_com_traco(tracos=tracos))

    assert len(_polilinhas_fechadas(contexto)) == 2 - tracos
    [contorno] = contornos
    assert contorno.caminhos == (0,)
    assert contorno.origem == "subcaminho"
    assert contorno.subcaminho == 0
    assert contorno.caixa == pytest.approx((90.0, 93.0, 110.0, 107.0), abs=0.05)


def test_mesma_elipse_da_polilinha_e_do_subcaminho_vira_um_contorno() -> None:
    contexto, contornos, _ = _contornos([poligono(_elipse())])

    assert len(_polilinhas_fechadas(contexto)) == 1
    [contorno] = contornos
    assert contorno.caminhos == (0,)


def test_segundo_subcaminho_do_caminho_guarda_o_indice() -> None:
    quadrado = poligono([(20.0, 20.0), (24.0, 20.0), (24.0, 24.0), (20.0, 24.0)])
    elipse = poligono(_elipse())
    caminho = Caminho((quadrado.subcaminhos[0], elipse.subcaminhos[0]), estilo(), "traco", 0)

    _, contornos, _ = _contornos([caminho])

    [contorno] = contornos
    assert (contorno.caminhos, contorno.subcaminho) == ((0,), 1)


# --- o que não vira contorno ------------------------------------------------------------------


def _octogono_irregular() -> list[Ponto]:
    """Oito lados fechados, longe de qualquer elipse: um retângulo de cantos chanfrados."""
    x0, y0, x1, y1 = 90.0, 96.0, 110.0, 104.0
    return [
        (x0 + 1, y0),
        (x1 - 1, y0),
        (x1, y0 + 1),
        (x1, y1 - 1),
        (x1 - 1, y1),
        (x0 + 1, y1),
        (x0, y1 - 1),
        (x0, y0 + 1),
    ]


@pytest.mark.parametrize(
    "vertices",
    [
        [(90.0, 95.0), (110.0, 95.0), (110.0, 105.0), (90.0, 105.0)],
        _octogono_irregular(),
    ],
    ids=["retangulo", "octogono-irregular"],
)
def test_poligono_fechado_nao_eliptico_nao_vira_contorno(vertices: list[Ponto]) -> None:
    caminhos = [poligono(vertices), _encostado(vertices[0], _CENTRO)]

    _, contornos, _ = _contornos(caminhos)

    assert contornos == []


def test_elipse_aberta_nao_vira_contorno() -> None:
    vertices = _elipse()
    itens = tuple(ItemCaminho("l", (vertices[i], vertices[i + 1])) for i in range(_LADOS - 4))
    aberta = Caminho((itens,), estilo(), "traco", 0)

    _, contornos, gasto = _contornos([aberta])
    _, _, gasto_vazio = _contornos([])

    assert contornos == []
    assert gasto == gasto_vazio


@pytest.mark.parametrize("cor", [None, _VERDE], ids=["preenchimento", "traco-e-preenchimento"])
def test_poligono_eliptico_preenchido_nao_vira_contorno_nem_paga(cor: Cor | None) -> None:
    vertices = _elipse()
    preenchido = poligono(vertices, preenchimento=_VERDE, cor=cor)

    _, contornos, gasto = _contornos([preenchido, _encostado(vertices[0], _CENTRO)])
    _, _, gasto_so_traco = _contornos([_encostado(vertices[0], _CENTRO)])

    assert contornos == []
    assert gasto == gasto_so_traco


# --- gasto ------------------------------------------------------------------------------------


def test_cada_subcaminho_que_passa_no_filtro_paga_um() -> None:
    """Dois ovais partidos e um octógono fechado passam no filtro; o resto não é examinado."""
    octogono = _octogono_irregular()
    passam = [
        *_elipse_com_traco((60.0, 60.0)),
        *_elipse_com_traco((200.0, 200.0)),
        poligono([(x + 100.0, y) for x, y in octogono]),
    ]
    nao_passam = [
        poligono([(20.0, 20.0), (24.0, 20.0), (24.0, 24.0), (20.0, 24.0)]),
        linha((250.0, 30.0), (260.0, 30.0)),
    ]
    contexto_base, _, gasto_base = _contornos(nao_passam)
    contexto, contornos, gasto = _contornos([*passam, *nao_passam])

    fechadas = len(_polilinhas_fechadas(contexto)) - len(_polilinhas_fechadas(contexto_base))
    # Cada contorno novo também entra no índice, que paga 1 por inserção.
    assert gasto - gasto_base == fechadas + 3 + len(contornos)
    assert len(contornos) == 2


# --- as gramáticas casam a variante com envolvente --------------------------------------------


_Casos = Sequence[tuple[str, Mapping[str, Any]]]


def _pares(casos: _Casos) -> list[tuple[Any, Any]]:
    return [
        ({"family_id": "autoral"}, {"id": v, "recognition": {"status": "enabled", "grammar": g}})
        for v, g in casos
    ]


def _variantes(pagina: PaginaGramatica, casos: _Casos) -> list[str]:
    return [str(c.variante["id"]) for c in casar_variantes(pagina, _pares(casos))]


def _bt(centro: Ponto, com_elipse: bool) -> list[Caminho]:
    """Retângulo do corpo e oval no mesmo caminho (dois subcaminhos) e a diagonal à parte."""
    cx, cy = centro
    meio_h, meio_l = CORPO[0] / 2, CORPO[1] / 2
    cantos = [(cx - meio_l, cy - meio_h), (cx + meio_l, cy - meio_h)]
    cantos += [(cx + meio_l, cy + meio_h), (cx - meio_l, cy + meio_h)]
    retangulo = poligono(cantos)
    subcaminhos = retangulo.subcaminhos
    if com_elipse:
        subcaminhos += poligono(_elipse(centro, 7.0, 7.0)).subcaminhos
    diagonal = linha((cx - meio_l * 2, cy + meio_h * 0.5), (cx + meio_l * 2, cy - meio_h * 0.5))
    return [Caminho(subcaminhos, estilo(), "traco", 0), diagonal]


@pytest.mark.parametrize(
    ("com_elipse", "esperada"),
    [(True, "cemig-eo-r3-s21-v002"), (False, "cemig-eo-r3-s21-v001")],
    ids=["com-elipse", "sem-elipse"],
)
def test_elipse_no_caminho_do_retangulo_do_bt_casa_a_envolvente(
    com_elipse: bool, esperada: str
) -> None:
    pagina = pagina_gramatica(_bt((150.0, 150.0), com_elipse))

    assert _variantes(pagina, CASOS_RECT_DIAGONAL) == [esperada]


def _haste(centro: Ponto, barras: Sequence[float], com_elipse: bool) -> list[Caminho]:
    """Haste e barras como em `stem_bars.desenhar_haste`; oval partido por um traço encostado."""
    cx, cy = centro
    ponta = cy - HASTE / 2
    caminhos = [linha((cx, cy + HASTE / 2), (cx, ponta))]
    for i, comprimento in enumerate(barras):
        y, meio = ponta - i * LACUNA, comprimento / 2
        caminhos.append(linha((cx - meio, y), (cx + meio, y)))
    if com_elipse:
        raio = max(barras) * 0.8 + len(barras) * LACUNA / 2
        meio_barras = (cx, ponta - (len(barras) - 1) * LACUNA / 2)
        caminhos += _elipse_com_traco(meio_barras, raio, raio)
    return caminhos


@pytest.mark.parametrize(
    ("barras", "com_elipse", "esperada"),
    [
        (DECRESCENTES, True, "cemig-eo-r3-s19-v002"),
        (ALTERNADAS, True, "cemig-eo-r3-s21-v006"),
        (DECRESCENTES, False, "cemig-eo-r3-s19-v001"),
        (ALTERNADAS, False, "cemig-eo-r3-s21-v005"),
    ],
    ids=["tres-com-elipse", "quatro-com-elipse", "tres-sem-elipse", "quatro-sem-elipse"],
)
def test_haste_dentro_do_oval_partido_casa_a_variante_com_envolvente(
    barras: Sequence[float], com_elipse: bool, esperada: str
) -> None:
    pagina = pagina_gramatica(_haste((150.0, 150.0), barras, com_elipse))

    assert _variantes(pagina, CASOS_HASTE) == [esperada]
