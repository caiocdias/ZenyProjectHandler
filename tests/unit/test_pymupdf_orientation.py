# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageChops
from tests.e07_pdf_fixtures import create_partial_vector_pdf
from tests.unit.test_pymupdf_analyzer import FakeOcr, _request

from zeny_project_handler.adapters.analysis import JsonAnalysisCache, PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.analysis.pymupdf_ocr import (
    _deduplicate_tiled_candidates,
    _extract_ocr_region,
)
from zeny_project_handler.adapters.analysis.pymupdf_orientation import dominant_text_rotation
from zeny_project_handler.domain.enums import TipoEvidencia
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.analysis import PaginaRasterOcr, TrechoTextoOcr


class RedMarkerOcr(FakeOcr):
    def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
        self.pages.append(pagina)
        image = Image.frombytes(
            "RGB", (pagina.largura_pixels, pagina.altura_pixels), pagina.dados_rgb
        )
        red, green, _blue = image.split()
        bounds = ImageChops.subtract(red, green).getbbox()
        if bounds is None:
            return ()
        left, top, right, bottom = bounds
        return (
            TrechoTextoOcr(
                texto="MARCADOR SINTETICO",
                caixa_normalizada=(
                    left / image.width,
                    top / image.height,
                    right / image.width,
                    bottom / image.height,
                ),
                confianca=0.91,
            ),
        )


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_dense_partial_text_orients_raster_and_maps_occurrence(
    tmp_path: Path, rotation: int
) -> None:
    source = tmp_path / "partial.pdf"
    create_partial_vector_pdf(source, text_rotation=rotation)
    engine = RedMarkerOcr()
    result = PyMuPdfDocumentAnalyzer(motor_ocr=engine).analisar(_request(source))
    found = [item for item in result.evidencias if item.tipo is TipoEvidencia.OCR]
    assert len(found) == 1  # marcador está também na sobreposição entre recortes
    assert len(engine.pages) == 9
    item = found[0]
    bounds = item.geometria.pontos
    assert float(bounds[0].x) == pytest.approx(160 / 240, abs=0.001)
    assert float(bounds[0].y) == pytest.approx(210 / 300, abs=0.001)
    assert float(bounds[1].x) == pytest.approx(190 / 240, abs=0.001)
    assert float(bounds[1].y) == pytest.approx(220 / 300, abs=0.001)
    attributes = dict(item.atributos_extraidos)
    assert attributes["rotacao_raster_graus"] == (-rotation) % 360
    assert attributes["confianca"] == Decimal("0.91")
    assert attributes["assinatura_capacidade_ocr"] == engine._capability.assinatura()
    assert not result.diagnosticos


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_crop_pixel_rounding_and_rotation_keep_marker_geometry(
    tmp_path: Path, rotation: int
) -> None:
    source = tmp_path / "crop.pdf"
    create_partial_vector_pdf(source)
    with pymupdf.open(source) as document:
        candidates = _extract_ocr_region(
            document[0],
            1,
            RedMarkerOcr(),
            450,
            bounds=(Decimal("0.6413"), Decimal("0.6801"), Decimal("0.8127"), Decimal("0.7503")),
            stable_suffix="borda",
            rotation_degrees=rotation,
        )
    assert len(candidates) == 1
    first, second = candidates[0].geometria.pontos
    assert float(first.x) == pytest.approx(160 / 240, abs=0.001)
    assert float(first.y) == pytest.approx(210 / 300, abs=0.001)
    assert float(second.x) == pytest.approx(190 / 240, abs=0.001)
    assert float(second.y) == pytest.approx(220 / 300, abs=0.001)


def test_orientation_requires_sufficient_consistent_text_and_honors_page_rotation() -> None:
    with pymupdf.open() as document:
        page = document.new_page()
        assert dominant_text_rotation(page) == 0
        page.insert_text((100, 100), "P7", rotate=90)
        assert dominant_text_rotation(page) == 0
        page.insert_text((200, 200), "ROTACAO PARCIAL CONFIRMADA", rotate=90)
        assert dominant_text_rotation(page) == 270
        page.set_rotation(90)
        assert dominant_text_rotation(page) == 0
        page.set_rotation(0)
        page.insert_text((200, 250), "CONFLITO DE ORIENTACAO NATIVA", rotate=0)
        assert dominant_text_rotation(page) == 0


def test_previous_extractor_cache_is_not_reused(tmp_path: Path) -> None:
    source = tmp_path / "partial.pdf"
    create_partial_vector_pdf(source)
    request = _request(source)
    cache = JsonAnalysisCache(tmp_path / "cache")
    previous = PyMuPdfDocumentAnalyzer(motor_ocr=RedMarkerOcr(), cache=cache)
    previous.versao = "1.11.0"
    previous.analisar(request)
    current = PyMuPdfDocumentAnalyzer(motor_ocr=RedMarkerOcr(), cache=cache)
    assert previous.assinatura_capacidade != current.assinatura_capacidade
    assert not current.analisar(request).cache_utilizado
    assert current.analisar(request).cache_utilizado


def test_same_text_in_adjacent_distinct_occurrences_is_preserved(tmp_path: Path) -> None:
    source = tmp_path / "occurrences.pdf"
    create_partial_vector_pdf(source)
    with pymupdf.open(source) as document:
        first = _extract_ocr_region(
            document[0],
            1,
            RedMarkerOcr(),
            450,
            bounds=(Decimal(0), Decimal(0), Decimal(1), Decimal(1)),
            stable_suffix="ocorrencia",
        )[0]
    first = replace(
        first,
        geometria=replace(
            first.geometria,
            pontos=(
                PontoNormalizado(Decimal("0.1"), Decimal("0.1")),
                PontoNormalizado(Decimal("0.106"), Decimal("0.11")),
            ),
        ),
    )
    second = replace(
        first,
        chave_estavel="outra",
        geometria=replace(
            first.geometria,
            pontos=(
                PontoNormalizado(Decimal("0.11"), Decimal("0.1")),
                PontoNormalizado(Decimal("0.116"), Decimal("0.11")),
            ),
        ),
    )
    assert _deduplicate_tiled_candidates((first, second, first)) == (first, second)


@pytest.mark.parametrize("page_rotation", [90, 180, 270])
def test_declared_page_rotation_and_crop_remain_in_display_coordinates(
    tmp_path: Path, page_rotation: int
) -> None:
    source = tmp_path / "rotated-page.pdf"
    create_partial_vector_pdf(source)
    with pymupdf.open(source) as document:
        page = document[0]
        page.set_rotation(page_rotation)
        marker = pymupdf.Rect(160, 210, 190, 220) * page.rotation_matrix
        expected = (
            marker.x0 / page.rect.width,
            marker.y0 / page.rect.height,
            marker.x1 / page.rect.width,
            marker.y1 / page.rect.height,
        )
        left, top, right, bottom = expected
        candidate = _extract_ocr_region(
            page,
            1,
            RedMarkerOcr(),
            450,
            bounds=(
                Decimal(str(left - 0.03)),
                Decimal(str(top - 0.03)),
                Decimal(str(right + 0.03)),
                Decimal(str(bottom + 0.03)),
            ),
            stable_suffix="pagina-girada",
            rotation_degrees=dominant_text_rotation(page),
        )[0]
        first, last = candidate.geometria.pontos
        assert tuple(float(v) for v in (first.x, first.y, last.x, last.y)) == pytest.approx(
            expected, abs=0.001
        )


def test_damaged_native_text_does_not_prevent_dense_raster_ocr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "damaged-text.pdf"
    create_partial_vector_pdf(source)
    request = _request(source)

    def fail_text(*_args: object, **_kwargs: object) -> object:
        raise ValueError("synthetic malformed text layer")

    monkeypatch.setattr(pymupdf.Page, "get_text", fail_text)
    engine = RedMarkerOcr()
    result = PyMuPdfDocumentAnalyzer(motor_ocr=engine).analisar(request)
    assert len(engine.pages) == 9
    assert len([item for item in result.evidencias if item.tipo is TipoEvidencia.OCR]) == 1
    assert [item.codigo for item in result.diagnosticos] == ["analise.texto_falhou"]
