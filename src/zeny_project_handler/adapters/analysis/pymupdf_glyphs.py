# mypy: disable-error-code="no-untyped-call"
"""Recortes de texto convertido em contornos, sem bordas ou traçados sobrepostos.

Os caminhos originais continuam sendo evidências. A camada temporária serve apenas
ao OCR: não consulta catálogo, não completa códigos e não modifica o documento.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, hypot, pi, radians, sin
from typing import Any

import pymupdf

from zeny_project_handler.ports.analysis import PaginaRasterOcr

MAXIMUM_GLYPH_GROUPS = 384
MAXIMUM_GLYPH_PIXELS = 8_000_000


def _path_points(item: Any) -> tuple[Any, ...]:
    if item[0] in {"l", "c"}:
        return tuple(item[1:])
    rect = item[1]
    if item[0] == "re":
        points = (rect.tl, rect.tr, rect.br, rect.bl)
        return tuple(reversed(points)) if len(item) > 2 and item[2] == -1 else points
    return rect.ul, rect.ur, rect.lr, rect.ll


def _is_glyph(drawing: dict[str, Any]) -> bool:
    rect = drawing["rect"]
    return (
        drawing["type"] == "f"
        and 0 < len(drawing["items"]) <= 256
        and 0.05 < rect.width < 6
        and 0.05 < rect.height < 6
        and all(item[0] in {"l", "c", "re", "qu"} for item in drawing["items"])
    )


def _adjacent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a, b = left["rect"], right["rect"]
    distance = hypot((a.x0 + a.x1 - b.x0 - b.x1) / 2, (a.y0 + a.y1 - b.y0 - b.y1) / 2)
    return bool(
        left["fill"] == right["fill"]
        and distance <= max(a.width, a.height, b.width, b.height) * 1.6
    )


def glyph_groups(page: Any) -> tuple[tuple[dict[str, Any], ...], ...]:
    """Agrupe caminhos consecutivos próximos; linhas, fotos e símbolos isolados separam runs."""
    groups: list[tuple[dict[str, Any], ...]] = []
    current: list[dict[str, Any]] = []
    for drawing in page.get_drawings():
        valid = _is_glyph(drawing)
        if current and (not valid or not _adjacent(current[-1], drawing)):
            if 2 <= len(current) <= 64:
                groups.append(tuple(current))
            current = []
        if valid:
            current.append(drawing)
    if 2 <= len(current) <= 64:
        groups.append(tuple(current))
    return tuple(groups)


def _axis_delta(left: float, right: float) -> float:
    return (left - right + pi / 4) % (pi / 2) - pi / 4


def _stroke_axis(group: tuple[dict[str, Any], ...], base: float) -> float:
    votes: list[tuple[float, float]] = []
    for drawing in group:
        for item in drawing["items"]:
            if item[0] != "l":
                continue
            start, end = item[1:]
            dx, dy = end.x - start.x, end.y - start.y
            length = hypot(dx, dy)
            if length > 0.3:
                votes.append((atan2(dy, dx) % (pi / 2), length))
    if not votes:
        return base
    peak = max(
        votes,
        key=lambda vote: sum(w for a, w in votes if abs(_axis_delta(a, vote[0])) < radians(3)),
    )[0]
    near = [(a, w) for a, w in votes if abs(_axis_delta(a, peak)) < radians(3)]
    axis = peak + sum(_axis_delta(a, peak) * w for a, w in near) / sum(w for _, w in near)
    axis += round((base - axis) / (pi / 2)) * (pi / 2)
    # Diagonais de N/A não podem girar a linha para outro eixo.
    return axis if abs(axis - base) < radians(10) else base


@dataclass(frozen=True)
class GlyphRegion:
    paths: tuple[dict[str, Any], ...]
    axis: tuple[float, float]
    bounds: tuple[float, float, float, float]

    def point(self, x: float, y: float) -> Any:
        ux, uy = self.axis
        return pymupdf.Point(x * ux - y * uy, x * uy + y * ux)

    def project(self, point: Any) -> tuple[float, float]:
        ux, uy = self.axis
        return point.x * ux + point.y * uy, -point.x * uy + point.y * ux

    def dimensions(self, dpi: int) -> tuple[int, int]:
        x0, y0, x1, y1 = self.bounds
        return int((x1 - x0) * dpi / 72 + 30) + 1, int((y1 - y0) * dpi / 72 + 30) + 1

    def render(self, page_number: int, dpi: int) -> PaginaRasterOcr:
        x0, y0, x1, y1 = self.bounds
        scale = dpi / 72

        def transform(point: Any) -> Any:
            x, y = self.project(point)
            return pymupdf.Point((x - x0) * scale + 15, (y - y0) * scale + 15)

        with pymupdf.open() as document:
            page = document.new_page(width=(x1 - x0) * scale + 30, height=(y1 - y0) * scale + 30)
            shape = page.new_shape()
            for drawing in self.paths:
                for item in drawing["items"]:
                    points = tuple(transform(point) for point in _path_points(item))
                    if item[0] == "l":
                        shape.draw_line(*points)
                    elif item[0] == "c":
                        shape.draw_bezier(*points)
                    else:
                        shape.draw_polyline((*points, points[0]))
                shape.finish(
                    fill=(0, 0, 0),
                    color=None,
                    even_odd=drawing["even_odd"],
                    closePath=drawing["closePath"],
                )
            shape.commit()
            pixmap = page.get_pixmap(alpha=False)
            return PaginaRasterOcr(
                pagina_numero=page_number,
                largura_pixels=pixmap.width,
                altura_pixels=pixmap.height,
                stride=pixmap.stride,
                dados_rgb=bytes(pixmap.samples),
                dpi=dpi,
            )


def glyph_region(group: tuple[dict[str, Any], ...]) -> GlyphRegion | None:
    first, last = group[0]["rect"], group[-1]["rect"]
    dx = (last.x0 + last.x1 - first.x0 - first.x1) / 2
    dy = (last.y0 + last.y1 - first.y0 - first.y1) / 2
    if hypot(dx, dy) < 0.5:
        return None
    angle = _stroke_axis(group, atan2(dy, dx))
    region = GlyphRegion(group, (cos(angle), sin(angle)), (0, 0, 0, 0))
    points = [
        region.project(point)
        for drawing in group
        for item in drawing["items"]
        for point in _path_points(item)
    ]
    if not points:
        return None
    x0, y0 = min(x for x, _ in points), min(y for _, y in points)
    x1, y1 = max(x for x, _ in points), max(y for _, y in points)
    if x1 - x0 < (y1 - y0) * 1.3:
        return None
    return GlyphRegion(group, region.axis, (x0, y0, x1, y1))
