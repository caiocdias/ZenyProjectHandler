"""Envolvente inclinada: o critério elíptico e o "dentro" valem para a elipse girada.

Desenho autoral, relativo à escala: ovais de 72 retas com o eixo maior girado de 30° a 60°, como
os que acompanham um corpo inclinado; os ovais alinhados aos eixos dão o mesmo resultado de antes.
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
from tests.fixtures.symbol_grammars.rect_diagonal import CASOS_RECT_DIAGONAL, CORPO, HASTE
from tests.fixtures.symbol_grammars.stem_bars import (
    ALTERNADAS,
    CASOS_HASTE,
    DECRESCENTES,
    LACUNA,
)
from tests.fixtures.symbol_grammars.stem_bars import HASTE as HASTE_BARRAS

from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import (
    Contorno,
    MarcasDaPagina,
    envolvente,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caminho,
    ItemCaminho,
    Polilinha,
    Ponto,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    CasamentoGramatica,
    casar_variantes,
)

_CENTRO: Final[Ponto] = (150.0, 150.0)
_LADOS: Final = 72
_TODA_A_PAGINA: Final = (0.0, 0.0, 300.0, 300.0)
_GRAUS: Final = (30.0, 45.0, 60.0)
_V001, _V002 = CASOS_RECT_DIAGONAL[0][0], CASOS_RECT_DIAGONAL[1][0]


def _gira(ponto: Ponto, graus: float, centro: Ponto = _CENTRO) -> Ponto:
    r = math.radians(graus)
    dx, dy = ponto[0] - centro[0], ponto[1] - centro[1]
    return (
        centro[0] + dx * math.cos(r) - dy * math.sin(r),
        centro[1] + dx * math.sin(r) + dy * math.cos(r),
    )


def _elipse_girada(
    a: float, b: float, graus: float, centro: Ponto = _CENTRO, lados: int = _LADOS
) -> list[Ponto]:
    """Semieixo `a` em x e `b` em y antes de girar `graus` em torno do `centro`."""
    pontos = [
        (
            centro[0] + a * math.cos(2 * math.pi * k / lados),
            centro[1] + b * math.sin(2 * math.pi * k / lados),
        )
        for k in range(lados)
    ]
    return [_gira(p, graus, centro) for p in pontos]


def _encostados(vertices: Sequence[Ponto], centro: Ponto = _CENTRO) -> list[Caminho]:
    """Dois traços que saem de vértices opostos: partem a polilinha reconstruída."""
    caminhos = []
    for vertice in (vertices[len(vertices) // 8], vertices[len(vertices) // 8 * 5]):
        dx, dy = vertice[0] - centro[0], vertice[1] - centro[1]
        norma = math.hypot(dx, dy)
        caminhos.append(linha(vertice, (vertice[0] + 3 * dx / norma, vertice[1] + 3 * dy / norma)))
    return caminhos


def _contornos(
    caminhos: Sequence[Caminho], primitivas: Sequence[Polilinha] | None = None
) -> tuple[list[Contorno], int]:
    contexto = contexto_gramaticas(pagina_gramatica(caminhos, primitivas=primitivas))
    antes = contexto.orcamento.gasto
    contornos = MarcasDaPagina(contexto).contornos
    gasto = contexto.orcamento.gasto - antes
    return list(contornos.consultar(_TODA_A_PAGINA)), gasto


def _raio_normalizado(contorno: Contorno, ponto: Ponto) -> float:
    a, b = contorno.semieixos
    c, s = math.cos(contorno.inclinacao), math.sin(contorno.inclinacao)
    dx, dy = ponto[0] - contorno.centro[0], ponto[1] - contorno.centro[1]
    return math.hypot((dx * c + dy * s) / a, (-dx * s + dy * c) / b)


# --- o oval girado vira contorno, nas duas rotas ----------------------------------------------


@pytest.mark.parametrize("razao", [1.5, 2.0], ids=["razao-1_5", "razao-2"])
@pytest.mark.parametrize("graus", _GRAUS, ids=["30", "45", "60"])
def test_subcaminho_eliptico_girado_vira_contorno(graus: float, razao: float) -> None:
    vertices = _elipse_girada(10.0, 10.0 / razao, graus)

    contornos, _ = _contornos([poligono(vertices), *_encostados(vertices)])

    [contorno] = contornos
    assert (contorno.origem, contorno.caminhos) == ("subcaminho", (0,))
    assert contorno.centro == pytest.approx(_CENTRO, abs=1e-6)
    assert sorted(contorno.semieixos) == pytest.approx([10.0 / razao, 10.0], abs=1e-6)
    assert all(_raio_normalizado(contorno, p) == pytest.approx(1.0, abs=1e-6) for p in vertices)


@pytest.mark.parametrize("graus", _GRAUS, ids=["30", "45", "60"])
def test_polilinha_eliptica_girada_vira_contorno(graus: float) -> None:
    vertices = _elipse_girada(10.0, 5.5, graus)
    polilinha = Polilinha(tuple(vertices), True, estilo(), (0,))

    contornos, _ = _contornos([linha((20.0, 20.0), (24.0, 20.0))], primitivas=[polilinha])

    [contorno] = contornos
    assert contorno.origem == "polilinha"
    assert all(_raio_normalizado(contorno, p) == pytest.approx(1.0, abs=1e-6) for p in vertices)


# --- o que não vira contorno ------------------------------------------------------------------


def _subdividido(cantos: Sequence[Ponto], por_lado: int) -> list[Ponto]:
    """Os lados do polígono, cada um partido em `por_lado` retas."""
    pontos = []
    for i, a in enumerate(cantos):
        b = cantos[(i + 1) % len(cantos)]
        pontos += [
            (a[0] + (b[0] - a[0]) * k / por_lado, a[1] + (b[1] - a[1]) * k / por_lado)
            for k in range(por_lado)
        ]
    return pontos


def _retangulo(meio_x: float, meio_y: float) -> list[Ponto]:
    cx, cy = _CENTRO
    return [
        (cx - meio_x, cy - meio_y),
        (cx + meio_x, cy - meio_y),
        (cx + meio_x, cy + meio_y),
        (cx - meio_x, cy + meio_y),
    ]


def _losango(meio_x: float, meio_y: float) -> list[Ponto]:
    cx, cy = _CENTRO
    return [(cx, cy - meio_y), (cx + meio_x, cy), (cx, cy + meio_y), (cx - meio_x, cy)]


def _octogono_irregular() -> list[Ponto]:
    """Retângulo de cantos chanfrados: oito lados, longe de qualquer elipse."""
    cx, cy = _CENTRO
    x0, y0, x1, y1 = cx - 10.0, cy - 4.0, cx + 10.0, cy + 4.0
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
    ("vertices", "graus"),
    [
        (_retangulo(10.0, 5.0), 45.0),
        (_subdividido(_retangulo(10.0, 5.0), 9), 45.0),
        (_subdividido(_retangulo(10.0, 10.0), 9), 45.0),
        (_subdividido(_losango(10.0, 5.0), 9), 30.0),
        (_octogono_irregular(), 30.0),
        (_octogono_irregular(), 60.0),
    ],
    ids=[
        "retangulo-45",
        "retangulo-subdividido-45",
        "quadrado-subdividido-45",
        "losango-subdividido-30",
        "octogono-irregular-30",
        "octogono-irregular-60",
    ],
)
def test_poligono_girado_nao_eliptico_nao_vira_contorno(
    vertices: list[Ponto], graus: float
) -> None:
    girados = [_gira(p, graus) for p in vertices]

    contornos, _ = _contornos([poligono(girados), *_encostados(girados)])

    assert contornos == []


def test_elipse_girada_aberta_nao_vira_contorno() -> None:
    vertices = _elipse_girada(10.0, 5.0, 45.0)
    itens = tuple(ItemCaminho("l", (vertices[i], vertices[i + 1])) for i in range(_LADOS - 6))

    contornos, _ = _contornos([Caminho((itens,), estilo(), "traco", 0)])

    assert contornos == []


# --- invariância e gasto ----------------------------------------------------------------------


@pytest.mark.parametrize(("a", "b"), [(10.0, 6.0), (6.0, 10.0)], ids=["deitada", "em-pe"])
def test_elipse_alinhada_aos_eixos_da_o_resultado_de_antes(a: float, b: float) -> None:
    vertices = _elipse_girada(a, b, 0.0)
    cx, cy = _CENTRO

    [contorno], _ = _contornos([poligono(vertices), *_encostados(vertices)])

    xs, ys = [p[0] for p in vertices], [p[1] for p in vertices]
    assert contorno.caixa == (min(xs), min(ys), max(xs), max(ys))
    assert contorno.inclinacao == 0.0
    assert contorno.semieixos == ((max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2)
    assert contorno.centro == ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    assert contorno.centro == pytest.approx((cx, cy))


def test_vertices_desigualmente_espacados_nao_inventam_inclinacao() -> None:
    """Oval alinhado de 10 por 6 com 40 vértices num quarto e 12 no resto: a direção vem do
    contorno, não da contagem de vértices."""
    cx, cy = _CENTRO
    angulos = [math.pi / 2 * k / 40 for k in range(40)]
    angulos += [math.pi / 2 + 3 * math.pi / 2 * k / 12 for k in range(12)]
    vertices = [(cx + 10.0 * math.cos(t), cy + 6.0 * math.sin(t)) for t in angulos]

    [contorno], _ = _contornos([poligono(vertices), *_encostados(vertices)])

    assert abs(contorno.inclinacao) < 0.02
    assert contorno.semieixos == pytest.approx((10.0, 6.0), abs=0.1)


def test_girar_o_oval_nao_muda_o_gasto() -> None:
    _, alinhado = _contornos([poligono(_elipse_girada(10.0, 5.0, 0.0))])
    _, girado = _contornos([poligono(_elipse_girada(10.0, 5.0, 45.0))])

    assert girado == alinhado


# --- dentro da envolvente ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("direcao", "conta"),
    [(45.0, True), (135.0, False)],
    ids=["no-eixo-maior", "no-eixo-menor-dentro-da-caixa"],
)
def test_dentro_da_envolvente_e_dentro_da_elipse_girada(direcao: float, conta: bool) -> None:
    """Ponto a 7 do centro: dentro do semieixo maior (10), fora do menor (5), e sempre dentro da
    caixa alinhada, cuja meia largura é 7,9."""
    vertices = _elipse_girada(10.0, 5.0, 45.0)
    contexto = contexto_gramaticas(pagina_gramatica([poligono(vertices)]))
    r = math.radians(direcao)
    ponto = (_CENTRO[0] + 7.0 * math.cos(r), _CENTRO[1] + 7.0 * math.sin(r))
    [contorno] = MarcasDaPagina(contexto).contornos.consultar(_TODA_A_PAGINA)
    assert contorno.caixa[0] < ponto[0] < contorno.caixa[2]
    assert contorno.caixa[1] < ponto[1] < contorno.caixa[3]

    achada = envolvente(
        MarcasDaPagina(contexto).contornos, (_CENTRO, ponto), 8.0, _CENTRO, frozenset()
    )

    assert (achada is not None) is conta


# --- as gramáticas casam a variante com envolvente --------------------------------------------


def _pares(casos: Sequence[tuple[str, Mapping[str, Any]]]) -> list[tuple[Any, Any]]:
    return [
        ({"family_id": "autoral"}, {"id": v, "recognition": {"status": "enabled", "grammar": g}})
        for v, g in casos
    ]


def _casamentos(
    pagina: PaginaGramatica, casos: Sequence[tuple[str, Mapping[str, Any]]]
) -> tuple[CasamentoGramatica, ...]:
    return casar_variantes(pagina, _pares(casos))


def _bt_girado(graus: float, *, elipse_no_eixo: bool = True, haste: bool = False) -> list[Caminho]:
    """Corpo (0) e diagonal (1) girados `graus`; oval (2) de 7 por 4 com o eixo maior no do corpo,
    ou de 7 por 3,5 atravessado nele; com `haste`, um traço (3) que sai da borda do oval no eixo
    do corpo."""
    cx, cy = _CENTRO
    meio_h, meio_l = CORPO[0] / 2, CORPO[1] / 2
    cantos = [(cx - meio_l, cy - meio_h), (cx + meio_l, cy - meio_h)]
    cantos += [(cx + meio_l, cy + meio_h), (cx - meio_l, cy + meio_h)]
    a, b = (4.0, 7.0) if elipse_no_eixo else (7.0, 3.5)
    caminhos = [
        poligono([_gira(p, graus) for p in cantos]),
        linha(
            _gira((cx - meio_l * 2, cy + meio_h * 0.5), graus),
            _gira((cx + meio_l * 2, cy - meio_h * 0.5), graus),
        ),
        poligono(_elipse_girada(a, b, graus)),
    ]
    if haste:
        caminhos.append(linha(_gira((cx, cy - b), graus), _gira((cx, cy - b - HASTE), graus)))
    return caminhos


@pytest.mark.parametrize("graus", _GRAUS, ids=["30", "45", "60"])
def test_bt_girado_dentro_do_oval_girado_casa_com_envolvente(graus: float) -> None:
    [casamento] = _casamentos(pagina_gramatica(_bt_girado(graus)), CASOS_RECT_DIAGONAL)

    assert casamento.variante["id"] == _V002
    assert casamento.componentes == (1, 2)


@pytest.mark.parametrize("graus", _GRAUS, ids=["30", "45", "60"])
def test_bt_atravessado_no_oval_girado_fica_sem_envolvente(graus: float) -> None:
    """Os cantos do corpo saem pelo semieixo menor, ainda que caibam na caixa do oval."""
    pagina = pagina_gramatica(_bt_girado(graus, elipse_no_eixo=False))

    assert [str(c.variante["id"]) for c in _casamentos(pagina, CASOS_RECT_DIAGONAL)] == [_V001]


@pytest.mark.parametrize("graus", _GRAUS, ids=["30", "45", "60"])
def test_haste_que_sai_da_borda_do_oval_girado_entra(graus: float) -> None:
    [casamento] = _casamentos(pagina_gramatica(_bt_girado(graus, haste=True)), CASOS_RECT_DIAGONAL)

    assert casamento.variante["id"] == _V002
    assert casamento.componentes == (1, 2, 3)


def _haste(barras: Sequence[float], graus: float) -> list[Caminho]:
    """Haste e barras como em `stem_bars.desenhar_haste`, dentro de um oval com o eixo maior nas
    barras e o menor na haste (razão 1,75), tudo girado `graus`."""
    cx, cy = _CENTRO
    ponta = cy - HASTE_BARRAS / 2
    caminhos = [linha(_gira((cx, cy + HASTE_BARRAS / 2), graus), _gira((cx, ponta), graus))]
    for i, comprimento in enumerate(barras):
        y, meio = ponta - i * LACUNA, comprimento / 2
        caminhos.append(linha(_gira((cx - meio, y), graus), _gira((cx + meio, y), graus)))
    raio = max(barras) * 0.8 + len(barras) * LACUNA / 2
    meio_barras = _gira((cx, ponta - (len(barras) - 1) * LACUNA / 2), graus)
    oval = _elipse_girada(raio, raio / 1.75, graus, centro=meio_barras)
    return [*caminhos, poligono(oval), *_encostados(oval, meio_barras)]


@pytest.mark.parametrize("graus", _GRAUS, ids=["30", "45", "60"])
@pytest.mark.parametrize(
    ("barras", "esperada"),
    [(DECRESCENTES, CASOS_HASTE[1][0]), (ALTERNADAS, CASOS_HASTE[5][0])],
    ids=["tres-barras", "quatro-barras"],
)
def test_haste_dentro_do_oval_girado_casa_com_envolvente(
    barras: Sequence[float], esperada: str, graus: float
) -> None:
    pagina = pagina_gramatica(_haste(barras, graus))

    assert [str(c.variante["id"]) for c in _casamentos(pagina, CASOS_HASTE)] == [esperada]
