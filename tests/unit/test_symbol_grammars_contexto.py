"""Núcleo puro das gramáticas: orçamento, grade, molduras, palavras, segmentos e fontes."""

from __future__ import annotations

import math
from itertools import pairwise, permutations
from typing import Any

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    estilo,
    linha,
    pagina_gramatica,
    poligono,
    retangulo_traco,
    texto,
)

from zeny_project_handler.adapters.analysis.drawing_model import symbol_grammars
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Arco,
    Caixa,
    Caminho,
    Circulo,
    ItemCaminho,
    PaginaModelo,
    Polilinha,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    FonteGramaticaFalhou,
    GradeEspacial,
    Moldura,
    OrcamentoConsultas,
    PaginaGramatica,
    Palavra,
    Segmento,
    TetoGramaticasExcedido,
    contem,
    contexto_gramaticas,
    intersecta,
    ponto_em,
    sobrepoe,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_modelo_com_indices

LIMITES: Caixa = (0.0, 0.0, 300.0, 300.0)


def _grade(itens: list[tuple[Caixa, str]], limites: Caixa = LIMITES) -> GradeEspacial[str]:
    return GradeEspacial(itens, limites, OrcamentoConsultas(1_000_000))


def _palavras(texto_da_pagina: TextoModelo) -> list[Palavra]:
    pagina = pagina_gramatica((), (texto_da_pagina,))
    return contexto_gramaticas(pagina).grade_palavras.consultar(LIMITES)


# --- orçamento ----------------------------------------------------------------------------


def test_orcamento_estoura_no_limite() -> None:
    orcamento = OrcamentoConsultas(3)
    orcamento.gastar(3)
    assert orcamento.gasto == 3
    with pytest.raises(TetoGramaticasExcedido):
        orcamento.gastar()


# --- grade --------------------------------------------------------------------------------


def test_grade_consulta_em_ordem_sem_repetir() -> None:
    grade = _grade(
        [
            ((20.0, 1.0, 22.0, 3.0), "so-na-segunda-celula"),
            ((1.0, 1.0, 30.0, 3.0), "nas-duas-celulas"),
            ((1.0, 1.0, 2.0, 2.0), "so-na-primeira-celula"),
        ]
    )

    assert grade.consultar((1.0, 1.0, 30.0, 3.0)) == [
        "so-na-segunda-celula",
        "nas-duas-celulas",
        "so-na-primeira-celula",
    ]


def test_grade_mantem_a_ordem_com_indices_esparsos() -> None:
    perto: Caixa = (1.0, 1.0, 2.0, 2.0)
    longe: Caixa = (200.0, 200.0, 201.0, 201.0)
    itens = [(perto if i % 7 == 0 else longe, i) for i in range(200)]
    grade = GradeEspacial(itens, LIMITES, OrcamentoConsultas(1_000))

    assert grade.consultar(perto) == [i for i in range(200) if i % 7 == 0]


def test_grade_ignora_item_fora_da_pagina() -> None:
    orcamento = OrcamentoConsultas(10)
    grade = GradeEspacial([((1000.0, 1000.0, 1010.0, 1010.0), "fora")], LIMITES, orcamento)

    assert grade.consultar((1000.0, 1000.0, 1010.0, 1010.0)) == []
    assert grade.consultar(LIMITES) == []
    assert orcamento.gasto == 0
    assert grade._celulas == {}


def test_coordenada_enorme_nao_multiplica_celulas() -> None:
    normal: tuple[Caixa, str] = ((10.0, 10.0, 12.0, 12.0), "normal")
    enorme: tuple[Caixa, str] = ((-1e300, -1e300, 1e300, 1e300), "enorme")
    so_normal = _grade([normal])
    com_enorme = _grade([normal, enorme])

    assert len(com_enorme._celulas) == len(so_normal._celulas)
    assert com_enorme.consultar((10.0, 10.0, 12.0, 12.0)) == ["normal", "enorme"]


def test_lista_de_grandes_entra_em_toda_consulta_contando_orcamento() -> None:
    orcamento = OrcamentoConsultas(100)
    grade = GradeEspacial(
        [((-1e300, -1e300, 1e300, 1e300), "enorme"), ((250.0, 250.0, 252.0, 252.0), "longe")],
        LIMITES,
        orcamento,
    )
    antes = orcamento.gasto

    assert grade.consultar((10.0, 10.0, 12.0, 12.0)) == ["enorme"]
    assert orcamento.gasto == antes + 1
    assert grade.consultar((5000.0, 5000.0, 5010.0, 5010.0)) == ["enorme"]
    assert orcamento.gasto == antes + 2


def test_consulta_acima_de_64_celulas_visita_tudo_e_paga_por_isso() -> None:
    orcamento = OrcamentoConsultas(100)
    grade = GradeEspacial(
        [((1.0, 1.0, 2.0, 2.0), "a"), ((280.0, 280.0, 282.0, 282.0), "b")], LIMITES, orcamento
    )
    antes = orcamento.gasto

    assert grade.consultar(LIMITES) == ["a", "b"]
    assert orcamento.gasto == antes + 2


def test_grade_indexa_segmento_horizontal_de_altura_zero() -> None:
    assert _grade([((10.0, 40.0, 30.0, 40.0), "h")]).consultar((12.0, 39.0, 14.0, 41.0)) == ["h"]


@pytest.mark.parametrize(
    "caixa",
    [
        (math.nan, 0.0, 1.0, 1.0),
        (0.0, 0.0, math.nan, 1.0),
        (math.inf, 0.0, math.inf, 1.0),
        (20.0, 0.0, 10.0, 1.0),
    ],
    ids=["nan-inicio", "nan-fim", "inf-fora", "invertida"],
)
def test_caixa_invalida_nao_entra_nem_quebra_a_consulta(caixa: Caixa) -> None:
    grade = _grade([(caixa, "x")])

    assert grade.consultar(LIMITES) == []
    assert grade.consultar(caixa) == []


# --- molduras -----------------------------------------------------------------------------


def test_molduras_retangulo_elipse_losango() -> None:
    pagina = pagina_gramatica(
        (
            retangulo_traco((10.0, 10.0, 30.0, 30.0), ordem=7),
            circulo_bezier((100.0, 100.0), 10.0, ordem=8),
            poligono(((200.0, 10.0), (220.0, 30.0), (200.0, 50.0), (180.0, 30.0)), ordem=9),
        )
    )

    assert contexto_gramaticas(pagina).molduras == (
        Moldura("retangulo", (10.0, 10.0, 30.0, 30.0), 0),
        Moldura("elipse", (90.0, 90.0, 110.0, 110.0), 1),
        Moldura("losango", (180.0, 10.0, 220.0, 50.0), 2),
    )


def test_moldura_de_quatro_tracos_separados() -> None:
    caminhos = (
        linha((10.0, 10.0), (30.0, 10.0), ordem=50),
        linha((30.0, 10.0), (30.0, 30.0), ordem=51),
        linha((30.0, 30.0), (10.0, 30.0), ordem=52),
        linha((10.0, 30.0), (10.0, 10.0), ordem=53),
    )
    outros = retangulo_traco((100.0, 100.0, 120.0, 120.0))

    molduras = contexto_gramaticas(pagina_gramatica((outros, *caminhos))).molduras

    assert molduras == (
        Moldura("retangulo", (100.0, 100.0, 120.0, 120.0), 0),
        Moldura("retangulo", (10.0, 10.0, 30.0, 30.0), 1),
    )


def test_retangulo_de_caminho_e_sua_polilinha_saem_uma_vez() -> None:
    caminho = retangulo_traco((10.0, 10.0, 30.0, 30.0))
    pagina = pagina_gramatica((caminho,))
    assert any(isinstance(p, Polilinha) and p.fechada for p in pagina.modelo.primitivas)

    assert contexto_gramaticas(pagina).molduras == (
        Moldura("retangulo", (10.0, 10.0, 30.0, 30.0), 0),
    )


def test_circulo_de_caminho_com_centro_nao_inteiro_sai_uma_vez() -> None:
    pagina = pagina_gramatica((circulo_bezier((100.37, 50.81), 3.3),))
    assert any(isinstance(p, Circulo) for p in pagina.modelo.primitivas)

    molduras = contexto_gramaticas(pagina).molduras

    assert [m.forma for m in molduras] == ["elipse"]
    assert molduras[0].caixa == pytest.approx((97.07, 47.51, 103.67, 54.11))


def test_traco_e_preenchimento_na_mesma_caixa_sao_duas_molduras() -> None:
    caixa: Caixa = (10.0, 10.0, 30.0, 30.0)
    cantos = ((10.0, 10.0), (30.0, 10.0), (30.0, 30.0), (10.0, 30.0))
    pagina = pagina_gramatica(
        (retangulo_traco(caixa), poligono(cantos, preenchimento=(0.5, 0.5, 0.5), cor=None))
    )

    assert contexto_gramaticas(pagina).molduras == (
        Moldura("retangulo", caixa, 0),
        Moldura("retangulo", caixa, 1),
    )


def test_primitivas_distintas_de_um_mesmo_caminho_nao_se_descartam() -> None:
    """Só a moldura vinda do caminho descarta a primitiva (R-10): dois discos, duas molduras."""
    dois_discos = circulo_bezier((50.0, 50.0), 5.0)
    outro_disco = circulo_bezier((100.0, 100.0), 5.0)
    caminho = Caminho(
        (*dois_discos.subcaminhos, *outro_disco.subcaminhos), estilo(), "traco", ordem=0
    )

    molduras = contexto_gramaticas(pagina_gramatica((caminho,))).molduras

    assert [(m.forma, m.caminho) for m in molduras] == [("elipse", 0), ("elipse", 0)]
    assert molduras[0].caixa != molduras[1].caixa


def test_circulo_de_dois_arcos_vira_elipse() -> None:
    cx, cy, raio = 100.0, 100.0, 12.0
    alca = 4.0 / 3.0 * raio
    itens = (
        ItemCaminho(
            "c",
            ((cx + raio, cy), (cx + raio, cy + alca), (cx - raio, cy + alca), (cx - raio, cy)),
        ),
        ItemCaminho(
            "c",
            ((cx - raio, cy), (cx - raio, cy - alca), (cx + raio, cy - alca), (cx + raio, cy)),
        ),
    )
    pagina = pagina_gramatica((Caminho((itens,), estilo(), "traco", 0),))

    molduras = contexto_gramaticas(pagina).molduras

    assert [(m.forma, m.caminho) for m in molduras] == [("elipse", 0)]
    assert molduras[0].caixa == pytest.approx((88.0, 88.0, 112.0, 112.0))


def test_degenerados_nao_viram_moldura() -> None:
    caminhos = (
        retangulo_traco((10.0, 10.0, 10.0, 40.0)),
        retangulo_traco((400.0, 400.0, 420.0, 420.0)),
        Caminho((), estilo(), "traco", 0),
    )
    primitivas = (
        Polilinha(((1.0, 1.0), (9.0, 1.0), (5.0, 9.0)), True, estilo(), (0,)),
        Polilinha(((1.0, 1.0), (9.0, 1.0), (9.0, 9.0), (1.0, 9.0)), False, estilo(), (0,)),
        Polilinha(((1.0, 1.0), (9.0, 1.0), (9.0, 9.0), (1.0, 9.0)), True, estilo(), ()),
        Circulo((50.0, 50.0), 0.0, estilo(), (0,)),
        Circulo((500.0, 500.0), 5.0, estilo(), (0,)),
        Circulo((50.0, 50.0), math.nan, estilo(), (0,)),
        Circulo((50.0, 50.0), math.inf, estilo(), (0,)),
        Circulo((50.0, 50.0), 5.0, estilo(), ()),
    )

    contexto = contexto_gramaticas(pagina_gramatica(caminhos, primitivas=primitivas))

    assert contexto.molduras == ()
    assert 2 not in contexto.caixas_caminhos
    assert contexto.grade_caminhos.consultar(LIMITES) == [0]


def test_elipse_fora_da_pagina_e_arco_nao_viram_moldura() -> None:
    fora = circulo_bezier((500.0, 500.0), 10.0)
    arco = Arco((50.0, 50.0), 10.0, 0.0, 90.0, estilo(), (0,))

    assert contexto_gramaticas(pagina_gramatica((fora,), primitivas=(arco,))).molduras == ()


def test_moldura_so_encostada_na_pagina_fica_de_fora() -> None:
    pagina = pagina_gramatica((retangulo_traco((300.0, 10.0, 320.0, 30.0)),), primitivas=())

    assert contexto_gramaticas(pagina).molduras == ()


def test_quatro_lados_que_nao_fecham_ou_ziguezagueiam_nao_viram_moldura() -> None:
    def cadeia(*pontos: tuple[float, float]) -> Caminho:
        itens = tuple(ItemCaminho("l", par) for par in pairwise(pontos))
        return Caminho((itens,), estilo(), "traco", 0)

    aberta = cadeia((10.0, 10.0), (30.0, 10.0), (30.0, 30.0), (10.0, 30.0), (10.0, 20.0))
    ziguezague = cadeia((10.0, 10.0), (30.0, 10.0), (30.0, 30.0), (30.0, 10.0), (10.0, 10.0))
    irregular = cadeia((10.0, 10.0), (30.0, 12.0), (35.0, 40.0), (5.0, 33.0), (10.0, 10.0))
    x_dobrado = Caminho(
        (
            (
                ItemCaminho("l", ((50.0, 10.0), (50.0, 50.0))),
                ItemCaminho("l", ((30.0, 30.0), (70.0, 30.0))),
                ItemCaminho("l", ((50.0, 50.0), (50.0, 10.0))),
                ItemCaminho("l", ((70.0, 30.0), (30.0, 30.0))),
            ),
        ),
        estilo(),
        "traco",
        0,
    )

    for caminho in (aberta, ziguezague, irregular, x_dobrado):
        pagina = pagina_gramatica((caminho,), primitivas=())
        assert contexto_gramaticas(pagina).molduras == ()


def test_losango_menor_que_o_lado_minimo_nao_vira_moldura() -> None:
    pequeno = poligono(((10.0, 10.0), (11.5, 11.5), (10.0, 13.0), (8.5, 11.5)))

    assert contexto_gramaticas(pagina_gramatica((pequeno,), primitivas=())).molduras == ()


def test_losango_com_folga_de_fechamento_ainda_casa_como_no_motor() -> None:
    itens = (
        ItemCaminho("l", ((50.0, 10.0), (70.0, 30.0))),
        ItemCaminho("l", ((70.0, 30.0), (50.0, 50.0))),
        ItemCaminho("l", ((50.0, 50.0), (30.0, 30.0))),
        ItemCaminho("l", ((30.0, 30.0), (50.5, 10.5))),
    )
    pagina = pagina_gramatica((Caminho((itens,), estilo(), "traco", 0),), primitivas=())

    assert [m.forma for m in contexto_gramaticas(pagina).molduras] == ["losango"]


def test_polilinha_de_quatro_pontos_vira_losango() -> None:
    losango = Polilinha(
        ((50.0, 10.0), (70.0, 30.0), (50.0, 50.0), (30.0, 30.0)), True, estilo(), (4, 2)
    )

    molduras = contexto_gramaticas(pagina_gramatica((), primitivas=(losango,))).molduras

    assert molduras == (Moldura("losango", (30.0, 10.0, 70.0, 50.0), 4),)


def test_caminho_de_quatro_curvas_com_item_a_mais_nao_e_elipse() -> None:
    disco = circulo_bezier((50.0, 50.0), 10.0)
    com_linha = Caminho(
        ((*disco.subcaminhos[0], ItemCaminho("l", ((60.0, 50.0), (80.0, 50.0)))),),
        estilo(),
        "traco",
        0,
    )

    assert contexto_gramaticas(pagina_gramatica((com_linha,), primitivas=())).molduras == ()


# --- alinhamento de índices ---------------------------------------------------------------


def test_alinhamento_de_indices_validado() -> None:
    modelo = PaginaModelo(
        0, 300.0, 300.0, (retangulo_traco((1.0, 1.0, 9.0, 9.0)),), (), (), (), (), ()
    )

    assert PaginaGramatica(modelo, (10,), frozenset()).indices_crus == (10,)
    with pytest.raises(ValueError):
        PaginaGramatica(modelo, (10, 11), frozenset())
    with pytest.raises(ValueError):
        PaginaGramatica(modelo, (), frozenset())


# --- palavras -----------------------------------------------------------------------------


ORIGENS = ["nativo", "shx", "glifo"]
# As rotações em que a repartição, já revogada, se decidia: nenhuma muda a caixa da palavra.
ROTACOES = [
    0.0,
    0.9,
    -0.5,
    1.5,
    45.0,
    90.0,
    178.5,
    179.5,
    180.0,
    180.9,
    181.5,
    358.5,
    359.5,
    math.nan,
    math.inf,
]


def test_palavras_de_um_span() -> None:
    caixa: Caixa = (0.0, 0.0, 50.0, 10.0)

    assert _palavras(texto("CT 12", caixa)) == [
        Palavra("CT", caixa, True),
        Palavra("12", caixa, True),
    ]
    assert _palavras(texto("ct", (0.0, 0.0, 20.0, 10.0))) == [
        Palavra("CT", (0.0, 0.0, 20.0, 10.0), False)
    ]


@pytest.mark.parametrize("origem", ORIGENS)
def test_span_sem_palavra_ou_de_caixa_nao_finita_nao_gera_palavra(origem: Any) -> None:
    assert _palavras(texto("   ", (0.0, 0.0, 50.0, 10.0), origem=origem)) == []
    assert _palavras(texto("CT", (math.nan, 0.0, 50.0, 10.0), origem=origem)) == []
    assert _palavras(texto("CT", (0.0, 0.0, math.inf, 10.0), origem=origem)) == []


@pytest.mark.parametrize("origem", ORIGENS)
def test_largura_que_estoura_o_float_nao_quebra(origem: Any) -> None:
    caixa: Caixa = (-1e308, 0.0, 1e308, 10.0)

    assert _palavras(texto("CT 12", caixa, origem=origem)) == [
        Palavra("CT", caixa, True),
        Palavra("12", caixa, True),
    ]


@pytest.mark.parametrize("rotacao", ROTACOES, ids=str)
@pytest.mark.parametrize("origem", ORIGENS)
def test_varias_palavras_usam_a_caixa_do_span_na_ordem_do_texto(
    origem: Any, rotacao: float
) -> None:
    """Repartir por caracteres não é exato em nenhuma origem (R-4), nem de cabeça para baixo."""
    caixa: Caixa = (0.0, 0.0, 50.0, 10.0)

    assert _palavras(texto("CT 12", caixa, origem=origem, rotacao=rotacao)) == [
        Palavra("CT", caixa, True),
        Palavra("12", caixa, True),
    ]


@pytest.mark.parametrize("rotacao", [0.0, 90.0, 180.0, math.nan], ids=["0", "90", "180", "nan"])
@pytest.mark.parametrize("origem", ORIGENS)
@pytest.mark.parametrize(
    "cru", [" ct ", "ct ", " ct", "ct\t"], ids=["ambos", "fim", "inicio", "tab"]
)
def test_espacos_nas_pontas_saem_do_texto_e_marcam_inteira(
    cru: str, origem: Any, rotacao: float
) -> None:
    """O span tem mais que a palavra: a caixa dele não diz onde ela está."""
    caixa: Caixa = (0.0, 0.0, 50.0, 10.0)

    assert _palavras(texto(cru, caixa, origem=origem, rotacao=rotacao)) == [
        Palavra("CT", caixa, True)
    ]


@pytest.mark.parametrize("rotacao", [0.0, 90.0, 180.0, math.nan], ids=["0", "90", "180", "nan"])
@pytest.mark.parametrize("origem", ORIGENS)
def test_span_que_e_exatamente_a_palavra_nao_e_inteira(origem: Any, rotacao: float) -> None:
    caixa: Caixa = (0.0, 0.0, 20.0, 40.0)

    assert _palavras(texto("ct", caixa, origem=origem, rotacao=rotacao)) == [
        Palavra("CT", caixa, False)
    ]


# --- spans colados ------------------------------------------------------------------------


def _palavras_de(*textos: TextoModelo) -> list[Palavra]:
    pagina = pagina_gramatica((), textos, primitivas=())
    return contexto_gramaticas(pagina).grade_palavras.consultar(LIMITES)


ESQUERDO: Caixa = (100.0, 130.0, 120.0, 140.0)


def _a_direita(lacuna: float, y0: float = 130.0, y1: float = 140.0) -> Caixa:
    return (120.0 + lacuna, y0, 132.0 + lacuna, y1)


def test_spans_colados_viram_uma_palavra_com_a_caixa_unida() -> None:
    """O motor lê `words`, e a PyMuPDF junta spans de estilos diferentes na mesma linha."""
    esquerdo = texto("qdp", (100.0, 130.0, 120.0, 141.0))
    direito = texto("12", (120.0, 131.0, 132.0, 140.0))

    assert _palavras_de(esquerdo, direito) == [Palavra("QDP12", (100.0, 130.0, 132.0, 141.0), True)]


def test_caixa_unida_inclui_o_span_da_direita_mais_alto() -> None:
    esquerdo = texto("AB", (100.0, 131.0, 120.0, 140.0))
    direito = texto("CD", (120.0, 130.0, 132.0, 141.0))

    assert _palavras_de(esquerdo, direito) == [Palavra("ABCD", (100.0, 130.0, 132.0, 141.0), True)]


@pytest.mark.parametrize(
    ("altura", "lacuna", "colam"),
    [
        pytest.param(10.0, 0.0, True, id="sem-lacuna"),
        pytest.param(10.0, 2.0, True, id="20-por-cento-da-altura"),
        pytest.param(10.0, 2.01, False, id="alem-de-20-por-cento"),
        pytest.param(10.0, -0.01, True, id="sobreposto-em-x"),
        pytest.param(10.0, -2.0, True, id="sobreposto-em-20-por-cento-da-altura"),
        pytest.param(10.0, -2.01, False, id="sobreposto-alem-de-20-por-cento"),
        pytest.param(2.0, 0.5, True, id="piso-de-meio-ponto"),
        pytest.param(2.0, 0.51, False, id="alem-do-piso"),
        pytest.param(2.0, -0.5, True, id="sobreposto-no-piso"),
        pytest.param(2.0, -0.51, False, id="sobreposto-alem-do-piso"),
    ],
)
def test_lacuna_entre_spans_colados(altura: float, lacuna: float, colam: bool) -> None:
    esquerdo: Caixa = (100.0, 130.0, 120.0, 130.0 + altura)
    direito = _a_direita(lacuna, 130.0, 130.0 + altura)

    palavras = _palavras_de(texto("AB", esquerdo), texto("CD", direito))

    assert [p.texto for p in palavras] == (["ABCD"] if colam else ["AB", "CD"])


@pytest.mark.parametrize("lacuna", [0.6, -0.6], ids=["afastado", "sobreposto"])
def test_lacuna_usa_a_menor_altura(lacuna: float) -> None:
    alto: Caixa = (100.0, 120.0, 120.0, 140.0)
    baixo = _a_direita(lacuna, 130.0, 132.0)

    assert [p.texto for p in _palavras_de(texto("AB", alto), texto("CD", baixo))] == ["AB", "CD"]


@pytest.mark.parametrize("lacuna", [0.6, -0.6], ids=["afastado", "sobreposto"])
def test_lacuna_usa_a_menor_altura_com_o_baixo_a_esquerda(lacuna: float) -> None:
    """Altura 4 daria folga de 0,8 e a janela a alcança; quem decide é a altura 2, com 0,5."""
    baixo: Caixa = (100.0, 130.0, 120.0, 132.0)
    alto: Caixa = (120.0 + lacuna, 129.0, 132.0, 133.0)

    assert [p.texto for p in _palavras_de(texto("AB", baixo), texto("CD", alto))] == ["AB", "CD"]


@pytest.mark.parametrize(
    "direito",
    [
        pytest.param(texto("CD", _a_direita(-0.3, 150.0, 160.0)), id="outra-linha"),
        pytest.param(texto("CD", _a_direita(-0.3), rotacao=0.5), id="outra-rotacao"),
        pytest.param(texto(" CD", _a_direita(-0.3)), id="espaco-na-juncao"),
        pytest.param(texto("CD", _a_direita(-0.3), origem="glifo"), id="glifo"),
        pytest.param(texto("CD", _a_direita(-0.3), origem="shx"), id="shx"),
    ],
)
def test_sobreposto_em_x_segue_as_outras_regras_da_colagem(direito: TextoModelo) -> None:
    assert [p.texto for p in _palavras_de(texto("AB", ESQUERDO), direito)] == ["AB", "CD"]


def test_palavra_fundida_e_inteira_para_a_guarda_recusar_por_sobreposicao() -> None:
    palavras = _palavras_de(texto("AB", ESQUERDO), texto("CD", _a_direita(1.5)))

    assert palavras == [Palavra("ABCD", (100.0, 130.0, 133.5, 140.0), True)]


# Caixas medidas na PyMuPDF: "i" de Helvetica 11 desenhado sobre o fim de "QDP" (lacuna -2,94).
QDP_MEDIDO: Caixa = (116.0, 127.18, 139.84, 142.29)


@pytest.mark.parametrize(
    "contido",
    [
        pytest.param((136.9, 127.18, 139.34, 142.29), id="dentro"),
        pytest.param((137.4, 127.18, 139.84, 142.29), id="mesma-borda-direita"),
    ],
)
def test_span_contido_na_ponta_do_outro_funde_porque_o_motor_le_uma_palavra(
    contido: Caixa,
) -> None:
    """Contenção funde: deixá-lo de fora faria o núcleo ver `QDP` onde o motor lê `QDPi`."""
    esperado = [Palavra("QDPI", QDP_MEDIDO, True)]

    assert _palavras_de(texto("QDP", QDP_MEDIDO), texto("i", contido)) == esperado
    assert _palavras_de(texto("i", contido), texto("QDP", QDP_MEDIDO)) == esperado


def test_span_contido_longe_da_borda_nao_funde() -> None:
    """Fora de [-t, +t]: mesmo contido, a lacuna é do início dele à borda direita do outro."""
    contido: Caixa = (120.0, 127.18, 122.0, 142.29)

    assert [p.texto for p in _palavras_de(texto("QDP", QDP_MEDIDO), texto("i", contido))] == [
        "QDP",
        "I",
    ]


def test_span_contido_na_ponta_funde_no_pdf_como_o_motor_le() -> None:
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=400, height=400)
        pagina.insert_text((116, 139), "QDP", fontsize=11)
        x = 116 + pymupdf.get_text_length("QDP", fontsize=11) - 2.94
        pagina.insert_text((x, 139), "i", fontsize=11, color=(1, 0, 0))
        assert [str(w[4]) for w in pagina.get_text("words")] == ["QDPi"]
        modelo, indices = pagina_modelo_com_indices(pagina, 0)
    contexto = contexto_gramaticas(PaginaGramatica(modelo, indices, frozenset()))

    palavras = contexto.grade_palavras.consultar((0.0, 0.0, 400.0, 400.0))

    assert [(p.texto, p.inteira) for p in palavras] == [("QDPI", True)]


@pytest.mark.parametrize(
    ("ordem", "esperado"),
    [pytest.param((0, 1), "IL", id="i-primeiro"), pytest.param((1, 0), "LI", id="l-primeiro")],
)
def test_caixas_iguais_fundem_na_ordem_da_pagina(ordem: tuple[int, int], esperado: str) -> None:
    """Sem borda para desempatar, a ordem da página decide e a união termina."""
    caixa: Caixa = (100.0, 130.0, 101.0, 140.0)
    spans = (texto("i", caixa), texto("l", caixa))

    palavras = _palavras_de(spans[ordem[0]], spans[ordem[1]])

    assert palavras == [Palavra(esperado, caixa, True)]


def test_spans_mutuamente_na_tolerancia_nao_formam_ciclo() -> None:
    """Cada um está em [-t, +t] do outro nos dois sentidos: o início da caixa decide o sentido."""
    menor = texto("A", (100.0, 130.0, 100.3, 140.0))
    maior = texto("B", (99.9, 130.0, 100.4, 140.0))

    assert _palavras_de(menor, maior) == [Palavra("BA", (99.9, 130.0, 100.4, 140.0), True)]
    assert _palavras_de(maior, menor) == [Palavra("BA", (99.9, 130.0, 100.4, 140.0), True)]


def test_fusao_independe_da_ordem_da_pagina_quando_as_caixas_nao_empatam() -> None:
    spans = (
        texto("A", (100.0, 130.0, 100.4, 140.0)),
        texto("B", (100.1, 130.0, 100.5, 140.0)),
        texto("C", (100.2, 130.0, 100.6, 140.0)),
        texto("D", (100.3, 130.0, 100.7, 140.0)),
    )

    resultados = {
        tuple(_palavras_de(*permutacao)) for permutacao in permutations(spans, len(spans))
    }

    assert resultados == {(Palavra("ABCD", (100.0, 130.0, 100.7, 140.0), True),)}


@pytest.mark.parametrize(
    ("y0", "y1", "colam"),
    [
        pytest.param(108.0, 112.0, True, id="metade-da-menor-altura"),
        pytest.param(108.1, 112.1, False, id="menos-da-metade"),
        pytest.param(98.0, 102.0, True, id="metade-por-cima"),
        pytest.param(97.9, 101.9, False, id="menos-da-metade-por-cima"),
        pytest.param(120.0, 124.0, False, id="outra-linha"),
    ],
)
def test_sobreposicao_vertical_de_spans_colados(y0: float, y1: float, colam: bool) -> None:
    palavras = _palavras_de(
        texto("AB", (100.0, 100.0, 120.0, 110.0)), texto("CD", _a_direita(0.0, y0, y1))
    )

    assert [p.texto for p in palavras] == (["ABCD"] if colam else ["AB", "CD"])


@pytest.mark.parametrize(
    ("rotacao_a", "rotacao_b", "colam"),
    [
        pytest.param(0.0, 0.0, True, id="zero"),
        pytest.param(1.0, 1.0, True, id="um-grau"),
        pytest.param(359.5, 359.5, True, id="logo-abaixo-de-360"),
        pytest.param(-0.5, -0.5, True, id="negativa"),
        pytest.param(0.0, 0.5, False, id="rotacoes-diferentes"),
        pytest.param(1.5, 1.5, False, id="alem-de-um-grau"),
        pytest.param(180.0, 180.0, False, id="invertido"),
        pytest.param(90.0, 90.0, False, id="vertical"),
        pytest.param(math.nan, math.nan, False, id="nan"),
    ],
)
def test_so_span_horizontal_de_mesma_rotacao_cola(
    rotacao_a: float, rotacao_b: float, colam: bool
) -> None:
    """Limitação registrada: rotacionado não é fundido."""
    palavras = _palavras_de(
        texto("AB", ESQUERDO, rotacao=rotacao_a), texto("CD", _a_direita(0.0), rotacao=rotacao_b)
    )

    assert [p.texto for p in palavras] == (["ABCD"] if colam else ["AB", "CD"])


@pytest.mark.parametrize(
    ("origem_a", "origem_b"),
    [
        ("shx", "shx"),
        ("glifo", "glifo"),
        ("nativo", "glifo"),
        ("glifo", "nativo"),
        ("shx", "nativo"),
    ],
    ids=["shx", "glifo", "nativo-glifo", "glifo-nativo", "shx-nativo"],
)
def test_so_nativo_cola(origem_a: Any, origem_b: Any) -> None:
    palavras = _palavras_de(
        texto("AB", ESQUERDO, origem=origem_a), texto("CD", _a_direita(0.0), origem=origem_b)
    )

    assert [p.texto for p in palavras] == ["AB", "CD"]


def test_espaco_na_juncao_nao_cola() -> None:
    assert _palavras_de(texto("AB ", ESQUERDO), texto("CD", _a_direita(0.0))) == [
        Palavra("AB", ESQUERDO, True),
        Palavra("CD", _a_direita(0.0), False),
    ]
    assert _palavras_de(texto("AB", ESQUERDO), texto(" CD", _a_direita(0.0))) == [
        Palavra("AB", ESQUERDO, False),
        Palavra("CD", _a_direita(0.0), True),
    ]


def test_varias_palavras_nos_spans_colados_seguem_a_regra_do_span() -> None:
    uniao: Caixa = (100.0, 130.0, 132.0, 140.0)

    assert _palavras_de(texto("AB C", ESQUERDO), texto("D E", _a_direita(0.0))) == [
        Palavra("AB", uniao, True),
        Palavra("CD", uniao, True),
        Palavra("E", uniao, True),
    ]


def test_cadeia_de_spans_colados_vira_um_texto_na_posicao_do_primeiro() -> None:
    longe = texto("Z", (200.0, 10.0, 210.0, 20.0))
    a = texto("A", (100.0, 130.0, 110.0, 140.0))
    b = texto("B", (110.0, 130.0, 120.0, 140.0))
    c = texto("C", (120.0, 130.0, 130.0, 140.0))

    assert _palavras_de(c, longe, b, a) == [
        Palavra("Z", longe.bbox, False),
        Palavra("ABC", (100.0, 130.0, 130.0, 140.0), True),
    ]


def test_texto_de_outra_coluna_entre_as_alturas_nao_impede_a_colagem() -> None:
    """Colar não pode depender de os dois spans serem vizinhos numa ordem por y."""
    esquerdo = texto("AB", (100.0, 130.0, 120.0, 140.0))
    outra_coluna = texto("ZZ", (200.0, 130.1, 220.0, 140.1))
    direito = texto("CD", (120.0, 130.3, 132.0, 140.3))

    assert [p.texto for p in _palavras_de(esquerdo, outra_coluna, direito)] == ["ABCD", "ZZ"]


def test_cola_no_vizinho_de_menor_lacuna() -> None:
    longe = texto("A", (90.0, 130.0, 119.5, 140.0))
    perto = texto("B", ESQUERDO)
    direito = texto("C", _a_direita(0.0))

    assert [p.texto for p in _palavras_de(longe, perto, direito)] == ["A", "BC"]


def test_menor_lacuna_e_em_modulo() -> None:
    sobreposto = texto("A", (90.0, 130.0, 120.4, 140.0))
    afastado = texto("B", (100.0, 130.0, 119.9, 140.0))
    direito = texto("C", _a_direita(0.0))

    assert sorted(p.texto for p in _palavras_de(sobreposto, afastado, direito)) == ["A", "BC"]
    assert sorted(p.texto for p in _palavras_de(afastado, sobreposto, direito)) == ["A", "BC"]


def test_span_cola_em_um_vizinho_so() -> None:
    assert [
        p.texto
        for p in _palavras_de(
            texto("A", ESQUERDO), texto("B", _a_direita(0.0)), texto("C", _a_direita(0.0))
        )
    ] == ["AB", "C"]


@pytest.mark.parametrize(
    "degenerado",
    [
        pytest.param(texto("Z", (120.0, 130.0, 120.0, 140.0)), id="largura-zero"),
        pytest.param(texto("Z", (120.0, 130.0, 130.0, 130.0)), id="altura-zero"),
        pytest.param(texto("Z", (130.0, 130.0, 120.0, 140.0)), id="invertida"),
        pytest.param(texto("Z", (120.0, math.nan, 130.0, 140.0)), id="nan"),
        pytest.param(texto("Z", (120.0, 130.0, math.inf, 140.0)), id="inf"),
        pytest.param(texto("", (120.0, 130.0, 130.0, 140.0)), id="vazio"),
        pytest.param(texto("   ", (120.0, 130.0, 130.0, 140.0)), id="so-espacos"),
    ],
)
def test_span_degenerado_nao_cola(degenerado: TextoModelo) -> None:
    palavras = _palavras_de(texto("AB", ESQUERDO), degenerado)

    assert palavras[0] == Palavra("AB", ESQUERDO, False)


def test_colagem_paga_um_por_span_que_pode_colar() -> None:
    nativos = (texto("A", (10.0, 10.0, 20.0, 20.0)), texto("B", (50.0, 50.0, 60.0, 60.0)))
    outros = (
        texto("C", (90.0, 90.0, 99.0, 99.0), origem="shx"),
        texto("D", (120.0, 120.0, 130.0, 130.0), origem="glifo"),
        texto("E", (150.0, 150.0, 160.0, 160.0), rotacao=90.0),
    )

    # 2 para colar e 5 palavras indexadas.
    pagina = pagina_gramatica((), (*nativos, *outros), primitivas=())
    assert contexto_gramaticas(pagina).orcamento.gasto == 2 + 5


def test_mesma_borda_direita_em_toda_a_pagina_paga_e_estoura_o_orcamento() -> None:
    """Cada span à direita visita os que terminam junto dele: quem paga é a página densa."""
    quantidade = 200
    esquerdos = [texto("A", (100.0, i * 0.7, 120.0, i * 0.7 + 0.5)) for i in range(quantidade)]
    direitos = [
        texto("B", (120.0, 150.0 + i * 0.7, 130.0, 150.5 + i * 0.7)) for i in range(quantidade)
    ]
    pagina = pagina_gramatica((), (*esquerdos, *direitos), primitivas=())

    assert contexto_gramaticas(pagina).orcamento.gasto >= quantidade * quantidade
    with pytest.raises(TetoGramaticasExcedido):
        contexto_gramaticas(pagina, limite=quantidade * quantidade // 2)


def test_janela_da_lacuna_negativa_paga_cada_candidato_antes_de_comparar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quem termina depois do início do span também é visitado, e pago antes de `_colados`."""
    quantidade = 200
    esquerdos = [texto("A", (100.0, i * 0.7, 120.4, i * 0.7 + 0.5)) for i in range(quantidade)]
    direitos = [
        texto("B", (120.0, 150.0 + i * 0.7, 130.0, 150.5 + i * 0.7)) for i in range(quantidade)
    ]
    pagina = pagina_gramatica((), (*esquerdos, *direitos), primitivas=())
    chamadas = {"n": 0}
    original = symbol_grammars._colados

    def contada(esquerdo: TextoModelo, direito: TextoModelo) -> bool:
        chamadas["n"] += 1
        return bool(original(esquerdo, direito))

    monkeypatch.setattr(symbol_grammars, "_colados", contada)

    assert contexto_gramaticas(pagina).orcamento.gasto >= quantidade * quantidade
    chamadas["n"] = 0
    limite = quantidade * quantidade // 2
    with pytest.raises(TetoGramaticasExcedido):
        contexto_gramaticas(pagina, limite=limite)
    assert chamadas["n"] <= limite


# --- segmentos ----------------------------------------------------------------------------


def test_segmentos_excluem_moldura_fechada() -> None:
    aberto = Caminho(
        (
            (
                ItemCaminho("l", ((10.0, 10.0), (30.0, 10.0))),
                ItemCaminho("l", ((30.0, 10.0), (30.0, 30.0))),
            ),
        ),
        estilo(),
        "traco",
        0,
    )
    irregular = poligono(((100.0, 100.0), (130.0, 102.0), (135.0, 140.0), (95.0, 133.0)))
    moldura = retangulo_traco((200.0, 200.0, 220.0, 220.0))
    disco = circulo_bezier((60.0, 60.0), 5.0)

    segmentos = contexto_gramaticas(
        pagina_gramatica((moldura, aberto, disco, irregular), primitivas=())
    ).grade_segmentos.consultar(LIMITES)

    assert segmentos[:2] == [
        Segmento((10.0, 10.0), (30.0, 10.0), 1),
        Segmento((30.0, 10.0), (30.0, 30.0), 1),
    ]
    assert [s.caminho for s in segmentos] == [1, 1, 3, 3, 3, 3]


def test_segmento_nao_finito_nao_entra() -> None:
    caminho = Caminho(
        (
            (ItemCaminho("l", ((10.0, 10.0), (math.nan, 10.0))),),
            (ItemCaminho("l", ((math.nan, 10.0), (10.0, 10.0))),),
        ),
        estilo(),
        "traco",
        0,
    )

    contexto = contexto_gramaticas(pagina_gramatica((caminho,), primitivas=()))

    assert contexto.grade_segmentos.consultar(LIMITES) == []
    assert contexto.caixas_caminhos == {}


# --- caminhos -----------------------------------------------------------------------------


def test_caixas_de_caminhos_sao_por_posicao_e_cobrem_todos_os_pontos() -> None:
    pagina = pagina_gramatica(
        (
            linha((10.0, 10.0), (20.0, 15.0), ordem=99),
            Caminho(((),), estilo(), "traco", 1),
            circulo_bezier((100.0, 100.0), 10.0, ordem=98),
        ),
        primitivas=(),
    )

    contexto = contexto_gramaticas(pagina)

    assert set(contexto.caixas_caminhos) == {0, 2}
    assert contexto.caixas_caminhos[0] == (10.0, 10.0, 20.0, 15.0)
    assert contexto.caixas_caminhos[2] == pytest.approx((90.0, 90.0, 110.0, 110.0))
    assert contexto.grade_caminhos.consultar(LIMITES) == [0, 2]


# --- semântica de borda -------------------------------------------------------------------


def test_semantica_de_borda() -> None:
    caixa: Caixa = (0.0, 0.0, 10.0, 10.0)
    encostada: Caixa = (10.0, 0.0, 20.0, 10.0)
    lado_zero: Caixa = (5.0, 0.0, 5.0, 10.0)

    assert contem(caixa, caixa)
    assert not contem(caixa, (0.0, 0.0, 10.1, 10.0))
    assert contem(caixa, lado_zero)
    assert not contem(lado_zero, lado_zero)
    assert not contem(lado_zero, (5.0, 2.0, 5.0, 3.0))

    assert ponto_em(caixa, (0.0, 0.0))
    assert ponto_em(caixa, (10.0, 10.0))
    assert not ponto_em(caixa, (10.1, 5.0))

    assert intersecta(caixa, (5.0, 5.0, 15.0, 15.0))
    assert not intersecta(caixa, encostada)
    assert not intersecta(encostada, caixa)
    assert not intersecta(caixa, lado_zero)
    assert not intersecta(lado_zero, caixa)
    assert not intersecta(caixa, (20.0, 20.0, 30.0, 30.0))


# --- fontes (R-8) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "codigo",
    [
        "modelo.caminhos_falhou",
        "modelo.primitivas_falhou",
        "modelo.textos_nativos_falhou",
        "modelo.textos_shx_falhou",
        "modelo.glifos_falhou",
    ],
)
def test_fonte_que_falhou_levanta(codigo: str) -> None:
    pagina = pagina_gramatica((), diagnosticos=(codigo,))

    with pytest.raises(FonteGramaticaFalhou) as erro:
        contexto_gramaticas(pagina)

    assert erro.value.codigo == codigo


@pytest.mark.parametrize(
    "codigo",
    ["modelo.grupos_falhou", "modelo.imagens_falhou", "modelo.imagens_anotacao_falhou"],
)
def test_fonte_que_nao_consumo_nao_bloqueia(codigo: str) -> None:
    contexto = contexto_gramaticas(pagina_gramatica((), diagnosticos=(codigo,)))

    assert contexto.molduras == ()


def test_glifos_limitados_levanta_teto() -> None:
    with pytest.raises(TetoGramaticasExcedido):
        contexto_gramaticas(pagina_gramatica((), diagnosticos=("modelo.glifos_limitados",)))


def test_glifos_desconhecidos_nao_bloqueia() -> None:
    pagina = pagina_gramatica((), diagnosticos=("modelo.glifos_desconhecidos",))

    assert contexto_gramaticas(pagina).molduras == ()


def test_falha_de_fonte_prevalece_sobre_glifos_limitados() -> None:
    pagina = pagina_gramatica(
        (), diagnosticos=("modelo.glifos_limitados", "modelo.textos_nativos_falhou")
    )

    with pytest.raises(FonteGramaticaFalhou):
        contexto_gramaticas(pagina)


# --- custo --------------------------------------------------------------------------------


def test_pagina_densa_estoura_o_orcamento_ao_construir() -> None:
    caminhos = [retangulo_traco((10.0, 10.0, 30.0, 30.0), ordem=i) for i in range(5_000)]
    pagina = pagina_gramatica(caminhos, primitivas=())

    with pytest.raises(TetoGramaticasExcedido):
        contexto_gramaticas(pagina, limite=1_000)


@pytest.mark.parametrize(
    ("a", "b", "esperado"),
    [
        pytest.param((0.0, 0.0, 10.0, 10.0), (5.0, 5.0, 15.0, 15.0), True, id="cruza"),
        pytest.param((0.0, 0.0, 10.0, 10.0), (10.0, 0.0, 20.0, 10.0), True, id="encosta-em-x"),
        pytest.param((0.0, 0.0, 10.0, 10.0), (0.0, 10.0, 10.0, 20.0), True, id="encosta-em-y"),
        pytest.param((0.0, 0.0, 10.0, 10.0), (10.0, 10.0, 20.0, 20.0), True, id="encosta-no-canto"),
        pytest.param((0.0, 0.0, 10.0, 10.0), (5.0, 5.0, 20.0, 5.0), True, id="altura-zero"),
        pytest.param((0.0, 0.0, 10.0, 10.0), (5.0, 5.0, 5.0, 20.0), True, id="largura-zero"),
        pytest.param((0.0, 0.0, 10.0, 10.0), (5.0, 5.0, 5.0, 5.0), True, id="ponto-dentro"),
        pytest.param((0.0, 0.0, 10.0, 10.0), (10.1, 0.0, 20.0, 10.0), False, id="longe-em-x"),
        pytest.param((0.0, 0.0, 10.0, 10.0), (0.0, 10.1, 10.0, 20.0), False, id="longe-em-y"),
        pytest.param((0.0, 0.0, 10.0, 10.0), (-5.0, 0.0, -0.1, 10.0), False, id="antes-em-x"),
        pytest.param((0.0, 0.0, 10.0, 10.0), (0.0, -5.0, 10.0, -0.1), False, id="antes-em-y"),
    ],
)
def test_sobrepoe_e_fechado(a: Caixa, b: Caixa, esperado: bool) -> None:
    """Ao contrário de `intersecta`, encostar conta, e caixa de lado 0 também."""
    assert sobrepoe(a, b) is esperado
    assert sobrepoe(b, a) is esperado


def test_contexto_gasta_um_por_item_indexado() -> None:
    pagina = pagina_gramatica(
        (
            retangulo_traco((10.0, 10.0, 30.0, 30.0)),
            linha((50.0, 50.0), (60.0, 50.0)),
            retangulo_traco((1000.0, 1000.0, 1020.0, 1020.0)),
        ),
        (texto("CT 12", (100.0, 100.0, 150.0, 110.0)),),
        primitivas=(),
    )

    # 1 span que pode colar, 1 moldura, 2 palavras, 1 segmento e 2 caminhos: o retângulo fora
    # da página não vira moldura, e nem seus segmentos nem seu caminho são indexados.
    assert contexto_gramaticas(pagina).orcamento.gasto == 1 + 1 + 2 + 1 + 2


def test_trabalho_da_consulta_cresce_com_a_densidade_local_e_nao_com_a_pagina() -> None:
    def gasto_da_consulta(distantes: int) -> tuple[int, list[Moldura], list[int]]:
        longe = [
            retangulo_traco(
                (
                    1000.0 + (i % 100) * 20.0,
                    1000.0 + (i // 100) * 20.0,
                    1010.0 + (i % 100) * 20.0,
                    1010.0 + (i // 100) * 20.0,
                ),
                ordem=i + 1,
            )
            for i in range(distantes)
        ]
        perto = retangulo_traco((10.0, 10.0, 30.0, 30.0))
        contexto = contexto_gramaticas(
            pagina_gramatica((perto, *longe), largura=4000.0, altura=4000.0)
        )
        antes = contexto.orcamento.gasto
        molduras = contexto.grade_molduras.consultar((10.0, 10.0, 30.0, 30.0))
        caminhos = contexto.grade_caminhos.consultar((10.0, 10.0, 30.0, 30.0))
        return contexto.orcamento.gasto - antes, molduras, caminhos

    gasto_menor, molduras_menor, caminhos_menor = gasto_da_consulta(1_000)
    gasto_maior, molduras_maior, caminhos_maior = gasto_da_consulta(2_000)

    assert gasto_menor == gasto_maior == 2
    assert molduras_menor == molduras_maior
    assert [m.caminho for m in molduras_menor] == [0]
    assert caminhos_menor == caminhos_maior == [0]


def test_consulta_em_celula_densa_estoura_o_orcamento() -> None:
    orcamento = OrcamentoConsultas(5_000)
    grade = GradeEspacial([((10.0, 10.0, 12.0, 12.0), i) for i in range(4_000)], LIMITES, orcamento)

    with pytest.raises(TetoGramaticasExcedido):
        grade.consultar((10.0, 10.0, 12.0, 12.0))
