# mypy: disable-error-code="no-untyped-call"
import pymupdf
import pytest

from zeny_project_handler.adapters.analysis.pymupdf_ocr_page import OcrPage


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("dpi", [144, 450])
def test_reused_display_list_has_identical_pixels_and_origins_without_annotations(
    rotation: int,
    dpi: int,
) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=100, height=150)
        page.insert_text((10, 50), "OCR CONTROL", fontsize=7)
        page.draw_line((0, 0), (100, 150), color=(0, 0.5, 0), width=0.3)
        note = page.add_rect_annot((5, 5, 95, 145))
        note.set_colors(fill=(1, 0, 0))
        note.update()
        page.set_rotation(rotation)
        cached = OcrPage(page)
        for clip in (page.rect, pymupdf.Rect(3.13, 5.17, 62.31, 77.43)):
            expected = page.get_pixmap(
                dpi=dpi, colorspace=pymupdf.csRGB, alpha=False, clip=clip, annots=False
            )
            actual = cached.get_pixmap(
                dpi=dpi, colorspace=pymupdf.csRGB, alpha=False, clip=clip, annots=False
            )
            assert (actual.x, actual.y, actual.width, actual.height, actual.xres, actual.yres) == (
                expected.x,
                expected.y,
                expected.width,
                expected.height,
                expected.xres,
                expected.yres,
            )
            assert actual.samples == expected.samples
        assert cached._display_list is cached._display_list
        assert cached.get_drawings() is cached.get_drawings()
        with pytest.raises(ValueError, match="anotações"):
            cached.get_pixmap(
                dpi=dpi, colorspace=pymupdf.csRGB, alpha=False, clip=page.rect, annots=True
            )
