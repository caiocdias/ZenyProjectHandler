"""Concordância de contornos repetidos na própria página, sem dicionário de códigos."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, hypot, radians, sin, sqrt
from typing import Any

from .pymupdf_glyphs import GlyphRegion, _path_points


@dataclass(frozen=True)
class GlyphShape:
    commands: tuple[str, ...]
    points: tuple[tuple[float, float], ...]


def glyph_shape(drawing: dict[str, Any], region: GlyphRegion) -> GlyphShape:
    points = tuple(region.project(p) for item in drawing["items"] for p in _path_points(item))
    cx = sum(x for x, _ in points) / len(points)
    cy = sum(y for _, y in points) / len(points)
    scale = sqrt(sum((x - cx) ** 2 + (y - cy) ** 2 for x, y in points) / len(points))
    return GlyphShape(
        tuple(item[0] for item in drawing["items"]),
        tuple(((x - cx) / scale, (y - cy) / scale) for x, y in points) if scale else (),
    )


def shape_error(left: GlyphShape, right: GlyphShape) -> float:
    if left.commands != right.commands or not left.points or len(left.points) != len(right.points):
        return float("inf")
    pairs = tuple(zip(left.points, right.points, strict=True))
    dot = sum(x * u + y * v for (x, y), (u, v) in pairs)
    cross = sum(x * v - y * u for (x, y), (u, v) in pairs)
    angle = atan2(cross, dot)
    # Não permitir reflexão nem meia-volta (por exemplo, confundir 6 com 9).
    if abs(angle) > radians(15):
        return float("inf")
    c, s = cos(angle), sin(angle)
    return sqrt(
        sum(hypot(x * c - y * s - u, x * s + y * c - v) ** 2 for (x, y), (u, v) in pairs)
        / len(pairs)
    )


class GlyphConsensus:
    def __init__(self) -> None:
        self._templates: dict[tuple[str, ...], list[tuple[int, str, GlyphShape]]] = {}

    def add(self, region_id: int, region: GlyphRegion, text: str) -> None:
        # Só usar alinhamentos completos: um caminho por caractere, sem completar fragmentos.
        text = text.replace(" ", "")
        if len(text) != len(region.paths) or not text.isascii():
            return
        for drawing, char in zip(region.paths, text, strict=True):
            if not char.isalnum():
                continue
            shape = glyph_shape(drawing, region)
            self._templates.setdefault(shape.commands, []).append((region_id, char, shape))

    def recognize(self, region_id: int, region: GlyphRegion, offset: int) -> str | None:
        shape = glyph_shape(region.paths[offset], region)
        votes: dict[str, set[int]] = {}
        for source_id, char, template in self._templates.get(shape.commands, ()):
            if source_id != region_id and shape_error(shape, template) <= 0.12:
                votes.setdefault(char, set()).add(source_id)
        # Duas outras ocorrências independentes e nenhuma leitura conflitante.
        if len(votes) != 1:
            return None
        char, sources = next(iter(votes.items()))
        return char if len(sources) >= 2 else None
