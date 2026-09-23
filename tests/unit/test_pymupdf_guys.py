# mypy: disable-error-code="no-untyped-call"
"""E06: reconhecimento vetorial de estais sem promoção elétrica implícita."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf
import pytest
from tests.fixtures.guys.fixtures import VARIANTS, FixtureOccurrence, Variant, build_fixture

from zeny_project_handler.adapters.analysis.pymupdf_guys import observar_estais, perfil_estais
from zeny_project_handler.adapters.persistence.domain_json import dumps_domain, loads_domain
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos, TipoGeometria
from zeny_project_handler.domain.project import Cabo
from zeny_project_handler.domain.symbols import ObservacaoSimbolo, ResultadoMetodoSimbolos
from zeny_project_handler.domain.values import GeometriaDocumento


def test_fixture_covers_e01_guy_inventory_once() -> None:
    inventory_path = Path(__file__).resolve().parents[2] / "docs/data/inventario-simbologia-v1.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    registered = {item["id"] for item in inventory["variants"] if item["owner_stage"] == "E06"}
    assert len(registered) == 17
    assert {variant.id for variant in VARIANTS} == registered
    assert len(VARIANTS) == len(registered)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, tuple[FixtureOccurrence, ...]]:
    path = tmp_path_factory.mktemp("e06-guys") / "author-guys.pdf"
    return path, build_fixture(path)


def _run(path: Path, page_number: int) -> ResultadoMetodoSimbolos:
    with pymupdf.open(path) as document:
        return observar_estais(
            document[page_number - 1],
            documento_id="e06-author-owned",
            documento_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            pagina_numero=page_number,
        )


def _attributes(observation: ObservacaoSimbolo) -> dict[str, object]:
    return dict(observation.atributos)


def _json_list(attributes: dict[str, object], field: str) -> list[object]:
    value = attributes[field]
    assert isinstance(value, str)
    decoded = json.loads(value)
    assert isinstance(decoded, list)
    return decoded


def _near_case(observation: ObservacaoSimbolo, case: FixtureOccurrence) -> bool:
    points = observation.geometria.pontos_normalizados
    center_x = sum(float(point.x) for point in points) / len(points)
    center_y = sum(float(point.y) for point in points) / len(points)
    x0, y0, x1, y1 = case.bbox
    return x0 - 0.06 <= center_x <= x1 + 0.06 and y0 - 0.08 <= center_y <= y1 + 0.08


def _matching_observations(
    result: ResultadoMetodoSimbolos, case: FixtureOccurrence
) -> list[ObservacaoSimbolo]:
    return [
        observation
        for observation in result.observacoes
        if _near_case(observation, case)
        and any(alternative.classe == "ESTAI" for alternative in observation.alternativas)
    ]


@pytest.mark.parametrize("variant", VARIANTS, ids=lambda variant: variant.id)
def test_each_e01_guy_cell_produces_mechanical_observation(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]], variant: Variant
) -> None:
    path, cases = corpus
    case = next(
        case for case in cases if case.variant_id == variant.id and case.stratum == "variant"
    )
    result = _run(path, case.page_number)
    assert result.completo
    assert result.perfil.assinatura() == perfil_estais().assinatura()
    assert result.coberturas[0].estado is EstadoMetodoSimbolos.CONCLUIDO
    matches = _matching_observations(result, case)
    assert len(matches) == 1, variant.id
    observation = matches[0]
    assert observation.geometria.tipo is TipoGeometria.POLILINHA
    path_points = observation.geometria.pontos_normalizados
    assert len(path_points) >= 2
    assert max(point.x for point in path_points) - min(point.x for point in path_points) >= 0.25
    assert observation.fonte.documento_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert observation.fonte.pagina_numero == case.page_number
    assert observation.primitivas
    attributes = _attributes(observation)
    assert variant.id in _json_list(attributes, "referencias_possiveis")
    assert _json_list(attributes, "componentes")
    assert isinstance(_json_list(attributes, "suportes_possiveis"), list)
    assert attributes["vinculo"] == "mecanico_possivel"
    assert attributes["conectividade_eletrica"] is False
    assert attributes["cardinalidade"] == "indeterminada"
    assert attributes["situacao_indeterminada"] is True
    assert observation.situacao is None


@pytest.mark.parametrize("variant", (VARIANTS[0], VARIANTS[1], VARIANTS[2], VARIANTS[-2]))
def test_bifurcated_anchor_does_not_need_text(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]], variant: Variant
) -> None:
    path, cases = corpus
    case = next(
        case for case in cases if case.variant_id == variant.id and case.stratum == "variant"
    )
    with pymupdf.open(path) as document:
        assert document[case.page_number - 1].get_text().strip() == ""
    assert len(_matching_observations(_run(path, case.page_number), case)) == 1


@pytest.mark.parametrize(
    "stratum",
    (
        "dashed_anchor",
        "no_support",
        "overprint",
        "counterpole",
        "simple_y",
        "backward_v",
        "backward_v_rotated",
        "shallow_v",
        "shallow_v_small",
        "shallow_overprint",
    ),
)
def test_dashed_or_overprinted_anchor_remains_one_candidate(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]], stratum: str
) -> None:
    path, cases = corpus
    case = next(case for case in cases if case.stratum == stratum)
    result = _run(path, case.page_number)
    matches = _matching_observations(result, case)
    assert len(matches) == 1, stratum
    assert _attributes(matches[0])["conectividade_eletrica"] is False
    if stratum in {
        "simple_y",
        "backward_v",
        "backward_v_rotated",
        "shallow_v",
        "shallow_v_small",
        "shallow_overprint",
    }:
        with pymupdf.open(path) as document:
            assert document[case.page_number - 1].get_text().strip() == ""
        assert VARIANTS[0].id in _json_list(_attributes(matches[0]), "referencias_possiveis")
    if stratum == "no_support":
        # A falta de suporte visível não pode vetar a forma do estai.
        supports = _json_list(_attributes(matches[0]), "suportes_possiveis")
        assert supports
        support_rows = [item for item in supports if isinstance(item, dict)]
        assert len(support_rows) == len(supports)
        assert all(item["id_suporte"] is None for item in support_rows)
        assert any(item["tipo"] == "suporte_indeterminado" for item in support_rows)
        assert {alt.subtipo for alt in matches[0].alternativas} >= {"ancora_MT", "ancora_AT"}


@pytest.mark.parametrize(
    "variant", (VARIANTS[3], VARIANTS[6], VARIANTS[9], VARIANTS[12]), ids=lambda v: v.shape
)
def test_other_guy_families_are_visual_without_text(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]], variant: Variant
) -> None:
    path, cases = corpus
    case = next(case for case in cases if case.stratum == f"no_text_{variant.shape}")
    with pymupdf.open(path) as document:
        assert document[case.page_number - 1].get_text().strip() == ""
    matches = _matching_observations(_run(path, case.page_number), case)
    assert len(matches) == 1, variant.shape
    assert variant.id in _json_list(_attributes(matches[0]), "referencias_possiveis")
    assert _attributes(matches[0])["conectividade_eletrica"] is False


def test_adjacent_guys_remain_two_mechanical_candidates(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]],
) -> None:
    path, cases = corpus
    neighbors = [case for case in cases if case.stratum == "neighbors"]
    assert len(neighbors) == 2
    result = _run(path, neighbors[0].page_number)
    assert len(result.observacoes) == 2
    for case in neighbors:
        assert len(_matching_observations(result, case)) == 1


@pytest.mark.parametrize(
    "stratum",
    (
        "dashed_conductor",
        "fence",
        "leader",
        "dimension",
        "pole_link",
        "counterpole_only",
        "text_only",
        "leader_y",
        "dimension_y",
        "conductor_y",
        "dimension_backward_v",
        "conductor_backward_v",
        "dimension_shallow_v",
        "conductor_shallow_v",
        "closed_triangle_arrow",
        "repeated_closed_triangle_arrows",
        "conductor_parallel_labeled",
        "leader_terminal_dot",
        "invisible_backward_v",
        "transparent_backward_v",
        "long_dashed_pole_span",
        "network_span_t_t",
        "dense_conductor_corridor",
        "compass_rose",
        "electric_symbol_ticks",
        "dense_corridor_shallow_branch",
        "compass_rose_open",
        "electric_symbol_stubs",
        "corridor_short_t_t",
        "closed_pole_loops",
        "compass_symmetric_radials",
        "inconsistent_stroke_guy_shape",
        "parallel_solid_dashed_anchor_like",
        "near_parallel_solid_dashed_anchor_like",
    ),
)
def test_conductor_and_cartographic_controls_are_not_guys(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]], stratum: str
) -> None:
    path, cases = corpus
    case = next(case for case in cases if case.stratum == stratum)
    result = _run(path, case.page_number)
    assert result.completo
    assert result.coberturas[0].estado is EstadoMetodoSimbolos.NAO_DETECCAO
    assert result.observacoes == (), stratum


def test_e03_round_trip_preserves_mechanical_geometry_and_uncertainty(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]],
) -> None:
    path, cases = corpus
    case = next(case for case in cases if case.variant_id == VARIANTS[0].id)
    result = _run(path, case.page_number)
    restored = loads_domain(dumps_domain(result), ResultadoMetodoSimbolos)
    assert restored == result
    assert restored.observacoes[0].id == result.observacoes[0].id
    assert restored.observacoes[0].geometria.tipo is TipoGeometria.POLILINHA
    assert _attributes(restored.observacoes[0])["vinculo"] == "mecanico_possivel"


def test_visual_result_has_no_electrical_proposals_or_spans(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]],
) -> None:
    path, cases = corpus
    case = next(case for case in cases if case.variant_id == VARIANTS[0].id)
    result = _run(path, case.page_number)
    assert isinstance(result, ResultadoMetodoSimbolos)
    assert result.observacoes
    assert not any(isinstance(item, PropostaElemento | Cabo) for item in result.observacoes)
    assert all(not isinstance(item.geometria, GeometriaDocumento) for item in result.observacoes)
    assert all(_attributes(item)["conectividade_eletrica"] is False for item in result.observacoes)
