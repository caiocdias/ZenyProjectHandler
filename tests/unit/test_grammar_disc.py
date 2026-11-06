"""Gramática do disco terminal sobre o modelo, com os casos do corpus `declarative_symbols`."""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise
from typing import Any, Final

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

from zeny_project_handler.adapters.analysis.drawing_model.grammar_disc import (
    Disco,
    casa_disco,
    discos_candidatos,
    pontas_terminais,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caixa,
    Caminho,
    Cor,
    ItemCaminho,
    Polilinha,
    Ponto,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    LIMITE_CONSULTAS_PAGINA,
    ContextoGramatica,
    Segmento,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)

GRAMATICA: Final[dict[str, Any]] = {
    "kind": "terminal_disc",
    "fill": "purple",
    "min_span": 1.0,
    "max_span": 4.0,
    "terminal_line": True,
}
ROXO: Final[Cor] = (0.31, 0.10, 0.30)
BRANCO: Final[Cor] = (1.0, 1.0, 1.0)
CINZA: Final[Cor] = (0.5, 0.5, 0.5)
VERDE_DA_LINHA: Final[Cor] = (0.0, 0.55, 0.2)
CENTRO: Final[Ponto] = (150.0, 150.0)
RAIO: Final = 1.4
# Raio cuja caixa tem representação binária exata: o centro de uma palavra cai na borda dela.
RAIO_EXATO: Final = 1.5
# Polilinha informada à mão: a origem não pode ser a posição do disco, que é 0 nesses testes.
POSICAO_DA_LINHA: Final = 1


# --- páginas ------------------------------------------------------------------------------


def _linha_terminal(cor: Cor = CINZA) -> Caminho:
    return linha((60.0, 150.0), CENTRO, cor=cor)


def _disco(
    preenchimento: Cor = ROXO, raio: float = RAIO, centro: Ponto = CENTRO, ordem: int = 0
) -> Caminho:
    return circulo_bezier(centro, raio, ordem, cor=preenchimento, preenchimento=preenchimento)


def _cordas(centro: Ponto, raio: float, quantidade: int) -> list[Caixa]:
    """Faixas horizontais empilhadas, cada uma com a corda do disco na sua altura."""
    altura = 2 * raio / quantidade
    caixas: list[Caixa] = []
    for indice in range(quantidade):
        topo = centro[1] - raio + indice * altura
        desvio = topo + altura / 2 - centro[1]
        meia = math.sqrt(raio * raio - desvio * desvio)
        caixas.append((centro[0] - meia, topo, centro[0] + meia, topo + altura))
    return caixas


def _cantos(caixa: Caixa) -> tuple[Ponto, Ponto, Ponto, Ponto]:
    x0, y0, x1, y1 = caixa
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _faixa(caixa: Caixa, ordem: int = 0, preenchimento: Cor = ROXO) -> Caminho:
    return poligono(_cantos(caixa), ordem, preenchimento, cor=None)


def _faixa_de_triangulos(caixa: Caixa, ordem: int = 0, cor: Cor = ROXO) -> Caminho:
    """Dois triângulos com traço e preenchimento, como no corpus: 6 `l` num só subcaminho."""
    a, b, c, d = _cantos(caixa)
    pontos = (a, b, c, a, c, d, a)
    itens = tuple(ItemCaminho("l", (p, q)) for p, q in pairwise(pontos))
    return Caminho((itens,), estilo(cor, cor), "traco_e_preenchimento", ordem)


def _disco_em_faixas(centro: Ponto = CENTRO, raio: float = RAIO) -> list[Caminho]:
    """12 faixas sem folga: retângulos nas pares, dois triângulos nas ímpares."""
    return [
        _faixa_de_triangulos(caixa) if indice % 2 else _faixa(caixa)
        for indice, caixa in enumerate(_cordas(centro, raio, 12))
    ]


def _elipse(rx: float, ry: float, centro: Ponto = CENTRO) -> Caminho:
    base = circulo_bezier((0.0, 0.0), 1.0, cor=None, preenchimento=ROXO)
    itens = tuple(
        ItemCaminho("c", tuple((centro[0] + x * rx, centro[1] + y * ry) for x, y in item.pontos))
        for item in base.subcaminhos[0]
    )
    return Caminho((itens,), base.estilo, base.tipo, 0)


def _com_subcaminhos(subcaminhos: Sequence[Sequence[ItemCaminho]]) -> Caminho:
    return Caminho(
        tuple(tuple(subcaminho) for subcaminho in subcaminhos),
        estilo(None, ROXO),
        "preenchimento",
        0,
    )


def _curvas(raio: float = RAIO) -> tuple[ItemCaminho, ...]:
    return circulo_bezier(CENTRO, raio).subcaminhos[0]


def _polilinha(
    pontos: Sequence[Ponto],
    *,
    fechada: bool = False,
    cor: Cor | None = CINZA,
    origens: tuple[int, ...] = (POSICAO_DA_LINHA,),
) -> Polilinha:
    return Polilinha(tuple(pontos), fechada, estilo(cor), origens)


def _casa(
    caminhos: Sequence[Caminho],
    textos: Sequence[TextoModelo] = (),
    *,
    translucidos: frozenset[int] = frozenset(),
    primitivas: Sequence[Polilinha] | None = None,
    gramatica: dict[str, Any] = GRAMATICA,
) -> bool:
    contexto = contexto_gramaticas(
        pagina_gramatica(caminhos, textos, primitivas, translucidos=translucidos)
    )
    pontas = pontas_terminais(contexto)
    return any(
        casa_disco(contexto, gramatica, disco, pontas) for disco in discos_candidatos(contexto)
    )


def _candidatos(caminhos: Sequence[Caminho]) -> tuple[Disco, ...]:
    return discos_candidatos(contexto_gramaticas(pagina_gramatica(caminhos)))


def _termina_com(primitivas: Sequence[Polilinha], raio: float = RAIO_EXATO) -> bool:
    """O disco fica na posição 0; a linha vem só da polilinha informada."""
    return _casa([_disco(raio=raio)], primitivas=primitivas)


# --- positivos do corpus ------------------------------------------------------------------


def test_disco_solido() -> None:
    caminhos = [_linha_terminal(), _disco()]
    assert _candidatos(caminhos) == (Disco((148.6, 148.6, 151.4, 151.4), 1, frozenset({1}), ROXO),)
    assert _casa(caminhos)


def test_disco_dividido() -> None:
    caminhos = [
        _linha_terminal(VERDE_DA_LINHA),
        circulo_bezier(CENTRO, RAIO, cor=None, preenchimento=ROXO),
        circulo_bezier(CENTRO, RAIO, cor=ROXO),
    ]
    assert [disco.caminho for disco in _candidatos(caminhos)] == [1]
    assert _casa(caminhos)


def test_disco_em_faixas() -> None:
    caminhos = [_linha_terminal(), *_disco_em_faixas()]
    discos = _candidatos(caminhos)
    assert len(discos) == 1
    assert discos[0].caminho == 1
    assert discos[0].membros == frozenset(range(1, 13))
    assert discos[0].preenchimento == ROXO
    assert discos[0].caixa[1] == pytest.approx(148.6)
    assert discos[0].caixa[3] == pytest.approx(151.4)
    assert _casa(caminhos)


# --- negativos do corpus ------------------------------------------------------------------


def test_sem_disco() -> None:
    assert not _casa([_linha_terminal()])


def test_norte() -> None:
    caminhos = [
        linha((38.0, 48.0), (38.0, 100.0)),
        linha((38.0, 48.0), (32.0, 62.0)),
        linha((38.0, 48.0), (44.0, 62.0)),
    ]
    assert not _casa(caminhos, [texto("N", (30.0, 26.0, 40.0, 40.0))])


def test_verde() -> None:
    caminhos = [_linha_terminal(), _disco((0.0, 0.6, 0.0))]
    assert len(_candidatos(caminhos)) == 1
    assert not _casa(caminhos)


def test_vermelho() -> None:
    caminhos = [_linha_terminal(), _disco((0.8, 0.0, 0.0))]
    assert len(_candidatos(caminhos)) == 1
    assert not _casa(caminhos)


def test_preto() -> None:
    caminhos = [_linha_terminal(), _disco((0.0, 0.0, 0.0))]
    assert len(_candidatos(caminhos)) == 1
    assert not _casa(caminhos)


def test_lilas() -> None:
    caminhos = [_linha_terminal(), _disco((0.75, 0.55, 0.9))]
    assert len(_candidatos(caminhos)) == 1
    assert not _casa(caminhos)


def test_sem_linha() -> None:
    caminhos = [_disco()]
    assert len(_candidatos(caminhos)) == 1
    assert not _casa(caminhos)


def test_linha_atravessando() -> None:
    caminhos = [linha((60.0, 150.0), (240.0, 150.0)), _disco()]
    assert len(_candidatos(caminhos)) == 1
    assert not _casa(caminhos)


def test_grande() -> None:
    assert _candidatos([_linha_terminal(), _disco(raio=6.0)]) == ()


def test_com_rotulo() -> None:
    caminhos = [_linha_terminal(), _disco()]
    assert _casa(caminhos)
    assert not _casa(caminhos, [texto("1", (149.4, 149.0, 150.4, 151.0))])


def test_anel_lilas() -> None:
    anel = circulo_bezier((134.0, 134.0), 24.0, cor=(0.75, 0.55, 0.9))
    assert not _casa([anel], [texto("EC", (116.0, 128.0, 130.0, 140.0))])


def test_coberto() -> None:
    cobertura = _faixa((140.0, 140.0, 160.0, 160.0), preenchimento=BRANCO)
    assert not _casa([_linha_terminal(), _disco(), cobertura])


def test_triangulo() -> None:
    x, y = CENTRO
    triangulo = poligono(
        ((x, y - 1.6), (x + 1.5, y + 1.0), (x - 1.5, y + 1.0)), preenchimento=ROXO, cor=None
    )
    assert _candidatos([_linha_terminal(), triangulo]) == ()
    assert not _casa([_linha_terminal(), triangulo])


# --- cobertura ----------------------------------------------------------------------------


def test_coberto_por_translucido_nao_cobre() -> None:
    cobertura = _faixa((140.0, 140.0, 160.0, 160.0), preenchimento=BRANCO)
    caminhos = [_linha_terminal(), _disco(), cobertura]
    assert _casa(caminhos, translucidos=frozenset({2}))
    # A posição é a do caminho: outra posição translúcida não libera a cobertura.
    assert not _casa(caminhos, translucidos=frozenset({0, 1}))


def test_coberto_antes_nao_cobre() -> None:
    cobertura = _faixa((140.0, 140.0, 160.0, 160.0), preenchimento=BRANCO)
    assert _casa([_linha_terminal(), cobertura, _disco()])


def test_contorno_sem_preenchimento_nao_cobre() -> None:
    assert _casa([_linha_terminal(), _disco(), retangulo_traco((140.0, 140.0, 160.0, 160.0))])


def test_cobertura_parcial_nao_cobre() -> None:
    cobertura = _faixa((140.0, 140.0, 150.0, 160.0), preenchimento=BRANCO)
    assert _casa([_linha_terminal(), _disco(), cobertura])


@pytest.mark.parametrize(
    ("recuo", "coberto"),
    [(0.005, True), (0.02, False)],
    ids=["dentro-da-folga", "fora-da-folga"],
)
def test_cobertura_tem_folga_de_um_centesimo(recuo: float, coberto: bool) -> None:
    x0, y0, x1, y1 = CENTRO[0] - RAIO, CENTRO[1] - RAIO, CENTRO[0] + RAIO, CENTRO[1] + RAIO
    cobertura = _faixa((x0 + recuo, y0 + recuo, x1 - recuo, y1 - recuo), preenchimento=BRANCO)
    assert _casa([_linha_terminal(), _disco(), cobertura]) is not coberto


def test_ultima_faixa_nao_cobre_o_proprio_disco() -> None:
    # Só a posição depois de `max(membros)` cobre, e o disco em faixas tem várias posições.
    assert _casa([_linha_terminal(), *_disco_em_faixas()])


# --- linha terminal -----------------------------------------------------------------------


def test_linha_de_dois_segmentos_atravessando_nao_termina() -> None:
    reta = [linha((60.0, 150.0), CENTRO), linha(CENTRO, (240.0, 150.0))]
    assert not _casa([*reta, _disco()])
    em_v = [linha((60.0, 100.0), CENTRO), linha(CENTRO, (240.0, 100.0))]
    assert not _casa([*em_v, _disco()])


def test_linha_em_ziguezague_termina_no_disco() -> None:
    ziguezague = [
        linha((60.0, 100.0), (120.0, 160.0)),
        linha((120.0, 160.0), (148.5, 151.0)),
        linha((148.5, 151.0), CENTRO),
    ]
    assert _casa([*ziguezague, _disco()])


def test_contorno_do_proprio_disco_nao_conta() -> None:
    triangulo = poligono(
        (CENTRO, (200.0, 150.0), (200.0, 200.0)), preenchimento=ROXO, cor=CINZA, ordem=1
    )
    contexto = contexto_gramaticas(pagina_gramatica([_disco(), triangulo]))
    pontas = pontas_terminais(contexto)
    caixa = (148.6, 148.6, 151.4, 151.4)
    assert casa_disco(contexto, GRAMATICA, Disco(caixa, 0, frozenset({0}), ROXO), pontas)
    assert not casa_disco(contexto, GRAMATICA, Disco(caixa, 0, frozenset({0, 1}), ROXO), pontas)


def test_segmento_com_traco_e_preenchimento_conta() -> None:
    triangulo = poligono((CENTRO, (200.0, 150.0), (200.0, 200.0)), preenchimento=ROXO, cor=CINZA)
    assert _casa([_disco(), triangulo])


@pytest.mark.parametrize(
    ("cor", "termina"),
    [(None, False), (BRANCO, False), ((0.9, 0.9, 0.9), False), ((0.89, 0.95, 0.95), True)],
    ids=["sem-cor", "branca", "no-limiar", "abaixo-do-limiar"],
)
def test_polilinha_quase_branca_nao_termina(cor: Cor | None, termina: bool) -> None:
    assert _termina_com([_polilinha(((60.0, 150.0), CENTRO), cor=cor)]) is termina


@pytest.mark.parametrize(
    ("cor", "termina"),
    [(None, False), ((0.9, 0.9, 0.9), False), ((0.89, 0.95, 0.95), True)],
    ids=["sem-cor", "no-limiar", "abaixo-do-limiar"],
)
def test_segmento_quase_branco_nao_termina(cor: Cor | None, termina: bool) -> None:
    triangulo = poligono((CENTRO, (200.0, 150.0), (200.0, 200.0)), preenchimento=ROXO, cor=cor)
    assert _casa([_disco(), triangulo]) is termina


def test_traco_puro_so_conta_pela_polilinha() -> None:
    # Sem primitivas, o segmento de traço puro de `grade_segmentos` não vira linha terminal.
    assert not _casa([_linha_terminal(), _disco()], primitivas=())


def test_polilinha_fechada_nao_termina() -> None:
    triangulo = (CENTRO, (200.0, 150.0), (200.0, 200.0))
    assert not _termina_com([_polilinha(triangulo, fechada=True)])


def test_moldura_com_traco_e_preenchimento_nao_conta_como_linha() -> None:
    # O `re` do motor não dá segmentos, e o núcleo não gera segmento de moldura fechada.
    moldura = poligono(_cantos((150.0, 150.0, 200.0, 200.0)), preenchimento=ROXO, cor=CINZA)
    assert not _casa([_disco(), moldura])


def test_polilinha_sem_origem_nao_termina() -> None:
    assert not _termina_com([_polilinha(((60.0, 150.0), CENTRO), origens=())])


def test_polilinha_nao_finita_nao_quebra() -> None:
    assert not _termina_com([_polilinha(((math.nan, 150.0), CENTRO))])
    assert not _termina_com([_polilinha(((math.inf, 150.0), CENTRO))])


def test_polilinha_de_um_ponto_nao_termina() -> None:
    assert not _termina_com([_polilinha((CENTRO,))])
    assert not _termina_com([_polilinha(())])


@pytest.mark.parametrize(
    ("ponta_proxima", "termina"),
    [(151.0, True), (151.2, False)],
    ids=["dentro-de-35-por-cento", "fora-de-35-por-cento"],
)
def test_ponta_proxima_usa_35_por_cento_do_vao(ponta_proxima: float, termina: bool) -> None:
    # Vão 3: a ponta precisa estar a até 1,05 do centro.
    assert _termina_com([_polilinha(((60.0, 150.0), (ponta_proxima, 150.0)))]) is termina


@pytest.mark.parametrize(
    ("ponta_proxima", "termina"),
    [(150.55, True), (150.65, False)],
    ids=["dentro-do-piso", "fora-do-piso"],
)
def test_ponta_proxima_tem_piso_de_0_6(ponta_proxima: float, termina: bool) -> None:
    # Vão 1,2 daria 0,42 sem o piso.
    assert _termina_com([_polilinha(((60.0, 150.0), (ponta_proxima, 150.0)))], 0.6) is termina


@pytest.mark.parametrize(
    ("ponta_distante", "termina"),
    [(156.0, False), (156.5, True)],
    ids=["no-dobro-do-vao", "alem-do-dobro-do-vao"],
)
def test_ponta_distante_passa_do_dobro_do_vao(ponta_distante: float, termina: bool) -> None:
    assert _termina_com([_polilinha((CENTRO, (ponta_distante, 150.0)))]) is termina


def test_ponta_longe_fora_da_pagina_ainda_termina() -> None:
    assert _termina_com([_polilinha(((1e300, 150.0), CENTRO))])


# --- pontas_terminais ---------------------------------------------------------------------


def test_pontas_indexam_uma_entrada_por_ponta() -> None:
    a, b = (60.0, 150.0), (240.0, 150.0)
    contexto = contexto_gramaticas(pagina_gramatica([linha(a, b)]))
    pontas = pontas_terminais(contexto)
    assert pontas.consultar((*a, *a)) == [Segmento(a, b, 0)]
    assert pontas.consultar((*b, *b)) == [Segmento(b, a, 0)]


def test_pontas_indexam_segmentos_com_traco_e_preenchimento() -> None:
    triangulo = poligono((CENTRO, (200.0, 150.0), (200.0, 200.0)), preenchimento=ROXO, cor=CINZA)
    contexto = contexto_gramaticas(pagina_gramatica([triangulo]))
    assert Segmento(CENTRO, (200.0, 150.0), 0) in pontas_terminais(contexto).consultar(
        (*CENTRO, *CENTRO)
    )


def test_pontas_gastam_um_por_ponta_indexada() -> None:
    pagina = pagina_gramatica(
        [
            linha((10.0, 10.0), (20.0, 10.0)),
            linha((30.0, 30.0), (40.0, 40.0)),
            # A margem é de 16 pt: esta ponta fica fora e não entra no índice.
            linha((50.0, 50.0), (-100.0, 50.0)),
            poligono(((60.0, 60.0), (70.0, 60.0), (70.0, 70.0)), preenchimento=ROXO),
        ]
    )
    contexto = contexto_gramaticas(pagina)
    antes = contexto.orcamento.gasto
    pontas_terminais(contexto)
    assert contexto.orcamento.gasto - antes == 2 + 2 + 1 + 6


def test_ponta_dentro_da_margem_da_pagina_entra_no_indice() -> None:
    a, b = (-10.0, 150.0), (150.0, 150.0)
    contexto = contexto_gramaticas(pagina_gramatica([linha(a, b)]))
    assert pontas_terminais(contexto).consultar((*a, *a)) == [Segmento(a, b, 0)]


# --- palavra sobre o disco ----------------------------------------------------------------


def test_centro_da_palavra_na_borda_do_disco_recusa() -> None:
    # Caixa do disco com x1 = 151,5; a palavra tem centro exato em 151,5. `ponto_em` é fechado,
    # enquanto `Rect.contains(Point)` do motor é semiaberto: aqui o núcleo recusa de propósito.
    caminhos = [_linha_terminal(), _disco(raio=RAIO_EXATO)]
    assert not _casa(caminhos, [texto("X", (151.0, 149.0, 152.0, 151.0))])


def test_centro_da_palavra_fora_do_disco_nao_recusa() -> None:
    caminhos = [_linha_terminal(), _disco(raio=RAIO_EXATO)]
    assert _casa(caminhos, [texto("X", (151.25, 149.0, 152.25, 151.0))])


def test_span_inteiro_sobre_o_disco_recusa() -> None:
    caminhos = [_linha_terminal(), _disco()]
    # O centro da caixa (164,5; 150) fica fora do disco, e só a interseção recusa.
    caixa: Caixa = (149.0, 149.0, 180.0, 151.0)
    assert not _casa(caminhos, [texto("A B C", caixa, origem="shx")])
    assert not _casa(caminhos, [texto("A B C", caixa, rotacao=45.0)])
    # De controle: repartida, nenhuma palavra tem o centro no disco; e palavra única não é
    # `inteira`, então vale o centro.
    assert _casa(caminhos, [texto("A B C", caixa)])
    assert _casa(caminhos, [texto("ABC", caixa, origem="shx")])


def test_span_inteiro_que_so_encosta_no_disco_nao_recusa() -> None:
    caixa: Caixa = (151.5, 149.0, 180.0, 151.0)
    assert _casa([_linha_terminal(), _disco(raio=RAIO_EXATO)], [texto("A B", caixa, origem="shx")])


# --- faixas -------------------------------------------------------------------------------


def test_faixas_com_buraco_nao_viram_disco() -> None:
    cordas = _cordas(CENTRO, RAIO, 12)
    assert _candidatos([_faixa(caixa) for caixa in (*cordas[:5], *cordas[7:])]) == ()


def test_faixa_descentrada_nao_vira_disco() -> None:
    def com_desvio(desvio: float) -> list[Caminho]:
        cordas = _cordas(CENTRO, RAIO, 12)
        x0, y0, x1, y1 = cordas[1]
        cordas[1] = (x0 + desvio, y0, x1 + desvio, y1)
        return [_faixa(caixa) for caixa in cordas]

    # O desvio de 0,5 passa dos 15% da largura; o de 0,3, não, e a pilha é a mesma.
    assert len(_candidatos(com_desvio(0.3))) == 1
    assert _candidatos(com_desvio(0.5)) == ()


def test_faixas_iguais_nao_viram_disco() -> None:
    altura = 2 * RAIO / 12
    topo = CENTRO[1] - RAIO
    faixas = [
        _faixa((148.6, topo + indice * altura, 151.4, topo + (indice + 1) * altura))
        for indice in range(12)
    ]
    assert _candidatos(faixas) == ()


@pytest.mark.parametrize(
    ("folga", "discos"),
    [(0.1, 1), (0.2, 0)],
    ids=["dentro-da-folga", "fora-da-folga"],
)
def test_folga_entre_faixas_e_de_0_15(folga: float, discos: int) -> None:
    cordas = _cordas(CENTRO, RAIO, 12)
    deslocadas = [(x0, y0 + folga, x1, y1 + folga) for x0, y0, x1, y1 in cordas[6:]]
    faixas = [_faixa(caixa) for caixa in (*cordas[:6], *deslocadas)]
    assert len(_candidatos(faixas)) == discos


@pytest.mark.parametrize(
    ("raio", "quantidade", "discos"),
    [(1.0, 4, 0), (1.25, 5, 1)],
    ids=["quatro-faixas", "cinco-faixas"],
)
def test_pilha_precisa_de_cinco_faixas(raio: float, quantidade: int, discos: int) -> None:
    faixas = [_faixa(caixa) for caixa in _cordas(CENTRO, raio, quantidade)]
    assert len(_candidatos(faixas)) == discos


def test_faixa_alta_demais_nao_conta() -> None:
    # Cada faixa com 0,7 de altura; a pilha seria redonda, com 7 faixas e raio 2,45.
    faixas = [_faixa(caixa) for caixa in _cordas(CENTRO, 2.45, 7)]
    assert _candidatos(faixas) == ()


def test_faixas_verticais_nao_viram_disco() -> None:
    # R-E06.2.1-7: a altura é a do espaço visual, e o disco girado 90° não tem faixas baixas.
    giradas = [(y0, x0, y1, x1) for x0, y0, x1, y1 in _cordas(CENTRO, RAIO, 12)]
    assert _candidatos([_faixa(caixa) for caixa in giradas]) == ()


def test_faixa_larga_demais_nao_conta() -> None:
    # Sem as faixas centrais, largas demais, o resto da pilha do raio 4,2 tem buraco.
    faixas = [_faixa(caixa) for caixa in _cordas(CENTRO, 4.2, 15)]
    assert _candidatos(faixas) == ()


def test_um_caminho_de_varios_retangulos_conta_uma_faixa_por_subcaminho() -> None:
    subcaminhos = [_faixa(caixa).subcaminhos[0] for caixa in _cordas(CENTRO, RAIO, 12)]
    discos = _candidatos([_com_subcaminhos(subcaminhos)])
    assert len(discos) == 1
    assert discos[0].membros == frozenset({0})


def test_caminho_so_de_linhas_conta_uma_faixa_pela_caixa() -> None:
    # Dois subcaminhos sem forma de retângulo, numa só faixa: a caixa é a da união deles.
    faixas = []
    for x0, y0, x1, y1 in _cordas(CENTRO, RAIO, 12):
        meio = (x0 + x1) / 2
        esquerda = ((x0, y0), (meio, y0), (meio, y1), (x0, y0))
        direita = ((meio, y0), (x1, y0), (x1, y1), (meio, y0))
        faixas.append(
            _com_subcaminhos(
                [
                    tuple(ItemCaminho("l", (p, q)) for p, q in pairwise(s))
                    for s in (esquerda, direita)
                ]
            )
        )
    assert len(_candidatos(faixas)) == 1


def test_caminho_com_menos_de_tres_linhas_nao_e_faixa() -> None:
    faixas = []
    for x0, y0, x1, y1 in _cordas(CENTRO, RAIO, 12):
        itens = (ItemCaminho("l", ((x0, y0), (x1, y0))), ItemCaminho("l", ((x1, y0), (x1, y1))))
        faixas.append(_com_subcaminhos([itens]))
    assert _candidatos(faixas) == ()


def test_faixa_com_curva_nao_conta() -> None:
    # A curva fica dentro da faixa: a caixa do caminho seria uma faixa boa, se ela contasse.
    faixas = []
    for caixa in _cordas(CENTRO, RAIO, 12):
        a, b, c, d = _cantos(caixa)
        faixas.append(
            _com_subcaminhos([_faixa(caixa).subcaminhos[0], (ItemCaminho("c", (a, d, c, b)),)])
        )
    assert _candidatos(faixas) == ()


def test_subcaminho_aberto_nao_e_retangulo() -> None:
    # 4 lados alternados, em espiral: um caminho só, cuja caixa inteira é alta demais.
    subcaminhos = []
    for x0, y0, x1, y1 in _cordas(CENTRO, RAIO, 12):
        pontos = ((x0, y0), (x1, y0), (x1, y1), (x0 + 0.05, y1), (x0 + 0.05, y0 + 0.05))
        subcaminhos.append(tuple(ItemCaminho("l", (p, q)) for p, q in pairwise(pontos)))
    assert _candidatos([_com_subcaminhos(subcaminhos)]) == ()


def test_quadrilatero_inclinado_nao_e_retangulo() -> None:
    # Fechado, mas sem lados nos eixos: conta como polígono, pela caixa do caminho inteiro.
    subcaminhos = []
    for x0, y0, x1, y1 in _cordas(CENTRO, RAIO, 12):
        meio_x, meio_y = (x0 + x1) / 2, (y0 + y1) / 2
        pontos = ((meio_x, y0), (x1, meio_y), (meio_x, y1), (x0, meio_y), (meio_x, y0))
        subcaminhos.append(tuple(ItemCaminho("l", (p, q)) for p, q in pairwise(pontos)))
    assert _candidatos([_com_subcaminhos(subcaminhos)]) == ()


def test_faixa_larga_fica_fora_da_pilha() -> None:
    cordas = _cordas(CENTRO, RAIO, 12)
    baixo = cordas[-1][3]
    larga = _faixa((145.0, baixo, 154.0, baixo + 0.2))
    discos = _candidatos([*(_faixa(caixa) for caixa in cordas), larga])
    assert [disco.membros for disco in discos] == [frozenset(range(12))]


def test_pilha_eliptica_nao_vira_disco() -> None:
    # Perfil de elipse: cada faixa bate com a corda, e só o aspecto da união recusa.
    faixas = [
        _faixa((150.0 - 2 * (150.0 - x0), y0, 150.0 + 2 * (x1 - 150.0), y1))
        for x0, y0, x1, y1 in _cordas(CENTRO, RAIO, 12)
    ]
    assert _candidatos(faixas) == ()


def test_faixa_continua_a_primeira_pilha_aberta() -> None:
    primeira, *resto = _cordas(CENTRO, RAIO, 12)
    faixas = [_faixa(primeira), _faixa(primeira), *(_faixa(caixa) for caixa in resto)]
    discos = _candidatos(faixas)
    assert [disco.membros for disco in discos] == [frozenset({0, *range(2, 13)})]


@pytest.mark.parametrize(
    "outro_centro",
    [(150.0, 100.0), (100.0, 150.0)],
    ids=["acima", "ao-lado"],
)
def test_dois_discos_em_faixas_da_mesma_cor(outro_centro: Ponto) -> None:
    caminhos = [*_disco_em_faixas(), *_disco_em_faixas(outro_centro)]
    assert len(_candidatos(caminhos)) == 2


def test_faixas_empilham_por_cor_arredondada_a_tres_casas() -> None:
    cordas = _cordas(CENTRO, RAIO, 12)
    quase_igual = [
        _faixa(caixa, preenchimento=(0.3101 if i % 2 else 0.3099, 0.1, 0.3))
        for i, caixa in enumerate(cordas)
    ]
    discos = _candidatos(quase_igual)
    assert len(discos) == 1
    assert discos[0].preenchimento == ROXO
    outra_cor = [
        _faixa(caixa, preenchimento=(0.312 if i % 2 else 0.31, 0.1, 0.3))
        for i, caixa in enumerate(cordas)
    ]
    assert _candidatos(outra_cor) == ()


def test_faixa_sem_preenchimento_nao_conta() -> None:
    assert _candidatos([retangulo_traco(caixa) for caixa in _cordas(CENTRO, RAIO, 12)]) == ()


def test_faixa_nao_finita_nao_quebra() -> None:
    faixas = [_faixa(caixa) for caixa in _cordas(CENTRO, RAIO, 12)]
    assert _candidatos([*faixas, _faixa((math.nan, 0.0, 1.0, 0.5))])[0].membros == frozenset(
        range(12)
    )


# --- disco de curva -----------------------------------------------------------------------


def test_disco_de_curva_soma_os_subcaminhos() -> None:
    curvas = _curvas()
    fecho = ItemCaminho("l", ((151.4, 150.0), (151.4, 150.5)))
    assert len(_candidatos([_com_subcaminhos([curvas[:2], curvas[2:], (fecho,)])])) == 1


@pytest.mark.parametrize(
    ("comprimento", "discos"),
    [(0.6, 1), (0.8, 0)],
    ids=["fecho-curto", "fecho-longo"],
)
def test_linha_de_fecho_ate_um_quarto_do_lado(comprimento: float, discos: int) -> None:
    # Um quarto do lado de 2,8 são 0,7.
    fecho = ItemCaminho("l", ((151.4, 150.0), (151.4, 150.0 + comprimento)))
    assert len(_candidatos([_com_subcaminhos([_curvas(), (fecho,)])])) == discos


def test_duas_linhas_de_fecho_nao_viram_disco() -> None:
    fecho = ItemCaminho("l", ((151.4, 150.0), (151.4, 150.1)))
    assert _candidatos([_com_subcaminhos([_curvas(), (fecho, fecho)])]) == ()


def test_quantidade_errada_de_curvas_nao_vira_disco() -> None:
    assert _candidatos([_com_subcaminhos([_curvas()[:3]])]) == ()
    assert _candidatos([_com_subcaminhos([_curvas(), _curvas()])]) == ()


def test_curvas_fora_da_elipse_nao_viram_disco() -> None:
    x0, y0, x1, y1 = 148.6, 148.6, 151.4, 151.4
    cantos = ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))
    itens = tuple(ItemCaminho("c", (p, p, q, q)) for p, q in pairwise(cantos))
    assert _candidatos([_com_subcaminhos([itens])]) == ()


def test_fim_de_curva_fora_da_elipse_nao_vira_disco() -> None:
    inicios = ((151.4, 150.0), (150.0, 151.4), (148.6, 150.0), (150.0, 148.6))
    fins = ((151.4, 151.4), (148.6, 151.4), (148.6, 148.6), (151.4, 148.6))
    itens = tuple(ItemCaminho("c", (p, p, q, q)) for p, q in zip(inicios, fins, strict=True))
    assert _candidatos([_com_subcaminhos([itens])]) == ()


def test_curva_nao_finita_nao_vira_disco() -> None:
    curvas = _curvas()
    x, y = curvas[0].pontos[1]
    torta = ItemCaminho("c", (curvas[0].pontos[0], (math.nan, y), (x, y), curvas[0].pontos[3]))
    assert _candidatos([_com_subcaminhos([(torta, *curvas[1:])])]) == ()


@pytest.mark.parametrize(
    ("rx", "ry", "discos"),
    [(1.2, 1.0, 1), (1.0, 1.2, 1), (1.3, 1.0, 0), (1.0, 1.3, 0)],
    ids=["larga", "alta", "larga-demais", "alta-demais"],
)
def test_aspecto_do_disco_de_curva(rx: float, ry: float, discos: int) -> None:
    assert len(_candidatos([_elipse(rx, ry)])) == discos


def test_circulo_de_raio_zero_nao_vira_disco() -> None:
    assert _candidatos([_disco(raio=0.0)]) == ()


def test_circulo_sem_preenchimento_nao_vira_disco() -> None:
    assert _candidatos([circulo_bezier(CENTRO, RAIO)]) == ()


def test_vao_acima_de_oito_nao_vira_disco_e_oito_vira() -> None:
    assert len(_candidatos([_disco(raio=4.0)])) == 1
    assert _candidatos([_disco(raio=4.1)]) == ()


def test_uma_caixa_arredondada_da_um_candidato_so() -> None:
    primeiro, segundo = _disco(), _disco((0.8, 0.0, 0.0))
    discos = _candidatos([primeiro, segundo])
    assert [disco.caminho for disco in discos] == [0]


def test_disco_de_curva_vem_antes_do_de_faixas_na_mesma_caixa() -> None:
    faixas = _disco_em_faixas()
    discos = _candidatos([*faixas, circulo_bezier(CENTRO, RAIO, cor=None, preenchimento=ROXO)])
    assert discos[0].membros == frozenset({12})


def test_caminho_sem_subcaminho_nao_vira_disco() -> None:
    assert _candidatos([_com_subcaminhos([])]) == ()


def test_preenchimento_nao_finito_nao_casa() -> None:
    caminhos = [_linha_terminal(), _disco((math.nan, 0.1, 0.3))]
    assert not _casa(caminhos)


# --- gramática ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raio", "casa"),
    [(0.4, False), (0.5, True), (2.0, True), (2.1, False)],
    ids=["menor", "no-minimo", "no-maximo", "maior"],
)
def test_vao_entre_os_limites_da_gramatica(raio: float, casa: bool) -> None:
    assert _casa([_linha_terminal(), _disco(raio=raio)]) is casa


@pytest.mark.parametrize(
    ("preenchimento", "casa"),
    [
        (ROXO, True),
        ((0.2, 0.1, 0.3), False),
        ((0.3, 0.1, 0.2), False),
        ((0.3, 0.24, 0.3), False),
        ((0.3, 0.23, 0.3), True),
        ((0.6, 0.1, 0.6), True),
        ((0.61, 0.1, 0.6), False),
    ],
    ids=[
        "corpus",
        "pouco-vermelho",
        "pouco-azul",
        "verde-no-limiar",
        "verde-abaixo",
        "brilho-no-limiar",
        "brilho-acima",
    ],
)
def test_limiares_do_roxo(preenchimento: Cor, casa: bool) -> None:
    assert _casa([_linha_terminal(), _disco(preenchimento)]) is casa


# --- bordas da página ---------------------------------------------------------------------


def test_disco_na_borda_da_pagina_casa() -> None:
    caminhos = [linha((100.0, 1.0), (1.0, 1.0)), _disco(centro=(1.0, 1.0))]
    assert _casa(caminhos)


def test_disco_fora_da_pagina_nao_casa_nem_quebra() -> None:
    fora = (-100.0, -100.0)
    assert not _casa([linha((-200.0, -100.0), fora), _disco(centro=fora)])


# --- orçamento ----------------------------------------------------------------------------


def _faixas_mesma_altura(quantidade: int) -> list[Caminho]:
    """Nenhuma continua a outra, e todas ficam abertas: a página hostil do laço quadrático."""
    return [_faixa((10.0, 10.0, 12.0, 10.5)) for _ in range(quantidade)]


def test_milhares_de_faixas_estouram_o_orcamento() -> None:
    contexto = contexto_gramaticas(pagina_gramatica(_faixas_mesma_altura(3000)))
    with pytest.raises(TetoGramaticasExcedido):
        discos_candidatos(contexto)
    # Para na primeira visita acima do limite: o trabalho fica limitado pelo orçamento.
    assert contexto.orcamento.gasto == LIMITE_CONSULTAS_PAGINA + 1


def test_faixas_gastam_um_por_pilha_aberta_visitada() -> None:
    contexto = contexto_gramaticas(pagina_gramatica(_faixas_mesma_altura(10)))
    antes = contexto.orcamento.gasto
    discos_candidatos(contexto)
    assert contexto.orcamento.gasto - antes == 45


def test_pilha_fechada_nao_volta_a_gastar() -> None:
    faixas = [_faixa((10.0, 10.0 * indice, 12.0, 10.0 * indice + 0.5)) for indice in range(1, 11)]
    contexto = contexto_gramaticas(pagina_gramatica(faixas))
    antes = contexto.orcamento.gasto
    discos_candidatos(contexto)
    assert contexto.orcamento.gasto - antes == 9


def _contexto_com_pontas_na_celula(limite: int = LIMITE_CONSULTAS_PAGINA) -> ContextoGramatica:
    linhas = [_polilinha((CENTRO, (150.1, 150.1))) for _ in range(1000)]
    return contexto_gramaticas(pagina_gramatica([_disco()], primitivas=linhas), limite=limite)


def test_milhares_de_pontas_na_celula_estouram_o_orcamento() -> None:
    medicao = _contexto_com_pontas_na_celula()
    pontas_terminais(medicao)
    contexto = _contexto_com_pontas_na_celula(medicao.orcamento.gasto + 100)
    pontas = pontas_terminais(contexto)
    disco = discos_candidatos(contexto)[0]
    with pytest.raises(TetoGramaticasExcedido):
        casa_disco(contexto, GRAMATICA, disco, pontas)
