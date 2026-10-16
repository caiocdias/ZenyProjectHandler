# mypy: disable-error-code="no-untyped-call"
"""Ligação detector legado → reconciliação → associação símbolo/poste.

O detector reporta só o pictograma (envolvente + barras) e guarda a haste até o
poste em ``simbolo_limites_suporte``. A associação deve medir a distância pela
geometria de suporte, não pelo centro do pictograma. Fixtures sintéticas autorais.
"""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

import pymupdf
import pytest

from zeny_project_handler.adapters.analysis.legacy_symbols import observar_simbolos_legados
from zeny_project_handler.adapters.analysis.pymupdf_support import _box_geometry
from zeny_project_handler.application.interpretation_pipeline import (
    _assess_symbol_occurrence,
    _symbol_occurrence_proposal,
)
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationPolicy,
    SymbolReconciliation,
    reconcile_symbols,
)
from zeny_project_handler.application.topology_compliance import _associate_proposals_to_poles
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico, TipoPoste
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
)
from zeny_project_handler.domain.project import Poste
from zeny_project_handler.domain.symbols import ResultadoMetodoSimbolos
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

_PAGE_SIZE = 2000.0
_PAGE_ID = uuid5(NAMESPACE_URL, "fixture:associacao-suporte:pagina")
_EXECUTION_ID = uuid5(NAMESPACE_URL, "fixture:associacao-suporte:execucao")
# Poste do qual sai a haste e um vizinho a ~0,003 do centro do pictograma além do primeiro.
_FIRST_POLE = (100.0, 100.0)
_NEIGHBOUR_POLE = (125.0, 165.0)


def _draw_ground(page: pymupdf.Page, start: tuple[float, float]) -> None:
    """Haste vertical de 30 pt, três barras decrescentes e círculo envolvente."""
    x, y = start
    black = (0, 0, 0)
    page.draw_line((x, y), (x, y + 30), color=black)
    for index, length in enumerate((12, 8, 4)):
        bar_y = y + 30 + index * 4
        page.draw_line((x - length / 2, bar_y), (x + length / 2, bar_y), color=black)
    page.draw_circle((x, y + 34), 8, color=black)


def _observed(stem_start: tuple[float, float], *, rotation: int = 0) -> ResultadoMetodoSimbolos:
    with pymupdf.open() as document:
        page = document.new_page(width=_PAGE_SIZE, height=_PAGE_SIZE)
        for center in (_FIRST_POLE, _NEIGHBOUR_POLE):
            page.draw_circle(center, 3, color=(0, 0, 0))
        _draw_ground(page, stem_start)
        page.set_rotation(rotation)
        return observar_simbolos_legados(
            page, documento_id="associacao", documento_sha256="c" * 64, pagina_numero=1
        )


def _point(x: float, y: float) -> PontoNormalizado:
    return PontoNormalizado(Decimal(str(x / _PAGE_SIZE)), Decimal(str(y / _PAGE_SIZE)))


def _pole_proposal(name: str, position: tuple[float, float]) -> PropostaElemento:
    return PropostaElemento(
        id=uuid5(NAMESPACE_URL, f"fixture:associacao-suporte:{name}"),
        execucao_id=_EXECUTION_ID,
        categoria=CategoriaElemento.POSTE,
        situacao_projeto=SituacaoProjeto.EXISTENTE,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(uuid5(NAMESPACE_URL, f"fixture:associacao-suporte:evidencia:{name}"),),
        geometria=GeometriaDocumento.ponto(_PAGE_ID, _point(*position)),
    )


def _poles() -> tuple[PropostaElemento, PropostaElemento]:
    return _pole_proposal("primeiro", _FIRST_POLE), _pole_proposal("vizinho", _NEIGHBOUR_POLE)


def _confirmed_poles(catalog: CatalogoTecnico) -> tuple[Poste, Poste]:
    pole_type = next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.POSTE)
        if isinstance(item, TipoPoste)
    )
    first, neighbour = (
        Poste(
            id=uuid5(NAMESPACE_URL, f"fixture:associacao-suporte:poste:{proposal.id}"),
            tipo_catalogo_id=pole_type.id,
            situacao=SituacaoProjeto.EXISTENTE,
            geometria=proposal.geometria,
        )
        for proposal in _poles()
    )
    return first, neighbour


def _single_occurrence(result: ResultadoMetodoSimbolos) -> SymbolReconciliation:
    symbols = reconcile_symbols((result,), CalibrationPolicy())
    assert len(symbols.occurrences) == 1
    return symbols


def _symbol_proposal(
    symbols: SymbolReconciliation, catalog: CatalogoTecnico
) -> tuple[PropostaElemento, PropostaElemento | None]:
    occurrence = symbols.occurrences[0]
    assessment = _assess_symbol_occurrence(occurrence, "base", _PAGE_ID, catalog, _poles())
    observation_ids = [
        uuid5(_EXECUTION_ID, f"simbolo:{observation.id}") for observation in occurrence.observations
    ]
    proposal = _symbol_occurrence_proposal(
        symbols, occurrence, _EXECUTION_ID, observation_ids, assessment
    )
    return proposal, assessment.support


def test_grounding_stem_from_pole_keeps_symbol_on_that_pole(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    result = _observed(_FIRST_POLE)
    assert len(result.observacoes) == 1
    observation = result.observacoes[0]
    assert observation.alternativas[0].classe == "ATERRAMENTO"
    # Pré-condição do caso: a caixa reportada é só o pictograma (sem a haste).
    ys = [float(point.y) * _PAGE_SIZE for point in observation.geometria.pontos_normalizados]
    assert min(ys) == pytest.approx(126, abs=0.5)
    symbols = _single_occurrence(result)

    proposal, support = _symbol_proposal(symbols, catalogo_inicial)
    first, _ = _poles()
    attributes = dict(proposal.atributos_sugeridos)
    assert support is not None
    assert support.id == first.id
    assert attributes["suporte_proposta_id"] == str(first.id)
    assert attributes["simbolo_associacao_resolvida"] is True
    assert attributes["associacao_pendente"] is False
    candidates = json.loads(str(attributes["simbolo_suportes_candidatos"]))
    assert [item["proposta_id"] for item in candidates] == [str(first.id)]

    # Conformidade: suporte não confirmado cai no poste mais próximo pela haste.
    first_pole, _ = _confirmed_poles(catalogo_inicial)
    associated = _associate_proposals_to_poles(
        (proposal,), {}, _confirmed_poles(catalogo_inicial), {_PAGE_ID: (Decimal(2000),) * 2}
    )
    assert associated == {proposal.id: first_pole.id}


def test_symbol_without_stem_reaching_a_pole_stays_without_support(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    symbols = _single_occurrence(_observed((400.0, 400.0)))
    proposal, support = _symbol_proposal(symbols, catalogo_inicial)
    attributes = dict(proposal.atributos_sugeridos)
    assert support is None
    assert attributes["suporte_proposta_id"] is None
    assert attributes["associacao_pendente"] is True
    assert json.loads(str(attributes["simbolo_suportes_candidatos"])) == []
    associated = _associate_proposals_to_poles(
        (proposal,), {}, _confirmed_poles(catalogo_inicial), {_PAGE_ID: (Decimal(2000),) * 2}
    )
    assert associated == {}


def test_observation_without_support_geometry_keeps_pictogram_association(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    """Outros métodos não informam haste: a medida continua pelo centro da caixa."""
    result = _observed(_FIRST_POLE)
    observation = result.observacoes[0]
    stripped = replace(
        observation,
        atributos=tuple(
            item for item in observation.atributos if item[0] != "simbolo_limites_suporte"
        ),
    )
    symbols = _single_occurrence(replace(result, observacoes=(stripped,)))
    assert symbols.occurrences[0].support_geometry is None
    proposal, support = _symbol_proposal(symbols, catalogo_inicial)
    attributes = dict(proposal.atributos_sugeridos)
    # Pelo pictograma os dois postes ficam a menos de 0,004 um do outro: ambíguo.
    assert support is None
    assert attributes["simbolo_geometria_suporte"] is None
    assert len(json.loads(str(attributes["simbolo_suportes_candidatos"]))) == 2


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_support_geometry_matches_detector_normalization_under_rotation(rotation: int) -> None:
    result = _observed(_FIRST_POLE, rotation=rotation)
    occurrence = _single_occurrence(result).occurrences[0]
    assert occurrence.support_geometry is not None
    raw = json.loads(str(dict(result.observacoes[0].atributos)["simbolo_limites_suporte"]))
    with pymupdf.open() as document:
        page = document.new_page(width=_PAGE_SIZE, height=_PAGE_SIZE)
        page.set_rotation(rotation)
        expected = _box_geometry(page, pymupdf.Rect(raw)).pontos
    actual = occurrence.support_geometry.pontos_normalizados
    assert len(actual) == len(expected)
    for got, want in zip(actual, expected, strict=True):
        assert float(got.x) == pytest.approx(float(want.x), abs=1e-12)
        assert float(got.y) == pytest.approx(float(want.y), abs=1e-12)


@pytest.mark.parametrize("raw", ["", "nao-json", "[1, 2, 3]", '["a", 0, 1, 1]', "[5, 0, 1, 1]"])
def test_malformed_support_bounds_are_ignored(raw: str) -> None:
    result = _observed(_FIRST_POLE)
    observation = result.observacoes[0]
    corrupted = replace(
        observation,
        atributos=tuple(
            (key, raw if key == "simbolo_limites_suporte" else value)
            for key, value in observation.atributos
        ),
    )
    occurrence = _single_occurrence(replace(result, observacoes=(corrupted,))).occurrences[0]
    assert occurrence.support_geometry is None
