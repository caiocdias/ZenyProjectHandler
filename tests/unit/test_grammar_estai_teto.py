"""Teto da gramática `forked_stem`: classificação única, gasto linear e página hostil."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import pytest
from tests.fixtures.symbol_grammars.estai import (
    GRAMATICAS_ESTAI,
    centro_do_garfo,
    estai_com_circulo,
    garfo,
    pagina_estai,
    x_sobre,
)
from tests.fixtures.symbol_grammars.paginas import pagina_gramatica

from zeny_project_handler.adapters.analysis.drawing_model import grammar_estai
from zeny_project_handler.adapters.analysis.drawing_model.grammar_estai import estai_candidatos
from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import MarcasDaPagina
from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import gasto_por_fase

_PASSO: Final = 60.0
_COLUNAS: Final = 5
_RAZAO_MAXIMA: Final = 12
_FOLGA_POR_GARFO: Final = 8
_EMPILHADOS: Final = 1_500
_ENCADEADOS: Final = 300


def _pagina(caminhos: list[Caminho], quantidade: int) -> PaginaGramatica:
    return pagina_gramatica(
        caminhos,
        primitivas=(),
        largura=_COLUNAS * _PASSO + 60.0,
        altura=(quantidade // _COLUNAS + 2) * _PASSO + 60.0,
    )


def _base(i: int) -> tuple[float, float]:
    return (30.0 + (i % _COLUNAS) * _PASSO, 30.0 + (i // _COLUNAS) * _PASSO)


def _pares(
    nomes: tuple[str, ...] = tuple(GRAMATICAS_ESTAI),
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [
        (
            {"family_id": "autoral"},
            {"id": nome, "recognition": {"status": "enabled", "grammar": GRAMATICAS_ESTAI[nome]}},
        )
        for nome in nomes
    ]


def _pagina_dos_tres_tipos(quantidade: int) -> PaginaGramatica:
    caminhos: list[Caminho] = []
    for i in range(quantidade):
        base = _base(i)
        if i % 3 == 0:
            caminhos.extend(garfo(base=base))
        elif i % 3 == 1:
            caminhos.extend(estai_com_circulo(base=base))
        else:
            caminhos.extend(garfo(base=base))
            caminhos.extend(x_sobre(base))
    return _pagina(caminhos, quantidade)


def test_classificacao_uma_vez_por_candidato() -> None:
    """As 3 variantes custam o mesmo que uma só: `casa_estai` só filtra a classificação pronta."""
    pagina = _pagina_dos_tres_tipos(12)

    tres = gasto_por_fase(pagina, _pares())
    uma = gasto_por_fase(pagina, _pares(("existente",)))

    assert tres.gramaticas > 0
    assert tres == uma


def _gasto_dos_candidatos(quantidade: int) -> tuple[int, int]:
    caminhos: list[Caminho] = []
    for i in range(quantidade):
        caminhos.extend(garfo(base=_base(i)))
    contexto = contexto_gramaticas(_pagina(caminhos, quantidade), limite=10**9)
    antes = contexto.orcamento.gasto
    candidatos = estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))
    return contexto.orcamento.gasto - antes, len(candidatos)


def test_gasto_cresce_linear_com_os_desenhos() -> None:
    """Contagem de trabalho (não tempo de parede): 10x mais desenhos isolados, no máximo 12x."""
    (pequeno, achados_pequeno), (grande, achados_grande) = (
        _gasto_dos_candidatos(10),
        _gasto_dos_candidatos(100),
    )

    assert (achados_pequeno, achados_grande) == (10, 100)
    assert pequeno > 0
    assert grande / pequeno <= _RAZAO_MAXIMA


def _limite_linear(pagina: PaginaGramatica, garfos: int) -> int:
    """Gasto dos índices da página mais o dobro do gasto linear medido por garfo isolado."""
    por_garfo = _gasto_dos_candidatos(100)[0] / 100
    return contexto_gramaticas(pagina).orcamento.gasto + int(2 * por_garfo * garfos)


def test_pagina_sa_cabe_no_limite_linear() -> None:
    """Controle negativo: com o mesmo limite do teste hostil, garfos isolados não estouram."""
    caminhos: list[Caminho] = []
    for i in range(_EMPILHADOS):
        caminhos.extend(garfo(base=_base(i)))
    pagina = _pagina(caminhos, _EMPILHADOS)
    contexto = contexto_gramaticas(pagina, limite=_limite_linear(pagina, _EMPILHADOS))

    assert len(estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))) == _EMPILHADOS


def _cascata(quantidade: int) -> PaginaGramatica:
    """Cada garfo que perde um X passa ao seguinte e o toma do vizinho: uma rodada por garfo."""
    caminhos: list[Caminho] = []
    for i in range(quantidade):
        base = (150.0, 10.0 + i * 8.0)
        caminhos += [*garfo(base=base), *x_sobre(centro_do_garfo(base=base), meio=9.0)]
    return pagina_estai(caminhos, altura=quantidade * 8.0 + 20.0)


def test_cascata_de_disputas_estoura_o_orcamento() -> None:
    """As rodadas da disputa percorrem todas as leituras: o custo é quadrático e o teto o vê."""
    pagina = _cascata(_ENCADEADOS)
    limite = _limite_linear(pagina, _ENCADEADOS)
    contexto = contexto_gramaticas(pagina, limite=limite)

    with pytest.raises(TetoGramaticasExcedido):
        estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))


def test_pagina_hostil_estoura_o_orcamento() -> None:
    """Garfos quase coincidentes custam muito mais que o linear (o gasto cresce com o cubo).

    O limite é o gasto dos índices mais o dobro do gasto linear medido; só o gasto da
    gramática, pago laço a laço, pode ultrapassá-lo.
    """
    caminhos: list[Caminho] = []
    for i in range(_EMPILHADOS):
        caminhos.extend(garfo(base=(100.0 + (i % 40) * 0.001, 100.0 + (i // 40) * 0.001)))
    pagina = pagina_gramatica(caminhos, primitivas=())
    limite = _limite_linear(pagina, _EMPILHADOS)
    contexto = contexto_gramaticas(pagina, limite=limite)

    with pytest.raises(TetoGramaticasExcedido):
        estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))

    assert contexto.orcamento.gasto >= limite


def test_cada_laco_de_estai_candidatos_paga(monkeypatch: pytest.MonkeyPatch) -> None:
    """O que `estai_candidatos` gasta fora das etapas é 1 por garfo lido (ou relido) e uma
    varredura das leituras por rodada da disputa; a vizinhança da deduplicação paga 1 + vizinhos."""
    contexto = contexto_gramaticas(_cascata(10))
    marcas = MarcasDaPagina(contexto)
    dentro = {"etapas": 0, "dedup": 0}
    chamadas = {"_classificar": 0, "disputar": 0, "lidos": 0}

    def medir(nome: str, chave: str) -> None:
        original = getattr(grammar_estai, nome)

        def com_medida(*args: Any, **kwargs: Any) -> Any:
            antes = contexto.orcamento.gasto
            try:
                return original(*args, **kwargs)
            finally:
                dentro[chave] += contexto.orcamento.gasto - antes
                if nome in chamadas:
                    chamadas[nome] += 1

        monkeypatch.setattr(grammar_estai, nome, com_medida)

    for nome in ("_classificar", "_garfos"):
        medir(nome, "etapas")
    original_disputar = grammar_estai._disputar

    def disputar(lidos: Any, perdas: Any) -> bool:
        chamadas["disputar"] += 1
        chamadas["lidos"] = len(lidos)
        return bool(original_disputar(lidos, perdas))

    monkeypatch.setattr(grammar_estai, "_disputar", disputar)
    medir("_deduplicar", "dedup")
    antes = contexto.orcamento.gasto

    estai_candidatos(contexto, marcas=marcas)

    total = contexto.orcamento.gasto - antes
    proprio = total - dentro["etapas"] - dentro["dedup"]
    assert chamadas["_classificar"] > chamadas["lidos"]  # houve ao menos uma releitura
    assert proprio == chamadas["_classificar"] + chamadas["disputar"] * chamadas["lidos"]
    assert dentro["dedup"] >= chamadas["lidos"]
