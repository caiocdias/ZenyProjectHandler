# mypy: disable-error-code="no-untyped-call"
"""Observações vetoriais de transformadores, independentes de literais.

O inventário E01 contém estados/nomes que compartilham desenho. Este método
identifica famílias gráficas; ``referencias_possiveis`` nunca significa que um
ID de referência ou a quantidade física foi confirmado.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pymupdf

from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import (
    AlternativaClasseSimbolo,
    CoberturaMetodoSimbolos,
    FonteObservacaoSimbolo,
    GeometriaObservacaoSimbolo,
    ObservacaoSimbolo,
    PerfilMetodoSimbolos,
    PrimitivaObservadaSimbolo,
    ResultadoMetodoSimbolos,
    TransformacaoSimbolo,
)
from zeny_project_handler.domain.values import PontoNormalizado

from .pymupdf_support import _box_geometry
from .pymupdf_symbols import _base_drawings, _drawing_points, _inherit_clipping

_VERSION = "e05-transformadores-v4"
_SOURCE = "cemig-eo-r3:it-eo-008:f02:inventario-v1"
_NEGATIVE_WORDS = frozenset({"POSTE", "ESTAI", "ATERRAMENTO", "PARA-RAIOS", "PARARRAIOS"})
_LEGEND_WORDS = frozenset({"LEGENDA", "SIMBOLOGIA"})
_Point = tuple[float, float]
_Source = tuple[int, int]


@dataclass(frozen=True, slots=True)
class _Line:
    start: _Point
    end: _Point
    source: _Source
    layer: str
    color: tuple[float, ...] | None

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)


@dataclass(frozen=True, slots=True)
class _Round:
    bounds: pymupdf.Rect
    sources: tuple[_Source, ...]
    layer: str
    color: tuple[float, ...] | None
    kind: str
    direction: float = 0.0
    curvature: float = 0.0
    endpoints: tuple[_Point, _Point] | None = None
    fill: tuple[float, ...] | None = None

    @property
    def center(self) -> _Point:
        return ((self.bounds.x0 + self.bounds.x1) / 2, (self.bounds.y0 + self.bounds.y1) / 2)

    @property
    def size(self) -> float:
        return max(float(self.bounds.width), float(self.bounds.height))


@dataclass(frozen=True, slots=True)
class _Shape:
    variant: str
    family: str
    class_code: str
    sources: tuple[_Source, ...]
    components: tuple[tuple[str, tuple[_Source, ...]], ...]
    bounds: pymupdf.Rect
    references: tuple[str, ...]
    possible_families: tuple[str, ...] = ()
    core_area: float = 0.0


def perfil_transformadores() -> PerfilMetodoSimbolos:
    """Perfil E03 separado do método legado; seus scores não são probabilidades."""
    return PerfilMetodoSimbolos(
        metodo_id="pymupdf-transformers",
        versao=_VERSION,
        familia="heuristica-geometrica-vetorial-transformadores",
        dominio_aplicacao="Traçados vetoriais da base; famílias gráficas E01 F02 §§18,24,25",
        classes_suportadas=("TRANSFORMADOR", "CONJUNTO_EO"),
        camadas_suportadas=("base",),
        fontes_compartilhadas=("pymupdf:get_drawings:extended", "normalizador-vetorial-e04"),
        perfil_referencia=_SOURCE,
        parametros=(
            ("pymupdf_version", str(pymupdf.VersionBind)),
            ("assinaturas", "triangulo,laços-pareados,semicirculos,enrolamentos"),
            ("score_bruto", None),
            ("cardinalidade", "indeterminada"),
        ),
    )


def _rgb(value: object) -> tuple[float, ...] | None:
    if not isinstance(value, (tuple, list)):
        return None
    try:
        return tuple(float(channel) for channel in value)
    except (TypeError, ValueError):
        return None


def _colored(color: tuple[float, ...] | None, name: str) -> bool:
    if color is None or len(color) < 3:
        return False
    red, green, blue = color[:3]
    if name == "cyan":
        return blue > 0.35 and green > 0.3 and red < min(blue, green) * 0.75
    if name == "purple":
        return red > 0.2 and blue > 0.2 and green < min(red, blue) * 0.8
    return red > 0.45 and red > green * 1.7 and red > blue * 1.7


def _bounds(points: tuple[_Point, ...]) -> pymupdf.Rect:
    return pymupdf.Rect(
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def _bezier_point(points: tuple[_Point, ...], t: float) -> _Point:
    start, first, second, end = points
    return (
        (1 - t) ** 3 * start[0]
        + 3 * (1 - t) ** 2 * t * first[0]
        + 3 * (1 - t) * t**2 * second[0]
        + t**3 * end[0],
        (1 - t) ** 3 * start[1]
        + 3 * (1 - t) ** 2 * t * first[1]
        + 3 * (1 - t) * t**2 * second[1]
        + t**3 * end[1],
    )


def _extract_parts(
    drawings: tuple[dict[str, Any], ...],
) -> tuple[tuple[_Line, ...], tuple[_Round, ...]]:
    lines: list[_Line] = []
    rounds: list[_Round] = []
    for drawing_index, drawing in enumerate(drawings):
        items = tuple(drawing.get("items") or ())
        if not items:
            continue
        layer = str(drawing.get("layer") or "")
        color = _rgb(drawing.get("color") or drawing.get("fill"))
        fill = _rgb(drawing.get("fill"))
        clip = drawing.get("scissor")
        curves: list[tuple[int, tuple[_Point, ...]]] = []
        for item_index, item in enumerate(items):
            operation = item[0]
            if operation == "l":
                start, end = ((float(point.x), float(point.y)) for point in item[1:3])
                if math.dist(start, end) > 0.01:
                    lines.append(_Line(start, end, (drawing_index, item_index), layer, color))
            elif operation == "c":
                points = tuple((float(point.x), float(point.y)) for point in item[1:5])
                if len(points) == 4:
                    curves.append((item_index, points))
            elif operation == "re":
                # A rectangle is context/negative geometry, never a triangular edge.
                continue
        if not curves:
            continue
        if len(curves) >= 3 and not any(item[0] == "l" for item in items):
            sampled = tuple(
                _bezier_point(group, t) for _, group in curves for t in (0, 0.25, 0.5, 0.75, 1)
            )
            bounds = _bounds(sampled)
            ratio = bounds.width / max(bounds.height, 0.01)
            endpoints = [curves[0][1][0], curves[-1][1][-1]]
            center = _center(bounds)
            radii = tuple(math.dist(point, center) for point in sampled)
            circular = min(radii) >= max(radii) * 0.82
            angular_bins = {
                int(
                    (math.atan2(point[1] - center[1], point[0] - center[0]) + math.pi) * 4 / math.pi
                )
                % 8
                for point in sampled
            }
            if (
                0.75 <= ratio <= 1.3
                and bounds.width >= 2
                and math.dist(*endpoints) <= bounds.width * 0.08
                and circular
                and len(angular_bins) >= 7
                and (clip is None or pymupdf.Rect(clip).contains(bounds))
            ):
                rounds.append(
                    _Round(
                        bounds,
                        tuple((drawing_index, index) for index, _ in curves),
                        layer,
                        color,
                        "loop",
                        fill=fill,
                    )
                )
                continue
        for item_index, points in curves:
            start, first, second, end = points
            chord = math.dist(start, end)
            if chord < 2:
                continue
            midpoint = tuple((start[i] + 3 * first[i] + 3 * second[i] + end[i]) / 8 for i in (0, 1))
            bulge = (
                abs(
                    (end[0] - start[0]) * (midpoint[1] - start[1])
                    - (end[1] - start[1]) * (midpoint[0] - start[0])
                )
                / chord
            )
            if not 0.12 <= bulge / chord <= 0.8:
                continue
            sampled = tuple(
                _bezier_point((start, first, second, end), t) for t in (0, 0.25, 0.5, 0.75, 1)
            )
            bounds = _bounds(sampled)
            if clip is not None and not pymupdf.Rect(clip).contains(bounds):
                continue
            rounds.append(
                _Round(
                    bounds,
                    ((drawing_index, item_index),),
                    layer,
                    color,
                    "arc",
                    math.atan2(end[1] - start[1], end[0] - start[0]) % math.pi,
                    (
                        (end[0] - start[0]) * (midpoint[1] - start[1])
                        - (end[1] - start[1]) * (midpoint[0] - start[0])
                    )
                    / (chord * chord),
                    (start, end),
                    fill,
                )
            )
    return tuple(lines), tuple(rounds)


def _near_point(first: _Point, second: _Point, scale: float) -> bool:
    return math.dist(first, second) <= max(0.15, min(1.5, scale * 0.045))


def _triangle_axis(
    vertices: tuple[_Point, _Point, _Point],
    core: tuple[_Source, ...],
    lines: tuple[_Line, ...],
    layer: str,
) -> _Source | None:
    """Require the median stroke of the equipment pictogram, not a bare arrow."""
    for index, apex in enumerate(vertices):
        base = tuple(point for position, point in enumerate(vertices) if position != index)
        midpoint = ((base[0][0] + base[1][0]) / 2, (base[0][1] + base[1][1]) / 2)
        span = math.dist(apex, midpoint)
        tolerance = max(0.4, min(2.0, span * 0.08))
        for line in lines:
            if line.source in core or line.layer != layer:
                continue
            if not 0.7 * span <= line.length <= 1.3 * span:
                continue
            if (
                math.dist(line.start, apex) <= tolerance
                and math.dist(line.end, midpoint) <= tolerance
            ) or (
                math.dist(line.end, apex) <= tolerance
                and math.dist(line.start, midpoint) <= tolerance
            ):
                return line.source
    return None


def _triangle_shapes(
    lines: tuple[_Line, ...], rounds: tuple[_Round, ...], drawings: tuple[dict[str, Any], ...]
) -> tuple[_Shape, ...]:
    # Endpoint buckets avoid scanning every drawing against every other drawing.
    buckets: dict[tuple[int, int], list[int]] = {}
    for index, line in enumerate(lines):
        if not 3 <= line.length <= 150:
            continue
        for point in (line.start, line.end):
            buckets.setdefault((round(point[0] / 2), round(point[1] / 2)), []).append(index)

    def adjacent(point: _Point) -> set[int]:
        x, y = round(point[0] / 2), round(point[1] / 2)
        return {
            index
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for index in buckets.get((x + dx, y + dy), ())
        }

    found: dict[tuple[_Source, ...], _Shape] = {}
    for first_index, first in enumerate(lines):
        if not 4 <= first.length <= 150:
            continue
        for vertex, opposite in ((first.start, first.end), (first.end, first.start)):
            for second_index in adjacent(vertex):
                if second_index == first_index:
                    continue
                second = lines[second_index]
                if second.layer != first.layer or not 0.45 <= second.length / first.length <= 2.2:
                    continue
                if _near_point(vertex, second.start, min(first.length, second.length)):
                    other = second.end
                elif _near_point(vertex, second.end, min(first.length, second.length)):
                    other = second.start
                else:
                    continue
                for third_index in adjacent(opposite) & adjacent(other):
                    if third_index in (first_index, second_index):
                        continue
                    third = lines[third_index]
                    if third.layer != first.layer:
                        continue
                    if not (
                        (
                            _near_point(opposite, third.start, first.length)
                            and _near_point(other, third.end, first.length)
                        )
                        or (
                            _near_point(opposite, third.end, first.length)
                            and _near_point(other, third.start, first.length)
                        )
                    ):
                        continue
                    if not 0.45 <= third.length / first.length <= 2.2:
                        continue
                    area2 = abs(
                        (opposite[0] - vertex[0]) * (other[1] - vertex[1])
                        - (opposite[1] - vertex[1]) * (other[0] - vertex[0])
                    )
                    if area2 < first.length**2 * 0.3:
                        continue
                    triangle = (first, second, third)
                    core = tuple(sorted(line.source for line in triangle))
                    if core in found:
                        continue
                    axis_source = _triangle_axis(
                        (vertex, opposite, other), core, lines, first.layer
                    )
                    if axis_source is None:
                        continue
                    bounds = _bounds((vertex, opposite, other))
                    symbol_points = [vertex, opposite, other]
                    size = max(bounds.width, bounds.height)
                    # A triangle's enclosing circle/X is a modifier, not another asset.
                    markers: list[tuple[str, tuple[_Source, ...]]] = []
                    circles = [
                        item
                        for item in rounds
                        if item.kind == "loop"
                        and item.layer == first.layer
                        and 1.05 <= item.size / size <= 2.7
                        and item.bounds.contains(bounds)
                    ]
                    if circles:
                        circle = min(circles, key=lambda item: item.size)
                        markers.append(("envoltoria", circle.sources))
                        symbol_points.extend((tuple(circle.bounds.tl), tuple(circle.bounds.br)))
                    cross_lines = [
                        item
                        for item in lines
                        if item.source not in core
                        and item.layer == first.layer
                        and _colored(item.color, "red")
                        and bounds.intersects(_bounds((item.start, item.end)))
                        and 0.4 <= item.length / size <= 2.5
                    ]
                    if len(cross_lines) >= 2:
                        markers.append(
                            ("x_vermelho", tuple(line.source for line in cross_lines[:2]))
                        )
                        symbol_points.extend(
                            point for line in cross_lines[:2] for point in (line.start, line.end)
                        )
                    cyan = any(
                        _colored(_rgb(drawing.get("fill") or drawing.get("color")), "cyan")
                        and bounds.intersects(pymupdf.Rect(drawing.get("rect") or bounds))
                        for drawing in drawings
                    )
                    purple = any(_colored(line.color, "purple") for line in triangle)
                    variant = (
                        "triangulo_roxo"
                        if purple
                        else "triangulo_meio_ciano"
                        if cyan
                        else "triangulo"
                    )
                    components = [
                        ("contorno_triangular", core),
                        ("eixo_interno", (axis_source,)),
                        *markers,
                    ]
                    if cyan:
                        fill_sources = tuple(
                            (index, item_index)
                            for index, drawing in enumerate(drawings)
                            if _colored(_rgb(drawing.get("fill")), "cyan")
                            and bounds.intersects(pymupdf.Rect(drawing.get("rect") or bounds))
                            for item_index, _ in enumerate(drawing.get("items") or ())
                        )
                        if fill_sources:
                            components.append(("preenchimento_ciano", fill_sources))
                    sources = tuple(sorted({source for _, refs in components for source in refs}))
                    ids: tuple[int, ...] = tuple(
                        range(16, 19) if purple else range(1, 7) if cyan else range(7, 16)
                    )
                    if markers:
                        marker = (
                            "x_vermelho"
                            if any(role == "x_vermelho" for role, _ in markers)
                            else markers[0][0]
                        )
                        target = 2 if marker == "x_vermelho" else 3
                        ids = tuple(index for index in ids if (index - 1) % 3 + 1 == target)
                    references = tuple(f"cemig-eo-r3-s18-v{index:03}" for index in ids)
                    found[core] = _Shape(
                        variant,
                        "family-f02-18",
                        "TRANSFORMADOR",
                        sources,
                        tuple(components),
                        _bounds(tuple(symbol_points)),
                        references,
                        core_area=float(bounds.width * bounds.height),
                    )
    # Multiple detection paths may choose different physical strokes of one outline.
    chosen: list[_Shape] = []
    for shape in sorted(
        found.values(),
        key=lambda item: (
            -item.core_area,
            item.bounds.x0,
            item.bounds.y0,
            item.sources,
        ),
    ):
        if any(
            other.bounds.contains(shape.bounds)
            or (
                math.dist(_center(shape.bounds), _center(other.bounds))
                <= max(shape.bounds.width, shape.bounds.height) * 0.08
                and abs(shape.bounds.width - other.bounds.width)
                <= max(shape.bounds.width, other.bounds.width) * 0.08
                and abs(shape.bounds.height - other.bounds.height)
                <= max(shape.bounds.height, other.bounds.height) * 0.08
            )
            for other in chosen
        ):
            continue
        chosen.append(shape)
    radial_sources: set[tuple[_Source, ...]] = set()
    for loop in rounds:
        if loop.kind != "loop":
            continue
        inside = tuple(
            shape
            for shape in chosen
            if loop.bounds.contains(pymupdf.Point(_center(shape.bounds)))
            and loop.size >= max(shape.bounds.width, shape.bounds.height) * 1.4
        )
        if len(inside) >= 3:
            radial_sources.update(shape.sources for shape in inside)
    return tuple(
        sorted(
            (shape for shape in chosen if shape.sources not in radial_sources),
            key=lambda item: (item.bounds.y0, item.bounds.x0),
        )
    )


def _center(bounds: pymupdf.Rect) -> _Point:
    return ((bounds.x0 + bounds.x1) / 2, (bounds.y0 + bounds.y1) / 2)


def _sector_shapes(
    rounds: tuple[_Round, ...],
    lines: tuple[_Line, ...],
    drawings: tuple[dict[str, Any], ...],
    used: set[_Source],
) -> tuple[_Shape, ...]:
    """Closed outline plus an internal filled cyan circular sector."""
    shapes: list[_Shape] = []
    for loop in rounds:
        if loop.kind != "loop" or set(loop.sources) & used or _colored(loop.color, "red"):
            continue
        center = loop.center
        for drawing_index, drawing in enumerate(drawings):
            if not _colored(_rgb(drawing.get("fill")), "cyan"):
                continue
            items = tuple(drawing.get("items") or ())
            if not any(item[0] == "c" for item in items) or not any(
                item[0] == "l" for item in items
            ):
                continue
            points = _drawing_points(items)
            if not points:
                continue
            fill_bounds = _bounds(points)
            if not loop.bounds.contains(fill_bounds):
                continue
            ratio = (fill_bounds.width * fill_bounds.height) / max(
                loop.bounds.width * loop.bounds.height, 0.01
            )
            if not 0.12 <= ratio <= 0.8:
                continue
            radial = any(
                item[0] == "l"
                and any(
                    math.dist((point.x, point.y), center) <= loop.size * 0.1 for point in item[1:3]
                )
                for item in items
            )
            if not radial:
                continue
            fill_sources = tuple((drawing_index, index) for index in range(len(items)))
            divider_sources = tuple(
                line.source
                for line in lines
                if line.source[0] != drawing_index
                and line.layer == loop.layer
                and 0.7 * loop.size <= line.length <= 1.3 * loop.size
                and math.dist(_center(_bounds((line.start, line.end))), center) <= loop.size * 0.1
            )
            sources = tuple(sorted({*loop.sources, *fill_sources, *divider_sources}))
            components: tuple[tuple[str, tuple[_Source, ...]], ...] = (
                ("contorno_circular", loop.sources),
                ("setor_ciano", fill_sources),
            )
            if divider_sources:
                components += (("diametro", divider_sources),)
            shapes.append(
                _Shape(
                    "circulo_setor_ciano",
                    "family-f02-18",
                    "TRANSFORMADOR",
                    sources,
                    components,
                    loop.bounds,
                    tuple(f"cemig-eo-r3-s18-v{index:03}" for index in range(1, 7)),
                )
            )
            used.update(sources)
            break
    return tuple(shapes)


def _angle_delta(first: float, second: float) -> float:
    delta = abs(first - second) % math.pi
    return min(delta, math.pi - delta)


def _line_angle(line: _Line) -> float:
    return math.atan2(line.end[1] - line.start[1], line.end[0] - line.start[0]) % math.pi


def _arc_pairs(members: tuple[_Round, ...]) -> tuple[tuple[_Round, _Round], ...]:
    """Pair opposite winding lobes on one chord; nearby arbitrary arcs do not suffice."""
    pending = list(members)
    pairs: list[tuple[_Round, _Round]] = []
    if not pending:
        return ()
    axis = math.cos(members[0].direction), math.sin(members[0].direction)
    while pending:
        first = pending.pop(0)
        candidates = []
        for second in pending:
            delta = second.center[0] - first.center[0], second.center[1] - first.center[1]
            along = abs(delta[0] * axis[0] + delta[1] * axis[1])
            if (
                first.curvature * second.curvature < 0
                and along <= min(first.size, second.size) * 0.28
                and math.dist(first.center, second.center) <= max(first.size, second.size) * 1.1
            ):
                candidates.append(second)
        if not candidates:
            return ()
        second = min(candidates, key=lambda item: math.dist(first.center, item.center))
        pending.remove(second)
        pairs.append((first, second))
    return tuple(pairs)


def _terminal_leads(members: tuple[_Round, ...], lines: tuple[_Line, ...]) -> tuple[_Line, ...]:
    endpoints = tuple(point for member in members for point in (member.endpoints or ()))
    if not endpoints:
        return ()
    size = max(member.size for member in members)
    axis = math.cos(members[0].direction), math.sin(members[0].direction)
    center = (
        sum(point[0] for point in endpoints) / len(endpoints),
        sum(point[1] for point in endpoints) / len(endpoints),
    )
    outer = max(
        abs((point[0] - center[0]) * axis[0] + (point[1] - center[1]) * axis[1])
        for point in endpoints
    )
    leads = []
    for line in lines:
        if not 0.15 * size <= line.length <= 1.5 * size:
            continue
        if _angle_delta(_line_angle(line), members[0].direction) > math.radians(22):
            continue
        ends = ((line.start, line.end), (line.end, line.start))
        if any(
            any(math.dist(near, point) <= size * 0.28 for point in endpoints)
            and abs((far[0] - center[0]) * axis[0] + (far[1] - center[1]) * axis[1])
            >= outer + size * 0.08
            for near, far in ends
        ):
            leads.append(line)
    return tuple(leads)


def _ground_terminal(members: tuple[_Round, ...], lines: tuple[_Line, ...]) -> tuple[_Line, ...]:
    """Stem anchored at a winding and three spaced terminal bars with taper."""
    size = max(member.size for member in members)
    angle = members[0].direction
    chord_centers = tuple(
        ((points[0][0] + points[1][0]) / 2, (points[0][1] + points[1][1]) / 2)
        for member in members
        if (points := member.endpoints) is not None
    )
    for stem in lines:
        if not 0.3 * size <= stem.length <= 1.4 * size:
            continue
        if abs(_angle_delta(_line_angle(stem), angle) - math.pi / 2) > math.radians(20):
            continue
        for near, far in ((stem.start, stem.end), (stem.end, stem.start)):
            if not any(math.dist(near, center) <= size * 0.2 for center in chord_centers):
                continue
            direction = (far[0] - near[0]) / stem.length, (far[1] - near[1]) / stem.length
            bars: list[tuple[float, _Line]] = []
            for line in lines:
                if line.source == stem.source or not 0.2 * size <= line.length <= 1.0 * size:
                    continue
                if _angle_delta(_line_angle(line), angle) > math.radians(18):
                    continue
                midpoint = _center(_bounds((line.start, line.end)))
                offset = midpoint[0] - near[0], midpoint[1] - near[1]
                axial = offset[0] * direction[0] + offset[1] * direction[1]
                lateral = abs(offset[0] * direction[1] - offset[1] * direction[0])
                if 0.85 * stem.length <= axial <= 1.55 * stem.length and lateral <= size * 0.14:
                    bars.append((axial, line))
            bars.sort(key=lambda item: item[0])
            for index in range(len(bars) - 2):
                first, second, third = bars[index : index + 3]
                if (
                    first[1].length > second[1].length * 1.08
                    and second[1].length > third[1].length * 1.08
                    and second[0] - first[0] >= size * 0.05
                    and third[0] - second[0] >= size * 0.05
                ):
                    return (stem, first[1], second[1], third[1])
    return ()


def _diagonal_connector(
    members: tuple[_Round, ...], lines: tuple[_Line, ...], bounds: pymupdf.Rect
) -> _Line | None:
    size = max(member.size for member in members)
    center = _center(bounds)
    return next(
        (
            line
            for line in lines
            if line.length >= size * 1.5
            and math.radians(10)
            <= _angle_delta(_line_angle(line), members[0].direction)
            <= math.radians(70)
            and math.dist(_center(_bounds((line.start, line.end))), center)
            <= max(bounds.width, bounds.height) * 0.3
        ),
        None,
    )


def _coherent_circular_windings(members: tuple[_Round, ...], lines: tuple[_Line, ...]) -> bool:
    """Require hollow windings, coherent strokes and no attached pole stem."""
    if any(
        member.fill is not None and (not member.fill or min(member.fill) < 0.95)
        for member in members
    ):
        return False
    colors = tuple(member.color for member in members)
    if any(color is None or len(color) < 3 for color in colors):
        return False
    first_color = colors[0]
    assert first_color is not None
    if any(
        max(abs(first_color[index] - color[index]) for index in range(3)) > 0.1
        for color in colors[1:]
        if color is not None
    ):
        return False
    for first in members:
        for second in members:
            if first is second:
                continue
            axis = (
                math.atan2(second.center[1] - first.center[1], second.center[0] - first.center[0])
                % math.pi
            )
            radius = first.size / 2
            for line in lines:
                if not 0.1 * first.size <= line.length <= 2 * first.size:
                    continue
                if _angle_delta(_line_angle(line), axis) < math.radians(65):
                    continue
                for near, far in ((line.start, line.end), (line.end, line.start)):
                    if (
                        abs(math.dist(near, first.center) - radius) <= first.size * 0.12
                        and math.dist(far, first.center) >= radius + first.size * 0.12
                        and math.dist(_center(_bounds((line.start, line.end))), second.center)
                        > second.size * 0.55
                    ):
                        return False
    return True


def _round_shapes(
    rounds: tuple[_Round, ...], lines: tuple[_Line, ...], used: set[_Source]
) -> tuple[_Shape, ...]:
    candidates = tuple(
        item
        for item in rounds
        if not set(item.sources) & used
        and not (item.kind == "loop" and _colored(item.color, "red"))
    )
    remaining = set(range(len(candidates)))
    shapes: list[_Shape] = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        group = {seed}
        frontier = [seed]
        while frontier:
            index = frontier.pop()
            first = candidates[index]
            for other_index in tuple(remaining):
                second = candidates[other_index]
                if second.kind != first.kind or second.layer != first.layer:
                    continue
                ratio = first.size / max(second.size, 0.01)
                if not 0.6 <= ratio <= 1.67:
                    continue
                distance = math.dist(first.center, second.center)
                minimum = 0.12 if first.kind == "arc" else 0.45
                maximum = 1.7 if first.kind == "arc" else 1.22
                if distance < minimum * min(first.size, second.size) and (
                    first.kind != "arc" or first.curvature * second.curvature >= 0
                ):
                    continue
                if distance > maximum * max(first.size, second.size):
                    continue
                if first.kind == "arc":
                    difference = abs(first.direction - second.direction) % math.pi
                    if min(difference, math.pi - difference) > math.radians(25):
                        continue
                remaining.remove(other_index)
                group.add(other_index)
                frontier.append(other_index)
        if len(group) < 2:
            continue
        members = tuple(candidates[index] for index in sorted(group))
        if len(members) == 2 and members[0].kind == "arc":
            first, second = members
            if first.endpoints is not None and second.endpoints is not None:
                (a0, a1), (b0, b1) = first.endpoints, second.endpoints
                tolerance = min(first.size, second.size) * 0.04
                closed_circle = (
                    (math.dist(a0, b0) <= tolerance and math.dist(a1, b1) <= tolerance)
                    or (math.dist(a0, b1) <= tolerance and math.dist(a1, b0) <= tolerance)
                ) and first.curvature * second.curvature < 0
                if closed_circle:
                    continue
        bounds = _bounds(
            tuple(
                point
                for member in members
                for point in (tuple(member.bounds.tl), tuple(member.bounds.br))
            )
        )
        nearby_lines = tuple(
            line
            for line in lines
            if line.layer == members[0].layer
            and line.length <= members[0].size * 5
            and math.dist(_center(bounds), _center(_bounds((line.start, line.end))))
            <= max(bounds.width, bounds.height) * 1.2
        )
        support_lines: tuple[_Line, ...] = ()
        if members[0].kind == "loop":
            if len(members) not in (2, 3):
                continue
            if any(
                math.dist(first.center, second.center) > 0.95 * min(first.size, second.size)
                or not 0.8 <= first.size / max(second.size, 0.01) <= 1.25
                for index, first in enumerate(members)
                for second in members[index + 1 :]
            ):
                continue
            if not _coherent_circular_windings(members, nearby_lines):
                continue
            variant = "enrolamentos_circulares" if len(members) == 2 else "enrolamentos_multiplos"
            family = "family-f02-18" if len(members) == 2 else "family-f02-24"
            references = (
                ("cemig-eo-r3-s18-v019",)
                if len(members) == 2
                else ("cemig-eo-r3-s24-v001", "cemig-eo-r3-s25-v004")
            )
            possible = ("family-f02-25",) if len(members) > 2 else ()
            class_code = "TRANSFORMADOR"
        else:
            count = len(members)
            nonred = tuple(line for line in nearby_lines if not _colored(line.color, "red"))
            red = tuple(line for line in nearby_lines if _colored(line.color, "red"))
            if count >= 5:
                if count != 6 or len(_arc_pairs(members)) != 3:
                    continue
                bridge = next(
                    (
                        line
                        for line in nonred
                        if line.length >= members[0].size * 2
                        and _angle_delta(_line_angle(line), members[0].direction)
                        <= math.radians(20)
                        and math.dist(_center(_bounds((line.start, line.end))), _center(bounds))
                        <= max(bounds.width, bounds.height) * 0.3
                    ),
                    None,
                )
                composite = bridge is not None
                support_lines = (bridge,) if bridge is not None else ()
                variant = "conjunto_medicao" if composite else "enrolamentos_terciarios"
                family = "family-f02-25" if composite else "family-f02-24"
                references = ("cemig-eo-r3-s25-v004",) if composite else ("cemig-eo-r3-s24-v001",)
                possible = ("family-f02-24",) if composite else ("family-f02-25",)
                class_code = "CONJUNTO_EO" if composite else "TRANSFORMADOR"
            elif count == 4:
                if len(_arc_pairs(members)) != 2:
                    continue
                diagonal = _diagonal_connector(members, nonred, bounds)
                angular = diagonal is not None
                cross = tuple(
                    line
                    for line in red
                    if line.length >= members[0].size * 2
                    and math.dist(_center(_bounds((line.start, line.end))), _center(bounds))
                    <= max(bounds.width, bounds.height) * 0.35
                )
                marker = (
                    cross[:2]
                    if len(cross) >= 2
                    and _angle_delta(_line_angle(cross[0]), _line_angle(cross[1]))
                    >= math.radians(70)
                    else ()
                )
                support_lines = ((diagonal,) if diagonal is not None else ()) + marker
                variant = "enrolamentos_angulares" if angular else "enrolamentos_pares"
                family = "family-f02-18"
                references = (
                    ("cemig-eo-r3-s18-v023",)
                    if angular and marker
                    else ("cemig-eo-r3-s18-v022",)
                    if angular
                    else ("cemig-eo-r3-s18-v019",)
                )
                possible = ()
                class_code = "TRANSFORMADOR"
            elif count == 3:
                leads = _terminal_leads(members, nonred)
                if not leads:
                    continue
                support_lines = leads
                multiple_taps = len(leads) >= 2
                variant = "enrolamento_derivacoes" if multiple_taps else "enrolamento_derivacao"
                family = "family-f02-24" if multiple_taps else "family-f02-18"
                references = (
                    ("cemig-eo-r3-s24-v002",) if multiple_taps else ("cemig-eo-r3-s18-v020",)
                )
                possible = ("family-f02-18",) if multiple_taps else ("family-f02-24",)
                class_code = "TRANSFORMADOR"
            elif count == 2:
                if len(_arc_pairs(members)) != 1:
                    continue
                ground = _ground_terminal(members, nonred)
                leads = () if ground else _terminal_leads(members, nonred)
                if not ground and not leads:
                    continue
                support_lines = ground or leads
                grounded = bool(ground)
                opposed = len(leads) >= 2 and not grounded
                lateral = (
                    opposed
                    and max(line.length for line in leads)
                    > min(line.length for line in leads) * 1.4
                )
                variant = (
                    "enrolamento_terra"
                    if grounded
                    else "semicirculos_laterais"
                    if lateral
                    else "enrolamentos_contrapostos"
                    if opposed
                    else "semicirculos"
                )
                family = "family-f02-18" if grounded else "family-f02-25"
                references = (
                    ("cemig-eo-r3-s18-v021",)
                    if grounded
                    else ("cemig-eo-r3-s25-v003",)
                    if lateral
                    else ("cemig-eo-r3-s25-v001",)
                    if opposed
                    else ("cemig-eo-r3-s25-v002", "cemig-eo-r3-s25-v003")
                )
                possible = ("family-f02-25",) if grounded else ("family-f02-18",)
                class_code = "TRANSFORMADOR"
            else:
                continue
        symbol_bounds = _bounds(
            tuple(
                point
                for member in members
                for point in (tuple(member.bounds.tl), tuple(member.bounds.br))
            )
            + tuple(point for line in support_lines for point in (line.start, line.end))
        )
        component_sources = tuple(
            sorted({source for member in members for source in member.sources})
        )
        line_sources = tuple(line.source for line in support_lines)
        all_sources = tuple(sorted({*component_sources, *line_sources}))
        components = tuple(("enrolamento", member.sources) for member in members)
        if line_sources:
            components += (("tracos_associados", line_sources),)
        shapes.append(
            _Shape(
                variant,
                family,
                class_code,
                all_sources,
                components,
                symbol_bounds,
                references,
                possible,
            )
        )
    return tuple(shapes)


def _nearby_text(page: Any, bounds: pymupdf.Rect) -> tuple[str | None, str | None, str]:
    size = max(float(bounds.width), float(bounds.height), 6)
    center = _center(bounds)
    near: list[tuple[float, str]] = []
    for word in page.get_text("words"):
        x0, y0, x1, y1, raw = word[:5]
        distance = math.dist(center, ((x0 + x1) / 2, (y0 + y1) / 2))
        if distance <= max(25, size * 3.5):
            near.append((distance, str(raw)))
    near.sort(key=lambda item: item[0])
    texts = [word for _, word in near[:8]]
    normalized = [re.sub(r"[^A-Z-]", "", word.upper()) for word in texts]
    conflict = next((word for word in normalized if word in _NEGATIVE_WORDS), None)
    context = "legend" if any(word in _LEGEND_WORDS for word in normalized) else "unknown"
    return (" ".join(texts) or None, conflict, context)


def _geometry(page: Any, bounds: pymupdf.Rect) -> GeometriaObservacaoSimbolo:
    normal = _box_geometry(page, bounds)
    corners = (bounds.tl, bounds.tr, bounds.br, bounds.bl)
    width, height = float(page.rect.width), float(page.rect.height)
    inverse = page.derotation_matrix
    matrix = (
        Decimal(str(width * inverse.a)),
        Decimal(str(width * inverse.b)),
        Decimal(str(height * inverse.c)),
        Decimal(str(height * inverse.d)),
        Decimal(str(inverse.e)),
        Decimal(str(inverse.f)),
    )
    rotated = tuple(point * page.rotation_matrix for point in corners)
    limited = any(not (0 <= point.x <= width and 0 <= point.y <= height) for point in rotated)
    return GeometriaObservacaoSimbolo(
        tipo=normal.tipo,
        pontos_originais=tuple((Decimal(str(point.x)), Decimal(str(point.y))) for point in corners),
        pontos_normalizados=normal.pontos,
        transformacao=TransformacaoSimbolo(
            normalizada_para_original=matrix,
            sistema_original="pymupdf-page-unrotated:points:top-left",
        ),
        normalizacao_limitada=limited,
    )


def _observation(
    page: Any,
    shape: _Shape,
    drawings: tuple[dict[str, Any], ...],
    source: FonteObservacaoSimbolo,
    profile: PerfilMetodoSimbolos,
) -> ObservacaoSimbolo:
    text, conflict, context = _nearby_text(page, shape.bounds)
    by_drawing: dict[int, set[int]] = {}
    for drawing_index, item_index in shape.sources:
        by_drawing.setdefault(drawing_index, set()).add(item_index)
    primitives = tuple(
        PrimitivaObservadaSimbolo(
            indice=str(index),
            camada=str(drawings[index].get("layer")) if drawings[index].get("layer") else None,
            pontos_originais=tuple(
                (Decimal(str(x)), Decimal(str(y)))
                for x, y in _drawing_points(
                    tuple(
                        item
                        for item_index, item in enumerate(drawings[index].get("items") or ())
                        if item_index in indices
                    )
                )
            ),
        )
        for index, indices in sorted(by_drawing.items())
    )
    attributes = (
        ("familia_inventario", shape.family),
        ("familias_possiveis", json.dumps(shape.possible_families)),
        ("variante_grafica", shape.variant),
        ("referencias_possiveis", json.dumps(shape.references)),
        (
            "componentes",
            json.dumps(
                [{"tipo": role, "fontes": refs} for role, refs in shape.components],
                ensure_ascii=False,
            ),
        ),
        ("cardinalidade", "indeterminada"),
        ("quantidade_ativos", None),
        ("texto_proximo", text),
        ("conflito_textual", conflict),
        ("contexto", context),
        ("origem_simbologia", _SOURCE),
    )
    alternatives = [AlternativaClasseSimbolo(classe=shape.class_code, subtipo=shape.variant)]
    if conflict is not None:
        alternatives.append(AlternativaClasseSimbolo(classe=None, subtipo=f"texto:{conflict}"))
    return ObservacaoSimbolo(
        fonte=source,
        metodo_assinatura=profile.assinatura(),
        geometria=_geometry(page, shape.bounds),
        alternativas=tuple(alternatives),
        score_bruto=None,
        primitivas=primitives,
        situacao=None,
        atributos=tuple(sorted(attributes)),
        conteudo_bruto=None,
    )


def observar_transformadores(
    page: Any,
    *,
    documento_id: str,
    documento_sha256: str,
    pagina_numero: int,
) -> ResultadoMetodoSimbolos:
    """Observe formas na base da página; texto e inventário não entram no matcher.

    O SHA-256 da fonte é fornecido pelo chamador e deve ser conferido por ele.
    Ausência de saída registra não detecção, jamais ausência física da classe.
    """
    if not all(
        math.isfinite(float(value)) and float(value) > 0
        for value in (page.rect.width, page.rect.height)
    ):
        raise ValueError("Página deve possuir dimensões positivas finitas")
    profile = perfil_transformadores()
    source = FonteObservacaoSimbolo(
        documento_id=documento_id,
        documento_sha256=documento_sha256,
        pagina_numero=pagina_numero,
        camada="base",
    )
    drawings = _inherit_clipping(_base_drawings(page))
    lines, rounds = _extract_parts(drawings)
    triangles = _triangle_shapes(lines, rounds, drawings)
    used = {source for triangle in triangles for source in triangle.sources}
    sectors = _sector_shapes(rounds, lines, drawings, used)
    rounded = _round_shapes(rounds, lines, used)
    shapes = tuple(
        sorted((*triangles, *sectors, *rounded), key=lambda item: (item.bounds.y0, item.bounds.x0))
    )
    observations = tuple(_observation(page, shape, drawings, source, profile) for shape in shapes)
    coverage = CoberturaMetodoSimbolos(
        fonte=source,
        regiao_normalizada=(
            PontoNormalizado(Decimal(0), Decimal(0)),
            PontoNormalizado(Decimal(1), Decimal(1)),
        ),
        classes_avaliadas=profile.classes_suportadas,
        estado=EstadoMetodoSimbolos.CONCLUIDO
        if observations
        else EstadoMetodoSimbolos.NAO_DETECCAO,
    )
    return ResultadoMetodoSimbolos(perfil=profile, coberturas=(coverage,), observacoes=observations)
