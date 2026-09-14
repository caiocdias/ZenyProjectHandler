# mypy: disable-error-code="no-untyped-call"
"""Reutilização local da lista de desenho durante os recortes OCR de uma página."""

from functools import cached_property
from typing import Any

import pymupdf


class OcrPage:
    def __init__(self, page: Any) -> None:
        self._page = page

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)

    @cached_property
    def _display_list(self) -> Any:
        return self._page.get_displaylist(annots=False)

    @cached_property
    def _drawings(self) -> list[dict[str, Any]]:
        return list(self._page.get_drawings())

    def get_drawings(self) -> list[dict[str, Any]]:
        return self._drawings

    def get_pixmap(
        self, *, dpi: int, colorspace: Any, alpha: bool, clip: Any, annots: bool = False
    ) -> Any:
        if annots:
            raise ValueError("O raster semântico não inclui anotações")
        pixmap = self._display_list.get_pixmap(
            matrix=pymupdf.Matrix(dpi / 72, dpi / 72),
            colorspace=colorspace,
            alpha=alpha,
            clip=clip,
        )
        pixmap.set_dpi(dpi, dpi)
        return pixmap
