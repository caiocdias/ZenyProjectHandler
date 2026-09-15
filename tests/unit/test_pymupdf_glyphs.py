# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pymupdf
import pytest
from PIL import Image, ImageOps
from tests.unit.test_pymupdf_analyzer import CharacterizationOcr

from zeny_project_handler.adapters.analysis import pymupdf_glyph_ocr as ocr
from zeny_project_handler.adapters.analysis import pymupdf_ocr_batch as batches
from zeny_project_handler.adapters.analysis.pymupdf_glyphs import glyph_groups, glyph_region
from zeny_project_handler.ports.analysis import PaginaRasterOcr, TrechoTextoOcr


def _outlined_pair(page: Any, x: float, y: float, angle: float = 0, gap: float = 1.5) -> None:
    """L e I em contornos públicos, junto de moldura e linha cruzada."""
    shape = page.new_shape()
    for points in (
        (
            (x, y),
            (x + 0.3, y),
            (x + 0.3, y + 1.7),
            (x + 1.1, y + 1.7),
            (x + 1.1, y + 2),
            (x, y + 2),
        ),
        ((x + gap, y), (x + gap + 0.3, y), (x + gap + 0.3, y + 2), (x + gap, y + 2)),
    ):
        shape.draw_polyline((*points, points[0]))
        shape.finish(
            color=None, fill=(0, 0.5, 0), morph=(pymupdf.Point(x, y), pymupdf.Matrix(angle))
        )
    shape.commit()
    page.draw_rect((x - 0.1, y - 0.1, x + 2, y + 2.1), color=(0, 0.5, 0))
    page.draw_line((x - 10, y + 1), (x + 10, y + 1), color=(0, 0.5, 0), width=0.4)


class _OutlineOcr(CharacterizationOcr):
    def __init__(self, fail_on: int | None = None) -> None:
        self.calls = 0
        self.fail_on = fail_on

    def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
        self.calls += 1
        if self.calls == self.fail_on:
            raise TimeoutError("private runtime details")
        image = Image.frombytes(
            "RGB", (pagina.largura_pixels, pagina.altura_pixels), pagina.dados_rgb
        )
        ink = ImageOps.invert(image.convert("L"))
        bands: list[tuple[int, int]] = []
        start = None
        for y in range(ink.height + 1):
            occupied = y < ink.height and ink.crop((0, y, ink.width, y + 1)).getbbox() is not None
            if occupied and start is None:
                start = y
            if not occupied and start is not None:
                bands.append((start, y))
                start = None
        result = []
        for top, bottom in bands:
            box = ink.crop((0, top, ink.width, bottom)).getbbox()
            assert box is not None
            result.append(
                TrechoTextoOcr(
                    texto="LI",
                    confianca=0.97,
                    caixa_normalizada=(
                        box[0] / ink.width,
                        top / ink.height,
                        box[2] / ink.width,
                        bottom / ink.height,
                    ),
                )
            )
        return tuple(result)


@pytest.mark.parametrize("angle", [0, 30, 90, 180, 270])
@pytest.mark.parametrize("rotation", [0, 90])
def test_vector_crop_excludes_crossing_line_and_maps_back_to_each_occurrence(
    angle: float,
    rotation: int,
) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=100, height=150)
        _outlined_pair(page, 20, 30, angle)
        _outlined_pair(page, 50, 70, angle)
        page.set_rotation(rotation)
        groups = glyph_groups(page)
        assert len(groups) == 2
        # The narrow pair is retained as paths but is not a line candidate.
        for group in groups:
            assert len(group) == 2
        # Exercise affine mapping directly even for a narrow pair.
        from math import cos, radians, sin

        from zeny_project_handler.adapters.analysis.pymupdf_glyphs import GlyphRegion

        axis = (cos(radians(-angle)), sin(radians(-angle)))
        region = GlyphRegion(groups[0], axis, (0, 0, 1, 1))
        coords = [
            region.project(p)
            for d in groups[0]
            for item in d["items"]
            for p in (item[1:] if item[0] in {"l", "c"} else (item[1].tl, item[1].br))
        ]
        bounds = (
            min(p[0] for p in coords),
            min(p[1] for p in coords),
            max(p[0] for p in coords),
            max(p[1] for p in coords),
        )
        region = GlyphRegion(groups[0], axis, bounds)
        raster = region.render(1, 1200)
        assert raster.largura_pixels < 70  # crossing line would be over 300 px
        reading = ocr._Reading(raster, _OutlineOcr().reconhecer(raster))
        candidates = ocr._candidates(page, 1, 0, region, reading)
        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.conteudo_bruto == "LI"
        assert dict(candidate.atributos_extraidos)["confianca"] == Decimal("0.97")
        assert dict(candidate.atributos_extraidos)["cor"] == "#008000"
        points = candidate.geometria.pontos
        expected = (pymupdf.Point(0.9, 1) * pymupdf.Matrix(-angle)) + pymupdf.Point(20, 30)
        expected *= page.rotation_matrix
        assert sum(float(p.x) for p in points) / 4 == pytest.approx(
            expected.x / page.rect.width, abs=0.002
        )
        assert sum(float(p.y) for p in points) / 4 == pytest.approx(
            expected.y / page.rect.height, abs=0.002
        )


def _wide_groups(page: Any, count: int) -> None:
    for index in range(count):
        _outlined_pair(page, 20, 20 + index * 10)
        # Make the pair longer while preserving one run, with a second adjacent pair.
    # Tests below exercise batch plumbing on explicit regions to avoid OCR-content assumptions.


def test_symbols_empty_frames_native_text_and_images_do_not_create_glyph_regions() -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        page.draw_rect((10, 10, 18, 12), color=(0, 0.5, 0))
        page.draw_circle((30, 30), 2, color=None, fill=(0, 0.5, 0))
        page.draw_line((10, 20), (90, 20), color=(0, 0.5, 0))
        page.insert_text((20, 100), "NATIVE CONTROL")
        assert glyph_groups(page) == ()
        assert ocr.extract_vector_glyphs(page, 1, _OutlineOcr(), 1200) == ((), ())


def test_pixel_limited_batches_resume_from_consumed_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    from zeny_project_handler.adapters.analysis.pymupdf_glyphs import GlyphRegion

    with pymupdf.open() as document:
        page = document.new_page()
        _wide_groups(page, 3)
        regions = [
            GlyphRegion(g, (1, 0), (20, 20 + i * 10, 21.8, 22 + i * 10))
            for i, g in enumerate(glyph_groups(page))
        ]
        monkeypatch.setattr(batches, "MAXIMUM_BATCH_PIXELS", 15_000)
        readings: dict[int, ocr._Reading] = {}
        engine = _OutlineOcr()
        ocr._read_batches(regions, 1, engine, 1200, readings)
        assert set(readings) == {0, 1, 2}
        assert engine.calls == 3
        assert all(r.items[0].texto == "LI" for r in readings.values())
        assert all(isinstance(r.raster, ocr._RasterGeometry) for r in readings.values())


def test_outline_size_guards_and_degenerate_baselines() -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        _outlined_pair(page, 20, 20)
        group = glyph_groups(page)[0]
        assert glyph_region(group) is None  # not a line: width < 1.3 * height
        assert glyph_region((group[0], group[0])) is None


@pytest.mark.parametrize("budget", ["groups", "pixels"])
def test_budget_is_checked_before_render_and_unread_regions_are_diagnosed(
    monkeypatch: pytest.MonkeyPatch,
    budget: str,
) -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        for index in range(3):
            _outlined_pair(page, 20, 20 + index * 10, gap=3 if index else 2.5)
        if budget == "groups":
            monkeypatch.setattr(ocr, "MAXIMUM_GLYPH_GROUPS", 1)
        else:
            monkeypatch.setattr(ocr, "MAXIMUM_GLYPH_PIXELS", 5150)
        candidates, diagnostics = ocr.extract_vector_glyphs(page, 1, _OutlineOcr(), 1200)
        assert len(candidates) == 1
        assert diagnostics[0].codigo == "analise.ocr_cobertura_parcial"
        assert "2 grupos" in diagnostics[0].mensagem


def test_failure_keeps_completed_vector_crops_and_sanitizes_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ocr, "MAXIMUM_BATCH_REGIONS", 1)
    with pymupdf.open() as document:
        page = document.new_page()
        _outlined_pair(page, 20, 20, gap=3)
        _outlined_pair(page, 20, 40, gap=3)
        candidates, diagnostics = ocr.extract_vector_glyphs(page, 1, _OutlineOcr(fail_on=2), 1200)
        assert len(candidates) == 1
        assert candidates[0].conteudo_bruto == "LI"
        assert diagnostics[0].codigo == "analise.ocr_glifos_falhou"
        assert "private" not in diagnostics[0].mensagem


def test_identical_text_at_distinct_vector_occurrences_remains_distinct() -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        _outlined_pair(page, 20, 20, gap=3)
        _outlined_pair(page, 20, 40, gap=3)
        candidates, diagnostics = ocr.extract_vector_glyphs(page, 1, _OutlineOcr(), 1200)
        assert not diagnostics
        assert [c.conteudo_bruto for c in candidates] == ["LI", "LI"]
        assert candidates[0].chave_estavel != candidates[1].chave_estavel
        assert candidates[0].geometria != candidates[1].geometria


def test_drawing_inspection_failure_is_a_sanitized_ocr_diagnostic() -> None:
    class BrokenPage:
        def get_drawings(self) -> list[dict[str, Any]]:
            raise ValueError("private source details")

    candidates, diagnostics = ocr.extract_vector_glyphs(BrokenPage(), 1, _OutlineOcr(), 1200)
    assert candidates == ()
    assert diagnostics[0].codigo == "analise.ocr_glifos_falhou"
    assert "private" not in diagnostics[0].mensagem


def test_packing_similar_widths_preserves_original_occurrence_indices_and_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ocr, "MAXIMUM_BATCH_REGIONS", 1)
    with pymupdf.open() as document:
        page = document.new_page()
        for index, gap in enumerate((3, 2.5, 2.7)):
            _outlined_pair(page, 20, 20 + index * 10, gap=gap)
        regions = [glyph_region(group) for group in glyph_groups(page)]
        assert all(region is not None for region in regions)
        valid_regions = [region for region in regions if region is not None]
        readings: dict[int, ocr._Reading] = {}
        ocr._read_batches(valid_regions, 1, _OutlineOcr(), 1200, readings)
        assert list(readings) == [1, 2, 0]
        for index, reading in readings.items():
            candidate = ocr._candidates(page, 1, index, valid_regions[index], reading)[0]
            y = sum(float(point.y) for point in candidate.geometria.pontos) / 4
            assert y == pytest.approx((21 + index * 10) / page.rect.height, abs=0.001)


@pytest.mark.parametrize("first_confidence,expected_calls", [(0.95, 1), (0.70, 2)])
def test_weak_retry_stops_on_reliable_reading_but_keeps_second_attempt_when_needed(
    first_confidence: float,
    expected_calls: int,
) -> None:
    class SequenceOcr(_OutlineOcr):
        def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
            self.calls += 1
            return (
                TrechoTextoOcr(
                    texto="LI",
                    confianca=first_confidence if self.calls == 1 else 0.96,
                    caixa_normalizada=(0.1, 0.1, 0.9, 0.9),
                ),
            )

    with pymupdf.open() as document:
        page = document.new_page()
        _outlined_pair(page, 20, 20, gap=3)
        region = glyph_region(glyph_groups(page)[0])
        assert region is not None
        readings = {0: ocr._Reading(region.render(1, 1800), ())}
        engine = SequenceOcr()
        ocr._retry_weak([region], 1, engine, 1800, readings)
        assert engine.calls == expected_calls
        assert readings[0].confidence >= 0.90


def test_weak_regions_after_twenty_four_get_a_higher_resolution_attempt() -> None:
    class ResolutionOcr(_OutlineOcr):
        def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
            self.calls += 1
            if pagina.dpi < 2400:
                return ()
            return (
                TrechoTextoOcr(texto="CAA", confianca=0.96, caixa_normalizada=(0.2, 0.2, 0.8, 0.8)),
            )

    with pymupdf.open() as document:
        page = document.new_page()
        _outlined_pair(page, 20, 20, gap=3)
        region = glyph_region(glyph_groups(page)[0])
        assert region is not None
        readings = {i: ocr._Reading(region.render(1, 1800), ()) for i in range(25)}
        engine = ResolutionOcr()
        ocr._retry_weak([region] * 25, 1, engine, 1800, readings)
        assert engine.calls == 75
        assert all(r.raster.dpi == 2400 and r.items[0].texto == "CAA" for r in readings.values())


def test_long_vector_label_is_not_silently_excluded_at_sixteen_glyphs() -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        for i in range(9):
            # Consecutive fill paths form a single 18-character label.
            shape = page.new_shape()
            for x in (20 + i * 3, 21.5 + i * 3):
                shape.draw_rect((x, 20, x + 0.5, 22))
                shape.finish(color=None, fill=(0, 0.5, 0))
            shape.commit()
        regions, skipped = ocr._regions(page, 1200)
        assert skipped == 0 and len(regions) == 1
        assert len(regions[0].paths) == 18


@pytest.mark.parametrize("text", ["ABC-2 CA", "ABC-2 CAA", "N-4", "TR-3-45", "N?(1)", "36m"])
def test_vector_candidates_keep_literal_codes_without_catalog_completion(text: str) -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        _outlined_pair(page, 20, 20, gap=3)
        region = glyph_region(glyph_groups(page)[0])
        assert region is not None
        reading = ocr._Reading(
            region.render(1, 1800),
            (TrechoTextoOcr(texto=text, caixa_normalizada=(0.2, 0.2, 0.8, 0.8)),),
        )
        candidate = ocr._candidates(page, 1, 0, region, reading)[0]
        assert candidate.conteudo_bruto == text
        assert "situacao_projeto_forcada" not in dict(candidate.atributos_extraidos)
