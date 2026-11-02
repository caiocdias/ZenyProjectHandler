from __future__ import annotations

import pytest

from zeny_project_handler.adapters.analysis.rapid_ocr import RapidLocalOcr, map_quad
from zeny_project_handler.ports.analysis import PaginaRasterOcr


def test_coordinate_mapping_uses_pixel_origin_and_keeps_polygon() -> None:
    quad: list[list[float]] = [[0, 0], [100, 2], [98, 40], [1, 39]]
    mapped = map_quad(quad, raster_origin=(201, 301), scale=2, page_size=(400, 600))
    assert len(mapped) == 4
    assert mapped[0] == pytest.approx([201 / 800, 301 / 1200])
    assert mapped[2] == pytest.approx([299 / 800, 341 / 1200])


def test_ocr_rejects_invalid_memory_before_calling_optional_engine() -> None:
    engine = object.__new__(RapidLocalOcr)
    for width, height, stride, data in ((3000, 3000, 9000, b""), (2, 2, 3, b"123456")):
        page = PaginaRasterOcr(
            pagina_numero=1,
            largura_pixels=width,
            altura_pixels=height,
            stride=stride,
            dados_rgb=data,
            dpi=600,
        )
        with pytest.raises(ValueError):
            engine.recognize_quads(page)
