"""Ataque ao teto `vao_maximo` de `discos_candidatos` (R-E06.3.5-3): todo caminho o respeita."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from itertools import pairwise
from typing import Final

import pytest
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    estilo,
    pagina_gramatica,
    poligono,
)

from zeny_project_handler.adapters.analysis.drawing_model.grammar_disc import (
    Disco,
    _aspecto_redondo,
    _caixas_de_faixa,
    discos_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Caminho,
    Cor,
    ItemCaminho,
    Ponto,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    LIMITE_CONSULTAS_PAGINA,
    ContextoGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)

ROXO: Final[Cor] = (0.31, 0.10, 0.30)
VERDE: Final[Cor] = (0.1, 0.8, 0.1)
CENTRO: Final[Ponto] = (150.0, 150.0)
TETO_DO_SCHEMA: Final = 72.0
DIAMETROS: Final = (10.0, 14.4, 14.9)


def _cantos(caixa: Caixa) -> tuple[Ponto, Ponto, Ponto, Ponto]:
    x0, y0, x1, y1 = caixa
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _cordas(diametro: float, quantidade: int) -> list[Caixa]:
    raio = diametro / 2
    altura = diametro / quantidade
    caixas: list[Caixa] = []
    for indice in range(quantidade):
        topo = CENTRO[1] - raio + indice * altura
        desvio = topo + altura / 2 - CENTRO[1]
        meia = math.sqrt(max(0.0, raio * raio - desvio * desvio))
        caixas.append((CENTRO[0] - meia, topo, CENTRO[0] + meia, topo + altura))
    return caixas


def _faixa_retangulo(caixa: Caixa, ordem: int) -> Caminho:
    return poligono(_cantos(caixa), ordem, ROXO, cor=None)


def _faixa_triangulos(caixa: Caixa, ordem: int) -> Caminho:
    a, b, c, d = _cantos(caixa)
    itens = tuple(ItemCaminho("l", (p, q)) for p, q in pairwise((a, b, c, a, c, d, a)))
    return Caminho((itens,), estilo(ROXO, ROXO), "traco_e_preenchimento", ordem)


def _faixa_mista(caixa: Caixa, ordem: int) -> Caminho:
    return _faixa_triangulos(caixa, ordem) if ordem % 2 else _faixa_retangulo(caixa, ordem)


def _curva_unica(diametro: float) -> list[Caminho]:
    return [circulo_bezier(CENTRO, diametro / 2, 0, cor=ROXO, preenchimento=ROXO)]


def _curva_dividida(diametro: float) -> list[Caminho]:
    raio = diametro / 2
    return [
        circulo_bezier(CENTRO, raio, 0, cor=None, preenchimento=ROXO),
        circulo_bezier(CENTRO, raio, 1, cor=ROXO),
    ]


def _faixas(diametro: float, fabrica: Callable[[Caixa, int], Caminho]) -> list[Caminho]:
    quantidade = math.ceil(diametro / 0.5)
    return [fabrica(caixa, indice) for indice, caixa in enumerate(_cordas(diametro, quantidade))]


def _faixas_retangulos(diametro: float) -> list[Caminho]:
    return _faixas(diametro, _faixa_retangulo)


def _faixas_triangulos(diametro: float) -> list[Caminho]:
    return _faixas(diametro, _faixa_triangulos)


def _faixas_mistas(diametro: float) -> list[Caminho]:
    return _faixas(diametro, _faixa_mista)


FORMATOS: Final[dict[str, Callable[[float], list[Caminho]]]] = {
    "curva_unica": _curva_unica,
    "curva_dividida": _curva_dividida,
    "faixas_retangulos": _faixas_retangulos,
    "faixas_triangulos": _faixas_triangulos,
    "faixas_mistas": _faixas_mistas,
}
CASOS: Final = [
    pytest.param(formato, diametro, id=f"{formato}-{diametro}")
    for formato in FORMATOS
    for diametro in DIAMETROS
]


def _contexto(caminhos: Sequence[Caminho]) -> ContextoGramatica:
    return contexto_gramaticas(pagina_gramatica(caminhos))


def _discos(caminhos: Sequence[Caminho], **kwargs: float) -> tuple[Disco, ...]:
    return discos_candidatos(_contexto(caminhos), **kwargs)


@pytest.mark.parametrize(("formato", "diametro"), CASOS)
def test_default_recusa_disco_acima_de_8_pt_em_todo_formato(formato: str, diametro: float) -> None:
    assert _discos(FORMATOS[formato](diametro)) == ()


@pytest.mark.parametrize(("formato", "diametro"), CASOS)
def test_teto_do_schema_aceita_disco_em_todo_formato(formato: str, diametro: float) -> None:
    discos = _discos(FORMATOS[formato](diametro), vao_maximo=TETO_DO_SCHEMA)
    assert len(discos) == 1
    assert discos[0].preenchimento == ROXO


@pytest.mark.parametrize(("formato", "diametro"), CASOS)
def test_teto_logo_abaixo_do_vao_recusa_o_disco_em_todo_formato(
    formato: str, diametro: float
) -> None:
    assert _discos(FORMATOS[formato](diametro), vao_maximo=diametro - 0.5) == ()


@pytest.mark.parametrize(("formato", "diametro"), CASOS)
def test_teto_folgado_acima_do_vao_aceita_o_disco_em_todo_formato(
    formato: str, diametro: float
) -> None:
    assert len(_discos(FORMATOS[formato](diametro), vao_maximo=diametro + 0.5)) == 1


@pytest.mark.parametrize("formato", ["curva_unica", "curva_dividida", "faixas_retangulos"])
def test_teto_menor_que_o_default_recusa_disco_de_5_pt(formato: str) -> None:
    caminhos = FORMATOS[formato](5.0)
    assert len(_discos(caminhos)) == 1
    assert len(_discos(caminhos, vao_maximo=6.0)) == 1
    assert _discos(caminhos, vao_maximo=4.0) == ()


def test_curva_dividida_aponta_para_o_preenchimento_com_teto_maior() -> None:
    discos = _discos(_curva_dividida(14.4), vao_maximo=TETO_DO_SCHEMA)
    assert [disco.caminho for disco in discos] == [0]


def test_caixa_do_disco_de_14_pt_e_a_da_curva() -> None:
    (disco,) = _discos(_curva_unica(14.4), vao_maximo=TETO_DO_SCHEMA)
    assert disco.caixa == pytest.approx((142.8, 142.8, 157.2, 157.2))


@pytest.mark.parametrize(
    ("vao_maximo", "aceita"), [(9.999, False), (10.0, True), (10.001, True), (8.0, False)]
)
def test_limite_exato_do_vao_na_curva(vao_maximo: float, aceita: bool) -> None:
    assert bool(_discos(_curva_unica(10.0), vao_maximo=vao_maximo)) is aceita


@pytest.mark.parametrize(
    ("vao_maximo", "aceita"), [(9.999, False), (10.0, True), (10.001, True), (8.0, False)]
)
def test_limite_exato_do_vao_na_faixa(vao_maximo: float, aceita: bool) -> None:
    caminho = poligono(_cantos((100.0, 100.0, 110.0, 100.5)), 0, ROXO, cor=None)
    assert bool(_caixas_de_faixa(caminho, None, vao_maximo)) is aceita


@pytest.mark.parametrize(
    ("caixa", "vao_maximo", "redondo"),
    [
        ((0.0, 0.0, 10.0, 10.0), 9.999, False),
        ((0.0, 0.0, 10.0, 10.0), 10.0, True),
        ((0.0, 0.0, 10.0, 10.0), 10.001, True),
        ((0.0, 0.0, 10.0, 8.0), 9.999, False),
        ((0.0, 0.0, 8.0, 10.0), 10.0, True),
    ],
)
def test_aspecto_redondo_compara_o_maior_lado_com_o_teto(
    caixa: Caixa, vao_maximo: float, redondo: bool
) -> None:
    assert _aspecto_redondo(caixa, vao_maximo) is redondo


def test_aspecto_continua_exigindo_proporcao_com_teto_enorme() -> None:
    assert not _aspecto_redondo((0.0, 0.0, 20.0, 10.0), TETO_DO_SCHEMA)
    assert not _aspecto_redondo((0.0, 0.0, 10.0, 20.0), TETO_DO_SCHEMA)


def test_elipse_achatada_de_14_pt_segue_recusada_com_teto_maior() -> None:
    elipse = circulo_bezier((0.0, 0.0), 1.0, 0, cor=None, preenchimento=ROXO)
    itens = tuple(
        ItemCaminho("c", tuple((150.0 + x * 10.0, 150.0 + y * 5.0) for x, y in item.pontos))
        for item in elipse.subcaminhos[0]
    )
    achatada = Caminho((itens,), elipse.estilo, elipse.tipo, 0)
    assert _discos([achatada], vao_maximo=TETO_DO_SCHEMA) == ()


def test_faixas_de_disco_de_100_pt_seguem_recusadas_com_teto_de_72() -> None:
    assert _discos(_faixas_retangulos(100.0), vao_maximo=TETO_DO_SCHEMA) == ()


def test_faixas_de_cores_alternadas_nao_se_misturam_com_teto_maior() -> None:
    caminhos = [
        poligono(_cantos(caixa), indice, ROXO if indice % 2 else VERDE, cor=None)
        for indice, caixa in enumerate(_cordas(14.4, 30))
    ]
    assert _discos(caminhos, vao_maximo=TETO_DO_SCHEMA) == ()


def test_curva_e_faixas_de_14_pt_dao_dois_discos_com_teto_maior() -> None:
    caminhos = _curva_unica(14.4)
    caminhos += [_faixa_retangulo(caixa, i + 1) for i, caixa in enumerate(_cordas(14.4, 30))]
    discos = _discos(caminhos, vao_maximo=TETO_DO_SCHEMA)
    assert sorted(disco.caminho for disco in discos) == [0, 1]


def test_discos_pequenos_continuam_iguais_com_teto_maior() -> None:
    caminhos = _curva_unica(2.8)
    caminhos += [_faixa_retangulo(caixa, i + 1) for i, caixa in enumerate(_cordas(4.0, 12))]
    assert _discos(caminhos, vao_maximo=TETO_DO_SCHEMA) == _discos(caminhos)


# --- orçamento ----------------------------------------------------------------------------


def _gasto_de(caminhos: Sequence[Caminho], **kwargs: float) -> int:
    """O gasto só de `discos_candidatos`, sem a montagem do contexto."""
    contexto = _contexto(caminhos)
    antes = contexto.orcamento.gasto
    discos_candidatos(contexto, **kwargs)
    return contexto.orcamento.gasto - antes


def _faixas_largas_iguais(quantidade: int, largura: float = 20.0) -> list[Caminho]:
    return [_faixa_retangulo((10.0, 10.0, 10.0 + largura, 10.5), i) for i in range(quantidade)]


def test_faixas_largas_nao_gastam_nada_no_default() -> None:
    assert _gasto_de(_faixas_largas_iguais(10)) == 0


def test_faixas_largas_gastam_um_por_pilha_aberta_visitada_com_teto_maior() -> None:
    assert _gasto_de(_faixas_largas_iguais(10), vao_maximo=TETO_DO_SCHEMA) == 45


def test_milhares_de_faixas_largas_estouram_o_orcamento_com_teto_maior() -> None:
    contexto = _contexto(_faixas_largas_iguais(3000))
    with pytest.raises(TetoGramaticasExcedido):
        discos_candidatos(contexto, vao_maximo=TETO_DO_SCHEMA)
    assert contexto.orcamento.gasto == LIMITE_CONSULTAS_PAGINA + 1


def test_milhares_de_faixas_largas_nao_estouram_no_default() -> None:
    assert _gasto_de(_faixas_largas_iguais(3000)) == 0


def test_pilha_fechada_de_faixas_largas_nao_volta_a_gastar_com_teto_maior() -> None:
    faixas = [_faixa_retangulo((10.0, 10.0 * i, 30.0, 10.0 * i + 0.5), i) for i in range(1, 11)]
    assert _gasto_de(faixas, vao_maximo=TETO_DO_SCHEMA) == 9


def test_pagina_sem_faixa_fina_nao_paga_com_teto_maior() -> None:
    caminhos = [
        circulo_bezier((50.0 + 30 * i, 50.0), 10.0, i, cor=ROXO, preenchimento=ROXO)
        for i in range(5)
    ]
    caminhos.append(poligono(_cantos((0.0, 0.0, 60.0, 40.0)), 5, ROXO, cor=None))
    assert _gasto_de(caminhos, vao_maximo=TETO_DO_SCHEMA) == 0
    assert _gasto_de(caminhos) == 0


def test_gasto_do_default_e_o_de_vao_maximo_8_explicito() -> None:
    caminhos = _faixas_retangulos(5.0)
    assert _gasto_de(caminhos) == _gasto_de(caminhos, vao_maximo=8.0) > 0


def test_vao_maximo_so_vale_por_palavra_chave() -> None:
    with pytest.raises(TypeError):
        discos_candidatos(_contexto([]), 72.0)  # type: ignore[misc]
