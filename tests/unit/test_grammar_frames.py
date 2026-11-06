"""As 5 gramáticas de moldura sobre o modelo, nos pares positivo/quase-acerto do corpus."""

from __future__ import annotations

import ast
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    linha,
    pagina_gramatica,
    poligono,
    retangulo_traco,
    texto,
)

from zeny_project_handler.adapters.analysis.drawing_model import grammar_frames
from zeny_project_handler.adapters.analysis.drawing_model.grammar_frames import casa_moldura
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Caminho,
    Circulo,
    Cor,
    ItemCaminho,
    Ponto,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    Moldura,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)

QUADRADO: Caixa = (110.0, 110.0, 158.0, 158.0)
CAMARA: Caixa = (101.0, 115.0, 169.0, 149.0)
# Lado 50: 6% da área é 150, valor exato em ponto flutuante.
LADO_50: Caixa = (100.0, 100.0, 150.0, 150.0)
CINZA: Cor = (0.86, 0.86, 0.88)
VERMELHO: Cor = (0.7, 0.0, 0.0)

ROTULO: dict[str, Any] = {
    "kind": "label_in_frame",
    "frame": "rectangle",
    "label": "CT",
    "max_span": 72,
}
ROTULO_VAZIO: dict[str, Any] = {**ROTULO, "empty_interior": True}
ROTULO_ANINHADO: dict[str, Any] = {**ROTULO, "nested_frame": True, "inner_fill": "gray"}
TRIANGULO_VAZIO: dict[str, Any] = {
    "kind": "triangle_in_frame",
    "frame": "rectangle",
    "fill": "empty",
    "max_span": 72,
}
TRIANGULO_SOLIDO: dict[str, Any] = {**TRIANGULO_VAZIO, "fill": "solid"}
DIAGONAIS: dict[str, Any] = {
    "kind": "framed_diagonals",
    "frame": "rectangle",
    "min_diagonals": 2,
    "max_span": 72,
}
BARRA: dict[str, Any] = {
    "kind": "nested_rectangles_bar",
    "frame": "rectangle",
    "central_bar": True,
    "max_span": 72,
}
LOSANGO: dict[str, Any] = {
    "kind": "diamond_three_dots",
    "frame": "diamond",
    "dot_count": 3,
    "max_span": 72,
}


def _contexto(
    caminhos: Sequence[Caminho], textos: Sequence[TextoModelo] = (), **opcoes: Any
) -> ContextoGramatica:
    return contexto_gramaticas(pagina_gramatica(caminhos, textos, **opcoes))


def _moldura(contexto: ContextoGramatica, caixa: Caixa, caminho: int | None = None) -> Moldura:
    achadas = [
        moldura
        for moldura in contexto.molduras
        if moldura.caixa == caixa and (caminho is None or moldura.caminho == caminho)
    ]
    assert len(achadas) == 1, f"esperava 1 moldura em {caixa}: {contexto.molduras}"
    return achadas[0]


def _casa(
    gramatica: dict[str, Any],
    caixa: Caixa,
    caminhos: Sequence[Caminho],
    textos: Sequence[TextoModelo] = (),
) -> bool:
    contexto = _contexto(caminhos, textos)
    return casa_moldura(contexto, gramatica, _moldura(contexto, caixa))


def _cantos(caixa: Caixa) -> tuple[Ponto, Ponto, Ponto, Ponto]:
    x0, y0, x1, y1 = caixa
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _preenchido(caixa: Caixa, preenchimento: Cor | None = CINZA, ordem: int = 0) -> Caminho:
    return poligono(_cantos(caixa), ordem, preenchimento)


# --- moldura -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("caixa", "gramatica", "esperado"),
    [
        pytest.param((100.0, 100.0, 172.0, 150.0), ROTULO, True, id="lado-maior-no-max-span"),
        pytest.param((100.0, 100.0, 172.5, 150.0), ROTULO, False, id="acima-do-max-span"),
        pytest.param((100.0, 100.0, 110.0, 104.0), ROTULO, True, id="lado-minimo"),
        pytest.param((100.0, 100.0, 103.9, 103.9), ROTULO, False, id="lado-abaixo-de-4"),
        pytest.param((100.0, 100.0, 150.0, 120.0), ROTULO, True, id="aspecto-2-5"),
        pytest.param((100.0, 100.0, 151.0, 120.0), ROTULO, False, id="aspecto-acima-de-2-5"),
        pytest.param((100.0, 100.0, 120.0, 150.0), ROTULO, True, id="aspecto-1-sobre-2-5"),
        pytest.param(
            (100.0, 100.0, 120.0, 151.0), ROTULO, False, id="aspecto-abaixo-de-1-sobre-2-5"
        ),
        pytest.param(
            (100.0, 100.0, 140.0, 110.0),
            {**ROTULO, "max_aspect": 4},
            True,
            id="max-aspect-da-gramatica",
        ),
        pytest.param(
            (100.0, 100.0, 140.0, 120.0),
            {**ROTULO, "max_aspect": 1.5},
            False,
            id="max-aspect-menor-recusa",
        ),
        pytest.param((100.0, 100.0, 125.0, 120.0), DIAGONAIS, True, id="diagonais-aspecto-1-25"),
        pytest.param((100.0, 100.0, 126.0, 120.0), DIAGONAIS, False, id="diagonais-acima-de-1-25"),
        pytest.param((100.0, 100.0, 116.0, 120.0), DIAGONAIS, True, id="diagonais-aspecto-0-8"),
        pytest.param((100.0, 100.0, 115.0, 120.0), DIAGONAIS, False, id="diagonais-abaixo-de-0-8"),
    ],
)
def test_moldura_fora_dos_limites_de_tamanho(
    caixa: Caixa, gramatica: dict[str, Any], esperado: bool
) -> None:
    x0, y0, x1, y1 = caixa
    if gramatica["kind"] == "framed_diagonals":
        diagonais = [linha((x0, y0), (x1, y1), 1), linha((x1, y0), (x0, y1), 2)]
        assert _casa(gramatica, caixa, [retangulo_traco(caixa), *diagonais]) is esperado
    else:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        palavra = texto("CT", (cx - 1.0, cy - 1.0, cx + 1.0, cy + 1.0))
        assert _casa(gramatica, caixa, [retangulo_traco(caixa)], [palavra]) is esperado


def _oval(centro: Ponto, raio_x: float, raio_y: float) -> Caminho:
    """Elipse de 4 Béziers: o círculo unitário em escala."""
    cx, cy = centro
    unitario = circulo_bezier((0.0, 0.0), 1.0)
    itens = tuple(
        ItemCaminho("c", tuple((cx + x * raio_x, cy + y * raio_y) for x, y in item.pontos))
        for item in unitario.subcaminhos[0]
    )
    return Caminho((itens,), unitario.estilo, unitario.tipo, 0)


ASPECTOS_REDONDOS = [
    pytest.param(14.3, True, id="aspecto-1-43"),
    pytest.param(14.4, False, id="acima-de-1-43"),
    pytest.param(7.0, True, id="aspecto-0-7"),
    pytest.param(6.9, False, id="abaixo-de-0-7"),
]


@pytest.mark.parametrize(("raio_x", "esperado"), ASPECTOS_REDONDOS)
def test_elipse_usa_o_aspecto_de_forma_redonda(raio_x: float, esperado: bool) -> None:
    cx, cy, raio_y = 100.0, 100.0, 10.0
    caixa = (cx - raio_x, cy - raio_y, cx + raio_x, cy + raio_y)
    gramatica = {**ROTULO, "frame": "ellipse"}
    palavra = texto("CT", (97.0, 97.0, 103.0, 103.0))
    contexto = _contexto([_oval((cx, cy), raio_x, raio_y)], [palavra], primitivas=())
    assert casa_moldura(contexto, gramatica, _moldura(contexto, caixa)) is esperado


@pytest.mark.parametrize(("raio_x", "esperado"), ASPECTOS_REDONDOS)
def test_losango_usa_o_aspecto_de_forma_redonda(raio_x: float, esperado: bool) -> None:
    cx, cy, raio_y = 100.0, 100.0, 10.0
    caixa = (cx - raio_x, cy - raio_y, cx + raio_x, cy + raio_y)
    pontas = ((cx, cy - raio_y), (cx + raio_x, cy), (cx, cy + raio_y), (cx - raio_x, cy))
    pontos = [circulo_bezier((cx + dx, cy), 1.0, i + 1) for i, dx in enumerate((-2.0, 0.0, 2.0))]
    contexto = _contexto([poligono(pontas), *pontos], primitivas=())
    assert casa_moldura(contexto, LOSANGO, _moldura(contexto, caixa)) is esperado


def test_forma_diferente_nao_casa() -> None:
    palavra = texto("CT", (118.0, 128.0, 150.0, 140.0))
    assert not _casa(ROTULO, QUADRADO, [circulo_bezier((134.0, 134.0), 24.0)], [palavra])
    assert not _casa(
        {**ROTULO, "frame": "ellipse"}, QUADRADO, [retangulo_traco(QUADRADO)], [palavra]
    )


@pytest.mark.parametrize("gramatica", [{"kind": "terminal_disc"}, {"kind": "outra"}, {}], ids=str)
def test_kind_desconhecido_levanta(gramatica: dict[str, Any]) -> None:
    contexto = _contexto([retangulo_traco(QUADRADO)])
    with pytest.raises(ValueError, match="desconhecid"):
        casa_moldura(contexto, gramatica, contexto.molduras[0])


# --- rótulo --------------------------------------------------------------------------------


def test_rotulo_em_retangulo() -> None:
    palavra = texto("CT", (116.0, 130.0, 132.0, 141.0))
    assert _casa(ROTULO, QUADRADO, [retangulo_traco(QUADRADO)], [palavra])


def test_rotulo_em_elipse() -> None:
    gramatica = {**ROTULO, "frame": "ellipse", "label": "EC"}
    palavra = texto("EC", (116.0, 130.0, 132.0, 141.0))
    assert _casa(gramatica, QUADRADO, [circulo_bezier((134.0, 134.0), 24.0)], [palavra])


def test_rotulo_errado() -> None:
    palavra = texto("ZZ", (116.0, 130.0, 132.0, 141.0))
    assert not _casa(ROTULO, QUADRADO, [retangulo_traco(QUADRADO)], [palavra])


def test_rotulo_fora_da_moldura() -> None:
    palavra = texto("CT", (200.0, 130.0, 216.0, 141.0))
    assert not _casa(ROTULO, QUADRADO, [retangulo_traco(QUADRADO)], [palavra])


@pytest.mark.parametrize(
    "caixa",
    [
        pytest.param((111.0, 130.0, 132.0, 141.0), id="esquerda"),
        pytest.param((116.0, 111.0, 132.0, 141.0), id="topo"),
        pytest.param((116.0, 130.0, 157.0, 141.0), id="direita"),
        pytest.param((116.0, 130.0, 132.0, 157.0), id="base"),
    ],
)
def test_rotulo_que_toca_a_borda_nao_casa(caixa: Caixa) -> None:
    assert not _casa(ROTULO, QUADRADO, [retangulo_traco(QUADRADO)], [texto("CT", caixa)])


def test_rotulo_com_as_pontas_na_borda_da_caixa_interna_casa() -> None:
    """`Rect.contains(Point)` do motor é semiaberto; o núcleo é fechado, por decisão do plano."""
    caixa = (100.0, 100.0, 160.0, 140.0)  # inset de 2 pt
    palavra = texto("CT", (102.0, 102.0, 158.0, 138.0))
    assert _casa(ROTULO, caixa, [retangulo_traco(caixa)], [palavra])


@pytest.mark.parametrize(
    "caixa",
    [
        pytest.param((101.99, 102.0, 158.0, 138.0), id="esquerda"),
        pytest.param((102.0, 101.99, 158.0, 138.0), id="topo"),
        pytest.param((102.0, 102.0, 158.01, 138.0), id="direita"),
        pytest.param((102.0, 102.0, 158.0, 138.01), id="base"),
    ],
)
def test_rotulo_logo_alem_da_caixa_interna_nao_casa(caixa: Caixa) -> None:
    moldura = (100.0, 100.0, 160.0, 140.0)
    assert not _casa(ROTULO, moldura, [retangulo_traco(moldura)], [texto("CT", caixa)])


def test_rotulo_minusculo_casa() -> None:
    palavra = texto("ct", (116.0, 130.0, 132.0, 141.0))
    assert _casa(ROTULO, QUADRADO, [retangulo_traco(QUADRADO)], [palavra])


def test_rotulo_em_glifo_casa() -> None:
    palavra = texto("CT", (116.0, 130.0, 132.0, 141.0), origem="glifo")
    assert _casa(ROTULO, QUADRADO, [retangulo_traco(QUADRADO)], [palavra])


def test_rotulo_em_shx_casa() -> None:
    palavra = texto("CT", (116.0, 130.0, 132.0, 141.0), origem="shx")
    assert _casa(ROTULO, QUADRADO, [retangulo_traco(QUADRADO)], [palavra])


@pytest.mark.parametrize(
    "span",
    [
        pytest.param(texto("CT LONGO", (116.0, 130.0, 196.0, 141.0), origem="shx"), id="shx"),
        pytest.param(texto("CT LONGO", (116.0, 130.0, 196.0, 141.0), rotacao=90.0), id="girado"),
        pytest.param(
            texto("CT LONGO", (116.0, 130.0, 196.0, 141.0), origem="glifo", rotacao=90.0),
            id="glifo-girado",
        ),
        pytest.param(
            texto("CT LONGO", (116.0, 130.0, 196.0, 141.0), origem="glifo"), id="glifo-horizontal"
        ),
        pytest.param(
            texto("LONGO CT", (116.0, 130.0, 196.0, 141.0), origem="glifo"),
            id="glifo-rotulo-no-fim",
        ),
        pytest.param(texto("CT LONGO", (116.0, 130.0, 196.0, 141.0)), id="nativo-horizontal"),
        pytest.param(texto("LONGO CT", (116.0, 130.0, 196.0, 141.0)), id="nativo-rotulo-no-fim"),
        pytest.param(texto("ct      ", (116.0, 130.0, 196.0, 141.0)), id="nativo-com-espacos"),
        pytest.param(texto("   ", (116.0, 130.0, 132.0, 141.0)), id="so-espacos"),
    ],
)
def test_rotulo_em_span_que_cruza_a_moldura_falha_fechado(span: TextoModelo) -> None:
    """A caixa da palavra é a do span (R-4): a parte dele fora da caixa interna recusa."""
    assert not _casa(ROTULO, QUADRADO, [retangulo_traco(QUADRADO)], [span])


def test_rotulo_com_espacos_nas_pontas_e_span_inteiro_dentro_casa() -> None:
    espacado = texto("  ct  ", (116.0, 130.0, 150.0, 141.0))
    inteiro = texto("CT LONGO", (116.0, 130.0, 150.0, 141.0), origem="shx")
    em_glifo = texto("CT LONGO", (116.0, 130.0, 150.0, 141.0), origem="glifo")
    assert _casa(ROTULO, QUADRADO, [retangulo_traco(QUADRADO)], [espacado])
    assert _casa(ROTULO, QUADRADO, [retangulo_traco(QUADRADO)], [inteiro])
    assert _casa(ROTULO, QUADRADO, [retangulo_traco(QUADRADO)], [em_glifo])


# --- interior vazio ------------------------------------------------------------------------


def test_empty_interior_recusa_marca_preenchida() -> None:
    palavra = texto("CT", (107.0, 130.0, 123.0, 141.0))
    marca = poligono(((136.0, 116.0), (168.0, 116.0), (168.0, 148.0)), 1, VERMELHO)
    assert not _casa(ROTULO_VAZIO, CAMARA, [retangulo_traco(CAMARA), marca], [palavra])


@pytest.mark.parametrize(
    ("marca", "recusa"),
    [
        pytest.param((120.0, 105.0, 135.0, 115.0), True, id="exatos-6-por-cento"),
        pytest.param((120.0, 105.0, 134.9, 115.0), False, id="abaixo-de-6-por-cento"),
    ],
)
def test_empty_interior_mede_a_marca_em_6_por_cento_da_area(marca: Caixa, recusa: bool) -> None:
    palavra = texto("CT", (105.0, 130.0, 118.0, 140.0))
    caminhos = [retangulo_traco(LADO_50), _preenchido(marca, VERMELHO, 1)]
    assert _casa(ROTULO_VAZIO, LADO_50, caminhos, [palavra]) is not recusa


def test_empty_interior_aceita_marca_que_nao_cabe_na_moldura() -> None:
    palavra = texto("CT", (105.0, 130.0, 118.0, 140.0))
    caminhos = [retangulo_traco(LADO_50), _preenchido((120.0, 105.0, 170.0, 145.0), VERMELHO, 1)]
    assert _casa(ROTULO_VAZIO, LADO_50, caminhos, [palavra])


def test_empty_interior_ignora_marca_sem_preenchimento() -> None:
    palavra = texto("CT", (105.0, 130.0, 118.0, 140.0))
    caminhos = [retangulo_traco(LADO_50), _preenchido((120.0, 105.0, 145.0, 125.0), None, 1)]
    assert _casa(ROTULO_VAZIO, LADO_50, caminhos, [palavra])


def test_empty_interior_recusa_diagonal_longa() -> None:
    palavra = texto("CT", (107.0, 130.0, 123.0, 141.0))
    caminhos = [retangulo_traco(CAMARA), linha((101.0, 115.0), (169.0, 149.0), 1)]
    assert not _casa(ROTULO_VAZIO, CAMARA, caminhos, [palavra])


@pytest.mark.parametrize(
    ("fim", "recusa"),
    [
        pytest.param((133.0, 133.0), True, id="acima-de-55-por-cento"),
        pytest.param((132.4, 133.0), False, id="x-abaixo-de-55-por-cento"),
        pytest.param((133.0, 132.4), False, id="y-abaixo-de-55-por-cento"),
    ],
)
def test_empty_interior_exige_55_por_cento_nos_dois_eixos(fim: Ponto, recusa: bool) -> None:
    palavra = texto("CT", (105.0, 135.0, 118.0, 145.0))
    caminhos = [retangulo_traco(LADO_50), linha((105.0, 105.0), fim, 1)]
    assert _casa(ROTULO_VAZIO, LADO_50, caminhos, [palavra]) is not recusa


def test_empty_interior_aceita_marca_pequena() -> None:
    palavra = texto("CT", (107.0, 130.0, 123.0, 141.0))
    caminhos = [
        retangulo_traco(CAMARA),
        linha((143.0, 130.0), (149.0, 130.0), 1, cor=(1.0, 0.4, 1.0)),
        linha((146.0, 127.0), (146.0, 133.0), 2, cor=(1.0, 0.4, 1.0)),
    ]
    assert _casa(ROTULO_VAZIO, CAMARA, caminhos, [palavra])


def test_empty_interior_com_externa_de_traco_e_preenchimento() -> None:
    """Cada caminho é moldura própria (R-10): o preenchimento marca a de traço, não a si mesmo."""
    palavra = texto("CT", (105.0, 130.0, 118.0, 140.0))
    caminhos = [retangulo_traco(LADO_50), _preenchido(LADO_50, CINZA, 1)]
    contexto = _contexto(caminhos, [palavra])
    assert not casa_moldura(contexto, ROTULO_VAZIO, _moldura(contexto, LADO_50, 0))
    assert casa_moldura(contexto, ROTULO_VAZIO, _moldura(contexto, LADO_50, 1))


def test_empty_interior_aceita_linha_longa_que_so_encosta_no_canto() -> None:
    palavra = texto("CT", (105.0, 130.0, 118.0, 140.0))
    caminhos = [retangulo_traco(LADO_50), linha((150.0, 150.0), (200.0, 200.0), 1)]
    assert _casa(ROTULO_VAZIO, LADO_50, caminhos, [palavra])


def test_empty_interior_julga_a_caixa_da_linha_e_nao_a_do_caminho() -> None:
    """O caminho cruza a moldura por outro subcaminho, e a linha longa fica toda fora dela."""
    palavra = texto("CT", (105.0, 130.0, 118.0, 140.0))
    longa = ItemCaminho("l", ((160.0, 160.0), (210.0, 210.0)))
    curta = ItemCaminho("l", ((140.0, 140.0), (145.0, 145.0)))
    base = linha((0.0, 0.0), (1.0, 1.0), 1)
    caminho = Caminho(((longa,), (curta,)), base.estilo, base.tipo, 1)
    assert _casa(ROTULO_VAZIO, LADO_50, [retangulo_traco(LADO_50), caminho], [palavra])


def test_empty_interior_ignora_curva_longa() -> None:
    """O motor só mede os `l`: uma Bézier de corda longa no interior não é marca."""
    palavra = texto("CT", (105.0, 135.0, 118.0, 145.0))
    a, b = (105.0, 105.0), (145.0, 145.0)
    base = linha(a, b, 1)
    curva = Caminho(((ItemCaminho("c", (a, a, b, b)),),), base.estilo, base.tipo, 1)
    assert _casa(ROTULO_VAZIO, LADO_50, [retangulo_traco(LADO_50), curva], [palavra])


def test_empty_interior_cobra_os_itens_do_caminho_no_orcamento() -> None:
    """Um caminho denso não pode ser varrido de graça por moldura: custaria O(F·itens)."""
    itens = tuple(ItemCaminho("l", ((120.0, 120.0), (121.0, 121.0))) for _ in range(1000))
    base = linha((0.0, 0.0), (1.0, 1.0), 1)
    denso = Caminho((itens,), base.estilo, base.tipo, 1)
    palavra = texto("CT", (105.0, 130.0, 118.0, 140.0))
    contexto = _contexto([retangulo_traco(LADO_50), denso], [palavra], primitivas=())
    antes = contexto.orcamento.gasto
    assert casa_moldura(contexto, ROTULO_VAZIO, _moldura(contexto, LADO_50))
    assert contexto.orcamento.gasto - antes >= len(itens)


def test_empty_interior_nao_cobra_os_itens_de_caminho_que_nao_cruza_a_moldura() -> None:
    """Na célula vizinha, a grade devolve o caminho; a caixa dele já basta para descartá-lo."""
    itens = tuple(ItemCaminho("l", ((152.0, 120.0), (153.0, 121.0))) for _ in range(1000))
    base = linha((0.0, 0.0), (1.0, 1.0), 1)
    vizinho = Caminho((itens,), base.estilo, base.tipo, 1)
    palavra = texto("CT", (105.0, 130.0, 118.0, 140.0))
    contexto = _contexto([retangulo_traco(LADO_50), vizinho], [palavra], primitivas=())
    antes = contexto.orcamento.gasto
    assert casa_moldura(contexto, ROTULO_VAZIO, _moldura(contexto, LADO_50))
    assert contexto.orcamento.gasto - antes < len(itens)


def test_moldura_de_caminho_sem_caixa_nao_quebra() -> None:
    """Um subcaminho `nan` tira o caminho de `caixas_caminhos`, mas a moldura dele continua."""
    moldura = retangulo_traco(QUADRADO)
    nan = ItemCaminho("l", ((math.nan, 0.0), (1.0, 1.0)))
    caminho = Caminho((*moldura.subcaminhos, (nan,)), moldura.estilo, moldura.tipo, 0)
    palavra = texto("CT", (116.0, 130.0, 132.0, 141.0))
    contexto = _contexto([caminho], [palavra], primitivas=())
    assert 0 not in contexto.caixas_caminhos
    alvo = _moldura(contexto, QUADRADO)
    assert casa_moldura(contexto, ROTULO_VAZIO, alvo)
    assert not casa_moldura(contexto, ROTULO_ANINHADO, alvo)
    assert not casa_moldura(contexto, TRIANGULO_VAZIO, alvo)
    assert not casa_moldura(contexto, DIAGONAIS, alvo)
    assert not casa_moldura(contexto, BARRA, alvo)


# --- moldura interna cinza -----------------------------------------------------------------

EXTERNA: Caixa = (108.0, 108.0, 168.0, 168.0)
INTERNA: Caixa = (114.0, 114.0, 162.0, 162.0)
PALAVRA_INTERNA = texto("CT", (119.0, 133.0, 140.0, 144.0))


def test_moldura_interna_cinza() -> None:
    caminhos = [retangulo_traco(EXTERNA), _preenchido(INTERNA, CINZA, 1)]
    assert _casa(ROTULO_ANINHADO, EXTERNA, caminhos, [PALAVRA_INTERNA])


def test_moldura_interna_sem_preenchimento_nao_casa() -> None:
    caminhos = [retangulo_traco(EXTERNA), _preenchido(INTERNA, None, 1)]
    assert not _casa(ROTULO_ANINHADO, EXTERNA, caminhos, [PALAVRA_INTERNA])


def test_moldura_interna_colorida_nao_casa() -> None:
    caminhos = [retangulo_traco(EXTERNA), _preenchido(INTERNA, (0.9, 0.2, 0.2), 1)]
    assert not _casa(ROTULO_ANINHADO, EXTERNA, caminhos, [PALAVRA_INTERNA])


def test_moldura_interna_descentrada_nao_casa() -> None:
    interna = (110.0, 110.0, 158.0, 158.0)  # desvio de 8 pt acima de 10% de 60
    caminhos = [retangulo_traco(EXTERNA), _preenchido(interna, CINZA, 1)]
    assert not _casa(ROTULO_ANINHADO, EXTERNA, caminhos, [PALAVRA_INTERNA])


@pytest.mark.parametrize(
    ("interna", "esperado"),
    [
        pytest.param((117.5, 117.5, 182.5, 182.5), True, id="razao-0-65"),
        pytest.param((118.0, 118.0, 182.0, 182.0), False, id="razao-abaixo-de-0-65"),
        pytest.param((101.0, 101.0, 199.0, 199.0), True, id="razao-0-98"),
        pytest.param((100.5, 100.5, 199.5, 199.5), False, id="razao-acima-de-0-98"),
        pytest.param((115.0, 110.0, 195.0, 190.0), True, id="desvio-horizontal-de-10-por-cento"),
        pytest.param((115.5, 110.0, 195.5, 190.0), False, id="desvio-horizontal-acima"),
        pytest.param((110.0, 115.0, 190.0, 195.0), True, id="desvio-vertical-de-10-por-cento"),
        pytest.param((110.0, 115.5, 190.0, 195.5), False, id="desvio-vertical-acima"),
        pytest.param((110.0, 110.0, 190.0, 201.0), False, id="nao-cabe"),
    ],
)
def test_moldura_interna_limites_de_razao_e_de_centro(interna: Caixa, esperado: bool) -> None:
    externa = (100.0, 100.0, 200.0, 200.0)
    gramatica = {**ROTULO_ANINHADO, "max_span": 100}
    palavra = texto("CT", (125.0, 140.0, 165.0, 160.0))
    caminhos = [retangulo_traco(externa), _preenchido(interna, CINZA, 1)]
    assert _casa(gramatica, externa, caminhos, [palavra]) is esperado


@pytest.mark.parametrize(
    ("cor", "esperado"),
    [
        pytest.param((0.15, 0.15, 0.15), True, id="canal-minimo"),
        pytest.param((0.14, 0.15, 0.15), False, id="canal-abaixo"),
        pytest.param((0.9, 0.9, 0.9), True, id="canal-maximo"),
        pytest.param((0.9, 0.9, 0.91), False, id="canal-acima"),
        pytest.param((0.5, 0.5, 0.6), True, id="amplitude-dentro"),
        pytest.param((0.5, 0.5, 0.63), False, id="amplitude-acima"),
        pytest.param((math.nan, 0.5, 0.5), False, id="canal-nan"),
    ],
)
def test_moldura_interna_o_que_e_cinza(cor: Cor, esperado: bool) -> None:
    caminhos = [retangulo_traco(EXTERNA), _preenchido(INTERNA, cor, 1)]
    assert _casa(ROTULO_ANINHADO, EXTERNA, caminhos, [PALAVRA_INTERNA]) is esperado


def test_moldura_interna_cinza_pintada_em_dois_caminhos() -> None:
    """Traço e depois preenchimento na mesma caixa: o segundo caminho é a moldura cinza (R-10)."""
    caminhos = [
        retangulo_traco(EXTERNA),
        retangulo_traco(INTERNA, 1),
        _preenchido(INTERNA, CINZA, 2),
    ]
    assert _casa(ROTULO_ANINHADO, EXTERNA, caminhos, [PALAVRA_INTERNA])


def test_moldura_interna_do_mesmo_caminho_nao_conta() -> None:
    externa = retangulo_traco(EXTERNA)
    interna = _preenchido(INTERNA, CINZA)
    caminho = Caminho((*externa.subcaminhos, *interna.subcaminhos), interna.estilo, interna.tipo, 0)
    contexto = _contexto([caminho], [PALAVRA_INTERNA], primitivas=())
    assert not casa_moldura(contexto, ROTULO_ANINHADO, _moldura(contexto, EXTERNA))


def test_moldura_interna_exige_o_rotulo_nela() -> None:
    """A palavra cabe na externa, mas sai da interna."""
    palavra = texto("CT", (112.0, 133.0, 125.0, 144.0))
    caminhos = [retangulo_traco(EXTERNA), _preenchido(INTERNA, CINZA, 1)]
    assert _casa(ROTULO, EXTERNA, caminhos, [palavra])
    assert not _casa(ROTULO_ANINHADO, EXTERNA, caminhos, [palavra])


def test_moldura_interna_elipse_nao_conta() -> None:
    elipse = circulo_bezier((138.0, 138.0), 24.0, 1, preenchimento=CINZA)
    caminhos = [retangulo_traco(EXTERNA), elipse]
    assert not _casa(ROTULO_ANINHADO, EXTERNA, caminhos, [PALAVRA_INTERNA])


# --- triângulo -----------------------------------------------------------------------------

PONTAS_TRIANGULO = ((134.0, 112.0), (156.0, 156.0), (112.0, 156.0))


def test_triangulo_vazio_e_solido() -> None:
    moldura = retangulo_traco(QUADRADO)
    assert _casa(TRIANGULO_VAZIO, QUADRADO, [moldura, poligono(PONTAS_TRIANGULO, 1)])
    solido = poligono(PONTAS_TRIANGULO, 1, VERMELHO)
    assert _casa(TRIANGULO_SOLIDO, QUADRADO, [moldura, solido])


def test_triangulo_de_preenchimento_trocado() -> None:
    moldura = retangulo_traco(QUADRADO)
    assert not _casa(TRIANGULO_SOLIDO, QUADRADO, [moldura, poligono(PONTAS_TRIANGULO, 1)])
    solido = poligono(PONTAS_TRIANGULO, 1, VERMELHO)
    assert not _casa(TRIANGULO_VAZIO, QUADRADO, [moldura, solido])


def test_triangulo_com_pontas_que_o_arredondamento_afasta_da_caixa_casa() -> None:
    """A forma é julgada em 2 casas, e a caixa do caminho não é arredondada."""
    pontas = ((134.0, 112.004), (156.004, 156.004), (112.004, 156.004))
    assert _casa(TRIANGULO_VAZIO, QUADRADO, [retangulo_traco(QUADRADO), poligono(pontas, 1)])


def test_triangulo_pequeno_nao_casa() -> None:
    pontas = ((134.0, 125.0), (142.0, 141.0), (126.0, 141.0))
    assert not _casa(TRIANGULO_VAZIO, QUADRADO, [retangulo_traco(QUADRADO), poligono(pontas, 1)])


def test_triangulo_invertido_nao_casa() -> None:
    """Julgado no espaço visual (R-7): y cresce para baixo, e a ponta para baixo não casa."""
    pontas = ((112.0, 112.0), (156.0, 112.0), (134.0, 156.0))
    assert not _casa(TRIANGULO_VAZIO, QUADRADO, [retangulo_traco(QUADRADO), poligono(pontas, 1)])


def test_triangulo_fora_da_moldura_nao_casa() -> None:
    pontas = ((134.0, 100.0), (156.0, 156.0), (112.0, 156.0))
    assert not _casa(TRIANGULO_VAZIO, QUADRADO, [retangulo_traco(QUADRADO), poligono(pontas, 1)])


GRANDE: Caixa = (95.0, 95.0, 215.0, 215.0)


@pytest.mark.parametrize(
    ("pontas", "esperado"),
    [
        pytest.param(
            ((168.0, 100.0), (200.0, 200.0), (100.0, 200.0)), True, id="topo-a-18-por-cento"
        ),
        pytest.param(
            ((168.5, 100.0), (200.0, 200.0), (100.0, 200.0)), False, id="topo-alem-de-18-por-cento"
        ),
        pytest.param(
            ((150.0, 100.0), (200.0, 200.0), (100.0, 185.0)), True, id="base-a-15-por-cento"
        ),
        pytest.param(
            ((150.0, 100.0), (200.0, 200.0), (100.0, 184.5)), False, id="base-alem-de-15-por-cento"
        ),
    ],
)
def test_triangulo_limites_de_forma(pontas: tuple[Ponto, Ponto, Ponto], esperado: bool) -> None:
    caminhos = [retangulo_traco(GRANDE), poligono(pontas, 1)]
    assert _casa({**TRIANGULO_VAZIO, "max_span": 120}, GRANDE, caminhos) is esperado


@pytest.mark.parametrize(
    ("pontas", "esperado"),
    [
        pytest.param(
            ((134.0, 134.0), (158.0, 158.0), (110.0, 158.0)), True, id="metade-da-moldura"
        ),
        pytest.param(((134.0, 134.1), (158.0, 158.0), (110.0, 158.0)), False, id="altura-menor"),
        pytest.param(((134.0, 134.0), (146.0, 158.0), (122.0, 158.0)), True, id="largura-metade"),
        pytest.param(((134.0, 134.0), (145.9, 158.0), (122.0, 158.0)), False, id="largura-menor"),
    ],
)
def test_triangulo_cobre_metade_da_moldura(
    pontas: tuple[Ponto, Ponto, Ponto], esperado: bool
) -> None:
    caminhos = [retangulo_traco(QUADRADO), poligono(pontas, 1)]
    assert _casa(TRIANGULO_VAZIO, QUADRADO, caminhos) is esperado


def test_triangulo_em_dois_subcaminhos_nao_casa() -> None:
    triangulo = poligono(PONTAS_TRIANGULO, 1)
    itens = triangulo.subcaminhos[0]
    repartido = Caminho(((itens[0],), itens[1:]), triangulo.estilo, triangulo.tipo, 1)
    assert not _casa(TRIANGULO_VAZIO, QUADRADO, [retangulo_traco(QUADRADO), repartido])


def test_triangulo_com_outro_subcaminho_nao_casa() -> None:
    triangulo = poligono(PONTAS_TRIANGULO, 1)
    extra = (ItemCaminho("l", ((130.0, 140.0), (131.0, 141.0))),)
    caminho = Caminho((*triangulo.subcaminhos, extra), triangulo.estilo, triangulo.tipo, 1)
    assert not _casa(TRIANGULO_VAZIO, QUADRADO, [retangulo_traco(QUADRADO), caminho])


def test_triangulo_que_nao_fecha_nao_casa() -> None:
    """Três lados soltos têm mais de 3 pontas distintas."""
    a, b, c = PONTAS_TRIANGULO
    base = poligono(PONTAS_TRIANGULO, 1)
    aberto = (
        ItemCaminho("l", (a, b)),
        ItemCaminho("l", (b, c)),
        ItemCaminho("l", (c, (120.0, 130.0))),
    )
    caminho = Caminho((aberto,), base.estilo, base.tipo, 1)
    assert not _casa(TRIANGULO_VAZIO, QUADRADO, [retangulo_traco(QUADRADO), caminho])


def test_tres_curvas_nao_sao_triangulo() -> None:
    base = poligono(PONTAS_TRIANGULO, 1)
    curvas = tuple(
        ItemCaminho("c", (item.pontos[0], item.pontos[0], item.pontos[1], item.pontos[1]))
        for item in base.subcaminhos[0]
    )
    caminho = Caminho((curvas,), base.estilo, base.tipo, 1)
    assert not _casa(TRIANGULO_VAZIO, QUADRADO, [retangulo_traco(QUADRADO), caminho])


def test_quadrilatero_nao_e_triangulo() -> None:
    pontas = ((134.0, 112.0), (156.0, 156.0), (134.0, 150.0), (112.0, 156.0))
    assert not _casa(TRIANGULO_VAZIO, QUADRADO, [retangulo_traco(QUADRADO), poligono(pontas, 1)])


# --- diagonais -----------------------------------------------------------------------------

X_NO_QUADRADO = (
    linha((111.0, 111.0), (157.0, 157.0), 1),
    linha((157.0, 111.0), (111.0, 157.0), 2),
)


def test_duas_diagonais() -> None:
    assert _casa(DIAGONAIS, QUADRADO, [retangulo_traco(QUADRADO), *X_NO_QUADRADO])


def test_diagonais_em_sentido_contrario_casam() -> None:
    caminhos = [
        retangulo_traco(QUADRADO),
        linha((157.0, 157.0), (111.0, 111.0), 1),
        linha((111.0, 157.0), (157.0, 111.0), 2),
    ]
    assert _casa(DIAGONAIS, QUADRADO, caminhos)


def test_uma_diagonal() -> None:
    assert not _casa(DIAGONAIS, QUADRADO, [retangulo_traco(QUADRADO), X_NO_QUADRADO[0]])


def test_a_mesma_diagonal_duas_vezes_conta_uma() -> None:
    caminhos = [
        retangulo_traco(QUADRADO),
        X_NO_QUADRADO[0],
        linha((157.0, 157.0), (111.0, 111.0), 2),
    ]
    assert not _casa(DIAGONAIS, QUADRADO, caminhos)


def test_diagonais_no_mesmo_caminho_casam() -> None:
    primeira, segunda = (caminho.subcaminhos[0] for caminho in X_NO_QUADRADO)
    base = X_NO_QUADRADO[0]
    xis = Caminho((primeira, segunda), base.estilo, base.tipo, 1)
    assert _casa(DIAGONAIS, QUADRADO, [retangulo_traco(QUADRADO), xis])


@pytest.mark.parametrize(
    ("caixa", "folga", "esperado"),
    [
        pytest.param(QUADRADO, 4.0, True, id="dentro-de-12-por-cento"),
        pytest.param(QUADRADO, 4.1, False, id="alem-de-12-por-cento"),
        pytest.param((100.0, 100.0, 106.0, 106.0), 1.0, True, id="dentro-do-piso-de-1-5"),
        pytest.param((100.0, 100.0, 106.0, 106.0), 1.1, False, id="alem-do-piso-de-1-5"),
    ],
)
def test_diagonais_tolerancia_nos_cantos(caixa: Caixa, folga: float, esperado: bool) -> None:
    x0, y0, x1, y1 = caixa
    caminhos = [
        retangulo_traco(caixa),
        linha((x0 + folga, y0 + folga), (x1 - folga, y1 - folga), 1),
        linha((x1, y0), (x0, y1), 2),
    ]
    assert _casa(DIAGONAIS, caixa, caminhos) is esperado


def test_diagonais_com_texto() -> None:
    palavra = texto("CT", (116.0, 130.0, 132.0, 141.0))
    assert not _casa(DIAGONAIS, QUADRADO, [retangulo_traco(QUADRADO), *X_NO_QUADRADO], [palavra])


def test_diagonais_com_centro_da_palavra_na_borda_recusa() -> None:
    """`Rect.contains(Point)` do motor é semiaberto; o núcleo é fechado, por decisão do plano."""
    palavra = texto("AB", (150.0, 130.0, 166.0, 140.0))
    assert not _casa(DIAGONAIS, QUADRADO, [retangulo_traco(QUADRADO), *X_NO_QUADRADO], [palavra])


def test_diagonais_com_centro_da_palavra_logo_alem_da_borda_casa() -> None:
    palavra = texto("AB", (150.1, 130.0, 166.1, 140.0))
    assert _casa(DIAGONAIS, QUADRADO, [retangulo_traco(QUADRADO), *X_NO_QUADRADO], [palavra])


def test_diagonais_com_span_inteiro_que_cruza_recusa() -> None:
    """Palavra `inteira` recusa pela interseção (R-4), mesmo com o centro fora da moldura."""
    span = texto("AB CD", (90.0, 120.0, 125.0, 130.0), origem="shx")
    assert not _casa(DIAGONAIS, QUADRADO, [retangulo_traco(QUADRADO), *X_NO_QUADRADO], [span])


def test_diagonais_com_palavra_unica_do_mesmo_tamanho_casa() -> None:
    """A mesma caixa em palavra que não é `inteira` é julgada pelo centro, como no motor."""
    palavra = texto("ABCD", (90.0, 120.0, 125.0, 130.0), origem="shx")
    assert _casa(DIAGONAIS, QUADRADO, [retangulo_traco(QUADRADO), *X_NO_QUADRADO], [palavra])


@pytest.mark.parametrize("origem", ["nativo", "shx", "glifo"])
@pytest.mark.parametrize("cru", ["AB CDE", "ABCDE "], ids=["varias-palavras", "espaco-no-fim"])
def test_diagonais_com_span_que_cruza_recusa(cru: str, origem: Any) -> None:
    """O centro do span fica fora, e a caixa real da palavra não é conhecida (R-4)."""
    span = texto(cru, (90.0, 120.0, 111.0, 130.0), origem=origem)
    assert not _casa(DIAGONAIS, QUADRADO, [retangulo_traco(QUADRADO), *X_NO_QUADRADO], [span])


@pytest.mark.parametrize("origem", ["nativo", "shx", "glifo"])
def test_diagonais_com_span_que_e_exatamente_a_palavra_julga_o_centro(origem: Any) -> None:
    palavra = texto("ABCDEF", (90.0, 120.0, 111.0, 130.0), origem=origem)
    assert _casa(DIAGONAIS, QUADRADO, [retangulo_traco(QUADRADO), *X_NO_QUADRADO], [palavra])


def test_diagonais_com_span_inteiro_que_so_encosta_casa() -> None:
    span = texto("AB CD", (90.0, 120.0, 110.0, 130.0), origem="shx")
    assert _casa(DIAGONAIS, QUADRADO, [retangulo_traco(QUADRADO), *X_NO_QUADRADO], [span])


def test_diagonais_com_span_inteiro_de_caixa_achatada_dentro_recusa() -> None:
    """Sem área, a caixa não intersecta nada; o centro dentro mantém a guarda fechada."""
    span = texto("AB CD", (120.0, 130.0, 150.0, 130.0), origem="shx")
    assert not _casa(DIAGONAIS, QUADRADO, [retangulo_traco(QUADRADO), *X_NO_QUADRADO], [span])


# --- retângulos com barra ------------------------------------------------------------------

INTERNA_BARRA: Caixa = (118.0, 118.0, 150.0, 150.0)
BARRA_CENTRAL = linha((119.0, 134.0), (149.0, 134.0), 2)


def test_retangulos_com_barra() -> None:
    caminhos = [retangulo_traco(QUADRADO), retangulo_traco(INTERNA_BARRA, 1), BARRA_CENTRAL]
    assert _casa(BARRA, QUADRADO, caminhos)


def test_sem_interno() -> None:
    assert not _casa(BARRA, QUADRADO, [retangulo_traco(QUADRADO), BARRA_CENTRAL])


def test_sem_barra() -> None:
    assert not _casa(
        BARRA, QUADRADO, [retangulo_traco(QUADRADO), retangulo_traco(INTERNA_BARRA, 1)]
    )


def test_barra_de_outro_retangulo_nao_conta() -> None:
    vizinho: Caixa = (210.0, 110.0, 258.0, 158.0)
    caminhos = [
        retangulo_traco(QUADRADO),
        retangulo_traco(INTERNA_BARRA, 1),
        retangulo_traco(vizinho, 2),
        retangulo_traco((218.0, 118.0, 250.0, 150.0), 3),
        linha((219.0, 134.0), (249.0, 134.0), 4),
    ]
    contexto = _contexto(caminhos)
    assert not casa_moldura(contexto, BARRA, _moldura(contexto, QUADRADO))
    assert casa_moldura(contexto, BARRA, _moldura(contexto, vizinho))


def test_barra_vertical_nao_conta() -> None:
    """A barra é horizontal no espaço visual (R-7)."""
    caminhos = [
        retangulo_traco(QUADRADO),
        retangulo_traco(INTERNA_BARRA, 1),
        linha((134.0, 119.0), (134.0, 149.0), 2),
    ]
    assert not _casa(BARRA, QUADRADO, caminhos)


@pytest.mark.parametrize(
    ("a", "b", "esperado"),
    [
        pytest.param((110.0, 150.0), (140.0, 150.0), True, id="60-por-cento-da-interna"),
        pytest.param((110.0, 150.0), (139.9, 150.0), False, id="curta"),
        pytest.param((110.0, 156.0), (140.0, 156.0), True, id="a-12-por-cento-do-meio"),
        pytest.param((110.0, 156.5), (140.0, 156.5), False, id="alem-de-12-por-cento"),
        pytest.param((110.0, 150.0), (140.0, 156.5), False, id="fim-alem-de-12-por-cento"),
        pytest.param((110.0, 156.5), (140.0, 150.0), False, id="inicio-alem-de-12-por-cento"),
        pytest.param((99.0, 150.0), (201.0, 150.0), True, id="folga-de-1-pt-na-externa"),
        pytest.param((98.9, 150.0), (140.0, 150.0), False, id="sai-pela-esquerda"),
        pytest.param((110.0, 150.0), (201.1, 150.0), False, id="sai-pela-direita"),
    ],
)
def test_barra_limites(a: Ponto, b: Ponto, esperado: bool) -> None:
    externa: Caixa = (100.0, 100.0, 200.0, 200.0)
    interna: Caixa = (125.0, 125.0, 175.0, 175.0)
    caminhos = [retangulo_traco(externa), retangulo_traco(interna, 1), linha(a, b, 2)]
    assert _casa({**BARRA, "max_span": 100}, externa, caminhos) is esperado


@pytest.mark.parametrize(
    ("interna", "esperado"),
    [
        pytest.param((127.5, 127.5, 172.5, 172.5), True, id="razao-0-45"),
        pytest.param((128.0, 128.0, 172.0, 172.0), False, id="razao-abaixo-de-0-45"),
        pytest.param((107.5, 107.5, 192.5, 192.5), True, id="razao-0-85"),
        pytest.param((107.0, 107.0, 193.0, 193.0), False, id="razao-acima-de-0-85"),
        pytest.param((123.0, 115.0, 193.0, 185.0), True, id="desvio-horizontal-de-16-por-cento"),
        pytest.param((123.5, 115.0, 193.5, 185.0), False, id="desvio-horizontal-acima"),
        pytest.param((115.0, 123.0, 185.0, 193.0), True, id="desvio-vertical-de-16-por-cento"),
        pytest.param((115.0, 123.5, 185.0, 193.5), False, id="desvio-vertical-acima"),
    ],
)
def test_barra_limites_da_interna(interna: Caixa, esperado: bool) -> None:
    externa: Caixa = (100.0, 100.0, 200.0, 200.0)
    meio = (interna[1] + interna[3]) / 2
    caminhos = [
        retangulo_traco(externa),
        retangulo_traco(interna, 1),
        linha((interna[0], meio), (interna[2], meio), 2),
    ]
    assert _casa({**BARRA, "max_span": 100}, externa, caminhos) is esperado


def test_barra_com_interno_de_outra_forma_nao_casa() -> None:
    caminhos = [
        retangulo_traco(QUADRADO),
        circulo_bezier((134.0, 134.0), 16.0, 1),
        BARRA_CENTRAL,
    ]
    assert not _casa(BARRA, QUADRADO, caminhos)


# --- losango com três pontos ---------------------------------------------------------------

CAIXA_LOSANGO: Caixa = (110.0, 110.0, 158.0, 158.0)
PONTAS_LOSANGO = ((134.0, 110.0), (158.0, 134.0), (134.0, 158.0), (110.0, 134.0))
PONTOS_DO_LOSANGO = ((126.0, 134.0), (134.0, 134.0), (142.0, 134.0))


def _caminhos_losango(centros: Sequence[Ponto], raio: float = 3.0) -> list[Caminho]:
    pontos = [circulo_bezier(centro, raio, i + 1) for i, centro in enumerate(centros)]
    return [poligono(PONTAS_LOSANGO), *pontos]


def test_losango_tres_pontos() -> None:
    assert _casa(LOSANGO, CAIXA_LOSANGO, _caminhos_losango(PONTOS_DO_LOSANGO))


def test_dois_pontos() -> None:
    assert not _casa(LOSANGO, CAIXA_LOSANGO, _caminhos_losango(PONTOS_DO_LOSANGO[:2]))


def test_quatro_pontos() -> None:
    centros = (*PONTOS_DO_LOSANGO, (134.0, 126.0))
    assert not _casa(LOSANGO, CAIXA_LOSANGO, _caminhos_losango(centros))


def test_ponto_fora_do_losango() -> None:
    """Dentro da caixa, mas além da borda inclinada do losango, o terceiro ponto não conta."""
    centros = (*PONTOS_DO_LOSANGO[:2], (152.0, 116.0))
    assert not _casa(LOSANGO, CAIXA_LOSANGO, _caminhos_losango(centros))


def test_retangulo_pequeno_nao_e_ponto() -> None:
    caminhos = [
        *_caminhos_losango(PONTOS_DO_LOSANGO[:2]),
        retangulo_traco((139.0, 131.0, 145.0, 137.0), 3),
    ]
    assert not _casa(LOSANGO, CAIXA_LOSANGO, caminhos)


def test_ponto_que_transborda_a_caixa_do_losango() -> None:
    """Centro perto da ponta e raio de 25% do lado: passa na distância, mas sai da caixa."""
    caminhos = [
        *_caminhos_losango(PONTOS_DO_LOSANGO[:2]),
        circulo_bezier((154.0, 134.0), 6.0, 3),
    ]
    contexto = _contexto(caminhos, primitivas=())
    assert not casa_moldura(contexto, LOSANGO, _moldura(contexto, CAIXA_LOSANGO))


def test_ponto_fora_da_caixa_do_losango() -> None:
    centros = (*PONTOS_DO_LOSANGO[:2], (200.0, 134.0))
    assert not _casa(LOSANGO, CAIXA_LOSANGO, _caminhos_losango(centros))


@pytest.mark.parametrize(
    ("raio", "esperado"),
    [
        pytest.param(1.45, True, id="logo-acima-de-0-06"),
        pytest.param(1.43, False, id="logo-abaixo-de-0-06"),
        pytest.param(7.19, True, id="logo-abaixo-de-0-3"),
        pytest.param(7.21, False, id="logo-acima-de-0-3"),
    ],
)
def test_pontos_limites_de_tamanho(raio: float, esperado: bool) -> None:
    centros = ((120.0, 134.0), (134.0, 134.0), (148.0, 134.0))
    contexto = _contexto(_caminhos_losango(centros, raio), primitivas=())
    assert casa_moldura(contexto, LOSANGO, _moldura(contexto, CAIXA_LOSANGO)) is esperado


@pytest.mark.parametrize(
    ("centro", "esperado"),
    [
        pytest.param((128.0, 112.0), True, id="abaixo-de-0-85"),
        pytest.param((128.5, 111.5), False, id="exatos-0-85"),
    ],
)
def test_pontos_limite_da_distancia_ao_centro(centro: Ponto, esperado: bool) -> None:
    caixa: Caixa = (100.0, 100.0, 140.0, 140.0)
    pontas = ((120.0, 100.0), (140.0, 120.0), (120.0, 140.0), (100.0, 120.0))
    centros = ((116.0, 120.0), (120.0, 120.0), centro)
    pontos = [circulo_bezier(c, 2.0, i + 1) for i, c in enumerate(centros)]
    contexto = _contexto([poligono(pontas), *pontos], primitivas=())
    assert casa_moldura(contexto, LOSANGO, _moldura(contexto, caixa)) is esperado


def test_tres_pontos_com_centro_nao_inteiro() -> None:
    """Cada ponto vira 4 `c` e o seu `Circulo`, que a proveniência descarta: conta 3 (R-10)."""
    centros = ((126.37, 134.21), (134.11, 134.73), (142.59, 133.87))
    contexto = _contexto(_caminhos_losango(centros))
    circulos = [p for p in contexto.pagina.modelo.primitivas if isinstance(p, Circulo)]
    assert len(circulos) == len(centros)
    assert sum(moldura.forma == "elipse" for moldura in contexto.molduras) == len(centros)
    assert casa_moldura(contexto, LOSANGO, _moldura(contexto, CAIXA_LOSANGO))


def test_tres_pontos_em_dois_caminhos_cada_nao_casa() -> None:
    """Cada ponto pintado em 2 caminhos conta 6, como no motor."""
    caminhos = [poligono(PONTAS_LOSANGO)]
    for centro in PONTOS_DO_LOSANGO:
        caminhos.append(circulo_bezier(centro, 3.0, len(caminhos), cor=None, preenchimento=CINZA))
        caminhos.append(circulo_bezier(centro, 3.0, len(caminhos)))
    assert not _casa(LOSANGO, CAIXA_LOSANGO, caminhos)


# --- orçamento e pureza --------------------------------------------------------------------


def test_cem_molduras_densas_estouram_o_orcamento() -> None:
    molduras = [retangulo_traco((100.0 + i * 0.01, 100.0, 148.0, 148.0), i) for i in range(100)]
    palavras = [texto("ZZ", (120.0, 120.0 + i * 0.01, 130.0, 130.0)) for i in range(100)]
    pagina = pagina_gramatica(molduras, palavras, primitivas=())
    custo_de_indexar = contexto_gramaticas(pagina).orcamento.gasto
    contexto = contexto_gramaticas(pagina, limite=custo_de_indexar + 1000)
    avaliadas = 0
    with pytest.raises(TetoGramaticasExcedido):
        for moldura in contexto.molduras:
            casa_moldura(contexto, DIAGONAIS, moldura)
            avaliadas += 1
    assert avaliadas < len(molduras) / 2
    assert contexto.orcamento.gasto <= custo_de_indexar + 1000 + len(palavras)


@pytest.mark.parametrize("gramatica", [BARRA, ROTULO_ANINHADO], ids=["barra", "aninhado"])
def test_molduras_vizinhas_pagam_na_consulta(gramatica: dict[str, Any]) -> None:
    molduras = [retangulo_traco((100.0 + i * 0.01, 100.0, 148.0, 148.0), i) for i in range(100)]
    palavra = texto("CT", (120.0, 120.0, 130.0, 130.0))
    contexto = _contexto(molduras, [palavra], primitivas=())
    antes = contexto.orcamento.gasto
    casa_moldura(contexto, gramatica, contexto.molduras[0])
    assert contexto.orcamento.gasto - antes >= len(molduras)


def test_modulo_nao_importa_pymupdf_nem_o_motor() -> None:
    fonte = Path(grammar_frames.__file__).read_text(encoding="utf-8")
    importados: set[str] = set()
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.Import):
            importados.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            importados.add(no.module or "")
    assert not any("pymupdf" in nome or "declarative_symbols" in nome for nome in importados)
