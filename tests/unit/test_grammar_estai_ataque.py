# mypy: disable-error-code="no-untyped-call"
"""Ataques à gramática `forked_stem` (E06.3.4, Task 2), pelo testador.

Desenhos autorais, relativos à haste e ao dente da fixture `estai.py`; nada vem de folha real.
Cobre o que a suíte do desenvolvedor não tenta: formas com a assinatura do garfo que não são
estai (seta fechada, continuação em polilinha, cota, chevrons, linha de chamada), posse de
componentes entre desenhos vizinhos, deduplicação por vértice, o wipeout, os limites geométricos,
a cor, a origem do texto, o trabalho fora do orçamento e a leitura por um PDF de verdade.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.estai import (
    BASE,
    BRANCO,
    CINZA,
    DENTE,
    ESPESSURA,
    GRAMATICAS_ESTAI,
    HASTE,
    PRETO,
    ROXO,
    VERDE,
    VERMELHO,
    centro_do_garfo,
    circulo,
    estai_com_circulo,
    fino,
    garfo,
    pagina_estai,
    polar,
    vertice_de,
    x_sobre,
)
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    pagina_gramatica,
    poligono,
    texto,
)
from tests.fixtures.symbol_grammars.rect_diagonal import pagina_desenhada
from tests.unit.test_guarda_fonte_estendida_testador import (
    _violacoes_de_bytes_e_inteiros,
    _violacoes_de_comentarios,
)
from tests.unit.test_symbol_packages_sem_memorizacao import _violacoes_de_fonte

from zeny_project_handler.adapters.analysis.drawing_model import grammar_estai, symbol_matcher
from zeny_project_handler.adapters.analysis.drawing_model.grammar_estai import (
    CandidatoEstai,
    casa_estai,
    estai_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import MarcasDaPagina
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Caminho,
    Cor,
    Estilo,
    ItemCaminho,
    Ponto,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    PaginaGramatica,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import casar_variantes
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas

_ARQUIVO: Final = Path(__file__)
NENHUM: Final = {"existente": 0, "instalar": 0, "retirar": 0}
SO_EXISTENTE: Final = {"existente": 1, "instalar": 0, "retirar": 0}
SO_INSTALAR: Final = {"existente": 0, "instalar": 1, "retirar": 0}
SO_RETIRAR: Final = {"existente": 0, "instalar": 0, "retirar": 1}
_RAIO: Final = DENTE * 0.8


def _contexto(caminhos: Sequence[Caminho], textos: Sequence[TextoModelo] = ()) -> ContextoGramatica:
    return contexto_gramaticas(pagina_estai(caminhos, textos=textos))


def _candidatos(
    caminhos: Sequence[Caminho], textos: Sequence[TextoModelo] = ()
) -> tuple[CandidatoEstai, ...]:
    contexto = _contexto(caminhos, textos)
    return estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))


def _grupos_do_contexto(contexto: ContextoGramatica) -> dict[str, int]:
    candidatos = estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))
    return {
        nome: len(casa_estai(contexto, gramatica, candidatos=candidatos))
        for nome, gramatica in GRAMATICAS_ESTAI.items()
    }


def _grupos(caminhos: Sequence[Caminho], textos: Sequence[TextoModelo] = ()) -> dict[str, int]:
    return _grupos_do_contexto(_contexto(caminhos, textos))


def _polilinha(pontos: Sequence[Ponto], cor: Cor | None = PRETO) -> Caminho:
    """Um caminho só, de vários trechos: a forma em que um condutor costuma vir."""
    itens = tuple(ItemCaminho("l", (a, b)) for a, b in pairwise(pontos))
    return Caminho((itens,), Estilo("", cor, None, ESPESSURA, ""), "traco", 0)


def _x_girado(centro: Ponto, graus: float, meio: float = 9.0) -> list[Caminho]:
    """X que gira com o símbolo, como o bloco de CAD inserido com rotação."""
    return [
        fino(
            polar(centro, graus + 45, meio),
            polar(centro, graus + 225, meio),
            VERMELHO,
            ordem=1,
            espessura=1.2,
        ),
        fino(
            polar(centro, graus + 135, meio),
            polar(centro, graus + 315, meio),
            VERMELHO,
            ordem=1,
            espessura=1.2,
        ),
    ]


def _pontas(graus: float = 0.0, abertura: float = 26.0) -> tuple[Ponto, Ponto]:
    vertice = vertice_de(graus)
    return polar(vertice, graus + abertura, DENTE), polar(vertice, graus - abertura, DENTE)


def _todos_os_caminhos(candidato: CandidatoEstai) -> set[int]:
    return {candidato.caminho_ancora, *candidato.componentes}


# Formas com a assinatura do garfo que não são estai (Review Focus 1) ----------------------------


def _ponta_tracada(ponta_a: Ponto, ponta_b: Ponto) -> Caminho:
    return fino(ponta_a, ponta_b)


def _ponta_cheia(ponta_a: Ponto, ponta_b: Ponto) -> Caminho:
    return poligono((vertice_de(), ponta_a, ponta_b), 1, preenchimento=PRETO, cor=None)


@pytest.mark.parametrize(
    "fechar",
    [pytest.param(_ponta_tracada, id="tampa"), pytest.param(_ponta_cheia, id="cheia")],
)
def test_seta_fechada_no_fim_da_linha_nao_casa(
    fechar: Callable[[Ponto, Ponto], Caminho],
) -> None:
    """A tampa entre as pontas fecha o garfo num triângulo: é ponta de seta, não estai."""
    ponta_a, ponta_b = _pontas()
    assert _grupos([*garfo(), fechar(ponta_a, ponta_b)]) == NENHUM


def test_ramal_que_continua_em_polilinha_pela_ponta_nao_casa() -> None:
    """O condutor derivado costuma ser um caminho de vários trechos, e não um traço solto."""
    ponta, _ = _pontas()
    meio = polar(ponta, 0, 16.0)
    assert _grupos([*garfo(), _polilinha((ponta, meio, polar(meio, 30, 16.0)))]) == NENHUM


def test_pe_de_galinha_com_cerca_em_polilinha_pelo_vertice_nao_casa() -> None:
    vertice = vertice_de()
    meio = polar(vertice, 0, 16.0)
    assert _grupos([*garfo(), _polilinha((vertice, meio, polar(meio, 10, 16.0)))]) == NENHUM


def test_cota_com_linha_de_extensao_nas_duas_pontas_nao_casa() -> None:
    """O eixo entre duas extensões perpendiculares é cota, como no `_dimension_extensions`."""

    def extensao(ponto: Ponto) -> Caminho:
        return fino(polar(ponto, 90, 14.0), polar(ponto, -90, 14.0))

    assert _grupos([*garfo(), extensao(vertice_de()), extensao(BASE)]) == NENHUM


def _segundo_chevron() -> list[Caminho]:
    vertice = polar(vertice_de(), 0, 6.0)
    return [
        fino(vertice, polar(vertice, 26, DENTE)),
        fino(vertice, polar(vertice, -26, DENTE)),
    ]


def test_dois_chevrons_em_linha_nao_casam() -> None:
    """Os chevrons da E06.3.5: um V encaixado no outro, à frente da linha."""
    assert _grupos([*garfo(), *_segundo_chevron()]) == NENHUM


def test_dois_chevrons_em_linha_com_a_saida_do_condutor_nao_casam() -> None:
    saida_de = polar(vertice_de(), 0, 6.0)
    assert _grupos([*garfo(), *_segundo_chevron(), fino(saida_de, polar(saida_de, 0, 20.0))]) == (
        NENHUM
    )


def test_linha_de_chamada_em_leque_saindo_do_texto_nao_casa() -> None:
    """Haste que nasce dentro da caixa de um texto é líder de anotação, não estai."""
    rotulo = texto("LEGENDA", (BASE[0] - 30.0, BASE[1] - 3.0, BASE[0] + 0.5, BASE[1] + 3.0))
    assert _grupos(garfo(), (rotulo,)) == NENHUM


def test_controle_garfo_com_texto_longe_da_base_casa() -> None:
    rotulo = texto("LEGENDA", (BASE[0] - 60.0, BASE[1] - 3.0, BASE[0] - 30.0, BASE[1] + 3.0))
    assert _grupos(garfo(), (rotulo,)) == SO_EXISTENTE


def test_linha_de_chamada_simples_nao_casa() -> None:
    joelho = polar(BASE, 0, 16.0)
    caminhos = [_polilinha((BASE, joelho, polar(joelho, 40, 12.0))), fino(BASE, joelho)]
    rotulo = texto("LEGENDA", (BASE[0] - 30.0, BASE[1] - 3.0, BASE[0], BASE[1] + 3.0))
    assert _grupos(caminhos, (rotulo,)) == NENHUM


def test_segmento_longo_a_frente_do_vertice_nao_casa() -> None:
    """A continuação vale ainda que o traço seja longo demais para ser dente ou haste."""
    vertice = vertice_de()
    assert _grupos([*garfo(), fino(vertice, polar(vertice, 0, 60.0))]) == NENHUM


def test_traco_grosso_a_frente_do_vertice_nao_casa() -> None:
    vertice = vertice_de()
    assert _grupos([*garfo(), fino(vertice, polar(vertice, 0, 16.0), espessura=2.0)]) == NENHUM


def test_seta_de_dois_lados_em_qualquer_abertura_nao_casa() -> None:
    vertice = vertice_de()
    for abertura in (20.0, 26.0, 35.0):
        caminhos = [
            fino(BASE, vertice),
            fino(vertice, polar(vertice, 180 - abertura, DENTE)),
            fino(vertice, polar(vertice, 180 + abertura, DENTE)),
        ]
        assert _grupos(caminhos) == NENHUM, abertura


# Posse dos componentes entre desenhos vizinhos (Review Focus 3 e 5) -----------------------------


def test_haste_nao_e_ancora_de_dois_garfos() -> None:
    """Um traço com garfo nas duas pontas não vira dois estais sobre a mesma haste."""
    caminhos = [
        *garfo(),
        fino(BASE, polar(BASE, 180 + 26, DENTE)),
        fino(BASE, polar(BASE, 180 - 26, DENTE)),
    ]
    ancoras = [candidato.caminho_ancora for candidato in _candidatos(caminhos)]
    assert len(ancoras) == len(set(ancoras)), ancoras


def test_x_do_garfo_vizinho_nao_marca_o_garfo_ao_lado() -> None:
    """Duas caixas que se encostam, X só sobre uma: a outra segue sem marca de retirada."""
    vizinho = (BASE[0], BASE[1] + 11.0)
    caminhos = [*garfo(), *garfo(base=vizinho), *x_sobre(centro_do_garfo())]
    assert _grupos(caminhos) == {"existente": 1, "instalar": 0, "retirar": 1}


def test_controle_x_de_garfo_distante_nao_marca_o_outro() -> None:
    vizinho = (BASE[0], BASE[1] + 40.0)
    caminhos = [*garfo(), *garfo(base=vizinho), *x_sobre(centro_do_garfo())]
    assert _grupos(caminhos) == {"existente": 1, "instalar": 0, "retirar": 1}


def test_x_entre_dois_garfos_nao_entra_nos_dois() -> None:
    """Um X só atravessando dois desenhos não pode virar componente dos dois."""
    caminhos = [
        *garfo(base=(BASE[0], BASE[1] - 7.0)),
        *garfo(base=(BASE[0], BASE[1] + 7.0)),
        *x_sobre((BASE[0] + 22.0, BASE[1])),
    ]
    candidatos = _candidatos(caminhos)
    assert len(candidatos) == 2
    assert _todos_os_caminhos(candidatos[0]).isdisjoint(_todos_os_caminhos(candidatos[1]))


def test_envolvente_unica_nao_entra_em_dois_garfos() -> None:
    """Um círculo que contém dois garfos não é a envolvente dos dois ao mesmo tempo."""
    caminhos = [
        *garfo(cor=VERDE, base=(BASE[0], BASE[1] - 4.5)),
        *garfo(cor=VERDE, base=(BASE[0], BASE[1] + 4.5)),
        circulo((BASE[0] + 25.0, BASE[1]), 16.0, VERDE),
    ]
    candidatos = _candidatos(caminhos)
    assert len(candidatos) == 2
    assert _todos_os_caminhos(candidatos[0]).isdisjoint(_todos_os_caminhos(candidatos[1]))


def test_garfos_de_cores_diferentes_no_mesmo_vertice_em_direcoes_diferentes_sao_dois() -> None:
    """A deduplicação é do desenho sobreposto; eixos diferentes no mesmo vértice são dois."""
    vertice = vertice_de()
    outro = [
        fino(polar(vertice, -90, HASTE), vertice),
        fino(vertice, polar(vertice, 90 + 26, DENTE)),
        fino(vertice, polar(vertice, 90 - 26, DENTE)),
    ]
    assert _grupos([*estai_com_circulo(), *outro]) == {
        "existente": 1,
        "instalar": 1,
        "retirar": 0,
    }


def test_dois_estais_opostos_so_um_com_x() -> None:
    caminhos = [*garfo(20.0), *garfo(200.0), *_x_girado(centro_do_garfo(20.0), 20.0)]
    assert _grupos(caminhos) == {"existente": 1, "instalar": 0, "retirar": 1}


def test_tres_estais_no_mesmo_poste_nao_inventam_garfo_na_base() -> None:
    """Três hastes na mesma base, duas a 30 graus do prolongamento da outra."""
    centro = (100.0, 100.0)
    caminhos = [*garfo(0.0, base=centro), *garfo(150.0, base=centro), *garfo(210.0, base=centro)]
    assert _grupos(caminhos) == {"existente": 3, "instalar": 0, "retirar": 0}


def test_estais_opostos_com_circulo_nao_trocam_a_envolvente() -> None:
    caminhos = [*estai_com_circulo(0.0), *estai_com_circulo(180.0)]
    candidatos = _candidatos(caminhos)
    assert sorted(c.caminho_ancora for c in candidatos) == [0, 4]
    for candidato in candidatos:
        assert ({3} if candidato.caminho_ancora == 0 else {7}) <= set(candidato.componentes)


def test_candidato_com_x_e_circulo_tem_todos_os_componentes() -> None:
    candidatos = _candidatos([*estai_com_circulo(), *x_sobre(centro_do_garfo())])
    assert len(candidatos) == 1
    assert candidatos[0].caminho_ancora == 0
    assert candidatos[0].componentes == (1, 2, 3, 4, 5)
    assert candidatos[0].enclosure == "ellipse"
    assert candidatos[0].removal_mark is True


def test_x_sobre_garfo_preto_com_circulo_de_outra_cor_ignora_o_circulo() -> None:
    caminhos = [
        *garfo(),
        circulo(centro_do_garfo(), _RAIO, VERDE),
        *x_sobre(centro_do_garfo()),
    ]
    candidatos = _candidatos(caminhos)
    assert len(candidatos) == 1
    assert candidatos[0].enclosure == "none"
    assert 3 not in candidatos[0].componentes
    assert _grupos(caminhos) == SO_RETIRAR


def test_caixa_com_x_sem_circulo_deixa_o_x_de_fora() -> None:
    centro = centro_do_garfo()
    caminhos = [*garfo(), *x_sobre(centro, meio=16.0)]
    candidatos = _candidatos(caminhos)
    assert len(candidatos) == 1
    assert candidatos[0].removal_mark is True
    ponta_a, ponta_b = _pontas()
    esperada = (BASE[0], ponta_b[1], ponta_a[0], ponta_a[1])
    assert candidatos[0].caixa == pytest.approx(esperada, abs=0.01)


# Deduplicação e determinismo --------------------------------------------------------------------


@pytest.mark.parametrize("inverter", [False, True], ids=["ordem_direta", "ordem_inversa"])
def test_desenho_preto_sob_o_verde_com_circulo_e_um_estai_instalar(inverter: bool) -> None:
    caminhos = [*garfo(), *estai_com_circulo()]
    assert _grupos(list(reversed(caminhos)) if inverter else caminhos) == SO_INSTALAR


def test_ordem_dos_caminhos_nao_muda_as_caixas() -> None:
    caminhos = [*garfo(), *garfo(180.0), *estai_com_circulo(base=(60.0, 60.0))]
    direta = sorted(c.caixa for c in _candidatos(caminhos))
    inversa = sorted(c.caixa for c in _candidatos(list(reversed(caminhos))))
    assert direta == inversa


def test_duas_leituras_da_mesma_pagina_sao_iguais() -> None:
    caminhos = [*garfo(), *estai_com_circulo(base=(60.0, 60.0))]
    primeira = [(c.caixa, c.caminho_ancora, c.componentes) for c in _candidatos(caminhos)]
    segunda = [(c.caixa, c.caminho_ancora, c.componentes) for c in _candidatos(caminhos)]
    assert primeira == segunda


# Tracejado, cor, camada, espessura, translúcido -------------------------------------------------


@pytest.mark.parametrize("padrao", ["[1 1] 0", "[0 0] 0", "[1] 0", "[3 2 1 2] 0"])
def test_padrao_de_traco_interrompido_nao_casa(padrao: str) -> None:
    assert _grupos(garfo(tracejado=padrao)) == NENHUM


@pytest.mark.parametrize("padrao", ["", "[] 0", "[]0", " [ ] 0"])
def test_padrao_de_traco_continuo_casa(padrao: str) -> None:
    assert _grupos(garfo(tracejado=padrao)) == SO_EXISTENTE


def test_so_um_dente_tracejado_nao_casa() -> None:
    vertice = vertice_de()
    ponta_a, ponta_b = _pontas()
    caminhos = [
        fino(BASE, vertice),
        fino(vertice, ponta_a, tracejado="[1 1] 0"),
        fino(vertice, ponta_b),
    ]
    assert _grupos(caminhos) == NENHUM


def test_so_a_haste_tracejada_nao_casa() -> None:
    vertice = vertice_de()
    ponta_a, ponta_b = _pontas()
    caminhos = [
        fino(BASE, vertice, tracejado="[1 1] 0"),
        fino(vertice, ponta_a),
        fino(vertice, ponta_b),
    ]
    assert _grupos(caminhos) == NENHUM


@pytest.mark.parametrize(
    "marca",
    [
        pytest.param(lambda: [circulo(centro_do_garfo(), _RAIO, ROXO)], id="circulo_roxo"),
        pytest.param(lambda: [*x_sobre(centro_do_garfo())], id="x_vermelho"),
    ],
)
def test_garfo_roxo_com_marca_nao_casa(marca: Callable[[], list[Caminho]]) -> None:
    assert _grupos([*garfo(cor=ROXO), *marca()]) == NENHUM


@pytest.mark.parametrize(
    "cor",
    [(0.15, 0.0, 0.15), (0.0, 0.1, 0.0), (0.1, 0.0, 0.0)],
    ids=["roxo_escuro", "verde_escuro", "vermelho_escuro"],
)
def test_cor_escura_que_nao_e_cinza_nao_casa_o_grupo_preto(cor: Cor) -> None:
    assert _grupos(garfo(cor=cor)) == NENHUM


def test_cor_ausente_nao_casa() -> None:
    assert _grupos(garfo(cor=None)) == NENHUM


@pytest.mark.parametrize(
    ("cor_garfo", "cor_circulo"),
    [(VERDE, PRETO), (VERDE, VERMELHO), (VERMELHO, VERDE)],
    ids=["verde_preto", "verde_vermelho", "vermelho_verde"],
)
def test_garfo_colorido_com_circulo_de_outra_cor_nao_casa(cor_garfo: Cor, cor_circulo: Cor) -> None:
    """Sem a envolvente da cor dele, o garfo colorido continua sem marca (R-E06.3.4-2)."""
    assert _grupos([*garfo(cor=cor_garfo), circulo(centro_do_garfo(), _RAIO, cor_circulo)]) == (
        NENHUM
    )


def test_garfo_colorido_com_circulo_vizinho_da_cor_dele_nao_casa() -> None:
    """Círculo da mesma cor ao lado, sem conter o garfo: nada de "instalar"."""
    longe = polar(centro_do_garfo(), 90, 14.0)
    assert _grupos([*garfo(cor=VERDE), circulo(longe, _RAIO, VERDE)]) == NENHUM


def test_haste_e_dentes_de_cores_diferentes_nao_casam() -> None:
    vertice = vertice_de()
    ponta_a, ponta_b = _pontas()
    caminhos = [fino(BASE, vertice), fino(vertice, ponta_a, CINZA), fino(vertice, ponta_b)]
    assert _grupos(caminhos) == NENHUM


def test_haste_e_dentes_de_camadas_diferentes_nao_casam() -> None:
    vertice = vertice_de()
    ponta_a, ponta_b = _pontas()
    caminhos = [
        fino(BASE, vertice, camada="A"),
        fino(vertice, ponta_a, camada="B"),
        fino(vertice, ponta_b, camada="B"),
    ]
    assert _grupos(caminhos) == NENHUM


@pytest.mark.parametrize(("espessura", "casa"), [(0.5, True), (0.51, False)], ids=["5", "51"])
def test_limite_de_espessura_do_garfo(espessura: float, casa: bool) -> None:
    vertice = vertice_de()
    ponta_a, ponta_b = _pontas()
    caminhos = [
        fino(BASE, vertice, espessura=espessura),
        fino(vertice, ponta_a, espessura=espessura),
        fino(vertice, ponta_b, espessura=espessura),
    ]
    assert (_grupos(caminhos) == SO_EXISTENTE) is casa


def test_so_um_dente_grosso_nao_casa() -> None:
    vertice = vertice_de()
    ponta_a, ponta_b = _pontas()
    caminhos = [fino(BASE, vertice), fino(vertice, ponta_a, espessura=1.0), fino(vertice, ponta_b)]
    assert _grupos(caminhos) == NENHUM


def _com_fontes(
    pagina: PaginaGramatica,
    *,
    translucidos: frozenset[int] = frozenset(),
    glifos: frozenset[int] = frozenset(),
) -> PaginaGramatica:
    return PaginaGramatica(pagina.modelo, pagina.indices_crus, translucidos, glifos)


def test_garfo_translucido_nao_casa() -> None:
    pagina = _com_fontes(pagina_estai(garfo()), translucidos=frozenset({0, 1, 2}))
    assert _grupos_do_contexto(contexto_gramaticas(pagina)) == NENHUM


# Wipeout ----------------------------------------------------------------------------------------


def _cobertura(ordem: int = 5) -> Caminho:
    return poligono(
        ((140.0, 130.0), (190.0, 130.0), (190.0, 170.0), (140.0, 170.0)),
        ordem=ordem,
        preenchimento=BRANCO,
        cor=None,
    )


def test_wipeout_em_l_cuja_caixa_cobre_o_garfo_nao_o_esconde() -> None:
    """A máscara em L passa ao lado do garfo: só a caixa dela o contém, a área branca não."""
    mascara = poligono(
        (
            (140.0, 130.0),
            (195.0, 130.0),
            (195.0, 135.0),
            (145.0, 135.0),
            (145.0, 170.0),
            (140.0, 170.0),
        ),
        ordem=5,
        preenchimento=BRANCO,
        cor=None,
    )
    assert _grupos([*garfo(), mascara]) == SO_EXISTENTE


def test_preenchimento_branco_desenhado_antes_nao_esconde() -> None:
    assert _grupos([_cobertura(ordem=0), *garfo(ordem=1)]) == SO_EXISTENTE


def test_preenchimento_branco_na_mesma_ordem_nao_esconde() -> None:
    assert _grupos([*garfo(ordem=5), _cobertura(ordem=5)]) == SO_EXISTENTE


def test_preenchimento_branco_translucido_nao_esconde() -> None:
    pagina = _com_fontes(pagina_estai([*garfo(), _cobertura()]), translucidos=frozenset({3}))
    assert _grupos_do_contexto(contexto_gramaticas(pagina)) == SO_EXISTENTE


def test_preenchimento_nao_branco_nao_esconde() -> None:
    cinza = poligono(
        ((140.0, 130.0), (190.0, 130.0), (190.0, 170.0), (140.0, 170.0)),
        ordem=5,
        preenchimento=(0.5, 0.5, 0.5),
        cor=None,
    )
    assert _grupos([*garfo(), cinza]) == SO_EXISTENTE


def test_preenchimento_branco_que_nao_alcanca_uma_ponta_nao_esconde() -> None:
    parcial = poligono(
        ((140.0, 130.0), (170.0, 130.0), (170.0, 170.0), (140.0, 170.0)),
        ordem=5,
        preenchimento=BRANCO,
        cor=None,
    )
    assert _grupos([*garfo(), parcial]) == SO_EXISTENTE


def test_envolvente_preenchida_de_branco_antes_do_garfo_vale() -> None:
    caminhos = [
        circulo_bezier(centro_do_garfo(), _RAIO, 0, cor=VERDE, preenchimento=BRANCO),
        *garfo(cor=VERDE, ordem=5),
    ]
    assert _grupos(caminhos) == SO_INSTALAR


def test_envolvente_preenchida_de_branco_depois_do_garfo_esconde() -> None:
    caminhos = [
        *garfo(cor=VERDE, ordem=0),
        circulo_bezier(centro_do_garfo(), _RAIO, 5, cor=VERDE, preenchimento=BRANCO),
    ]
    assert _grupos(caminhos) == NENHUM


# Limites geométricos -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("abertura", "casa"),
    [(14.9, False), (15.1, True), (39.9, True), (40.1, False)],
    ids=["abaixo_de_15", "acima_de_15", "abaixo_de_40", "acima_de_40"],
)
def test_limite_do_angulo_do_dente(abertura: float, casa: bool) -> None:
    assert (_grupos(garfo(abertura=abertura)) == SO_EXISTENTE) is casa


@pytest.mark.parametrize(
    ("angulo_a", "angulo_b", "casa"),
    [(20.0, 29.0, True), (20.0, 31.0, False)],
    ids=["diferenca_9", "diferenca_11"],
)
def test_limite_de_assimetria_dos_dentes(angulo_a: float, angulo_b: float, casa: bool) -> None:
    vertice = vertice_de()
    caminhos = [
        fino(BASE, vertice),
        fino(vertice, polar(vertice, angulo_a, DENTE)),
        fino(vertice, polar(vertice, -angulo_b, DENTE)),
    ]
    assert (_grupos(caminhos) == SO_EXISTENTE) is casa


def test_dentes_do_mesmo_lado_da_haste_nao_casam() -> None:
    vertice = vertice_de()
    caminhos = [
        fino(BASE, vertice),
        fino(vertice, polar(vertice, 20, DENTE)),
        fino(vertice, polar(vertice, 32, DENTE)),
    ]
    assert _grupos(caminhos) == NENHUM


@pytest.mark.parametrize(
    ("comprimento_b", "casa"),
    [(13.7, True), (13.9, False)],
    ids=["razao_1_14", "razao_1_16"],
)
def test_limite_da_razao_entre_os_dentes(comprimento_b: float, casa: bool) -> None:
    vertice = vertice_de()
    caminhos = [
        fino(BASE, vertice),
        fino(vertice, polar(vertice, 26, DENTE)),
        fino(vertice, polar(vertice, -26, comprimento_b)),
    ]
    assert (_grupos(caminhos) == SO_EXISTENTE) is casa


@pytest.mark.parametrize(
    ("dente", "casa"),
    [(8.7, False), (8.9, True), (15.9, True), (16.2, False)],
    ids=["curto", "minimo", "maximo", "maior_que_a_haste"],
)
def test_limite_do_dente_relativo_a_haste(dente: float, casa: bool) -> None:
    assert (_grupos(garfo(dente=dente)) == SO_EXISTENTE) is casa


_GLIFO: Final = (texto("A", (10.0, 10.0, 12.0, 12.0), "glifo"),)
_SHX: Final = (texto("A", (10.0, 10.0, 12.0, 12.0), "shx"),)
_NATIVO: Final = (texto("A", (10.0, 10.0, 12.0, 12.0), "nativo"),)


@pytest.mark.parametrize(
    ("haste", "dente", "textos", "casa"),
    [
        pytest.param(4.1, 2.4, _GLIFO, True, id="glifo_minimo"),
        pytest.param(3.9, 2.4, _GLIFO, False, id="glifo_abaixo"),
        pytest.param(19.9, 14.0, _GLIFO, True, id="glifo_maximo"),
        pytest.param(20.1, 14.0, _GLIFO, False, id="glifo_acima"),
        pytest.param(10.1, 6.0, _NATIVO, True, id="nativo_minimo"),
        pytest.param(9.9, 6.0, _NATIVO, False, id="nativo_abaixo"),
        pytest.param(23.9, 14.0, _NATIVO, True, id="nativo_maximo"),
        pytest.param(24.1, 14.0, _NATIVO, False, id="nativo_acima"),
        pytest.param(5.0, 3.0, _SHX, False, id="shx_curta"),
        pytest.param(23.9, 14.0, _SHX, True, id="shx_maximo"),
        pytest.param(5.0, 3.0, (), False, id="sem_texto_curta"),
    ],
)
def test_limite_da_haste_por_origem_do_texto(
    haste: float, dente: float, textos: tuple[TextoModelo, ...], casa: bool
) -> None:
    assert (_grupos(garfo(haste=haste, dente=dente), textos) == SO_EXISTENTE) is casa


def test_haste_curta_vale_quando_o_glifo_predomina_na_pagina_mista() -> None:
    textos = (
        texto("A", (10.0, 10.0, 12.0, 12.0), "glifo"),
        texto("B", (20.0, 10.0, 22.0, 12.0), "glifo"),
        texto("C", (30.0, 10.0, 32.0, 12.0), "nativo"),
    )
    assert _grupos(garfo(haste=5.0, dente=3.0), textos) == SO_EXISTENTE


def test_haste_curta_nao_vale_quando_o_nativo_predomina_na_pagina_mista() -> None:
    textos = (
        texto("A", (10.0, 10.0, 12.0, 12.0), "nativo"),
        texto("B", (20.0, 10.0, 22.0, 12.0), "nativo"),
        texto("C", (30.0, 10.0, 32.0, 12.0), "glifo"),
    )
    assert _grupos(garfo(haste=5.0, dente=3.0), textos) == NENHUM


# Texto, X, envolvente e rotação ------------------------------------------------------------------


def test_texto_alem_das_pontas_nao_impede() -> None:
    vertice = vertice_de()
    rotulo = texto("A", (vertice[0] + 20.0, vertice[1] - 1.0, vertice[0] + 22.0, vertice[1] + 1.0))
    assert _grupos(garfo(), (rotulo,)) == SO_EXISTENTE


def test_cruz_alinhada_ao_eixo_nao_e_x() -> None:
    centro = centro_do_garfo()
    braco_a = fino(polar(centro, 0, 9.0), polar(centro, 180, 9.0), VERMELHO, espessura=1.2)
    braco_b = fino(polar(centro, 90, 9.0), polar(centro, 270, 9.0), VERMELHO, espessura=1.2)
    assert _grupos([*garfo(), braco_a, braco_b]) == SO_EXISTENTE


def test_x_de_bracos_de_cores_diferentes_nao_e_x() -> None:
    centro = centro_do_garfo()
    caminhos = [
        *garfo(),
        fino(polar(centro, 45, 9.0), polar(centro, 225, 9.0), VERMELHO, espessura=1.2),
        fino(polar(centro, 135, 9.0), polar(centro, 315, 9.0), PRETO, espessura=1.2),
    ]
    assert _grupos(caminhos) == SO_EXISTENTE


@pytest.mark.parametrize("graus", [0.0, 30.0, 45.0, 90.0, 135.0, 200.0, 300.0])
def test_x_girado_com_o_simbolo_casa_so_retirar(graus: float) -> None:
    centro = centro_do_garfo(graus)
    assert _grupos([*estai_com_circulo(graus), *_x_girado(centro, graus)]) == SO_RETIRAR
    assert _grupos([*garfo(graus), *_x_girado(centro, graus)]) == SO_RETIRAR


@pytest.mark.parametrize("graus", [0.0, 45.0, 90.0, 180.0, 270.0])
def test_caixa_com_circulo_une_envolvente_e_haste_em_qualquer_rotacao(graus: float) -> None:
    centro = centro_do_garfo(graus)
    candidatos = _candidatos(estai_com_circulo(graus))
    assert len(candidatos) == 1
    caixa = candidatos[0].caixa
    assert caixa[0] == pytest.approx(min(BASE[0], centro[0] - _RAIO), abs=0.6)
    assert caixa[1] == pytest.approx(min(BASE[1], centro[1] - _RAIO), abs=0.6)
    assert caixa[2] == pytest.approx(max(BASE[0], centro[0] + _RAIO), abs=0.6)
    assert caixa[3] == pytest.approx(max(BASE[1], centro[1] + _RAIO), abs=0.6)


def test_envolvente_em_bezier_conta() -> None:
    caminhos = [*garfo(cor=VERDE), circulo_bezier(centro_do_garfo(), _RAIO, cor=VERDE)]
    assert _grupos(caminhos) == SO_INSTALAR


def test_envolvente_com_primitivas_reconstruidas_nao_repete_componente() -> None:
    caminhos = [*garfo(cor=VERDE), circulo(centro_do_garfo(), _RAIO, VERDE)]
    contexto = contexto_gramaticas(pagina_gramatica(caminhos, primitivas=None))
    candidatos = estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))
    assert len(candidatos) == 1
    assert candidatos[0].enclosure == "ellipse"
    assert candidatos[0].componentes == (1, 2, 3)


# Contexto, despacho ------------------------------------------------------------------------------


def test_candidatos_misturados_de_dois_contextos_sao_recusados() -> None:
    a = _contexto(garfo())
    b = _contexto(garfo())
    candidatos = (
        *estai_candidatos(a, marcas=MarcasDaPagina(a)),
        *estai_candidatos(b, marcas=MarcasDaPagina(b)),
    )
    with pytest.raises(ValueError, match="outro contexto"):
        casa_estai(a, GRAMATICAS_ESTAI["existente"], candidatos=candidatos)


def test_marcas_de_outro_contexto_sao_recusadas() -> None:
    a = _contexto(garfo())
    b = _contexto(garfo())
    with pytest.raises(ValueError, match="outro contexto"):
        estai_candidatos(a, marcas=MarcasDaPagina(b))


def test_candidatos_vazios_nao_casam_e_nao_recalculam() -> None:
    contexto = _contexto(garfo())
    assert casa_estai(contexto, GRAMATICAS_ESTAI["existente"], candidatos=()) == []


def _pares(*nomes: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        ({"family_id": "autoral"}, {"id": n, "recognition": {"grammar": GRAMATICAS_ESTAI[n]}})
        for n in nomes
    ]


def test_estai_candidatos_roda_uma_vez_por_pagina(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[int] = []
    original = vars(symbol_matcher)["estai_candidatos"]

    def contar(*args: Any, **kwargs: Any) -> Any:
        chamadas.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(symbol_matcher, "estai_candidatos", contar)
    achados = casar_variantes(pagina_estai(garfo()), _pares("existente", "instalar", "retirar"))
    assert [str(a.variante["id"]) for a in achados] == ["existente"]
    assert len(chamadas) == 1


def test_sem_variante_de_estai_nao_classifica(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[int] = []

    def contar(*args: Any, **kwargs: Any) -> Any:
        chamadas.append(1)
        return ()

    monkeypatch.setattr(symbol_matcher, "estai_candidatos", contar)
    assert casar_variantes(pagina_estai(garfo()), []) == ()
    assert chamadas == []


def test_despacho_leva_ancora_e_componentes_do_candidato() -> None:
    caminhos = estai_com_circulo()
    achados = casar_variantes(pagina_estai(caminhos), _pares("instalar"))
    assert len(achados) == 1
    assert achados[0].componentes == (1, 2, 3)


# Trabalho fora do orçamento ----------------------------------------------------------------------


class _MathContado:
    """O `math` do módulo com `dist` contado: mede o trabalho real das comparações."""

    def __init__(self) -> None:
        self.distancias = 0

    def __getattr__(self, nome: str) -> Any:
        return getattr(math, nome)

    def dist(self, a: Sequence[float], b: Sequence[float]) -> float:
        self.distancias += 1
        return math.dist(a, b)


def test_raios_vizinhos_fora_da_tolerancia_pagam_o_orcamento(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_Pontas.em` percorre as nove células e só cobra o que passa na distância.

    Milhares de traços curtos (que não são semente) terminam num ponto e 180 hastes terminam num
    anel a 0,2 pt dele, nas células vizinhas: cada haste examina todos os traços curtos, e nenhum
    deles paga. O trabalho tem de ficar na ordem do gasto, ou o teto da página não o vê.
    """
    centro: Ponto = (150.125, 150.125)
    curtos = [fino(centro, polar(centro, i * 360.0 / 4000, 6.0)) for i in range(4000)]
    anel = [polar(centro, k * 40.0, 0.2) for k in range(9)]
    hastes = [
        fino(ponto, polar(ponto, k * 40.0 + passo * 3.0, 16.0))
        for k, ponto in enumerate(anel)
        for passo in range(20)
    ]
    contexto = _contexto([*curtos, *hastes])
    marcas = MarcasDaPagina(contexto)
    contador = _MathContado()
    monkeypatch.setattr(grammar_estai, "math", contador)

    antes = contexto.orcamento.gasto
    estai_candidatos(contexto, marcas=marcas)
    gasto = contexto.orcamento.gasto - antes

    assert contador.distancias <= 20 * gasto, f"{contador.distancias} comparações, gasto {gasto}"


# PDF de verdade ----------------------------------------------------------------------------------


def _desenhar_garfo(
    pagina: pymupdf.Page,
    *,
    base: Ponto = BASE,
    graus: float = 0.0,
    cor: Cor = PRETO,
    tracejado: str | None = None,
) -> None:
    vertice = polar(base, graus, HASTE)
    extremos = (polar(vertice, graus + 26, DENTE), polar(vertice, graus - 26, DENTE))
    for inicio, fim in ((base, vertice), (vertice, extremos[0]), (vertice, extremos[1])):
        pagina.draw_line(inicio, fim, color=cor, width=ESPESSURA, dashes=tracejado)


def _circulo_pdf(pagina: pymupdf.Page, centro: Ponto, raio: float, cor: Cor) -> None:
    pontos = [polar(centro, i * 360.0 / 32, raio) for i in range(33)]
    pagina.draw_polyline(pontos, color=cor, width=ESPESSURA)


def _grupos_do_pdf(desenhar: Callable[[pymupdf.Page], object]) -> dict[str, int]:
    return _grupos_do_contexto(contexto_gramaticas(pagina_desenhada(desenhar)))


def test_pdf_garfo_preto_casa_so_existente() -> None:
    assert _grupos_do_pdf(_desenhar_garfo) == SO_EXISTENTE


def test_pdf_garfo_tracejado_nao_casa() -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        _desenhar_garfo(pagina, tracejado="[3 2] 0")

    assert _grupos_do_pdf(desenhar) == NENHUM


def test_pdf_verde_com_circulo_casa_so_instalar() -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        _desenhar_garfo(pagina, cor=VERDE)
        _circulo_pdf(pagina, centro_do_garfo(), _RAIO, VERDE)

    assert _grupos_do_pdf(desenhar) == SO_INSTALAR


def test_pdf_x_sobre_circulo_casa_so_retirar() -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        _desenhar_garfo(pagina, cor=VERDE)
        centro = centro_do_garfo()
        _circulo_pdf(pagina, centro, _RAIO, VERDE)
        pagina.draw_line(polar(centro, 45, 9.0), polar(centro, 225, 9.0), color=VERMELHO, width=1.2)
        pagina.draw_line(
            polar(centro, 135, 9.0), polar(centro, 315, 9.0), color=VERMELHO, width=1.2
        )

    assert _grupos_do_pdf(desenhar) == SO_RETIRAR


@pytest.mark.parametrize("rotacao", [90, 180, 270])
def test_pdf_com_rotate_mantem_a_caixa_exibida(rotacao: int) -> None:
    base: Ponto = (100.0, 80.0)
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        _desenhar_garfo(pagina, base=base)
        pagina.set_rotation(rotacao)
        matriz = pagina.rotation_matrix
        exibida = pagina_para_gramaticas(pagina, 0)

    def exibir(ponto: Ponto) -> Ponto:
        x, y = ponto
        return (matriz.a * x + matriz.c * y + matriz.e, matriz.b * x + matriz.d * y + matriz.f)

    vertice = polar(base, 0.0, HASTE)
    pontos = [
        exibir(p) for p in (base, vertice, polar(vertice, 26, DENTE), polar(vertice, -26, DENTE))
    ]
    contexto = contexto_gramaticas(exibida)
    candidatos = estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))
    assert len(candidatos) == 1
    esperada: Caixa = (
        min(p[0] for p in pontos),
        min(p[1] for p in pontos),
        max(p[0] for p in pontos),
        max(p[1] for p in pontos),
    )
    assert candidatos[0].caixa == pytest.approx(esperada, abs=0.1)


# Guarda de fonte ---------------------------------------------------------------------------------


def test_este_arquivo_passa_na_guarda_de_fonte() -> None:
    """A guarda de `_GRAMATICAS_NOVAS` (fonte, comentários, bytes e inteiros) neste arquivo."""
    fonte = _ARQUIVO.read_text(encoding="utf-8")

    assert _violacoes_de_fonte(fonte, _ARQUIVO.name) == []
    assert _violacoes_de_comentarios(fonte, _ARQUIVO.name) == []
    assert _violacoes_de_bytes_e_inteiros(fonte, _ARQUIVO.name) == []
