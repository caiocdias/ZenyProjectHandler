# mypy: disable-error-code="no-untyped-call"
"""Controles públicos de texto parcial, orientação e bordas sem dados do projeto real."""

from pathlib import Path

import pymupdf


def create_partial_vector_pdf(path: Path, *, text_rotation: int = 90) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=240, height=300)
        page.insert_text(
            (120, 160), "CONTROLE PARCIAL DE ORIENTACAO", fontsize=5, rotate=text_rotation
        )
        for index in range(1001):
            x = 10 + index % 100
            y = 180 + index // 100
            page.draw_line((x, y), (x + 0.3, y + 0.3))
        page.draw_rect((160, 210, 190, 220), color=None, fill=(1, 0, 0))
        document.save(path)
