"""Núcleo puro das gramáticas: orçamento, grade, molduras, palavras, segmentos e fontes."""

from __future__ import annotations

import math
from itertools import pairwise

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
)

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


def test_palavras_de_um_span() -> None:
    caixa: Caixa = (0.0, 0.0, 50.0, 10.0)

    assert _palavras(texto("CT 12", caixa, origem="glifo")) == [
        Palavra("CT", (0.0, 0.0, 20.0, 10.0), False),
        Palavra("12", (30.0, 0.0, 50.0, 10.0), False),
    ]
    assert _palavras(texto("CT 12", caixa)) == [
        Palavra("CT", caixa, True),
        Palavra("12", caixa, True),
    ]
    assert _palavras(texto("ct", (0.0, 0.0, 20.0, 10.0))) == [
        Palavra("CT", (0.0, 0.0, 20.0, 10.0), False)
    ]
    assert _palavras(texto("ct", (0.0, 0.0, 20.0, 10.0), origem="glifo")) == [
        Palavra("CT", (0.0, 0.0, 20.0, 10.0), False)
    ]
    assert _palavras(texto("   ", caixa)) == []
    assert _palavras(texto("   ", caixa, origem="glifo")) == []
    assert _palavras(texto("CT 12", caixa, rotacao=45.0)) == [
        Palavra("CT", caixa, True),
        Palavra("12", caixa, True),
    ]
    assert _palavras(texto("CT 12", caixa, origem="glifo", rotacao=45.0)) == [
        Palavra("CT", caixa, True),
        Palavra("12", caixa, True),
    ]
    assert _palavras(texto("CT 12", caixa, origem="shx", rotacao=0.0)) == [
        Palavra("CT", caixa, True),
        Palavra("12", caixa, True),
    ]
    assert _palavras(texto("CT", (math.nan, 0.0, 50.0, 10.0))) == []
    assert _palavras(texto("CT", (0.0, 0.0, math.inf, 10.0))) == []
    assert _palavras(texto("CT", (math.nan, 0.0, 50.0, 10.0), origem="glifo")) == []


def test_largura_que_estoura_o_float_nao_quebra() -> None:
    caixa: Caixa = (-1e308, 0.0, 1e308, 10.0)

    assert _palavras(texto("CT 12", caixa, origem="glifo")) == []
    assert _palavras(texto("CT 12", caixa)) == [
        Palavra("CT", caixa, True),
        Palavra("12", caixa, True),
    ]


def test_palavra_unica_nao_repartida_nao_e_inteira() -> None:
    caixa: Caixa = (0.0, 0.0, 20.0, 40.0)

    assert _palavras(texto("CT", caixa, rotacao=90.0)) == [Palavra("CT", caixa, False)]
    assert _palavras(texto("CT", caixa, origem="shx")) == [Palavra("CT", caixa, False)]
    assert _palavras(texto("CT", caixa, origem="glifo", rotacao=90.0)) == [
        Palavra("CT", caixa, False)
    ]


def test_espacos_nas_pontas_ocupam_largura_e_saem_do_texto() -> None:
    assert _palavras(texto(" ct ", (0.0, 0.0, 40.0, 10.0), origem="glifo")) == [
        Palavra("CT", (10.0, 0.0, 30.0, 10.0), False)
    ]


def test_palavra_unica_com_espacos_fora_do_nativo_nao_e_inteira() -> None:
    caixa: Caixa = (0.0, 0.0, 40.0, 10.0)

    assert _palavras(texto(" ct ", caixa, origem="shx")) == [Palavra("CT", caixa, False)]
    assert _palavras(texto(" ct ", caixa, origem="glifo", rotacao=90.0)) == [
        Palavra("CT", caixa, False)
    ]


@pytest.mark.parametrize(
    "rotacao",
    [0.0, 0.9, 45.0, 90.0, 180.0, math.nan],
    ids=["0", "0.9", "45", "90", "180", "nan"],
)
def test_texto_nativo_nunca_e_repartido(rotacao: float) -> None:
    """Repartir por caracteres só é exato em largura fixa, e o nativo é proporcional (R-4)."""
    caixa: Caixa = (0.0, 0.0, 50.0, 10.0)

    assert _palavras(texto("CT 12", caixa, rotacao=rotacao)) == [
        Palavra("CT", caixa, True),
        Palavra("12", caixa, True),
    ]


@pytest.mark.parametrize("rotacao", [0.0, 90.0, 180.0, math.nan], ids=["0", "90", "180", "nan"])
@pytest.mark.parametrize(
    "cru", [" ct ", "ct ", " ct", "ct\t"], ids=["ambos", "fim", "inicio", "tab"]
)
def test_nativo_com_espacos_nas_pontas_e_inteira(cru: str, rotacao: float) -> None:
    """O span tem mais que a palavra: a caixa dele não diz onde ela está."""
    caixa: Caixa = (0.0, 0.0, 50.0, 10.0)

    assert _palavras(texto(cru, caixa, rotacao=rotacao)) == [Palavra("CT", caixa, True)]


@pytest.mark.parametrize("rotacao", [0.0, 90.0, 180.0, math.nan], ids=["0", "90", "180", "nan"])
def test_nativo_que_e_exatamente_a_palavra_nao_e_inteira(rotacao: float) -> None:
    caixa: Caixa = (0.0, 0.0, 50.0, 10.0)

    assert _palavras(texto("ct", caixa, rotacao=rotacao)) == [Palavra("CT", caixa, False)]


@pytest.mark.parametrize(
    "rotacao", [179.5, 180.0, 180.9], ids=["abaixo-de-180", "em-180", "acima-de-180"]
)
def test_texto_de_cabeca_para_baixo_e_repartido_espelhado(rotacao: float) -> None:
    assert _palavras(texto("CT 12", (0.0, 0.0, 50.0, 10.0), origem="glifo", rotacao=rotacao)) == [
        Palavra("CT", (30.0, 0.0, 50.0, 10.0), False),
        Palavra("12", (0.0, 0.0, 20.0, 10.0), False),
    ]


@pytest.mark.parametrize(
    "rotacao", [0.9, 359.5, -0.5], ids=["pouco-acima-de-0", "pouco-abaixo-de-360", "negativa"]
)
def test_tolerancia_de_um_grau_reparte(rotacao: float) -> None:
    assert not any(
        palavra.inteira
        for palavra in _palavras(
            texto("CT 12", (0.0, 0.0, 50.0, 10.0), origem="glifo", rotacao=rotacao)
        )
    )


@pytest.mark.parametrize(
    "rotacao",
    [1.5, 90.0, 178.5, 181.5, 358.5, math.nan, math.inf],
    ids=["1.5", "90", "178.5", "181.5", "358.5", "nan", "inf"],
)
def test_fora_da_tolerancia_nao_reparte(rotacao: float) -> None:
    caixa: Caixa = (0.0, 0.0, 50.0, 10.0)

    assert _palavras(texto("CT 12", caixa, origem="glifo", rotacao=rotacao)) == [
        Palavra("CT", caixa, True),
        Palavra("12", caixa, True),
    ]


def test_texto_de_glifo_horizontal_e_repartido() -> None:
    assert not any(
        palavra.inteira
        for palavra in _palavras(texto("CT 12", (0.0, 0.0, 50.0, 10.0), origem="glifo"))
    )


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

    # 1 moldura, 2 palavras, 1 segmento e 2 caminhos: o retângulo fora da página não vira
    # moldura, e nem seus segmentos nem seu caminho são indexados.
    assert contexto_gramaticas(pagina).orcamento.gasto == 1 + 2 + 1 + 2


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
