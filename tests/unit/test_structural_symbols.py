# mypy: disable-error-code="no-untyped-call"
"""Author-owned behavioral controls for the opt-in E09 structural detector.

Ground truth is the drawing code below. It is never passed to the detector as a
template, ROI or class hint; the sealed E16 reserve is not imported or opened.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pymupdf
import pytest
from tests.factories import complete_project

from zeny_project_handler.adapters.analysis.legacy_symbols import (
    observar_simbolos_legados,
    perfil_simbolos_legados,
)
from zeny_project_handler.adapters.analysis.raster_symbols import (
    ConfiguracaoDetectorRaster,
    carregar_templates_raster,
    observar_simbolos_raster,
    perfis_simbolos_raster,
)
from zeny_project_handler.adapters.analysis.structural_symbols import (
    ConfiguracaoDetectorEstrutural,
    observar_simbolos_estruturais,
    perfil_simbolos_estruturais,
)
from zeny_project_handler.application.spans import detectar_vaos
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import ObservacaoSimbolo, ResultadoMetodoSimbolos

_SOURCE_HASH = "e" * 64
_INK = (0.0, 0.0, 0.0)


def _line(page: pymupdf.Page, a: tuple[float, float], b: tuple[float, float]) -> None:
    page.draw_line(a, b, color=_INK, width=0.65)


def _barred_symbol(
    page: pymupdf.Page,
    x: float,
    y: float,
    *,
    bars: int = 3,
    gap: float = 0.0,
    bend: float = 0.0,
) -> None:
    """A three/four-bar author drawing with optional broken/deformed strokes."""
    lengths = (10.0, 7.0, 4.0, 7.0)[:bars]
    if gap:
        _line(page, (x, y), (x + 7.5 - gap, y))
        _line(page, (x + 7.5 + gap, y + bend), (x + 15, y + bend))
    else:
        _line(page, (x, y), (x + 15, y + bend))
    for index, length in enumerate(lengths):
        bar_x = x + 15 + 4 * index
        center_y = y + bend * min(1.0, (bar_x - x) / 15)
        _line(
            page,
            (bar_x - bend / 3, center_y - length / 2),
            (bar_x + bend / 3, center_y + length / 2),
        )


def _sloped_variable_width_symbol(page: pymupdf.Page, *, tapering: bool) -> None:
    """Small skew and mixed pen widths challenge row/column run extraction."""
    page.draw_line((42, 53), (57, 54.2), color=_INK, width=1.4)
    lengths = (10.0, 7.0, 4.0) if tapering else (10.0, 10.0, 10.0)
    for index, (length, width) in enumerate(zip(lengths, (0.65, 1.4, 2.0), strict=True)):
        x = 57 + 4 * index
        page.draw_line(
            (x - 0.6, 54.2 - length / 2),
            (x + 0.6, 54.2 + length / 2),
            color=_INK,
            width=width,
        )


def _raster_copy(page: pymupdf.Page, document: pymupdf.Document) -> pymupdf.Page:
    """Remove vector primitives while keeping the visual drawing and page size."""
    image = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).tobytes("png")
    copied = document.new_page(width=page.rect.width, height=page.rect.height)
    copied.insert_image(copied.rect, stream=image)
    assert copied.get_drawings() == []
    return copied


def _detect(page: pymupdf.Page, **configuration: Any) -> ResultadoMetodoSimbolos:
    return observar_simbolos_estruturais(
        page,
        documento_id="e09-author-control",
        documento_sha256=_SOURCE_HASH,
        pagina_numero=1,
        configuracao=ConfiguracaoDetectorEstrutural(**configuration),
    )


def _bbox(observation: ObservacaoSimbolo) -> tuple[float, float, float, float]:
    points = observation.geometria.pontos_originais
    return (
        float(min(point[0] for point in points)),
        float(min(point[1] for point in points)),
        float(max(point[0] for point in points)),
        float(max(point[1] for point in points)),
    )


def _nearest(result: ResultadoMetodoSimbolos, x: float, y: float) -> ObservacaoSimbolo | None:
    candidates = [
        observation
        for observation in result.observacoes
        if (box := _bbox(observation))[0] - 5 <= x <= box[2] + 5 and box[1] - 7 <= y <= box[3] + 7
    ]
    return min(candidates, key=lambda item: abs(_bbox(item)[0] - x), default=None)


def test_raster_only_broken_and_bent_strokes_are_exclusive_to_structural_vs_legacy() -> None:
    with pymupdf.open() as source, pymupdf.open() as raster_document:
        vector = source.new_page(width=280, height=160)
        _barred_symbol(vector, 42, 53, gap=0.5, bend=1.2)
        raster = _raster_copy(vector, raster_document)
        legacy = observar_simbolos_legados(
            raster,
            documento_id="e09-author-control",
            documento_sha256=_SOURCE_HASH,
            pagina_numero=1,
        )
        structural = _detect(raster)
        raster_matchers = observar_simbolos_raster(
            raster,
            documento_id="e09-author-control",
            documento_sha256=_SOURCE_HASH,
            pagina_numero=1,
            templates=carregar_templates_raster(),
            configuracao=ConfiguracaoDetectorRaster(tile_pixels=256, sobreposicao_pixels=96),
        )
    assert legacy.observacoes == ()
    assert all(result.observacoes == () for result in raster_matchers)
    found = _nearest(structural, 55, 53)
    assert found is not None
    assert found.alternativas[0].classe == "ATERRAMENTO"
    # The graph must associate the detached left stem, not only the bars.
    assert abs(_bbox(found)[0] - 42) <= 1
    assert found.raster_sha256 is not None
    assert found.fonte.documento_sha256 == _SOURCE_HASH
    assert structural.completo


def test_broken_vector_stem_retains_complete_symbol_box() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=280, height=160)
        _barred_symbol(page, 42, 53, gap=0.5, bend=0.4)
        result = _detect(page, entrada="vetor")
    found = _nearest(result, 42, 53)
    assert found is not None
    assert found.alternativas[0].classe == "ATERRAMENTO"
    assert abs(_bbox(found)[0] - 42) <= 1
    assert result.completo


def test_local_skeleton_recovers_slightly_sloped_mixed_width_raster_symbol() -> None:
    with pymupdf.open() as source, pymupdf.open() as raster_document:
        page = source.new_page(width=180, height=110)
        _sloped_variable_width_symbol(page, tapering=True)
        raster = _raster_copy(page, raster_document)
        result = _detect(raster)
    found = _nearest(result, 50, 54)
    assert found is not None
    assert found.alternativas[0].classe == "ATERRAMENTO"
    assert abs(_bbox(found)[0] - 42) <= 2
    skeleton = dict(found.atributos)
    assert int(skeleton["esqueleto_pixels"] or 0) > 0
    assert int(skeleton["esqueleto_juncoes"] or 0) >= 1
    assert result.completo


def test_local_skeleton_does_not_invent_taper_on_similar_thick_lines() -> None:
    with pymupdf.open() as source, pymupdf.open() as raster_document:
        page = source.new_page(width=180, height=110)
        _sloped_variable_width_symbol(page, tapering=False)
        raster = _raster_copy(page, raster_document)
        result = _detect(raster)
    assert result.observacoes == ()
    assert result.coberturas[0].estado is EstadoMetodoSimbolos.NAO_DETECCAO


@pytest.mark.parametrize("input_kind", ["vetor", "raster"])
def test_similar_three_and_four_bar_symbols_remain_separate_occurrences(input_kind: str) -> None:
    with pymupdf.open() as document, pymupdf.open() as raster_document:
        page = document.new_page(width=320, height=180)
        _barred_symbol(page, 35, 45, bars=3)
        _barred_symbol(page, 188, 105, bars=4)
        if input_kind == "raster":
            page = _raster_copy(page, raster_document)
        result = _detect(page, entrada=input_kind)
    ground = _nearest(result, 35, 45)
    mt = _nearest(result, 188, 105)
    assert ground is not None and mt is not None
    assert ground.id != mt.id
    assert ground.alternativas[0].classe == "ATERRAMENTO"
    assert mt.alternativas[0].classe == "PARA_RAIOS_MT"
    assert len(result.observacoes) == 2


@pytest.mark.parametrize("input_kind", ["vetor", "raster"])
def test_disconnected_bars_and_nearby_components_do_not_form_symbol(input_kind: str) -> None:
    with pymupdf.open() as document, pymupdf.open() as raster_document:
        page = document.new_page(width=280, height=170)
        _line(page, (36, 65), (63, 65))
        for index, length in enumerate((10.0, 7.0, 4.0)):
            x = 51 + index * 4
            _line(page, (x, 83 - length / 2), (x, 83 + length / 2))
        if input_kind == "raster":
            page = _raster_copy(page, raster_document)
        result = _detect(page, entrada=input_kind)
    assert result.observacoes == ()
    assert result.coberturas[0].estado is EstadoMetodoSimbolos.NAO_DETECCAO


def test_dense_visual_graph_reports_budget_failure_without_false_completion() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=160, height=160)
        for coordinate in range(10, 150, 7):
            _line(page, (coordinate, 10), (coordinate, 150))
            _line(page, (10, coordinate), (150, coordinate))
        result = _detect(page, entrada="vetor", limite_tracos=8, limite_expansoes=16)
    assert not result.completo
    assert all(
        coverage.estado not in {EstadoMetodoSimbolos.CONCLUIDO, EstadoMetodoSimbolos.NAO_DETECCAO}
        and coverage.motivo
        for coverage in result.coberturas
    )


def test_method_identity_separates_algorithm_from_shared_input() -> None:
    raster = perfil_simbolos_estruturais()
    vector = perfil_simbolos_estruturais(
        configuracao=ConfiguracaoDetectorEstrutural(entrada="vetor")
    )
    raster_matcher = perfis_simbolos_raster(templates=carregar_templates_raster())[0]
    legacy = perfil_simbolos_legados()
    assert raster.assinatura() != vector.assinatura()
    assert raster.familia != raster_matcher.familia
    assert vector.familia != legacy.familia
    assert raster.possui_origem_correlacionada(raster_matcher)
    assert vector.possui_origem_correlacionada(legacy)
    changed_budget = perfil_simbolos_estruturais(
        configuracao=replace(ConfiguracaoDetectorEstrutural(), limite_expansoes=1000)
    )
    assert changed_budget.assinatura() != raster.assinatura()


def test_skeleton_revision_changes_method_version_and_signature() -> None:
    revised = perfil_simbolos_estruturais()
    predecessor = replace(revised, versao="e09-stroke-graph-1")
    assert revised.versao != predecessor.versao
    assert revised.assinatura() != predecessor.assinatura()
    assert dict(revised.parametros)["skeleton_algorithm"] == "zhang-suen-local-v1"


def test_opt_in_detection_leaves_source_and_legacy_results_unchanged() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=220, height=130)
        _barred_symbol(page, 45, 60)
        before_contents = tuple(document.xref_stream(xref) for xref in page.get_contents())
        before_drawings = page.get_drawings()
        before_legacy = observar_simbolos_legados(
            page,
            documento_id="e09-author-control",
            documento_sha256=_SOURCE_HASH,
            pagina_numero=1,
        )
        structural = _detect(page, entrada="vetor")
        after_legacy = observar_simbolos_legados(
            page,
            documento_id="e09-author-control",
            documento_sha256=_SOURCE_HASH,
            pagina_numero=1,
        )
        assert tuple(document.xref_stream(xref) for xref in page.get_contents()) == before_contents
        assert page.get_drawings() == before_drawings
    assert before_legacy == after_legacy
    assert structural.perfil.metodo_id != before_legacy.perfil.metodo_id
    assert structural.observacoes
    assert any(
        int(dict(item.atributos).get("grafo_juncoes_visuais") or 0) > 0
        for item in structural.observacoes
    )
    assert all(
        "electrical_connectivity" not in dict(item.atributos)
        or dict(item.atributos)["electrical_connectivity"] is False
        for item in structural.observacoes
    )


def test_visual_junctions_do_not_change_electrical_span_builder(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    electrical_before = detectar_vaos(project)
    assert electrical_before
    connections_before = project.conexoes_internas
    with pymupdf.open() as document:
        page = document.new_page(width=220, height=130)
        _barred_symbol(page, 45, 60)
        visual = _detect(page, entrada="vetor")
    assert visual.observacoes
    assert any(
        int(dict(item.atributos).get("grafo_juncoes_visuais") or 0) > 0
        for item in visual.observacoes
    )
    assert detectar_vaos(project) == electrical_before
    assert project.conexoes_internas == connections_before


@pytest.mark.parametrize("source", ["raster", "vetor"])
def test_empty_page_is_explicit_non_detection(source: str) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=100, height=80)
        result = _detect(page, entrada=source)
    assert result.observacoes == ()
    assert result.completo
    assert result.coberturas[0].estado is EstadoMetodoSimbolos.NAO_DETECCAO
