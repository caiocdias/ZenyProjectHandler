"""Teto da gramática `disc_mark`: classificação única, gasto linear e páginas hostis.

Cada `gastar` de `grammar_disc_mark.py` tem uma página em que só ele separa o gasto linear do
estouro; o fechamento da tarefa registra a mutação (cada `gastar` trocado por `pass`) e qual teste
a mata.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

import pytest
from tests.fixtures.symbol_grammars.disc_mark import (
    CAIXA_DUPLA,
    CENTRO,
    FUSIVEL,
    VAO,
    VERMELHO,
    conteudo_caixa_dupla,
    conteudo_fusivel,
    disco,
    polilinha,
    pontos_dos_terminais,
)
from tests.fixtures.symbol_grammars.paginas import circulo_bezier, linha, pagina_gramatica

from zeny_project_handler.adapters.analysis.drawing_model.grammar_disc_mark import (
    CandidatoDiscMark,
    _deduplicar,
    disc_mark_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    LIMITE_CONSULTAS_PAGINA,
    OrcamentoConsultas,
    PaginaGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    casar_variantes,
    gasto_por_fase,
)

_PASSO: Final = 40.0
_COLUNAS: Final = 10
_RAZAO_MAXIMA: Final = 12
_ISOLADOS: Final = 1_000
_EMPILHADOS: Final = 60
_POLILINHAS: Final = 300
_Variante = tuple[Mapping[str, Any], Mapping[str, Any]]


def _pagina(caminhos: Sequence[Caminho], quantidade: int = 1) -> PaginaGramatica:
    return pagina_gramatica(
        caminhos,
        primitivas=(),
        largura=_COLUNAS * _PASSO + 60.0,
        altura=(quantidade // _COLUNAS + 2) * _PASSO + 60.0,
    )


def _pares() -> list[_Variante]:
    return [
        ({"id": "pacote"}, {"id": nome, "recognition": {"status": "enabled", "grammar": gramatica}})
        for nome, gramatica in (("fusivel", FUSIVEL), ("caixa-dupla", CAIXA_DUPLA))
    ]


def _isolados(quantidade: int) -> list[Caminho]:
    """Fusíveis e caixas duplas alternados, cada um longe dos outros."""
    caminhos: list[Caminho] = []
    for i in range(quantidade):
        centro = (30.0 + (i % _COLUNAS) * _PASSO, 30.0 + (i // _COLUNAS) * _PASSO)
        conteudo = conteudo_fusivel if i % 2 == 0 else conteudo_caixa_dupla
        caminhos.append(disco(VAO, VERMELHO, len(caminhos), centro))
        caminhos.extend(_em(conteudo(VAO, len(caminhos)), centro))
    return caminhos


def _em(caminhos: list[Caminho], centro: tuple[float, float]) -> list[Caminho]:
    """Os fixtures de conteúdo são montados em torno de `CENTRO`; aqui vão para `centro`."""
    dx, dy = centro[0] - CENTRO[0], centro[1] - CENTRO[1]
    return [
        Caminho(
            tuple(
                tuple(
                    type(item)(item.tipo, tuple((x + dx, y + dy) for x, y in item.pontos))
                    for item in subcaminho
                )
                for subcaminho in caminho.subcaminhos
            ),
            caminho.estilo,
            caminho.tipo,
            caminho.ordem,
        )
        for caminho in caminhos
    ]


def _gasto_dos_candidatos(pagina: PaginaGramatica) -> tuple[int, int]:
    contexto = contexto_gramaticas(pagina, limite=10**9)
    antes = contexto.orcamento.gasto
    candidatos = disc_mark_candidatos(contexto)
    return contexto.orcamento.gasto - antes, len(candidatos)


def _gasto_isolados(quantidade: int) -> tuple[int, int]:
    return _gasto_dos_candidatos(_pagina(_isolados(quantidade), quantidade))


def _limite_linear(pagina: PaginaGramatica, discos: int) -> int:
    """Gasto dos índices da página mais o dobro do gasto linear medido por disco isolado."""
    por_disco = _gasto_isolados(100)[0] / 100
    return contexto_gramaticas(pagina).orcamento.gasto + int(2 * por_disco * discos)


def _estoura(pagina: PaginaGramatica, limite: int) -> bool:
    contexto = contexto_gramaticas(pagina, limite=limite)
    try:
        disc_mark_candidatos(contexto)
    except TetoGramaticasExcedido:
        return True
    return False


# --- classificação uma vez por candidato e linearidade ------------------------------------


def test_classificacao_uma_vez_por_candidato() -> None:
    """As 2 variantes custam o mesmo que uma só: `casa_disc_mark` só filtra a classificação."""
    pagina = _pagina(_isolados(12), 12)

    duas = gasto_por_fase(pagina, _pares())
    uma = gasto_por_fase(pagina, _pares()[:1])

    assert duas.gramaticas > 0
    assert duas == uma


def test_gasto_cresce_linear_com_os_desenhos() -> None:
    """Contagem de trabalho (não tempo de parede): 10x mais desenhos isolados, no máximo 12x."""
    (pequeno, achados_pequeno), (grande, achados_grande) = _gasto_isolados(10), _gasto_isolados(100)

    assert (achados_pequeno, achados_grande) == (10, 100)
    assert pequeno > 0
    assert grande / pequeno <= _RAZAO_MAXIMA


# --- página hostil: discos empilhados sobre muito conteúdo preto --------------------------


def _empilhados(discos: int, polilinhas: int) -> PaginaGramatica:
    """Cada disco vê todas as polilinhas: `discos` x `polilinhas` leituras de conteúdo."""
    caminhos = [disco(VAO, VERMELHO, i) for i in range(discos)]
    for j in range(polilinhas):
        deslocamento = (j % 7) * 0.02
        caminhos.append(
            polilinha(
                VAO,
                (-0.05, 0.3),
                (0.05, 0.02),
                discos + j,
                segmentos=10,
                centro=(CENTRO[0] + deslocamento, CENTRO[1]),
            )
        )
    return _pagina(caminhos)


def test_pagina_sa_cabe_no_limite_linear() -> None:
    """Controle negativo: com o mesmo cálculo de limite do teste hostil, isolados não estouram."""
    pagina = _pagina(_isolados(_ISOLADOS), _ISOLADOS)
    contexto = contexto_gramaticas(pagina, limite=_limite_linear(pagina, _ISOLADOS))

    assert len(disc_mark_candidatos(contexto)) == _ISOLADOS


def test_pagina_hostil_estoura_o_limite_linear() -> None:
    pagina = _empilhados(_EMPILHADOS, _POLILINHAS)
    limite = _limite_linear(pagina, _EMPILHADOS)
    contexto = contexto_gramaticas(pagina, limite=limite)

    with pytest.raises(TetoGramaticasExcedido):
        disc_mark_candidatos(contexto)

    assert contexto.orcamento.gasto > limite


def test_pagina_hostil_ultrapassa_o_limite_real_da_pagina() -> None:
    """Sem limite calibrado: o teto de produção barra o casamento inteiro das variantes."""
    pagina = _empilhados(300, 800)
    assert contexto_gramaticas(pagina).orcamento.gasto < LIMITE_CONSULTAS_PAGINA

    with pytest.raises(TetoGramaticasExcedido):
        casar_variantes(pagina, _pares())


# --- um teste por `gastar`: só ele separa o linear do estouro -----------------------------


def test_gasto_dos_subcaminhos_do_disco_vermelho() -> None:
    """Um disco vermelho de milhares de subcaminhos paga cada um, antes de contar os itens."""
    base = circulo_bezier(CENTRO, VAO / 2, 0, cor=VERMELHO, preenchimento=VERMELHO)
    hostil = Caminho(base.subcaminhos * 3_000, base.estilo, base.tipo, base.ordem)
    pagina = _pagina([hostil])

    assert _estoura(pagina, contexto_gramaticas(pagina).orcamento.gasto + 1_000)
    assert not _estoura(
        _pagina([base]), contexto_gramaticas(_pagina([base])).orcamento.gasto + 1_000
    )


def test_gasto_por_caminho_da_pagina() -> None:
    """Varrer os caminhos em busca de discos custa 1 por caminho, mesmo sem nenhum disco."""
    caminhos = [linha((10.0, 10.0 + i * 0.01), (20.0, 10.0 + i * 0.01), i) for i in range(5_000)]
    pagina = _pagina(caminhos)

    assert _estoura(pagina, contexto_gramaticas(pagina).orcamento.gasto + 1_000)
    assert not _estoura(pagina, contexto_gramaticas(pagina).orcamento.gasto + 6_000)


def test_gasto_por_disco_vermelho_classificado() -> None:
    """Cada disco vermelho sem conteúdo custa 3,4: o caminho, o subcaminho, a classificação e
    0,4 de leitura do disco (6.800 medidos para 2.000 discos); sem a classificação, 4.800."""
    quantidade = 2_000
    caminhos = [
        disco(VAO, VERMELHO, i, (30.0 + (i % 40) * 30.0, 30.0 + (i // 40) * 30.0))
        for i in range(quantidade)
    ]
    pagina = _pagina(caminhos, quantidade)
    base = contexto_gramaticas(pagina).orcamento.gasto

    assert _estoura(pagina, base + 5_000)
    assert not _estoura(pagina, base + 6_800)


def test_gasto_dos_itens_do_conteudo_preto() -> None:
    """Cada leitura de um desenho preto dentro do disco paga os itens dele."""
    pagina = _empilhados(_EMPILHADOS, _POLILINHAS)
    base = contexto_gramaticas(pagina).orcamento.gasto
    leituras = _EMPILHADOS * _POLILINHAS * 10

    assert _estoura(pagina, base + leituras - 1)


def test_gasto_da_comparacao_por_posicao() -> None:
    """Centenas de curvas em posições distintas custam mais que a leitura dos itens delas."""
    pontos = pontos_dos_terminais(VAO, 1)
    pagina = _pagina([disco(VAO, VERMELHO, 0), *pontos, *_curvas_espalhadas(1_500)])
    base = contexto_gramaticas(pagina).orcamento.gasto
    itens = 1_500 * 10

    assert _estoura(
        pagina, base + 3 * itens
    )  # 66.487 medidos: 15.000 de itens, o resto é a posição
    assert not _estoura(pagina, base + 70_000)


def _curvas_espalhadas(quantidade: int) -> list[Caminho]:
    """Curvas abertas de 10 segmentos, cada uma com o centro numa de ~60 posições distintas."""
    caminhos: list[Caminho] = []
    for i in range(quantidade):
        passo = 0.13 * VAO
        centro = (
            CENTRO[0] + ((i % 8) - 3.5) * passo * 0.7,
            CENTRO[1] + (((i // 8) % 8) - 3.5) * passo * 0.7,
        )
        caminhos.append(
            polilinha(VAO * 0.04, (-0.5, 0.0), (0.5, 0.0), i + 1, segmentos=10, centro=centro)
        )
    return caminhos


def test_gasto_das_retas_da_caixa_dupla() -> None:
    """Muitas retas curtas (que não são a da caixa) dentro do disco pagam também a varredura."""
    caixa_dupla = conteudo_caixa_dupla(VAO, 1)
    retas = [
        linha((CENTRO[0] - 0.25, CENTRO[1] + i * 0.0001), (CENTRO[0] + 0.25, CENTRO[1]), 10 + i)
        for i in range(3_000)
    ]
    pagina = _pagina([disco(VAO, VERMELHO, 0), *caixa_dupla, *retas])
    base = contexto_gramaticas(pagina).orcamento.gasto

    # 15.050 medidos acima dos índices; sem a varredura das retas, 12.048.
    assert _estoura(pagina, base + 14_000)
    assert not _estoura(pagina, base + 16_000)


def test_gasto_da_deduplicacao_por_vizinhanca() -> None:
    """Candidatos de centros próximos, todos distintos, pagam 1 + os vizinhos já escolhidos."""
    quantidade = 1_500
    pagina = _pagina([])
    candidatos = _candidatos_proximos(pagina, quantidade)
    orcamento = OrcamentoConsultas(10 * quantidade)

    with pytest.raises(TetoGramaticasExcedido):
        _deduplicar(candidatos, orcamento)

    assert orcamento.gasto > 10 * quantidade
    assert len(_deduplicar(candidatos, OrcamentoConsultas(10**9))) == quantidade


def _candidatos_proximos(pagina: PaginaGramatica, quantidade: int) -> tuple[CandidatoDiscMark, ...]:
    contexto = contexto_gramaticas(pagina)
    lado = 40
    vao = 5.0
    passo = 0.2 * vao  # acima da tolerância de 0.15 vao: nenhum é redesenho de outro
    return tuple(
        CandidatoDiscMark(
            contexto,
            (
                20.0 + (i % lado) * passo,
                20.0 + (i // lado) * passo,
                20.0 + (i % lado) * passo + vao,
                20.0 + (i // lado) * passo + vao,
            ),
            i,
            (),
            "fuse_curve",
        )
        for i in range(quantidade)
    )
