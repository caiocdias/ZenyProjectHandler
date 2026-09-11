# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pymupdf
import pytest
from PIL import Image
from tests.unit.test_pymupdf_analyzer import CharacterizationOcr

from zeny_project_handler.adapters.analysis import pymupdf_ocr_batch as batch_module
from zeny_project_handler.adapters.analysis.pymupdf_ocr import (
    _extract_remaining_frame_labels,
    _linear_label_candidates,
    _operational_frame,
)
from zeny_project_handler.adapters.analysis.pymupdf_ocr_batch import pack_ocr_rows
from zeny_project_handler.domain.enums import TipoGeometria
from zeny_project_handler.ports.analysis import (
    ConfiguracaoAnaliseDocumento,
    PaginaRasterOcr,
    TrechoTextoOcr,
)


def _raster() -> PaginaRasterOcr:
    return PaginaRasterOcr(
        pagina_numero=1,
        largura_pixels=80,
        altura_pixels=20,
        stride=240,
        dados_rgb=b"\x00" * 4800,
        dpi=720,
    )


def test_batch_keeps_pixels_and_maps_out_of_order_repeated_labels_to_each_crop() -> None:
    batch = pack_ocr_rows((_raster(), _raster()))
    assert batch is not None
    assert batch.boxes == ((28, 28, 108, 48), (28, 76, 108, 96))
    raster = batch.raster
    assert (raster.largura_pixels, raster.altura_pixels) == (136, 124)
    picture = Image.frombytes("RGB", (136, 124), raster.dados_rgb)
    assert picture.getpixel((30, 30)) == (0, 0, 0)
    assert picture.getpixel((30, 65)) == (255, 255, 255)
    for index, top in ((1, 81), (0, 33)):
        item = TrechoTextoOcr(
            texto="CM2(1)",
            caixa_normalizada=(38 / 136, top / 124, 98 / 136, (top + 10) / 124),
            confianca=0.91,
        )
        located = batch.locate(item)
        assert located is not None
        assert located[0] == index
        assert located[1].caixa_normalizada == pytest.approx((0.125, 0.25, 0.875, 0.75))
        assert located[1].texto == item.texto
        assert located[1].confianca == item.confianca


@pytest.mark.parametrize(
    "box",
    [(0, 0, 1, 1), (0.3, 0.42, 0.5, 0.55), (0.4, 0.3, 0.3, 0.35), (-0.1, 0.1, 0.5, 0.2)],
)
def test_text_crossing_crops_or_in_padding_is_rejected(
    box: tuple[float, float, float, float],
) -> None:
    batch = pack_ocr_rows((_raster(), _raster()))
    assert batch is not None
    assert batch.locate(TrechoTextoOcr(texto="CM2(1)", caixa_normalizada=box)) is None


def test_batch_limits_regions_before_allocating_a_large_raster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = pack_ocr_rows((_raster(),) * 100)
    assert batch is not None
    assert len(batch.boxes) == 48
    monkeypatch.setattr(batch_module, "MAXIMUM_BATCH_PIXELS", 12_000)
    limited = pack_ocr_rows((_raster(),) * 100)
    assert limited is not None
    assert len(limited.boxes) == 1
    monkeypatch.setattr(batch_module, "MAXIMUM_BATCH_PIXELS", 1)
    assert pack_ocr_rows((_raster(),)) is None
    assert pack_ocr_rows(()) is None


@pytest.mark.parametrize("changed_component", ["dpi", "page"])
def test_batch_rejects_mixed_page_or_resolution(changed_component: str) -> None:
    changed = (
        replace(_raster(), dpi=900)
        if changed_component == "dpi"
        else replace(_raster(), pagina_numero=2)
    )
    with pytest.raises(ValueError, match="mesma página"):
        pack_ocr_rows((_raster(), changed))


class _RowsOcr(CharacterizationOcr):
    def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
        self.pages.append(pagina)
        items = tuple(
            TrechoTextoOcr(
                texto="CM2(1)",
                caixa_normalizada=(38 / 136, top / 124, 98 / 136, (top + 10) / 124),
                confianca=0.91,
            )
            for top in (81, 33)
        )
        return (*items, items[0])


def test_batched_frames_keep_geometry_confidence_and_distinct_occurrences() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=100, height=100)
        page.draw_rect((10, 10, 18, 12), color=(0, 0.5, 0))
        page.draw_rect((25, 30, 33, 32), color=(0, 0.5, 0))
        frames = tuple(
            frame
            for drawing in page.get_drawings()
            if (frame := _operational_frame(page, drawing)) is not None
        )
        engine = _RowsOcr()
        candidates, processed = _extract_remaining_frame_labels(page, 1, engine, 720, frames)
        assert processed == len(candidates) == 2
        assert len(engine.pages) == 1
        assert candidates[0].chave_estavel != candidates[1].chave_estavel
        for candidate, expected in zip(candidates, ((0.26, 0.305), (0.11, 0.105)), strict=True):
            assert candidate.conteudo_bruto == "CM2(1)"
            assert candidate.geometria.tipo == TipoGeometria.POLIGONO
            first_point = candidate.geometria.pontos[0]
            assert (float(first_point.x), float(first_point.y)) == pytest.approx(expected)
            attributes = dict(candidate.atributos_extraidos)
            assert attributes["confianca"] == Decimal("0.91")
            assert attributes["motor_ocr"] == "tesseract-moldura-retificada-lote"


class _EmptyRowsOcr(CharacterizationOcr):
    def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
        self.pages.append(pagina)
        return ()


def test_frames_beyond_the_batch_budget_are_diagnosed() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=200, height=200)
        for index in range(49):
            x, y = 10 + (index % 7) * 20, 10 + (index // 7) * 20
            page.draw_rect((x, y, x + 8, y + 2), color=(0, 0.5, 0))
        engine = _EmptyRowsOcr()
        candidates, diagnostics = _linear_label_candidates(
            page, 1, engine, ConfiguracaoAnaliseDocumento()
        )
        assert candidates == ()
        assert len(engine.pages) == 1
        assert [item.codigo for item in diagnostics] == ["analise.ocr_cobertura_parcial"]
        assert "1 molduras" in diagnostics[0].mensagem


class _FailingRowsOcr(CharacterizationOcr):
    def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
        raise TimeoutError("local path must not escape")


def test_batch_failure_is_visible_and_does_not_expose_runtime_details() -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=100, height=100)
        page.draw_rect((10, 10, 18, 12), color=(0, 0.5, 0))
        candidates, diagnostics = _linear_label_candidates(
            page, 1, _FailingRowsOcr(), ConfiguracaoAnaliseDocumento()
        )
        assert candidates == ()
        assert diagnostics[0].codigo == "analise.ocr_rotulos_lineares_falhou"
        assert "local path" not in diagnostics[0].mensagem
