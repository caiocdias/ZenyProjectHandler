# mypy: disable-error-code="no-untyped-call"
"""Ataque ao núcleo das gramáticas: bordas, paridade com o motor atual e custo por contagem."""

from __future__ import annotations

import ast
import dataclasses
import math
import random
import re
import sys
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from types import FrameType
from typing import Any

import pymupdf
import pytest
from tests.fixtures.symbol_grammars import paginas
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    estilo,
    linha,
    pagina_gramatica,
    poligono,
    retangulo_traco,
    texto,
)

from zeny_project_handler.adapters.analysis import declarative_symbols, pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.drawing_model import symbol_grammars
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Arco,
    Caixa,
    Caminho,
    Circulo,
    Cor,
    ItemCaminho,
    Polilinha,
    Ponto,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    LIMITE_CONSULTAS_PAGINA,
    ContextoGramatica,
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
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_modelo_com_indices

LIMITES: Caixa = (0.0, 0.0, 300.0, 300.0)
TUDO: Caixa = (-16.0, -16.0, 316.0, 316.0)
PRETO: Cor = (0.0, 0.0, 0.0)
FORMA_DO_MOTOR = {"rectangle": "retangulo", "ellipse": "elipse", "diamond": "losango"}


def _grade(itens: list[tuple[Caixa, str]], limites: Caixa = LIMITES) -> GradeEspacial[str]:
    return GradeEspacial(itens, limites, OrcamentoConsultas(1_000_000))


def _cadeia(*pontos: Ponto) -> tuple[ItemCaminho, ...]:
    return tuple(ItemCaminho("l", par) for par in pairwise(pontos))


def _caminho(*subcaminhos: tuple[ItemCaminho, ...]) -> Caminho:
    return Caminho(subcaminhos, estilo(), "traco", 0)


def _dois_arcos(cx: float, cy: float, raio: float) -> tuple[ItemCaminho, ...]:
    alca = 4.0 / 3.0 * raio
    return (
        ItemCaminho(
            "c",
            ((cx + raio, cy), (cx + raio, cy + alca), (cx - raio, cy + alca), (cx - raio, cy)),
        ),
        ItemCaminho(
            "c",
            ((cx - raio, cy), (cx - raio, cy - alca), (cx + raio, cy - alca), (cx + raio, cy)),
        ),
    )


def _molduras(pagina: PaginaGramatica) -> list[tuple[str, Caixa, int]]:
    return [(m.forma, m.caixa, m.caminho) for m in contexto_gramaticas(pagina).molduras]


def _palavras(*textos: Any) -> list[Palavra]:
    return contexto_gramaticas(pagina_gramatica((), textos)).grade_palavras.consultar(TUDO)


def _segmentos(contexto: ContextoGramatica) -> list[Segmento]:
    return contexto.grade_segmentos.consultar(TUDO)


# --- contrato público ---------------------------------------------------------------------


def test_limite_padrao_do_contexto_e_o_do_plano() -> None:
    assert LIMITE_CONSULTAS_PAGINA == 2_000_000

    orcamento = contexto_gramaticas(pagina_gramatica(())).orcamento

    orcamento.gastar(2_000_000)
    with pytest.raises(TetoGramaticasExcedido):
        orcamento.gastar()


def test_tipos_de_valor_sao_imutaveis_e_sem_dict() -> None:
    contexto = contexto_gramaticas(pagina_gramatica(()))
    caixa: Caixa = (0.0, 0.0, 1.0, 1.0)
    casos: list[tuple[object, str]] = [
        (Moldura("elipse", caixa, 0), "caminho"),
        (Segmento((0.0, 0.0), (1.0, 1.0), 0), "caminho"),
        (Palavra("A", caixa, False), "texto"),
        (contexto.pagina, "translucidos"),
        (contexto, "molduras"),
    ]

    for valor, campo in casos:
        assert not hasattr(valor, "__dict__")
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(valor, campo, None)


def test_teto_e_falha_de_fonte_sao_excecoes_distintas() -> None:
    """A E06.2.2 traduz uma em `FORA_DOMINIO` e a outra em `FALHA` (R-3 e R-8)."""
    assert not issubclass(TetoGramaticasExcedido, FonteGramaticaFalhou)
    assert not issubclass(FonteGramaticaFalhou, TetoGramaticasExcedido)


@pytest.mark.parametrize(
    "modulo",
    [symbol_grammars, paginas],
    ids=["nucleo", "fixture"],
)
def test_nucleo_e_fixture_nao_importam_pymupdf_nem_o_motor(modulo: Any) -> None:
    arvore = ast.parse(Path(modulo.__file__).read_text(encoding="utf-8"))

    importados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            importados.add(no.module or "")
            importados.update(alias.name for alias in no.names)

    assert importados
    assert not {nome for nome in importados if "pymupdf" in nome or "declarative_symbols" in nome}


# --- orçamento ----------------------------------------------------------------------------


def test_orcamento_estourado_continua_estourando() -> None:
    """Tudo ou nada (R-3): quem engolir a exceção não ganha consultas de graça."""
    orcamento = OrcamentoConsultas(1)
    orcamento.gastar()
    with pytest.raises(TetoGramaticasExcedido):
        orcamento.gastar()

    with pytest.raises(TetoGramaticasExcedido):
        orcamento.gastar()


# --- grade --------------------------------------------------------------------------------


def _toca(a: Caixa, b: Caixa) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _recorte(caixa: Caixa, limites: Caixa) -> Caixa | None:
    x0, y0 = max(caixa[0], limites[0]), max(caixa[1], limites[1])
    x1, y1 = min(caixa[2], limites[2]), min(caixa[3], limites[3])
    return (x0, y0, x1, y1) if x0 <= x1 and y0 <= y1 else None


@pytest.mark.parametrize("semente", range(6))
def test_grade_nunca_perde_item_que_toca_a_consulta(semente: int) -> None:
    """Contra a varredura: coordenadas em bordas de célula, negativas e além dos limites."""
    rng = random.Random(semente)
    origens = (-40.0, -16.0, -8.0, 0.0, 15.5, 16.0, 32.0, 48.0, 100.0, 299.0, 316.0, 330.0)
    tamanhos = (0.0, 1.0, 16.0, 40.0, 120.0, 500.0)

    def sortear() -> Caixa:
        x0, y0 = rng.choice(origens), rng.choice(origens)
        return (x0, y0, x0 + rng.choice(tamanhos), y0 + rng.choice(tamanhos))

    itens = [(sortear(), indice) for indice in range(150)]
    grade = GradeEspacial(itens, TUDO, OrcamentoConsultas(10**9))

    for _ in range(150):
        consulta = sortear()
        resultado = grade.consultar(consulta)
        assert resultado == sorted(set(resultado))
        recorte_da_consulta = _recorte(consulta, TUDO)
        for caixa, indice in itens:
            recorte_do_item = _recorte(caixa, TUDO)
            if recorte_do_item is None:
                assert indice not in resultado
            elif recorte_da_consulta is not None and _toca(recorte_do_item, recorte_da_consulta):
                assert indice in resultado


@pytest.mark.parametrize(
    ("caixa", "grande"),
    [
        ((0.0, 0.0, 127.0, 127.0), False),
        ((0.0, 0.0, 128.0, 127.0), True),
        ((0.0, 0.0, 1023.0, 1.0), False),
        ((0.0, 0.0, 1024.0, 1.0), True),
    ],
    ids=["8x8-celulas", "9x8-celulas", "64x1-celulas", "65x1-celulas"],
)
def test_teto_de_64_celulas_decide_quem_vai_para_grandes(caixa: Caixa, grande: bool) -> None:
    grade = _grade([(caixa, "x")], (0.0, 0.0, 2000.0, 2000.0))

    assert grade._grandes == ([0] if grande else [])
    assert not grade._celulas if grande else len(grade._celulas) <= 64
    assert grade.consultar((1.0, 0.0, 2.0, 1.0)) == ["x"]


def test_grandes_e_celulas_saem_juntos_na_ordem_de_insercao() -> None:
    grade = _grade(
        [
            ((1.0, 1.0, 2.0, 2.0), "antes"),
            ((-1e300, -1e300, 1e300, 1e300), "enorme"),
            ((3.0, 3.0, 4.0, 4.0), "depois"),
        ]
    )

    assert grade.consultar((1.0, 1.0, 4.0, 4.0)) == ["antes", "enorme", "depois"]


def test_valores_iguais_em_entradas_distintas_nao_se_fundem() -> None:
    """ "Sem repetir" é por entrada: a deduplicação por caixa é de `casar_variantes` (R-10)."""
    caixa: Caixa = (1.0, 1.0, 2.0, 2.0)

    assert _grade([(caixa, "x"), (caixa, "x")]).consultar(caixa) == ["x", "x"]


# --- custo, por contagem ------------------------------------------------------------------


def test_construir_a_grade_custa_um_por_item_e_o_trabalho_fica_em_64_vezes_o_gasto() -> None:
    """Decisão 4 do desenvolvedor: o gasto conta item distinto; as entradas de célula, até 64."""
    orcamento = OrcamentoConsultas(1_000_000)
    caixa: Caixa = (0.0, 0.0, 127.0, 127.0)

    grade = GradeEspacial([(caixa, indice) for indice in range(50)], LIMITES, orcamento)

    assert orcamento.gasto == 50
    assert sum(len(lista) for lista in grade._celulas.values()) == 64 * 50

    assert grade.consultar(caixa) == list(range(50))
    assert orcamento.gasto == 100


def test_grandes_cobram_em_toda_consulta_ate_estourar() -> None:
    quantidade = 100
    consultas_pagas = 3
    orcamento = OrcamentoConsultas(quantidade * (1 + consultas_pagas))
    grade = GradeEspacial(
        [((-1e300, -1e300, 1e300, 1e300), indice) for indice in range(quantidade)],
        LIMITES,
        orcamento,
    )

    for passo in range(consultas_pagas):
        grade.consultar((float(passo), 0.0, float(passo) + 1.0, 1.0))
    assert orcamento.gasto == quantidade * (1 + consultas_pagas)

    with pytest.raises(TetoGramaticasExcedido):
        grade.consultar((50.0, 50.0, 51.0, 51.0))


def _pagina_de_molduras(quantidade: int) -> PaginaGramatica:
    caminhos = [retangulo_traco((10.0, 10.0, 30.0, 30.0), ordem=i) for i in range(quantidade)]
    return pagina_gramatica(caminhos, primitivas=())


def _pagina_de_segmentos(quantidade: int) -> PaginaGramatica:
    caminhos = [linha((10.0, 10.0), (12.0, 12.0), ordem=i) for i in range(quantidade)]
    return pagina_gramatica(caminhos, primitivas=())


def _pagina_de_spans(quantidade: int) -> PaginaGramatica:
    textos = [texto("CT", (10.0, 10.0, 12.0, 12.0)) for _ in range(quantidade)]
    return pagina_gramatica((), textos)


def _pagina_de_um_span_longo(quantidade: int) -> PaginaGramatica:
    return pagina_gramatica((), (texto("A " * quantidade, (10.0, 10.0, 12.0, 12.0)),))


@pytest.mark.parametrize(
    "montar",
    [_pagina_de_molduras, _pagina_de_segmentos, _pagina_de_spans, _pagina_de_um_span_longo],
    ids=["molduras", "segmentos", "spans", "um-span-longo"],
)
def test_teto_ao_construir_e_exato_e_deterministico(
    montar: Callable[[int], PaginaGramatica],
) -> None:
    pagina = montar(50)

    gasto = contexto_gramaticas(pagina).orcamento.gasto

    assert gasto >= 50
    assert contexto_gramaticas(pagina).orcamento.gasto == gasto
    assert contexto_gramaticas(pagina, limite=gasto).orcamento.gasto == gasto
    with pytest.raises(TetoGramaticasExcedido):
        contexto_gramaticas(pagina, limite=gasto - 1)


def test_as_quatro_grades_gastam_o_mesmo_orcamento() -> None:
    contexto = contexto_gramaticas(
        pagina_gramatica(
            (retangulo_traco((10.0, 10.0, 30.0, 30.0)), linha((50.0, 50.0), (60.0, 50.0))),
            (texto("CT", (70.0, 70.0, 90.0, 80.0)),),
            primitivas=(),
        )
    )
    grades: tuple[GradeEspacial[Any], ...] = (
        contexto.grade_molduras,
        contexto.grade_palavras,
        contexto.grade_segmentos,
        contexto.grade_caminhos,
    )

    for grade in grades:
        antes = contexto.orcamento.gasto
        assert grade.consultar(TUDO)
        assert contexto.orcamento.gasto > antes


def _chamadas_ao_construir(pagina: PaginaGramatica) -> int:
    """Chamadas e retomadas de função durante a construção: laço quadrático aparece na contagem."""
    chamadas = 0

    def contar(_quadro: FrameType, evento: str, _argumento: object) -> None:
        nonlocal chamadas
        if evento in {"call", "c_call"}:
            chamadas += 1

    anterior = sys.getprofile()
    sys.setprofile(contar)
    try:
        contexto_gramaticas(pagina)
    finally:
        sys.setprofile(anterior)
    return chamadas


def _pagina_sobreposta(quantidade: int) -> PaginaGramatica:
    """Itens sobrepostos nas mesmas células, todos diferentes: uma busca por igual não para cedo."""
    caminhos: list[Caminho] = []
    primitivas: list[Polilinha | Circulo | Arco] = []
    textos = []
    for i in range(quantidade):
        d = i * 0.001
        x0, y0, x1, y1 = 10.0 + d, 10.0 + d, 30.0 + d, 30.0 + d
        cantos: tuple[Ponto, ...] = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        caminhos += [
            retangulo_traco((x0, y0, x1, y1), ordem=3 * i),
            linha((x0, y0), (x1, y1), ordem=3 * i + 1),
            circulo_bezier((20.0 + d, 20.0 + d), 10.0, ordem=3 * i + 2),
        ]
        primitivas += [
            Polilinha(cantos, True, estilo(), (3 * i,)),
            Polilinha(cantos, True, estilo(), (3 * i + 1,)),
            Circulo((20.0 + d, 20.0 + d), 10.0, estilo(), (3 * i + 2,)),
        ]
        textos.append(texto("CT 12", (x0, y0, x1, y0 + 2.0)))
    return pagina_gramatica(caminhos, textos, primitivas=primitivas)


def test_trabalho_fora_do_orcamento_e_linear_em_itens_sobrepostos() -> None:
    """O orçamento só cobra o que foi indexado: o resto da construção não pode ser quadrático na
    densidade local (Review Focus 1)."""
    menor = _chamadas_ao_construir(_pagina_sobreposta(200))
    maior = _chamadas_ao_construir(_pagina_sobreposta(400))

    assert menor > 200
    assert maior <= 2.1 * menor


# --- molduras: proveniência (R-10) --------------------------------------------------------


def test_quatro_tracos_fora_de_ordem_usam_a_menor_posicao() -> None:
    outro = retangulo_traco((100.0, 100.0, 120.0, 120.0))
    tracos = (
        linha((30.0, 10.0), (30.0, 30.0)),
        linha((10.0, 30.0), (10.0, 10.0)),
        linha((10.0, 10.0), (30.0, 10.0)),
        linha((30.0, 30.0), (10.0, 30.0)),
    )

    assert _molduras(pagina_gramatica((outro, *tracos))) == [
        ("retangulo", (100.0, 100.0, 120.0, 120.0), 0),
        ("retangulo", (10.0, 10.0, 30.0, 30.0), 1),
    ]


def test_molduras_de_primitivas_vem_depois_das_de_caminho() -> None:
    tracos = (
        linha((10.0, 10.0), (30.0, 10.0)),
        linha((30.0, 10.0), (30.0, 30.0)),
        linha((30.0, 30.0), (10.0, 30.0)),
        linha((10.0, 30.0), (10.0, 10.0)),
    )
    depois = retangulo_traco((100.0, 100.0, 120.0, 120.0))

    assert _molduras(pagina_gramatica((*tracos, depois))) == [
        ("retangulo", (100.0, 100.0, 120.0, 120.0), 4),
        ("retangulo", (10.0, 10.0, 30.0, 30.0), 0),
    ]


def test_mesmo_retangulo_pintado_duas_vezes_no_mesmo_estilo_sao_duas_molduras() -> None:
    caixa: Caixa = (10.0, 10.0, 30.0, 30.0)

    assert _molduras(pagina_gramatica((retangulo_traco(caixa), retangulo_traco(caixa)))) == [
        ("retangulo", caixa, 0),
        ("retangulo", caixa, 1),
    ]


def test_primitiva_de_origem_mista_fica_mesmo_com_uma_origem_ja_em_moldura() -> None:
    """Decisão 8: só se descarta a primitiva cujas origens todas já geraram a forma."""
    retangulo_a = _cadeia((10.0, 10.0), (30.0, 10.0), (30.0, 30.0), (10.0, 30.0), (10.0, 10.0))
    metade_de_b = (
        _cadeia((50.0, 50.0), (70.0, 50.0)),
        _cadeia((70.0, 50.0), (70.0, 70.0)),
    )
    outra_metade_de_b = (
        linha((70.0, 70.0), (50.0, 70.0)),
        linha((50.0, 70.0), (50.0, 50.0)),
    )

    pagina = pagina_gramatica((_caminho(retangulo_a, *metade_de_b), *outra_metade_de_b))

    assert _molduras(pagina) == [
        ("retangulo", (10.0, 10.0, 30.0, 30.0), 0),
        ("retangulo", (50.0, 50.0, 70.0, 70.0), 0),
    ]


def test_primitiva_de_outra_forma_no_mesmo_caminho_nao_e_descartada() -> None:
    retangulo = _cadeia((10.0, 10.0), (30.0, 10.0), (30.0, 30.0), (10.0, 30.0), (10.0, 10.0))

    molduras = _molduras(pagina_gramatica((_caminho(retangulo, _dois_arcos(100.0, 100.0, 10.0)),)))

    assert [(forma, caminho) for forma, _, caminho in molduras] == [
        ("retangulo", 0),
        ("elipse", 0),
    ]


# --- molduras: geometria ------------------------------------------------------------------


@pytest.mark.parametrize(
    "pontos",
    [
        ((10.0, 10.0), (10.0, 30.0), (30.0, 30.0), (30.0, 10.0)),
        ((30.0, 30.0), (30.0, 10.0), (10.0, 10.0), (10.0, 30.0)),
        ((30.0, 10.0), (10.0, 10.0), (10.0, 30.0), (30.0, 30.0)),
    ],
    ids=["comeca-na-vertical", "comeca-no-canto-oposto", "anti-horario"],
)
def test_retangulo_nao_depende_do_primeiro_lado(pontos: tuple[Ponto, ...]) -> None:
    pagina = pagina_gramatica((poligono(pontos),), primitivas=())

    assert _molduras(pagina) == [("retangulo", (10.0, 10.0, 30.0, 30.0), 0)]


@pytest.mark.parametrize(
    ("desvio", "forma_esperada"),
    [(0.009, ["retangulo"]), (0.02, [])],
    ids=["dentro-da-tolerancia", "fora-da-tolerancia"],
)
def test_tolerancia_de_alinhamento_do_retangulo(desvio: float, forma_esperada: list[str]) -> None:
    caminho = _caminho(
        _cadeia((10.0, 10.0), (30.0, 10.0 + desvio), (30.0, 30.0), (10.0, 30.0), (10.0, 10.0))
    )

    molduras = contexto_gramaticas(pagina_gramatica((caminho,), primitivas=())).molduras

    assert [m.forma for m in molduras] == forma_esperada


@pytest.mark.parametrize(
    ("folga", "forma_esperada"),
    [(0.009, ["retangulo"]), (0.3, [])],
    ids=["dentro-da-tolerancia", "fora-da-tolerancia"],
)
def test_fechamento_do_retangulo_de_caminho(folga: float, forma_esperada: list[str]) -> None:
    caminho = _caminho(
        _cadeia((10.0, 10.0), (30.0, 10.0), (30.0, 30.0), (10.0, 30.0), (10.0, 10.0 + folga))
    )

    molduras = contexto_gramaticas(pagina_gramatica((caminho,), primitivas=())).molduras

    assert [m.forma for m in molduras] == forma_esperada


def test_retangulo_com_folga_de_fechamento_ainda_entra_pela_polilinha() -> None:
    """As duas rotas de `fechado`: o caminho recusa, a polilinha funde em 0,5 pt, e o subcaminho
    que não virou moldura de caminho continua nos segmentos."""
    caminho = _caminho(
        _cadeia((10.0, 10.0), (30.0, 10.0), (30.0, 30.0), (10.0, 30.0), (10.0, 10.3))
    )

    contexto = contexto_gramaticas(pagina_gramatica((caminho,)))

    assert [(m.forma, m.caminho) for m in contexto.molduras] == [("retangulo", 0)]
    assert len(_segmentos(contexto)) == 4


@pytest.mark.parametrize(
    ("caixa", "entra"),
    [
        ((280.0, 280.0, 300.0, 300.0), True),
        ((-10.0, 10.0, 10.0, 30.0), True),
        ((295.0, 295.0, 315.0, 315.0), True),
        ((-20.0, 10.0, 0.0, 30.0), False),
        ((10.0, 300.0, 30.0, 320.0), False),
    ],
    ids=[
        "canto-por-dentro",
        "atravessa-a-esquerda",
        "atravessa-o-canto",
        "encostada-a-esquerda",
        "encostada-embaixo",
    ],
)
def test_moldura_na_borda_da_pagina_mantem_a_caixa_inteira(caixa: Caixa, entra: bool) -> None:
    pagina = pagina_gramatica((retangulo_traco(caixa),), primitivas=())

    assert _molduras(pagina) == ([("retangulo", caixa, 0)] if entra else [])


def test_elipse_de_lado_zero_nao_entra() -> None:
    curva = ItemCaminho("c", ((50.0, 10.0), (50.0, 20.0), (50.0, 30.0), (50.0, 40.0)))
    caminho = _caminho((curva, curva, curva, curva))

    assert _molduras(pagina_gramatica((caminho,))) == []


def test_coordenadas_nao_finitas_nao_viram_moldura() -> None:
    nan = math.nan
    curva = ItemCaminho("c", ((nan, 10.0), (50.0, 20.0), (50.0, 30.0), (50.0, 40.0)))
    caminhos = (
        retangulo_traco((nan, 10.0, 30.0, 30.0)),
        retangulo_traco((10.0, math.inf, 30.0, 30.0)),
        _caminho((curva, curva, curva, curva)),
    )
    primitivas = (
        Polilinha(((nan, 1.0), (9.0, 1.0), (9.0, 9.0), (1.0, 9.0)), True, estilo(), (0,)),
        Circulo((nan, 50.0), 5.0, estilo(), (0,)),
        Circulo((math.inf, 50.0), 5.0, estilo(), (0,)),
    )

    contexto = contexto_gramaticas(pagina_gramatica(caminhos, primitivas=primitivas))

    assert contexto.molduras == ()
    assert contexto.caixas_caminhos == {}


_LIXO: tuple[float, ...] = (
    math.nan,
    math.inf,
    -math.inf,
    1e308,
    -1e308,
    1e300,
    5e-324,
    -0.0,
    16.0,
    150.0,
    250.0,
)


@pytest.mark.parametrize("semente", range(4))
def test_coordenada_lixo_nao_levanta_e_moldura_sai_finita_e_na_pagina(semente: int) -> None:
    """Review Focus 2 e 5: nada do que entra como número faz o núcleo levantar outra exceção."""
    rng = random.Random(semente)
    pagina: Caixa = (0.0, 0.0, 300.0, 300.0)

    def valor() -> float:
        return rng.choice(_LIXO)

    def ponto() -> Ponto:
        return (valor(), valor())

    def caixa() -> Caixa:
        return (valor(), valor(), valor(), valor())

    for _ in range(200):
        pontos = [ponto() for _ in range(5)]
        fechado = _cadeia(*pontos[:4], pontos[0])
        curvas = tuple(ItemCaminho("c", (ponto(), ponto(), ponto(), ponto())) for _ in range(4))
        conteudo = pagina_gramatica(
            (_caminho(fechado), _caminho(curvas), _caminho(_cadeia(ponto(), ponto()))),
            (
                texto("CT 12", caixa(), rotacao=valor()),
                texto("CT 12", caixa(), origem="shx", rotacao=valor()),
                texto(" ct ", caixa(), origem="glifo", rotacao=rng.choice((0.0, 180.0))),
            ),
            primitivas=(
                Polilinha(tuple(pontos[:4]), True, estilo(), (0,)),
                Circulo(ponto(), valor(), estilo(), (1,)),
                Arco(ponto(), valor(), valor(), valor(), estilo(), (1,)),
            ),
        )

        contexto = contexto_gramaticas(conteudo)

        for moldura in contexto.molduras:
            assert all(math.isfinite(v) for v in moldura.caixa)
            assert intersecta(moldura.caixa, pagina)
        for consulta in (caixa(), (-math.inf, -math.inf, math.inf, math.inf)):
            contexto.grade_molduras.consultar(consulta)
            contexto.grade_palavras.consultar(consulta)
            contexto.grade_segmentos.consultar(consulta)
            contexto.grade_caminhos.consultar(consulta)


@pytest.mark.parametrize("semente", range(2))
def test_is_diamond_igual_ao_do_motor(semente: int) -> None:
    """Cópia dos limiares (R-1) contra o original, com lados e ruído em torno da tolerância."""
    rng = random.Random(semente)
    divergencias = []
    for _ in range(2_000):
        cx, cy = rng.uniform(0.0, 100.0), rng.uniform(0.0, 100.0)
        largura = rng.choice((2.0, 3.9, 4.0, 5.0, 12.5, 13.0, 30.0, 100.0))
        altura = rng.choice((2.0, 3.9, 4.0, 5.0, 12.5, 13.0, 30.0, 100.0))
        ruido = rng.choice((0.0, 0.5, 1.0, 1.2, 3.0))
        cantos = (
            (cx, cy - altura / 2),
            (cx + largura / 2, cy),
            (cx, cy + altura / 2),
            (cx - largura / 2, cy),
        )
        pontas = [
            (x + rng.uniform(-ruido, ruido), y + rng.uniform(-ruido, ruido))
            for i in range(4)
            for x, y in (cantos[i], cantos[(i + 1) % 4])
        ]
        xs, ys = [p[0] for p in pontas], [p[1] for p in pontas]
        caixa: Caixa = (min(xs), min(ys), max(xs), max(ys))
        nucleo = symbol_grammars._is_diamond(pontas, caixa)
        motor = declarative_symbols._is_diamond(
            [pymupdf.Point(p) for p in pontas], pymupdf.Rect(caixa)
        )
        if nucleo != motor:
            divergencias.append((pontas, caixa, nucleo, motor))

    assert divergencias == []


# --- molduras: paridade com `_frame_candidates` em PDF real ---------------------------------


def _dois_discos_de_dois_arcos(forma: Any) -> None:
    for cx, cy in ((50.0, 50.0), (150.0, 150.0)):
        alca = 4.0 / 3.0 * 10.0
        forma.draw_bezier((cx + 10, cy), (cx + 10, cy + alca), (cx - 10, cy + alca), (cx - 10, cy))
        forma.draw_bezier((cx - 10, cy), (cx - 10, cy - alca), (cx + 10, cy - alca), (cx + 10, cy))


def _quatro_curvas_com_controle_fora_da_caixa(forma: Any) -> None:
    forma.draw_bezier((50, 50), (10, 120), (120, 10), (100, 50))
    forma.draw_bezier((100, 50), (200, 60), (90, 200), (100, 100))
    forma.draw_bezier((100, 100), (10, 300), (100, 120), (50, 100))
    forma.draw_bezier((50, 100), (5, 90), (40, 60), (50, 50))


def _dois_retangulos(forma: Any) -> None:
    forma.draw_rect(pymupdf.Rect(10, 10, 40, 40))
    forma.draw_rect(pymupdf.Rect(50, 50, 90, 90))


def _losango_de_quatro_linhas(forma: Any) -> None:
    forma.draw_line((250, 10), (270, 30))
    forma.draw_line((270, 30), (250, 50))
    forma.draw_line((250, 50), (230, 30))
    forma.draw_line((230, 30), (250, 10))


_Achado = tuple[str, tuple[float, ...], int]


def _no_pdf(
    desenhar: Callable[[Any], object], preenchimento: Cor | None = None
) -> tuple[list[_Achado], list[_Achado]]:
    """As molduras do motor e as do núcleo, cada uma com o índice cru de `get_drawings`."""
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=400, height=400)
        forma = pagina.new_shape()
        desenhar(forma)
        forma.finish(color=PRETO, fill=preenchimento)
        forma.commit()
        motor = [
            (
                FORMA_DO_MOTOR[tipo],
                tuple(round(float(v), 3) for v in (caixa.x0, caixa.y0, caixa.x1, caixa.y1)),
                indice,
            )
            for tipo, caixa, indice in declarative_symbols._frame_candidates(
                tuple(pagina.get_drawings(extended=True))
            )
        ]
        modelo, indices = pagina_modelo_com_indices(pagina, 0)
    contexto = contexto_gramaticas(PaginaGramatica(modelo, indices, frozenset()))
    nucleo: list[_Achado] = [
        (m.forma, tuple(round(v, 3) for v in m.caixa), indices[m.caminho])
        for m in contexto.molduras
    ]
    return motor, nucleo


@pytest.mark.parametrize(
    ("desenhar", "preenchimento"),
    [
        pytest.param(lambda f: f.draw_rect(pymupdf.Rect(10, 10, 40, 30)), None, id="re"),
        pytest.param(
            lambda f: f.draw_rect(pymupdf.Rect(10, 10, 40, 30)), (0.5, 0.5, 0.5), id="re-preenchido"
        ),
        pytest.param(lambda f: f.draw_rect(pymupdf.Rect(10, 10, 10, 40)), None, id="re-lado-zero"),
        pytest.param(_dois_retangulos, None, id="dois-re-no-mesmo-caminho"),
        pytest.param(lambda f: f.draw_circle((100, 50), 10), None, id="circulo"),
        pytest.param(lambda f: f.draw_circle((100, 50), 10), (1.0, 0.0, 0.0), id="disco"),
        pytest.param(lambda f: f.draw_oval(pymupdf.Rect(150, 40, 190, 60)), None, id="oval"),
        pytest.param(_quatro_curvas_com_controle_fora_da_caixa, None, id="controle-fora-da-caixa"),
        pytest.param(_dois_discos_de_dois_arcos, None, id="dois-discos-de-dois-arcos"),
        pytest.param(
            lambda f: f.draw_polyline([(250, 10), (270, 30), (250, 50), (230, 30), (250, 10)]),
            None,
            id="losango-polilinha",
        ),
        pytest.param(_losango_de_quatro_linhas, None, id="losango-quatro-linhas"),
        pytest.param(
            lambda f: f.draw_quad(pymupdf.Quad((300, 10), (320, 30), (280, 30), (300, 50))),
            None,
            id="losango-quad",
        ),
        pytest.param(
            lambda f: f.draw_polyline([(50, 10), (50, 50), (70, 30), (30, 30), (50, 10)]),
            None,
            id="gravata-como-no-motor",
        ),
        pytest.param(
            lambda f: f.draw_polyline([(250, 10), (270, 30), (250, 50), (230, 30), (250.4, 10.4)]),
            None,
            id="losango-aberto-de-cinco-linhas",
        ),
    ],
)
def test_molduras_iguais_as_do_motor(
    desenhar: Callable[[Any], object], preenchimento: Cor | None
) -> None:
    motor, nucleo = _no_pdf(desenhar, preenchimento)

    assert nucleo == motor


# --- segmentos ----------------------------------------------------------------------------


def test_tracos_de_moldura_separada_continuam_nos_segmentos() -> None:
    """A regra só exclui o subcaminho que é moldura fechada de 4 `l`: as guardas os veem."""
    tracos = (
        linha((10.0, 10.0), (30.0, 10.0)),
        linha((30.0, 10.0), (30.0, 30.0)),
        linha((30.0, 30.0), (10.0, 30.0)),
        linha((10.0, 30.0), (10.0, 10.0)),
    )

    contexto = contexto_gramaticas(pagina_gramatica(tracos))

    assert len(contexto.molduras) == 1
    assert [s.caminho for s in _segmentos(contexto)] == [0, 1, 2, 3]


def test_subcaminho_de_quatro_lados_que_nao_virou_moldura_fica_nos_segmentos() -> None:
    contexto = contexto_gramaticas(
        pagina_gramatica((retangulo_traco((10.0, 10.0, 10.0, 40.0)),), primitivas=())
    )

    assert contexto.molduras == ()
    assert len(_segmentos(contexto)) == 4


def test_segmento_mantem_o_sentido_e_e_achado_pela_caixa_normalizada() -> None:
    contexto = contexto_gramaticas(
        pagina_gramatica((linha((30.0, 40.0), (10.0, 20.0), ordem=9),), primitivas=())
    )

    assert contexto.grade_segmentos.consultar((15.0, 25.0, 16.0, 26.0)) == [
        Segmento((30.0, 40.0), (10.0, 20.0), 0)
    ]


def test_segmento_gigante_e_recortado_e_nao_multiplica_celulas() -> None:
    contexto = contexto_gramaticas(
        pagina_gramatica((linha((-1e300, 50.0), (1e300, 50.0)),), primitivas=())
    )

    assert contexto.grade_segmentos._grandes == []
    assert len(contexto.grade_segmentos._celulas) == 21
    assert contexto.grade_segmentos.consultar((100.0, 49.0, 101.0, 51.0)) == [
        Segmento((-1e300, 50.0), (1e300, 50.0), 0)
    ]
    assert contexto.grade_segmentos.consultar((100.0, 200.0, 101.0, 201.0)) == []


# --- caminhos e contexto ------------------------------------------------------------------


def test_caixa_de_caminho_fora_da_pagina_existe_mas_nao_entra_na_grade() -> None:
    contexto = contexto_gramaticas(
        pagina_gramatica(
            (
                retangulo_traco((10.0, 10.0, 30.0, 30.0)),
                retangulo_traco((1000.0, 1000.0, 1020.0, 1020.0)),
            ),
            primitivas=(),
        )
    )

    assert contexto.caixas_caminhos[1] == (1000.0, 1000.0, 1020.0, 1020.0)
    assert contexto.grade_caminhos.consultar(TUDO) == [0]


def test_grade_de_molduras_traz_toda_moldura_do_contexto() -> None:
    contexto = contexto_gramaticas(
        pagina_gramatica(
            (
                retangulo_traco((-10.0, 10.0, 10.0, 30.0)),
                circulo_bezier((100.0, 100.0), 10.0),
                poligono(((200.0, 10.0), (220.0, 30.0), (200.0, 50.0), (180.0, 30.0))),
            )
        )
    )

    assert contexto.grade_molduras.consultar(TUDO) == list(contexto.molduras)
    assert len(contexto.molduras) == 3


@pytest.mark.parametrize(
    ("largura", "altura", "candidatos"),
    [(math.inf, math.inf, [0, 1]), (math.nan, math.nan, [0, 1]), (0.0, 0.0, [1])],
    ids=["infinita", "nan", "vazia"],
)
def test_pagina_de_dimensao_estranha_nao_quebra_o_contexto(
    largura: float, altura: float, candidatos: list[int]
) -> None:
    """Com item e consulta finitos, nada leva `math.floor` ao infinito. Sem limite finito, o
    retângulo em 1e300 cobriria células demais e vai para `grandes`."""
    pagina = pagina_gramatica(
        (retangulo_traco((1e300, 0.0, 1.1e300, 10.0)), retangulo_traco((10.0, 10.0, 30.0, 30.0))),
        (texto("CT 12", (10.0, 10.0, 60.0, 20.0)),),
        primitivas=(),
        largura=largura,
        altura=altura,
    )

    contexto = contexto_gramaticas(pagina)

    assert contexto.grade_caminhos.consultar((12.0, 12.0, 13.0, 13.0)) == candidatos


@pytest.mark.parametrize(
    "mediabox",
    ["[0 0 1e39 1e39]", "[-1e38 -1e38 3e38 3e38]"],
    ids=["acima-do-float32", "largura-acima-do-float32"],
)
def test_mediabox_gigante_nao_chega_como_pagina_nao_finita(mediabox: str) -> None:
    """A página não finita, único caminho até `math.floor(inf)`, não vem da PyMuPDF."""
    with pymupdf.open() as documento:
        xref = documento.new_page().xref
        documento.xref_set_key(xref, "MediaBox", mediabox)
        modelo, _ = pagina_modelo_com_indices(documento.load_page(0), 0)

    assert math.isfinite(modelo.largura)
    assert math.isfinite(modelo.altura)


# --- palavras -----------------------------------------------------------------------------


@pytest.mark.parametrize("origem", ["nativo", "glifo", "shx"])
@pytest.mark.parametrize(
    "rotacao",
    [0.0, 1.0, -1.0, 45.0, 90.0, 179.0, 180.0, 181.0, 270.0, 359.0, 360.0, 540.0, 720.0],
)
def test_nenhum_span_e_repartido_em_origem_ou_rotacao_alguma(origem: Any, rotacao: float) -> None:
    caixa: Caixa = (0.0, 0.0, 50.0, 10.0)

    assert _palavras(texto("CT 12", caixa, origem=origem, rotacao=rotacao)) == [
        Palavra("CT", caixa, True),
        Palavra("12", caixa, True),
    ]


@pytest.mark.parametrize(
    ("conteudo", "inteira"),
    [("CT", False), ("ct", False), ("  CT", True), ("CT  ", True), ("	CT	", True)],
    ids=["uma-palavra", "minuscula", "espacos-na-frente", "espacos-atras", "tabs"],
)
def test_nativo_de_uma_palavra_so_e_inteiro_se_tem_espaco_nas_pontas(
    conteudo: str, inteira: bool
) -> None:
    caixa: Caixa = (0.0, 0.0, 50.0, 10.0)

    assert _palavras(texto(conteudo, caixa)) == [Palavra("CT", caixa, inteira)]


@pytest.mark.parametrize("origem", ["nativo", "glifo", "shx"])
@pytest.mark.parametrize(
    "separador", ["	", chr(0xA0), " 	 "], ids=["tab", "espaco-duro", "espacos-mistos"]
)
def test_qualquer_espaco_separa_palavras_do_span_inteiro(separador: str, origem: Any) -> None:
    caixa: Caixa = (0.0, 0.0, 70.0, 10.0)

    assert _palavras(texto(f"CT{separador}12", caixa, origem=origem)) == [
        Palavra("CT", caixa, True),
        Palavra("12", caixa, True),
    ]


@pytest.mark.parametrize("rotacao", [0.0, 180.0])
def test_espacos_assimetricos_deixam_a_palavra_inteira_com_a_caixa_do_span(rotacao: float) -> None:
    caixa: Caixa = (0.0, 0.0, 30.0, 10.0)

    assert _palavras(texto(" ct", caixa, origem="glifo", rotacao=rotacao)) == [
        Palavra("CT", caixa, True)
    ]


def test_texto_vazio_nao_gera_palavra() -> None:
    assert _palavras(texto("", (0.0, 0.0, 40.0, 10.0))) == []


def test_bbox_invertida_nao_gera_palavra_nem_excecao() -> None:
    assert _palavras(texto("CT 12", (50.0, 0.0, 0.0, 10.0))) == []


def test_palavra_na_margem_entra_e_alem_dela_nao_gasta() -> None:
    pagina = pagina_gramatica(
        (),
        (
            texto("MARGEM", (305.0, 10.0, 310.0, 20.0)),
            texto("FORA", (320.0, 10.0, 330.0, 20.0)),
        ),
    )

    contexto = contexto_gramaticas(pagina)

    assert contexto.orcamento.gasto == 1
    assert [p.texto for p in contexto.grade_palavras.consultar(TUDO)] == ["MARGEM"]


@pytest.mark.parametrize(
    ("conteudo", "rotacao"),
    [
        ("CT 12 ab", 0),
        ("CT 12 ab", 180),
        ("  CT  12  ", 0),
        ("  CT  12  ", 180),
    ],
    ids=["em-pe", "invertido", "com-espacos-em-pe", "com-espacos-invertido"],
)
def test_texto_nativo_do_pdf_fica_com_a_caixa_do_span_que_contem_as_palavras_do_motor(
    conteudo: str, rotacao: int
) -> None:
    """O motor lê `words`; o núcleo guarda o span inteiro, que contém cada palavra dele."""
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=400, height=400)
        pagina.insert_text((200, 200), conteudo, fontname="cour", fontsize=10, rotate=rotacao)
        esperadas = [(str(w[4]).upper(), w[:4]) for w in pagina.get_text("words")]
        modelo, indices = pagina_modelo_com_indices(pagina, 0)
    contexto = contexto_gramaticas(PaginaGramatica(modelo, indices, frozenset()))

    palavras = contexto.grade_palavras.consultar((0.0, 0.0, 400.0, 400.0))

    assert [p.texto for p in palavras] == [texto_esperado for texto_esperado, _ in esperadas]
    assert all(p.inteira and p.caixa == modelo.textos[0].bbox for p in palavras)
    for palavra, (_, caixa) in zip(palavras, esperadas, strict=True):
        assert contem(
            palavra.caixa, (caixa[0] + 0.01, caixa[1] + 0.01, caixa[2] - 0.01, caixa[3] - 0.01)
        )


def test_span_vertical_do_pdf_fica_inteiro() -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=400, height=400)
        pagina.insert_text((200, 200), "CT 12", fontname="cour", fontsize=10, rotate=90)
        modelo, indices = pagina_modelo_com_indices(pagina, 0)
    contexto = contexto_gramaticas(PaginaGramatica(modelo, indices, frozenset()))

    palavras = contexto.grade_palavras.consultar((0.0, 0.0, 400.0, 400.0))

    assert [p.texto for p in palavras] == ["CT", "12"]
    assert all(p.inteira and p.caixa == modelo.textos[0].bbox for p in palavras)


# --- fontes (R-8) -------------------------------------------------------------------------


def test_toda_fonte_do_adaptador_esta_classificada_em_r8() -> None:
    """`_FONTES_CONSUMIDAS` é lista fechada: fonte nova sem classificar não bloquearia nada."""
    assert pymupdf_drawing_model.__file__ is not None
    codigo = Path(pymupdf_drawing_model.__file__).read_text(encoding="utf-8")

    nomes = set(re.findall(r'_fonte\(\s*"(\w+)"', codigo))

    assert {f"modelo.{nome}_falhou" for nome in nomes} == {
        "modelo.caminhos_falhou",
        "modelo.primitivas_falhou",
        "modelo.textos_nativos_falhou",
        "modelo.textos_shx_falhou",
        "modelo.glifos_falhou",
        "modelo.grupos_falhou",
        "modelo.imagens_falhou",
        "modelo.imagens_anotacao_falhou",
    }
    assert '"modelo.glifos_limitados"' in codigo
    assert '"modelo.glifos_desconhecidos"' in codigo


def test_falha_de_fonte_vem_antes_de_gastar_o_orcamento() -> None:
    pagina = pagina_gramatica(
        [retangulo_traco((10.0, 10.0, 30.0, 30.0), ordem=i) for i in range(10)],
        primitivas=(),
        diagnosticos=("modelo.caminhos_falhou",),
    )

    with pytest.raises(FonteGramaticaFalhou):
        contexto_gramaticas(pagina, limite=0)


# --- semântica de borda, contra a PyMuPDF ---------------------------------------------------

_VALORES = (0.0, 5.0, 10.0, 20.0)
_CAIXAS: list[Caixa] = [
    (x0, y0, x1, y1)
    for x0 in _VALORES
    for y0 in _VALORES
    for x1 in _VALORES
    for y1 in _VALORES
    if x0 <= x1 and y0 <= y1
]


def test_intersecta_igual_a_rect_intersects() -> None:
    assert [
        (a, b)
        for a in _CAIXAS
        for b in _CAIXAS
        if bool(pymupdf.Rect(a).intersects(pymupdf.Rect(b))) != intersecta(a, b)
    ] == []


def test_contem_igual_a_rect_contains_quando_a_externa_tem_area() -> None:
    externas = [c for c in _CAIXAS if c[0] < c[2] and c[1] < c[3]]

    assert [
        (a, b)
        for a in externas
        for b in _CAIXAS
        if bool(pymupdf.Rect(a).contains(pymupdf.Rect(b))) != contem(a, b)
    ] == []


def test_auxiliares_recusam_nan() -> None:
    caixa: Caixa = (0.0, 0.0, 10.0, 10.0)
    invalida: Caixa = (math.nan, 0.0, 5.0, 5.0)

    assert not contem(caixa, invalida)
    assert not contem(invalida, caixa)
    assert not intersecta(caixa, invalida)
    assert not intersecta(invalida, caixa)
    assert not ponto_em(caixa, (math.nan, 5.0))
    assert not ponto_em(invalida, (1.0, 1.0))


# --- a fixture que as próximas tarefas usam ---------------------------------------------------


def test_fixture_reconstroi_primitivas_e_desloca_os_indices() -> None:
    caminhos = (retangulo_traco((10.0, 10.0, 30.0, 30.0)), circulo_bezier((100.0, 100.0), 10.0))

    pagina = pagina_gramatica(
        caminhos, translucidos=frozenset({1}), diagnosticos=("modelo.glifos_desconhecidos",)
    )

    assert pagina.indices_crus == (10, 11)
    assert pagina.translucidos == frozenset({1})
    assert pagina.modelo.diagnosticos == ("modelo.glifos_desconhecidos",)
    assert [type(p) for p in pagina.modelo.primitivas] == [Polilinha, Circulo]
    assert pagina_gramatica(caminhos, primitivas=()).modelo.primitivas == ()
