# mypy: disable-error-code="no-untyped-call"
from math import cos, radians, sin

import pymupdf
import pytest
from PIL import Image

from zeny_project_handler.adapters.analysis.pymupdf_glyph_consensus import (
    GlyphConsensus,
    GlyphShape,
    shape_error,
)
from zeny_project_handler.adapters.analysis.pymupdf_glyphs import GlyphRegion


def _region() -> GlyphRegion:
    paths = tuple(
        {"items": [("re", pymupdf.Rect(x, 0, x + 0.3, 2), 1)], "even_odd": False, "closePath": True}
        for x in (0, 1)
    )
    return GlyphRegion(paths, (1, 0), (0, 0, 1.3, 2))


def test_shape_agreement_requires_two_other_regions_and_rejects_conflicting_readings() -> None:
    region = _region()
    atlas = GlyphConsensus()
    atlas.add(0, region, "11")
    assert atlas.recognize(9, region, 0) is None  # two glyphs in one region are one vote
    atlas.add(1, region, "11")
    assert atlas.recognize(9, region, 0) == "1"
    assert atlas.recognize(0, region, 0) is None  # no self-confirmation
    atlas.add(2, region, "II")
    assert atlas.recognize(9, region, 0) is None


def test_partial_ocr_cannot_seed_a_glyph_mapping() -> None:
    atlas = GlyphConsensus()
    for index in range(3):
        atlas.add(index, _region(), "1")
    assert atlas.recognize(9, _region(), 0) is None


def test_shape_comparison_accepts_small_rotation_but_not_reflection_or_half_turn() -> None:
    points = ((-1.0, -0.3), (0.2, 1.0), (0.8, -0.7))
    shape = GlyphShape(("l",), points)
    angle = radians(5)
    rotated = tuple(
        (x * cos(angle) - y * sin(angle), x * sin(angle) + y * cos(angle)) for x, y in points
    )
    assert shape_error(shape, GlyphShape(("l",), rotated)) == pytest.approx(0, abs=1e-10)
    assert shape_error(shape, GlyphShape(("l",), tuple((-x, -y) for x, y in points))) == float(
        "inf"
    )
    assert shape_error(shape, GlyphShape(("l",), tuple((-x, y) for x, y in points))) > 0.12
    assert shape_error(shape, GlyphShape(("c",), points)) == float("inf")


def test_rectangular_counter_keeps_opposite_winding_in_the_ocr_raster() -> None:
    path = {
        "items": [("re", pymupdf.Rect(0, 0, 3, 3), 1), ("re", pymupdf.Rect(1, 1, 2, 2), -1)],
        "even_odd": False,
        "closePath": True,
    }
    region = GlyphRegion((path,), (1, 0), (0, 0, 3, 3))
    raster = region.render(1, 720)
    image = Image.frombytes("RGB", (raster.largura_pixels, raster.altura_pixels), raster.dados_rgb)
    assert image.getpixel((30, 30)) == (255, 255, 255)
    assert image.getpixel((20, 30)) == (0, 0, 0)
