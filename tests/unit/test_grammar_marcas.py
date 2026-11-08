"""Marcas compartilhadas das gramáticas do modelo: envolvente, X, cor, sinal da página e gasto."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    linha,
    pagina_gramatica,
    poligono,
    texto,
)
from tests.fixtures.symbol_grammars.stem_bars import (
    ALTERNADAS,
    CASOS_HASTE,
    CIRCULO_POLIGONAL,
    NEGATIVOS,
    desenhar_haste,
    desenhar_positivo,
    pagina_desenhada,
)

from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import (
    Contorno,
    MarcasDaPagina,
    cor_canonica,
    envolvente,
    origem_predominante,
    tem_x,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_stem import hastes_candidatas
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Caminho,
    Cor,
    Ponto,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    PaginaGramatica,
    Segmento,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import gasto_por_fase

_CENTRO: Final[Ponto] = (100.0, 100.0)
_RAIO: Final = 10.0
_PRETO: Final[Cor] = (0.0, 0.0, 0.0)
_VERTICAL: Final = math.pi / 2
_PICTOGRAMA: Final[Caixa] = (95.0, 95.0, 105.0, 105.0)
_BRACO_A: Final[tuple[Ponto, Ponto]] = ((92.0, 92.0), (108.0, 108.0))
_BRACO_B: Final[tuple[Ponto, Ponto]] = ((92.0, 108.0), (108.0, 92.0))


def _contexto(caminhos: Sequence[Caminho]) -> ContextoGramatica:
    return contexto_gramaticas(pagina_gramatica(caminhos))


def _vertices(n: int, recuo: float = 0.0, centro: Ponto = _CENTRO) -> list[Ponto]:
    """Polígono de `n` vértices na circunferência; os ímpares recuados em `recuo` do raio."""
    return [
        (
            centro[0] + _RAIO * (1.0 - recuo * (k % 2)) * math.cos(2 * math.pi * k / n),
            centro[1] + _RAIO * (1.0 - recuo * (k % 2)) * math.sin(2 * math.pi * k / n),
        )
        for k in range(n)
    ]


def _envolvente_unica(
    caminhos: Sequence[Caminho],
    *,
    escala: float = 8.0,
    exigidos: Sequence[Ponto] = (_CENTRO,),
    proprios: frozenset[int] = frozenset(),
) -> Contorno | None:
    marcas = MarcasDaPagina(_contexto(caminhos))
    return envolvente(marcas.contornos, exigidos, escala, _CENTRO, proprios)


# --- envolvente: Bézier e polilinha elíptica --------------------------------------------------


def test_envolvente_bezier_contem_os_exigidos() -> None:
    achada = _envolvente_unica([circulo_bezier(_CENTRO, _RAIO)], exigidos=(_CENTRO, (104.0, 97.0)))

    assert achada is not None
    assert achada.caminhos == (0,)
    assert achada.caixa == pytest.approx((90.0, 90.0, 110.0, 110.0))


def test_envolvente_que_nao_contem_um_exigido_nao_conta() -> None:
    assert (
        _envolvente_unica([circulo_bezier(_CENTRO, _RAIO)], exigidos=(_CENTRO, (112.0, 100.0)))
        is None
    )


def test_envolvente_dos_proprios_caminhos_nao_conta() -> None:
    assert _envolvente_unica([circulo_bezier(_CENTRO, _RAIO)], proprios=frozenset({0})) is None


@pytest.mark.parametrize(
    ("escala", "achada"),
    [(6.6, True), (6.5, False), (21.0, True), (21.1, False)],
    ids=[
        "diametro-no-maximo",
        "diametro-acima-do-maximo",
        "diametro-no-minimo",
        "abaixo-do-minimo",
    ],
)
def test_diametro_da_envolvente_relativo_a_escala(escala: float, achada: bool) -> None:
    """Diâmetro 20 dentro de 0,95 a 3,06 vezes a escala."""
    resultado = _envolvente_unica([circulo_bezier(_CENTRO, _RAIO)], escala=escala)

    assert (resultado is not None) is achada


@pytest.mark.parametrize(("vertices", "achada"), [(7, False), (8, True), (32, True)])
def test_limiar_de_vertices_da_envolvente_poligonal(vertices: int, achada: bool) -> None:
    resultado = _envolvente_unica([poligono(_vertices(vertices))])

    assert (resultado is not None) is achada
    if resultado is not None:
        assert resultado.caminhos == (0,)


@pytest.mark.parametrize(("recuo", "achada"), [(0.15, True), (0.19, True), (0.21, False)])
def test_limiar_de_desvio_da_envolvente_poligonal(recuo: float, achada: bool) -> None:
    resultado = _envolvente_unica([poligono(_vertices(32, recuo))])

    assert (resultado is not None) is achada


def test_envolvente_escolhe_a_menor_elipse() -> None:
    caminhos = [
        circulo_bezier(_CENTRO, 12.0),
        poligono(_vertices(32)),
    ]

    resultado = _envolvente_unica(caminhos)

    assert resultado is not None
    assert resultado.caminhos == (1,)


# --- X de retirada ----------------------------------------------------------------------------


def _segmentos(contexto: ContextoGramatica, *caminhos: int) -> frozenset[Segmento]:
    return frozenset(s for s in contexto.grade_segmentos.itens if s.caminho in caminhos)


def _x(contexto: ContextoGramatica, proprios: frozenset[Segmento] = frozenset()) -> Any:
    return tem_x(contexto, _PICTOGRAMA, 8.0, _VERTICAL, proprios)


def test_x_com_dois_bracos_soltos() -> None:
    contexto = _contexto([linha(*_BRACO_A), linha(*_BRACO_B)])

    par = _x(contexto)

    assert par is not None
    assert {s.caminho for s in par} == {0, 1}


def test_x_com_braco_em_contorno_nao_conta() -> None:
    """O braço é um traço só: o lado de um quadrilátero fechado não forma X."""
    a, b = _BRACO_B
    lado = poligono([a, b, (b[0] + 16.0, b[1]), (a[0] + 16.0, a[1])])

    assert _x(_contexto([linha(*_BRACO_A), lado])) is None


def test_x_com_bracos_proprios_nao_conta() -> None:
    contexto = _contexto([linha(*_BRACO_A), linha(*_BRACO_B)])

    assert _x(contexto, _segmentos(contexto, 1)) is None


def test_x_paga_cada_par_de_bracos_examinado() -> None:
    contexto = _contexto([linha(*_BRACO_A), linha(*_BRACO_B), linha((92.0, 93.0), (108.0, 109.0))])
    antes = contexto.orcamento.gasto

    _x(contexto)

    assert contexto.orcamento.gasto - antes == 6


@pytest.mark.parametrize(
    ("cor_a", "cor_b", "forma"),
    [
        (_PRETO, _PRETO, True),
        (_PRETO, (0.1, 0.1, 0.1), True),
        ((1.0, 0.0, 0.0), (0.8, 0.1, 0.0), True),
        (_PRETO, (1.0, 0.0, 0.0), False),
        ((0.25, 0.25, 0.75), (0.265, 0.25, 0.75), True),
        ((0.25, 0.25, 0.75), (0.275, 0.25, 0.75), False),
        (_PRETO, (0.25, 0.25, 0.75), False),
    ],
    ids=[
        "preto-preto",
        "preto-quase-preto",
        "vermelho-vermelho-escuro",
        "preto-vermelho",
        "fora-do-legado-na-tolerancia",
        "fora-do-legado-acima-da-tolerancia",
        "legado-e-fora-do-legado",
    ],
)
def test_bracos_do_x_comparam_as_cores_entre_si(cor_a: Cor, cor_b: Cor, forma: bool) -> None:
    contexto = _contexto([linha(*_BRACO_A, cor=cor_a), linha(*_BRACO_B, cor=cor_b)])

    assert (_x(contexto) is not None) is forma


# --- cor canônica e sinal da página -----------------------------------------------------------


@pytest.mark.parametrize(
    ("cor", "preenchimento", "esperada"),
    [
        ((0.0, 0.0, 0.0), None, "#000000"),
        ((40 / 255, 40 / 255, 0.0), None, "#000000"),
        ((41 / 255, 0.0, 0.0), None, None),
        ((1.0, 0.0, 0.0), None, "#FF0000"),
        ((0.0, 0.5, 0.0), None, "#008000"),
        ((0.0, 0.0, 1.0), None, None),
        (None, (1.0, 0.0, 0.0), "#FF0000"),
        ((0.0, 0.0, 1.0), (0.0, 0.5, 0.0), "#008000"),
        (None, None, None),
    ],
)
def test_cor_canonica_do_legado(
    cor: Cor | None, preenchimento: Cor | None, esperada: str | None
) -> None:
    assert cor_canonica(cor, preenchimento) == esperada


@pytest.mark.parametrize(
    ("origens", "esperada"),
    [
        ((), "nativo"),
        (("glifo", "glifo", "nativo"), "glifo"),
        (("shx", "nativo", "nativo"), "nativo"),
        (("glifo", "nativo"), "nativo"),
        (("glifo", "shx"), "shx"),
        (("nativo", "shx"), "shx"),
    ],
)
def test_origem_predominante_da_pagina(origens: tuple[Any, ...], esperada: str) -> None:
    textos = [texto("A", (5.0, 5.0 + i, 9.0, 9.0 + i), o) for i, o in enumerate(origens)]

    assert origem_predominante(pagina_gramatica((), textos).modelo) == esperada


# --- marcas da página: preguiçosas e pagas uma vez --------------------------------------------


def _com_contornos() -> ContextoGramatica:
    return _contexto(
        [
            poligono(_vertices(32)),
            poligono(_vertices(32, centro=(200.0, 200.0))),
            circulo_bezier((50.0, 200.0), _RAIO),
        ]
    )


def test_marcas_nao_pagam_os_contornos_se_ninguem_pede() -> None:
    contexto = _com_contornos()
    antes = contexto.orcamento.gasto

    marcas = MarcasDaPagina(contexto)

    assert marcas.origem == "nativo"
    assert contexto.orcamento.gasto == antes


def test_marcas_pagam_os_contornos_uma_vez() -> None:
    contexto = _com_contornos()
    antes = contexto.orcamento.gasto
    marcas = MarcasDaPagina(contexto)

    contornos = marcas.contornos
    pago = contexto.orcamento.gasto - antes

    assert pago == 5
    assert marcas.contornos is contornos
    assert contexto.orcamento.gasto - antes == pago
    assert len(list(contornos.consultar((0.0, 0.0, 300.0, 300.0)))) == 3


def _haste_com_envolvente() -> PaginaGramatica:
    return pagina_desenhada(lambda p: desenhar_positivo(p, "cemig-eo-r3-s19-v002"))


def test_hastes_usam_as_marcas_recebidas() -> None:
    """Contornos já pagos pelas marcas não são pagos de novo pelas hastes."""
    sozinho = contexto_gramaticas(_haste_com_envolvente())
    antes = sozinho.orcamento.gasto
    [proprias] = hastes_candidatas(sozinho)
    gasto_sozinho = sozinho.orcamento.gasto - antes

    compartilhado = contexto_gramaticas(_haste_com_envolvente())
    inicio = compartilhado.orcamento.gasto
    marcas = MarcasDaPagina(compartilhado)
    assert marcas.contornos is not None
    assert compartilhado.orcamento.gasto > inicio
    [recebidas] = hastes_candidatas(compartilhado, marcas=marcas)

    assert compartilhado.orcamento.gasto - inicio == gasto_sozinho
    assert isinstance(recebidas.envolvente, Contorno)
    assert recebidas == proprias


def test_hastes_sem_haste_nao_pagam_os_contornos_das_marcas() -> None:
    contexto = _com_contornos()
    marcas = MarcasDaPagina(contexto)
    antes = contexto.orcamento.gasto

    assert hastes_candidatas(contexto, marcas=marcas) == ()
    gasto_com_marcas = contexto.orcamento.gasto - antes

    outro = _com_contornos()
    inicio = outro.orcamento.gasto
    assert hastes_candidatas(outro) == ()
    assert gasto_com_marcas == outro.orcamento.gasto - inicio
    assert marcas.contornos is not None
    assert contexto.orcamento.gasto - antes > gasto_com_marcas


# --- o gasto da haste não muda com a extração -------------------------------------------------


def _pares() -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [
        ({"family_id": "autoral"}, {"id": v, "recognition": {"status": "enabled", "grammar": g}})
        for v, g in CASOS_HASTE
    ]


def _todas_as_variantes(pagina: pymupdf.Page) -> None:
    for i, (variante, _) in enumerate(CASOS_HASTE):
        centro = (40.0 + (i % 4) * 70.0, 60.0 + (i // 4) * 120.0)
        desenhar_positivo(pagina, variante, centro=centro, graus=15.0 * i)


def _poligonal_com_x(pagina: pymupdf.Page) -> None:
    desenhar_haste(pagina, ALTERNADAS, envolvente=True, contorno=CIRCULO_POLIGONAL, x=True)


def _so_contornos(pagina: pymupdf.Page) -> None:
    for k in range(3):
        cx = 60.0 + 80.0 * k
        vertices = [
            (cx + 10 * math.cos(2 * math.pi * i / 32), 150 + 10 * math.sin(2 * math.pi * i / 32))
            for i in range(32)
        ]
        pagina.draw_polyline([*vertices, vertices[0]], color=_PRETO, width=0.5)
    NEGATIVOS["glifo_e"](pagina)


@pytest.mark.parametrize(
    ("desenhar", "indices", "gramaticas"),
    [(_todas_as_variantes, 96, 319), (_poligonal_com_x, 47, 224), (_so_contornos, 107, 105)],
    ids=["oito-variantes", "poligonal-com-x", "contornos-sem-haste"],
)
def test_gasto_da_haste_e_o_medido_antes_da_extracao(
    desenhar: Callable[[pymupdf.Page], None], indices: int, gramaticas: int
) -> None:
    """Valores medidos antes de as marcas saírem de `grammar_stem`: a extração não muda o gasto."""
    gasto = gasto_por_fase(pagina_desenhada(desenhar), _pares())

    assert (gasto.colagem, gasto.indices, gasto.gramaticas) == (0, indices, gramaticas)
