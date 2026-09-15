"""Regressões E12: cor/risco são evidências locais, nunca autoridade técnica."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFont
from tests.unit.test_pymupdf_analyzer import CharacterizationOcr

from zeny_project_handler.adapters.analysis.pymupdf_revision_ocr import (
    _bands,
    _cells,
    _color_mask,
    _strike_rows,
    revision_color_readings,
)
from zeny_project_handler.ports.analysis import PaginaRasterOcr, TrechoTextoOcr


def _picture() -> Image.Image:
    picture = Image.new("RGB", (220, 130), "white")
    draw = ImageDraw.Draw(picture)
    font = ImageFont.load_default(size=24)
    draw.text((10, 8), "N4(1)", fill="red", font=font)
    draw.line((10, 23, 74, 23), fill="red", width=2)
    draw.rectangle((10, 45, 80, 78), outline="green")
    draw.rectangle((80, 45, 153, 78), outline="green")
    draw.text((12, 46), "N4(1)", fill="green", font=font)
    draw.text((83, 46), "N3(2)", fill="green", font=font)
    draw.text((10, 90), "CA CAA 36m", fill="black", font=font)
    return picture


class _LiteralOcr(CharacterizationOcr):
    def reconhecer_rotulo_operacional(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
        self.pages.append(pagina)
        # Deliberadamente incerto: o extrator deve preservar, sem completar para N4.
        return (TrechoTextoOcr(texto="N?(1)", caixa_normalizada=(0, 0, 1, 1), confianca=0.3),)


def test_separate_cells_colors_strike_and_literal_geometry() -> None:
    picture = _picture()
    engine = _LiteralOcr()
    pixmap = SimpleNamespace(width=220, height=130, samples=picture.tobytes(), x=100, y=200)
    page = SimpleNamespace(rect=SimpleNamespace(width=600, height=800))
    readings, failed = revision_color_readings(pixmap, page, 1, 72, engine)
    assert not failed
    green = [r for r in readings if r["color"] == "verde"]
    red = [r for r in readings if r["color"] == "vermelho"]
    assert len(green) == 2 and len(red) == 2
    assert green[0]["box"][2] < green[1]["box"][0]
    assert all(not r["horizontal_strike"] for r in green)
    assert all(r["horizontal_strike"] for r in red)
    assert {r["preprocessing"] for r in red} == {
        "cor_original",
        "cor_interpolacao_risco_horizontal",
    }
    assert all(r["text"] == "N?(1)" and r["requires_review"] for r in readings)
    assert all(0 < r["box"][0] < r["box"][2] < 1 for r in readings)
    assert all(0 < r["box"][1] < r["box"][3] < 1 for r in readings)
    assert all(r["box"][3] < (200 + 90) / 800 for r in readings)  # black neighbour excluded


@pytest.mark.parametrize("color", ["black", "blue", "white"])
def test_neutral_text_photos_or_empty_crop_do_not_become_colored_operations(color: str) -> None:
    picture = Image.new("RGB", (80, 40), color)
    pixmap = SimpleNamespace(width=80, height=40, samples=picture.tobytes(), x=0, y=0)
    page = SimpleNamespace(rect=SimpleNamespace(width=100, height=100))
    engine = _LiteralOcr()
    assert revision_color_readings(pixmap, page, 1, 300, engine) == ([], False)
    assert not engine.pages


def test_empty_frame_and_underline_are_not_strikes_or_text() -> None:
    picture = Image.new("RGB", (100, 50), "white")
    draw = ImageDraw.Draw(picture)
    draw.rectangle((5, 5, 90, 40), outline="green")
    mask = _color_mask(picture, "verde")
    band = mask.crop(_bands(mask)[0])
    assert not _strike_rows(band)
    for cell in _cells(band):
        assert band.crop(cell).getbbox() is None


@pytest.mark.parametrize("cancel", [False, True])
def test_color_failure_preserves_prior_readings_and_cancellation_propagates(cancel: bool) -> None:
    class Failing(_LiteralOcr):
        def reconhecer_rotulo_operacional(
            self, pagina: PaginaRasterOcr
        ) -> tuple[TrechoTextoOcr, ...]:
            if self.pages:
                if cancel:
                    raise KeyboardInterrupt
                raise TimeoutError("private runtime path")
            return super().reconhecer_rotulo_operacional(pagina)

    picture = _picture()
    pixmap = SimpleNamespace(width=220, height=130, samples=picture.tobytes(), x=0, y=0)
    page = SimpleNamespace(rect=SimpleNamespace(width=600, height=800))
    if cancel:
        with pytest.raises(KeyboardInterrupt):
            revision_color_readings(pixmap, page, 1, 300, Failing())
    else:
        readings, failed = revision_color_readings(pixmap, page, 1, 300, Failing())
        assert failed and len(readings) == 1
