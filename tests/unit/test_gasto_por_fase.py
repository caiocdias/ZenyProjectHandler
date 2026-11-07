# mypy: disable-error-code="no-untyped-call"
"""Gasto do orçamento de gramáticas por fase: colagem, índices e gramáticas."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import pytest
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    linha,
    pagina_gramatica,
    retangulo_traco,
    texto,
)

from zeny_project_handler.adapters.analysis.drawing_model import symbol_grammars, symbol_matcher
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    FonteGramaticaFalhou,
    PaginaGramatica,
    TetoGramaticasExcedido,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    casar_variantes,
    gasto_por_fase,
)

Par = tuple[Mapping[str, Any], Mapping[str, Any]]

_MOLDURA: Final[Caixa] = (101.0, 115.0, 169.0, 149.0)
_ROTULO: Final[Caixa] = (107.0, 130.0, 125.0, 142.0)
_CENTRO_DISCO: Final = (150.0, 150.0)
_ROXO: Final = (0.31, 0.10, 0.30)
_CINZA: Final = (0.5, 0.5, 0.5)
_DISCO: Final[dict[str, Any]] = {
    "kind": "terminal_disc",
    "fill": "purple",
    "min_span": 1.0,
    "max_span": 4.0,
    "terminal_line": True,
}
_ROTULO_GRAMATICA: Final[dict[str, Any]] = {
    "kind": "label_in_frame",
    "frame": "rectangle",
    "label": "CT",
    "max_span": 96,
}


def _par(identificador: str, gramatica: Mapping[str, Any]) -> Par:
    return {"family_id": "p"}, {
        "id": identificador,
        "recognition": {"status": "enabled", "grammar": gramatica},
    }


def _pagina() -> PaginaGramatica:
    return pagina_gramatica(
        (
            retangulo_traco(_MOLDURA),
            linha((60.0, 150.0), _CENTRO_DISCO, cor=_CINZA),
            circulo_bezier(_CENTRO_DISCO, 1.4, cor=None, preenchimento=_ROXO),
        ),
        (texto("CT", _ROTULO),),
    )


_VARIANTES: Final = (_par("m", _ROTULO_GRAMATICA), _par("d", _DISCO))


def test_casar_variantes_nao_muda_saida_nem_gasto(monkeypatch: pytest.MonkeyPatch) -> None:
    contextos: list[ContextoGramatica] = []
    original = symbol_grammars.contexto_gramaticas

    def espiao(pagina: PaginaGramatica, **kwargs: Any) -> ContextoGramatica:
        contexto = original(pagina, **kwargs)
        contextos.append(contexto)
        return contexto

    monkeypatch.setattr(symbol_matcher, "contexto_gramaticas", espiao)

    casamentos = casar_variantes(_pagina(), _VARIANTES)

    assert [(c.variante["id"], c.caixa, c.caminho) for c in casamentos] == [
        ("m", (101.0, 115.0, 169.0, 149.0), 0),
        ("d", (148.6, 148.6, 151.4, 151.4), 2),
    ]
    assert contextos[0].orcamento.gasto == 18


def _coluna_alinhada(linhas: int) -> PaginaGramatica:
    """`linhas` textos de uma só borda direita: o pior caso da colagem."""
    return pagina_gramatica(
        (), tuple(texto("A", (10.0, 5.0 + 10.0 * i, 20.0, 10.0 + 10.0 * i)) for i in range(linhas))
    )


def test_fases_somam_o_gasto_fixado() -> None:
    gasto = gasto_por_fase(_pagina(), _VARIANTES)

    assert gasto.total == 18
    assert gasto.total == gasto.colagem + gasto.indices + gasto.gramaticas
    assert min(gasto.colagem, gasto.indices, gasto.gramaticas) > 0


def test_colagem_cresce_com_colunas_alinhadas() -> None:
    poucas = gasto_por_fase(_coluna_alinhada(3), (_par("m", _ROTULO_GRAMATICA),))
    muitas = gasto_por_fase(_coluna_alinhada(30), (_par("m", _ROTULO_GRAMATICA),))

    assert muitas.colagem > poucas.colagem
    assert muitas.gramaticas == poucas.gramaticas


def test_sem_disco_gramaticas_nao_paga_pontas() -> None:
    sem_disco = pagina_gramatica((retangulo_traco(_MOLDURA),), (texto("CT", _ROTULO),))

    so_rotulo = gasto_por_fase(sem_disco, (_par("m", _ROTULO_GRAMATICA),))
    com_variante_de_disco = gasto_por_fase(sem_disco, _VARIANTES)

    assert com_variante_de_disco == so_rotulo
    assert gasto_por_fase(_pagina(), _VARIANTES).gramaticas > so_rotulo.gramaticas


def test_teto_vale_na_medicao() -> None:
    real = gasto_por_fase(_pagina(), _VARIANTES, limite=10**12)

    with pytest.raises(TetoGramaticasExcedido):
        gasto_por_fase(_pagina(), _VARIANTES, limite=5)
    with pytest.raises(TetoGramaticasExcedido):
        gasto_por_fase(_pagina(), _VARIANTES, limite=real.total - 1)
    assert gasto_por_fase(_pagina(), _VARIANTES, limite=real.total) == real
    assert real.total == 18


def test_fonte_falhou_levanta_com_qualquer_limite() -> None:
    pagina = pagina_gramatica((), diagnosticos=("modelo.glifos_falhou",))

    for limite in (1, 10**12):
        with pytest.raises(FonteGramaticaFalhou):
            gasto_por_fase(pagina, _VARIANTES, limite=limite)


def test_glifos_limitados_levanta_teto_com_qualquer_limite() -> None:
    pagina = pagina_gramatica((), diagnosticos=("modelo.glifos_limitados",))

    for limite in (1, 10**12):
        with pytest.raises(TetoGramaticasExcedido):
            gasto_por_fase(pagina, _VARIANTES, limite=limite)
