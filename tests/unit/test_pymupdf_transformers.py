# mypy: disable-error-code="no-untyped-call"
"""E05: reconhecimento por desenho, sem literal ou contagem patrimonial implícita."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf
import pytest
from tests.fixtures.transformers.fixtures import (
    VARIANTS,
    FixtureOccurrence,
    Variant,
    build_circular_stem_fixture,
    build_fill_morphology_fixture,
    build_fixture,
    build_generalization_fixture,
)

from zeny_project_handler.adapters.analysis.pymupdf_transformers import (
    observar_transformadores,
    perfil_transformadores,
)
from zeny_project_handler.adapters.persistence.domain_json import dumps_domain, loads_domain
from zeny_project_handler.domain.symbols import ObservacaoSimbolo, ResultadoMetodoSimbolos


def test_fixture_covers_all_e01_transformer_variants() -> None:
    inventory_path = Path(__file__).resolve().parents[2] / "docs/data/inventario-simbologia-v1.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    registered = {item["id"] for item in inventory["variants"] if item["owner_stage"] == "E05"}
    assert len(registered) == 29
    assert {variant.id for variant in VARIANTS} == registered


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, tuple[FixtureOccurrence, ...]]:
    path = tmp_path_factory.mktemp("e05-transformers") / "author-transformers.pdf"
    return path, build_fixture(path)


@pytest.fixture(scope="module")
def generalization_corpus(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, tuple[FixtureOccurrence, ...]]:
    path = tmp_path_factory.mktemp("e05-transformers-b3") / "author-generalization.pdf"
    return path, build_generalization_fixture(path)


@pytest.fixture(scope="module")
def circular_stem_corpus(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, tuple[FixtureOccurrence, ...]]:
    path = tmp_path_factory.mktemp("e05-transformers-b4") / "author-circular-stems.pdf"
    return path, build_circular_stem_fixture(path)


@pytest.fixture(scope="module")
def fill_morphology_corpus(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, tuple[FixtureOccurrence, ...]]:
    path = tmp_path_factory.mktemp("e05-transformers-b5") / "author-fill-morphology.pdf"
    return path, build_fill_morphology_fixture(path)


def _run(path: Path, page_number: int) -> ResultadoMetodoSimbolos:
    with pymupdf.open(path) as document:
        return observar_transformadores(
            document[page_number - 1],
            documento_id="e05-author-owned",
            documento_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            pagina_numero=page_number,
        )


def _attributes(observation: ObservacaoSimbolo) -> dict[str, object]:
    return dict(observation.atributos)


def _possible_references(observation: ObservacaoSimbolo) -> set[str]:
    raw = _attributes(observation)["referencias_possiveis"]
    assert isinstance(raw, str)
    references = json.loads(raw)
    assert isinstance(references, list)
    return set(references)


def _center(observation: ObservacaoSimbolo) -> tuple[float, float]:
    points = observation.geometria.pontos_normalizados
    return (
        float(sum(point.x for point in points) / len(points)),
        float(sum(point.y for point in points) / len(points)),
    )


def _near_case(observation: ObservacaoSimbolo, case: FixtureOccurrence) -> bool:
    center_x, center_y = _center(observation)
    x0, y0, x1, y1 = case.bbox
    return x0 - 0.07 <= center_x <= x1 + 0.07 and y0 - 0.07 <= center_y <= y1 + 0.07


def _iou(observation: ObservacaoSimbolo, case: FixtureOccurrence) -> float:
    points = observation.geometria.pontos_normalizados
    detected = (
        min(float(point.x) for point in points),
        min(float(point.y) for point in points),
        max(float(point.x) for point in points),
        max(float(point.y) for point in points),
    )
    expected = case.bbox
    width = max(0.0, min(detected[2], expected[2]) - max(detected[0], expected[0]))
    height = max(0.0, min(detected[3], expected[3]) - max(detected[1], expected[1]))
    intersection = width * height
    detected_area = (detected[2] - detected[0]) * (detected[3] - detected[1])
    expected_area = (expected[2] - expected[0]) * (expected[3] - expected[1])
    return intersection / (detected_area + expected_area - intersection)


@pytest.mark.parametrize("variant", VARIANTS, ids=lambda variant: variant.id)
def test_each_registered_visual_variant_is_observed_without_external_literal(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]], variant: Variant
) -> None:
    path, cases = corpus
    case = next(case for case in cases if case.variant_id == variant.id)
    with pymupdf.open(path) as document:
        text = document[case.page_number - 1].get_text().strip()
    assert not any(token in text.upper() for token in ("TRANSFORMADOR", "TR-", "KVA"))

    result = _run(path, case.page_number)
    assert result.perfil.assinatura() == perfil_transformadores().assinatura()
    assert result.completo
    matches = [
        observation
        for observation in result.observacoes
        if _near_case(observation, case)
        and any(
            alternative.classe == variant.expected_class for alternative in observation.alternativas
        )
    ]
    assert len(matches) == 1, variant.id
    observation = matches[0]
    assert _iou(observation, case) >= 0.5, (variant.id, _iou(observation, case))
    assert variant.id in _possible_references(observation)
    assert observation.fonte.pagina_numero == case.page_number
    assert observation.fonte.documento_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert observation.primitivas
    assert observation.situacao is None
    attributes = _attributes(observation)
    assert attributes["cardinalidade"] == "indeterminada"
    assert attributes["quantidade_ativos"] is None
    assert attributes["componentes"]
    assert not any(key in attributes for key in ("potencia_kva", "fases", "modelo"))


def test_composite_and_overprint_keep_one_observation_and_unknown_asset_count(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]],
) -> None:
    path, cases = corpus
    composite = next(case for case in cases if case.variant_id == "cemig-eo-r3-s25-v004")
    overprint = next(case for case in cases if case.stratum == "duplicate_overprint")
    for case in (composite, overprint):
        result = _run(path, case.page_number)
        matches = [
            observation for observation in result.observacoes if _near_case(observation, case)
        ]
        assert len(matches) == 1
        attributes = _attributes(matches[0])
        assert attributes["cardinalidade"] == "indeterminada"
        assert attributes["quantidade_ativos"] is None


def test_neighboring_symbols_remain_separate(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]],
) -> None:
    path, cases = corpus
    neighbors = [case for case in cases if case.stratum == "neighbors"]
    assert len(neighbors) == 2
    result = _run(path, neighbors[0].page_number)
    for case in neighbors:
        matches = [
            observation for observation in result.observacoes if _near_case(observation, case)
        ]
        assert len(matches) == 1
    assert len({_center(observation) for observation in result.observacoes}) >= 2


def test_legend_is_observed_as_reference_context_without_asset_count(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]],
) -> None:
    path, cases = corpus
    case = next(case for case in cases if case.context == "legend")
    matches = [
        observation
        for observation in _run(path, case.page_number).observacoes
        if _near_case(observation, case)
    ]
    assert len(matches) == 1
    attributes = _attributes(matches[0])
    assert attributes["contexto"] == "legend"
    assert attributes["quantidade_ativos"] is None
    assert matches[0].situacao is None


def test_incompatible_text_is_separate_from_visual_geometry(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]],
) -> None:
    path, cases = corpus
    plain_case = next(case for case in cases if case.variant_id == "cemig-eo-r3-s18-v007")
    conflict_case = next(case for case in cases if case.stratum == "text_conflict")
    plain = next(
        observation
        for observation in _run(path, plain_case.page_number).observacoes
        if _near_case(observation, plain_case)
    )
    conflicting = next(
        observation
        for observation in _run(path, conflict_case.page_number).observacoes
        if _near_case(observation, conflict_case)
    )
    plain_attributes = _attributes(plain)
    conflict_attributes = _attributes(conflicting)
    assert plain.geometria.pontos_originais == conflicting.geometria.pontos_originais
    assert plain_attributes["variante_grafica"] == conflict_attributes["variante_grafica"]
    assert "POSTE" in str(conflict_attributes["texto_proximo"]).upper()
    assert "POSTE" in str(conflict_attributes["conflito_textual"]).upper()
    assert conflicting.situacao is None
    assert conflicting.geometria.pontos_originais == plain.geometria.pontos_originais


def test_rotation_and_scale_preserve_a_single_visual_observation(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]],
) -> None:
    path, cases = corpus
    case = next(case for case in cases if case.stratum == "rotation_scale")
    result = _run(path, case.page_number)
    matches = [observation for observation in result.observacoes if _near_case(observation, case)]
    assert len(matches) == 1
    assert case.variant_id in _possible_references(matches[0])


def test_circles_post_and_glyph_do_not_create_transformers(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]],
) -> None:
    path, cases = corpus
    case = next(case for case in cases if case.context == "negative")
    result = _run(path, case.page_number)
    assert result.observacoes == ()


def test_round_cyan_sector_is_one_transformer_without_text_or_asset_count(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]],
) -> None:
    path, cases = corpus
    case = next(case for case in cases if case.stratum == "round_cyan_sector")
    with pymupdf.open(path) as document:
        assert document[case.page_number - 1].get_text().strip() == ""
    result = _run(path, case.page_number)
    assert len(result.observacoes) == 1
    observation = result.observacoes[0]
    assert _iou(observation, case) >= 0.5
    assert any(item.classe == "TRANSFORMADOR" for item in observation.alternativas)
    assert case.variant_id in _possible_references(observation)
    attributes = _attributes(observation)
    assert str(attributes["variante_grafica"]).startswith("circulo")
    assert attributes["contexto"] == "unknown"
    assert attributes["cardinalidade"] == "indeterminada"
    assert attributes["quantidade_ativos"] is None
    assert attributes["conflito_textual"] is None
    assert observation.situacao is None


@pytest.mark.parametrize(
    "stratum",
    (
        "compass_rose",
        "pole_circles",
        "green_pole_markers",
        "repeated_details",
        "red_protection_annotation",
    ),
)
def test_b2_visual_decoys_do_not_create_transformers(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]], stratum: str
) -> None:
    path, cases = corpus
    case = next(case for case in cases if case.stratum == stratum)
    result = _run(path, case.page_number)
    assert result.completo
    assert result.observacoes == (), stratum


def test_e03_round_trip_preserves_visual_provenance_and_raw_score(
    corpus: tuple[Path, tuple[FixtureOccurrence, ...]],
) -> None:
    path, cases = corpus
    case = next(case for case in cases if case.variant_id == "cemig-eo-r3-s18-v007")
    result = _run(path, case.page_number)
    restored = loads_domain(dumps_domain(result), ResultadoMetodoSimbolos)
    assert restored == result
    assert restored.observacoes[0].id == result.observacoes[0].id
    assert restored.observacoes[0].score_bruto == result.observacoes[0].score_bruto


@pytest.mark.parametrize(
    "stratum",
    ("disconnected_pole_lobes", "disconnected_compass_lobes", "embedded_red_protection"),
)
def test_b3_disconnected_lobes_and_embedded_annotations_are_not_transformers(
    generalization_corpus: tuple[Path, tuple[FixtureOccurrence, ...]], stratum: str
) -> None:
    path, cases = generalization_corpus
    case = next(case for case in cases if case.stratum == stratum)
    result = _run(path, case.page_number)
    assert result.completo
    assert result.observacoes == (), stratum


@pytest.mark.parametrize("stratum", ("small_cyan_sector", "occluded_cyan_sector"))
def test_b3_cyan_sectors_remain_one_transformer_with_unknown_quantity(
    generalization_corpus: tuple[Path, tuple[FixtureOccurrence, ...]], stratum: str
) -> None:
    path, cases = generalization_corpus
    case = next(case for case in cases if case.stratum == stratum)
    with pymupdf.open(path) as document:
        assert document[case.page_number - 1].get_text().strip() == ""
    result = _run(path, case.page_number)
    assert len(result.observacoes) == 1
    observation = result.observacoes[0]
    assert _iou(observation, case) >= 0.5
    assert any(item.classe == "TRANSFORMADOR" for item in observation.alternativas)
    assert case.variant_id in _possible_references(observation)
    attributes = _attributes(observation)
    assert str(attributes["variante_grafica"]).startswith("circulo")
    assert attributes["cardinalidade"] == "indeterminada"
    assert attributes["quantidade_ativos"] is None
    assert observation.situacao is None


@pytest.mark.parametrize(
    "stratum",
    (
        "multicolor_unconnected_pole_circles",
        "open_pole_ring_with_stem",
        "red_protection_ring_with_stem",
    ),
)
def test_b4_pole_and_protection_rings_are_not_transformers(
    circular_stem_corpus: tuple[Path, tuple[FixtureOccurrence, ...]], stratum: str
) -> None:
    path, cases = circular_stem_corpus
    case = next(case for case in cases if case.stratum == stratum)
    result = _run(path, case.page_number)
    assert result.completo
    assert result.observacoes == (), stratum


def test_b4_connected_overlapping_windings_remain_one_unknown_count_transformer(
    circular_stem_corpus: tuple[Path, tuple[FixtureOccurrence, ...]],
) -> None:
    path, cases = circular_stem_corpus
    case = next(case for case in cases if case.stratum == "connected_overlapping_windings")
    result = _run(path, case.page_number)
    assert len(result.observacoes) == 1
    observation = result.observacoes[0]
    assert _iou(observation, case) >= 0.5
    assert any(item.classe == "TRANSFORMADOR" for item in observation.alternativas)
    attributes = _attributes(observation)
    assert attributes["cardinalidade"] == "indeterminada"
    assert attributes["quantidade_ativos"] is None
    assert observation.situacao is None


@pytest.mark.parametrize("stratum", ("filled_multicolor_post_marks", "small_filled_terminal_point"))
def test_b5_filled_post_marks_and_terminal_points_are_not_transformers(
    fill_morphology_corpus: tuple[Path, tuple[FixtureOccurrence, ...]], stratum: str
) -> None:
    path, cases = fill_morphology_corpus
    case = next(case for case in cases if case.stratum == stratum)
    result = _run(path, case.page_number)
    assert result.completo
    assert result.observacoes == (), stratum


def test_b5_hollow_connected_loops_remain_one_transformer(
    fill_morphology_corpus: tuple[Path, tuple[FixtureOccurrence, ...]],
) -> None:
    path, cases = fill_morphology_corpus
    case = next(case for case in cases if case.stratum == "hollow_connected_windings")
    result = _run(path, case.page_number)
    assert len(result.observacoes) == 1
    observation = result.observacoes[0]
    assert _iou(observation, case) >= 0.5
    assert any(item.classe == "TRANSFORMADOR" for item in observation.alternativas)
    attributes = _attributes(observation)
    assert attributes["cardinalidade"] == "indeterminada"
    assert attributes["quantidade_ativos"] is None
    assert observation.situacao is None
