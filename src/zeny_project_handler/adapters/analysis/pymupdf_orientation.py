# mypy: disable-error-code="no-untyped-call"
"""Orientação cardinal sustentada pelos eixos do texto parcial de uma página densa."""

from __future__ import annotations

from collections import Counter
from math import atan2, degrees
from typing import Any

import pymupdf


def dominant_text_rotation(page: Any) -> int:
    """Retorne o giro anti-horário do raster; ausência ou conflito mantém a orientação."""
    weights: Counter[int] = Counter()
    total = 0
    try:
        blocks = page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    except Exception:
        # A camada textual danificada não pode impedir a recuperação pelo raster.
        # O extrator nativo registra sua falha separadamente.
        return 0
    for block in blocks["blocks"]:
        for line in block.get("lines", ()):
            weight = sum(len(span.get("text", "").strip()) for span in line["spans"])
            total += weight
            direction = pymupdf.Point(line["dir"])
            origin = pymupdf.Point(0, 0) * page.rotation_matrix
            endpoint = direction * page.rotation_matrix
            angle = degrees(atan2(endpoint.y - origin.y, endpoint.x - origin.x)) % 360
            cardinal = round(angle / 90) * 90
            if abs(angle - cardinal) <= 5:
                weights[cardinal % 360] += weight
    if not weights or total < 20:
        return 0
    rotation, count = weights.most_common(1)[0]
    return rotation if count / total >= 0.8 else 0


def unrotate_box(
    box: tuple[float, float, float, float], rotation: int
) -> tuple[float, float, float, float]:
    """Desfaça giro cardinal do raster antes de projetar os pixels na página."""
    left, top, right, bottom = box
    if rotation == 90:
        return 1 - bottom, left, 1 - top, right
    if rotation == 180:
        return 1 - right, 1 - bottom, 1 - left, 1 - top
    if rotation == 270:
        return top, 1 - right, bottom, 1 - left
    return box
