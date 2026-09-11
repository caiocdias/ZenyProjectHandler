# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pymupdf
import pytest
from tests.unit.test_pymupdf_analyzer import CharacterizationOcr

from zeny_project_handler.adapters.analysis.pymupdf_ocr import (
    _geometry_from_rectified_ocr,
    _linear_cable_frames,
    _linear_label_candidates,
    _operational_frame,
    _rectified_frame_region,
)
from zeny_project_handler.domain.enums import TipoGeometria
from zeny_project_handler.ports.analysis import ConfiguracaoAnaliseDocumento, TrechoTextoOcr


def _frame_pdf(path: Path, *, angle: int, retrace: bool, crossing: bool = False) -> Path:
    with pymupdf.open() as document:
        page = document.new_page(width=100, height=100)
        rectangle = pymupdf.Rect(40, 40, 56, 44)
        shape = page.new_shape()
        shape.draw_polyline((rectangle.tl, rectangle.tr, rectangle.br, rectangle.bl, rectangle.tl))
        if retrace:
            shape.draw_line(rectangle.tl, (48, 42 if crossing else 40))
        shape.finish(
            color=(0, 0.5, 0),
            closePath=False,
            morph=(pymupdf.Point(50, 50), pymupdf.Matrix(angle)),
        )
        shape.commit()
        document.save(path)
    return path


@pytest.mark.parametrize("angle", [0, 30, 90, 180, 270])
def test_retraced_frame_keeps_bounds_without_reflection(tmp_path: Path, angle: int) -> None:
    path = _frame_pdf(tmp_path / "frame.pdf", angle=angle, retrace=True)
    with pymupdf.open(path) as document:
        page = document[0]
        frames = _linear_cable_frames(page)
        assert len(frames) == 1
        frame = frames[0]
        horizontal, vertical = frame.horizontal_axis, frame.vertical_axis
        assert horizontal[0] * vertical[1] - horizontal[1] * vertical[0] > 0
        assert frame.width_points == pytest.approx(16, abs=0.001)
        assert frame.height_points == pytest.approx(4, abs=0.001)
        region = _rectified_frame_region(page, 1, frame, 450, isolate="green", padding=True)
        padding = region.padding_pixels
        item = TrechoTextoOcr(
            texto="ABN-25(25)",
            caixa_normalizada=(
                padding / region.raster.largura_pixels,
                padding / region.raster.altura_pixels,
                (padding + region.content_width_pixels) / region.raster.largura_pixels,
                (padding + region.content_height_pixels) / region.raster.altura_pixels,
            ),
            confianca=0.93,
        )
        geometry = _geometry_from_rectified_ocr(region, item, page)
        assert geometry.tipo == TipoGeometria.POLIGONO
        assert len(geometry.pontos) == 4
        assert tuple(float(value) for value in frame.bounds) == pytest.approx(
            (
                float(min(point.x for point in geometry.pontos)),
                float(min(point.y for point in geometry.pontos)),
                float(max(point.x for point in geometry.pontos)),
                float(max(point.y for point in geometry.pontos)),
            ),
            abs=0.00001,
        )
        if angle == 30:
            assert geometry.pontos[0].y != geometry.pontos[1].y


def test_line_crossing_a_frame_is_not_a_redundant_border(tmp_path: Path) -> None:
    path = _frame_pdf(tmp_path / "crossing.pdf", angle=30, retrace=True, crossing=True)
    with pymupdf.open(path) as document:
        assert _linear_cable_frames(document[0]) == ()


@pytest.mark.parametrize("rectangle", [(10, 10, 14, 12), (10, 10, 18, 14)])
def test_small_or_square_symbols_do_not_become_label_frames(
    rectangle: tuple[int, int, int, int],
) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=100, height=100)
        page.draw_rect(rectangle, color=(0, 0.5, 0))
        assert _operational_frame(page, page.get_drawings()[0]) is None


def test_small_frame_receives_one_bounded_ocr_call() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=100, height=100)
        page.draw_rect((10, 10, 18, 12), color=(0, 0.5, 0))
        assert _operational_frame(page, page.get_drawings()[0]) is not None
        assert _linear_cable_frames(page) == ()
        engine = CharacterizationOcr()
        candidates, diagnostics = _linear_label_candidates(
            page, 1, engine, ConfiguracaoAnaliseDocumento()
        )
        assert candidates == ()
        assert diagnostics == ()
        assert len(engine.pages) == 1


def test_rectified_crop_at_page_edge_keeps_geometry_normalized() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=100, height=100)
        page.draw_rect((0, 0, 16, 4), color=(0, 0.5, 0))
        frame = _linear_cable_frames(page)[0]
        region = _rectified_frame_region(
            page,
            1,
            frame,
            450,
            horizontal_start=-0.5,
            horizontal_span=2,
            vertical_start=-1,
            vertical_span=3,
            isolate="green",
            padding=True,
        )
        geometry = _geometry_from_rectified_ocr(
            region,
            TrechoTextoOcr(texto="ABN-25(25)", caixa_normalizada=(0, 0, 1, 1), confianca=0.9),
            page,
        )
        assert geometry.tipo == TipoGeometria.POLIGONO
        assert all(
            Decimal(0) <= coordinate <= Decimal(1)
            for point in geometry.pontos
            for coordinate in (point.x, point.y)
        )
        assert geometry.pontos[0].x == geometry.pontos[0].y == Decimal(0)


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_declared_page_rotation_preserves_rectified_frame(rotation: int) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=100, height=160)
        source = pymupdf.Rect(20, 30, 36, 34)
        page.draw_rect(source, color=(0, 0.5, 0))
        page.set_rotation(rotation)
        expected = source * page.rotation_matrix
        frame = _linear_cable_frames(page)[0]
        assert tuple(float(v) for v in frame.bounds) == pytest.approx(
            (
                expected.x0 / page.rect.width,
                expected.y0 / page.rect.height,
                expected.x1 / page.rect.width,
                expected.y1 / page.rect.height,
            )
        )
        region = _rectified_frame_region(page, 1, frame, 450, isolate="green", padding=False)
        assert min(region.raster.dados_rgb) == 0
