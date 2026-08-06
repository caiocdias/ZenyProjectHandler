# mypy: disable-error-code="no-untyped-call"
"""Construtores pequenos de PDFs determinísticos usados pelos testes."""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from zeny_project_handler.ports.pdf import OrcamentoRenderizacaoPdf

_XREF_PATTERN = re.compile(r"(?<!\d)(\d+)\s+\d+\s+R")
TEST_RENDER_BUDGET = OrcamentoRenderizacaoPdf(
    limite_pixels=8_000_000,
    limite_bytes=64 * 1024 * 1024,
)


def create_feature_pdf(path: Path) -> Path:
    document = pymupdf.open()
    source_form = pymupdf.open()
    try:
        form_page = source_form.new_page(width=40, height=40)
        form_page.draw_circle((20, 20), 12, color=(0, 0, 1), fill=(0, 0, 1))

        page = document.new_page(width=200, height=100)
        optional_group = document.add_ocg("Camada de teste")
        page.draw_rect(
            pymupdf.Rect(10, 10, 80, 50),
            color=(1, 0, 0),
            fill=(1, 0, 0),
            oc=optional_group,
        )
        page.insert_text((15, 75), "POSTE P1")
        page.insert_image(pymupdf.Rect(90, 10, 110, 30), stream=_red_pixel_png())
        page.add_stamp_annot(pymupdf.Rect(120, 10, 170, 40), stamp=0)
        page.show_pdf_page(pymupdf.Rect(120, 50, 160, 90), source_form, 0)

        rotated = document.new_page(width=200, height=100)
        rotated.insert_text((30, 50), "PAGINA GIRADA")
        rotated.set_cropbox(pymupdf.Rect(20, 10, 180, 90))
        rotated.set_rotation(90)

        scanned = document.new_page(width=120, height=120)
        scanned.insert_image(scanned.rect, stream=_red_pixel_png())
        document.save(path)
    finally:
        source_form.close()
        document.close()
    return path


def create_golden_pdf(path: Path) -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page(width=72, height=48)
        page.draw_rect(page.rect, color=(1, 1, 1), fill=(1, 1, 1))
        page.draw_rect(pymupdf.Rect(18, 12, 54, 36), color=(1, 0, 0), fill=(1, 0, 0))
        document.save(path)
    finally:
        document.close()
    return path


def create_clip_rotation_golden_pdf(path: Path) -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page(width=80, height=60)
        page.draw_rect(pymupdf.Rect(0, 0, 40, 30), color=(1, 0, 0), fill=(1, 0, 0))
        page.draw_rect(pymupdf.Rect(40, 0, 80, 30), color=(0, 1, 0), fill=(0, 1, 0))
        page.draw_rect(pymupdf.Rect(0, 30, 40, 60), color=(0, 0, 1), fill=(0, 0, 1))
        page.draw_rect(pymupdf.Rect(40, 30, 80, 60), color=(1, 1, 0), fill=(1, 1, 0))
        document.save(path)
    finally:
        document.close()
    return path


def create_large_format_pdf(path: Path, *, width_points: float, height_points: float) -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page(width=width_points, height=height_points)
        page.insert_text((24, 36), "PRANCHA SINTETICA")
        document.save(path)
    finally:
        document.close()
    return path


def create_catalog_pdf(path: Path, code: str) -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page(width=240, height=160)
        page.insert_text((20, 25), "P1")
        page.insert_text((20, 40), code)
        document.save(path)
    finally:
        document.close()
    return path


def create_mixed_raster_text_pdf(path: Path) -> Path:
    """Página com texto nativo suficiente e uma imagem que ainda exige OCR."""
    document = pymupdf.open()
    try:
        page = document.new_page(width=120, height=120)
        page.insert_image(page.rect, stream=_red_pixel_png())
        page.insert_text((10, 20), "TEXTO NATIVO SUFICIENTE NA MARGEM")
        document.save(path)
    finally:
        document.close()
    return path


def create_small_raster_region_pdf(path: Path) -> Path:
    """Página híbrida com uma pequena região raster que precisa de OCR localizado."""
    document = pymupdf.open()
    try:
        page = document.new_page(width=200, height=200)
        page.insert_text((10, 20), "TEXTO NATIVO SUFICIENTE NO CARIMBO DO PROJETO")
        page.insert_image(
            pymupdf.Rect(140, 120, 180, 160),
            stream=_scanned_text_png(),
        )
        document.save(path)
    finally:
        document.close()
    return path


def create_dense_vector_text_pdf(path: Path) -> Path:
    """Página CAD sintética em que glifos podem ter sido convertidos em muitos caminhos."""
    document = pymupdf.open()
    try:
        page = document.new_page(width=120, height=120)
        page.insert_text((10, 20), "TEXTO NATIVO SUFICIENTE NO CARIMBO")
        shape = page.new_shape()
        for index in range(1000):
            coordinate = float(index % 100) + 10
            row = float(index // 100) + 40
            shape.draw_line((coordinate, row), (coordinate + 0.2, row + 0.2))
            shape.finish()
        shape.commit()
        document.save(path)
    finally:
        document.close()
    return path


def create_analysis_pdf(path: Path) -> Path:
    """PDF rico, incluindo imagem em appearance stream e Form XObject aninhado."""
    document = pymupdf.open()
    nested = pymupdf.open()
    try:
        nested_page = nested.new_page(width=40, height=40)
        nested_page.draw_circle((20, 20), 12, color=(0, 0, 1), fill=(0, 0, 1))
        nested_page.insert_image(pymupdf.Rect(12, 12, 28, 28), stream=_red_pixel_png())

        page = document.new_page(width=240, height=160)
        page.insert_text((12, 25), "POSTE P1", fontsize=10)
        page.insert_text((105, 40), "P2", fontsize=10)
        page.insert_text((25, 135), "MT", fontsize=9, rotate=90)
        page.draw_line((10, 40), (90, 40), color=(0, 1, 0), width=2)
        page.draw_bezier((10, 55), (30, 35), (60, 75), (90, 55), color=(0, 0, 1))
        page.draw_polyline([(10, 70), (50, 90), (90, 70)], color=(1, 0, 0), closePath=True)
        image_xref = page.insert_image(pymupdf.Rect(105, 10, 125, 30), stream=_red_pixel_png())
        stamp = page.add_stamp_annot(pymupdf.Rect(135, 10, 205, 40), stamp=0)
        page.add_freetext_annot(pymupdf.Rect(105, 45, 180, 65), "ESTRUTURA N1")
        page.add_rect_annot(pymupdf.Rect(105, 70, 150, 100))
        note = page.add_text_annot((205, 85), "NOTA COM POPUP")
        note.set_popup(pymupdf.Rect(155, 100, 230, 145))
        page.show_pdf_page(pymupdf.Rect(10, 105, 50, 145), nested, 0)

        appearance_match = _XREF_PATTERN.search(str(document.xref_get_key(stamp.xref, "AP")[1]))
        assert appearance_match is not None
        appearance_xref = int(appearance_match.group(1))
        document.xref_set_key(
            appearance_xref, "Resources/XObject/ImAppearance", f"{image_xref} 0 R"
        )
        original_stream = bytes(document.xref_stream(appearance_xref) or b"")
        document.update_stream(
            appearance_xref,
            original_stream + b"\nq 12 0 0 12 2 2 cm /ImAppearance Do Q\n",
        )

        scanned = document.new_page(width=120, height=120)
        scanned.insert_image(scanned.rect, stream=_red_pixel_png())
        document.save(path)
    finally:
        nested.close()
        document.close()
    return path


def create_protected_pdf(path: Path, password: str = "senha") -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page(width=100, height=100)
        page.insert_text((10, 50), "PROTEGIDO")
        document.save(
            path,
            encryption=int(pymupdf.PDF_ENCRYPT_AES_256),  # type: ignore[attr-defined]
            owner_pw="proprietario",
            user_pw=password,
        )
    finally:
        document.close()
    return path


def _red_pixel_png() -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 2, 2), False)
    pixmap.clear_with(0xFF0000)
    return bytes(pixmap.tobytes("png"))


def _scanned_text_png() -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page(width=100, height=50)
        page.insert_text((5, 25), "280653/7683008", fontsize=8)
        return bytes(page.get_pixmap(dpi=144, alpha=False).tobytes("png"))
    finally:
        document.close()
