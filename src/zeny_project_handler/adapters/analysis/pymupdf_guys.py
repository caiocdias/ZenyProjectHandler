# mypy: disable-error-code="no-untyped-call"
"""Observações vetoriais de estais, sem criar condutores ou conectividade.

As células de situação do inventário F02 compartilham traçado. O método
reconhece apenas a composição geométrica e mantém IDs/apoios como possibilidades.
Texto próximo não é condição de detecção nem prova de subtipo ou de situação.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pymupdf

from zeny_project_handler.domain.enums import EstadoMetodoSimbolos, TipoGeometria
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

from .pymupdf_support import _normalized_points
from .pymupdf_symbols import _base_drawings, _inherit_clipping

_VERSION = "e06-estais-v3"
_SOURCE = "cemig-eo-r3:it-eo-008:f02:inventario-v1"
_Point = tuple[float, float]
_Source = tuple[int, int]
# Axes shorter than _AXIS_MIN are only compact anchor blocks: a shaft leaving
# the pole centre and ending in a two-tine fork, without T-T, hook or cut.
_AXIS_MIN = 26.0
_COMPACT_MIN = 6.0
_ENDPOINT_TOLERANCE = 2.0
# Polygons need enough sides to read as a drawn circle, not as a frame.
_RING_SIDES_MIN = 12


@dataclass(frozen=True, slots=True)
class _Stroke:
    start: _Point
    end: _Point
    source: _Source
    layer: str
    color: tuple[float, ...] | None
    width: float | None
    dashed: bool

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)


@dataclass(frozen=True, slots=True)
class _Hook:
    endpoints: tuple[_Point, _Point]
    controls: tuple[_Point, _Point]
    source: _Source
    layer: str

    @property
    def middle(self) -> _Point:
        first, second = self.endpoints
        return ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)

    @property
    def size(self) -> float:
        return math.dist(*self.endpoints)


@dataclass(frozen=True, slots=True)
class _Ring:
    """Closed near-circular contour, kept apart from strokes and hooks."""

    center: _Point
    radius: float
    sources: tuple[_Source, ...]
    layer: str
    color: tuple[float, ...] | None
    width: float | None


@dataclass(frozen=True, slots=True)
class _Axis:
    points: tuple[_Point, ...]
    strokes: tuple[_Stroke, ...]
    gap: float = 0.0

    @property
    def start(self) -> _Point:
        return self.points[0]

    @property
    def end(self) -> _Point:
        return self.points[-1]

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)

    @property
    def layer(self) -> str:
        return self.strokes[0].layer


@dataclass(frozen=True, slots=True)
class _Terminal:
    kind: str
    sources: tuple[_Source, ...]
    points: tuple[_Point, ...]


@dataclass(frozen=True, slots=True)
class _Guy:
    variant: str
    axis: _Axis
    terminals: tuple[_Terminal, ...]
    cut_sources: tuple[_Source, ...] = ()

    @property
    def sources(self) -> tuple[_Source, ...]:
        return tuple(
            sorted(
                {stroke.source for stroke in self.axis.strokes}
                | {source for terminal in self.terminals for source in terminal.sources}
                | set(self.cut_sources)
            )
        )


class _StrokeIndex:
    """Local stroke candidates, without a candidate-count cap."""

    def __init__(
        self,
        strokes: tuple[_Stroke, ...],
        *,
        min_length: float = 0,
        max_length: float = math.inf,
    ) -> None:
        self.cells: dict[tuple[int, int], list[_Stroke]] = {}
        for stroke in strokes:
            if not min_length <= stroke.length <= max_length:
                continue
            center = (
                (stroke.start[0] + stroke.end[0]) / 2,
                (stroke.start[1] + stroke.end[1]) / 2,
            )
            key = math.floor(center[0] / 64), math.floor(center[1] / 64)
            self.cells.setdefault(key, []).append(stroke)

    def rectangle(self, bounds: pymupdf.Rect, margin: float = 45) -> tuple[_Stroke, ...]:
        x0, x1 = math.floor((bounds.x0 - margin) / 64), math.floor((bounds.x1 + margin) / 64)
        y0, y1 = math.floor((bounds.y0 - margin) / 64), math.floor((bounds.y1 + margin) / 64)
        return tuple(
            stroke
            for x in range(x0, x1 + 1)
            for y in range(y0, y1 + 1)
            for stroke in self.cells.get((x, y), ())
        )


def perfil_estais() -> PerfilMetodoSimbolos:
    """Capacidades do método E06; scores não são probabilidades."""
    return PerfilMetodoSimbolos(
        metodo_id="pymupdf-guys",
        versao=_VERSION,
        familia="heuristica-geometrica-vetorial-estais",
        dominio_aplicacao="Traçados vetoriais da base; estais E01 F02 §§14-15",
        classes_suportadas=("ESTAI",),
        camadas_suportadas=("base",),
        fontes_compartilhadas=("pymupdf:get_drawings:extended", "normalizador-vetorial-e04"),
        perfil_referencia=_SOURCE,
        parametros=(
            ("pymupdf_version", str(pymupdf.VersionBind)),
            ("assinaturas", "bifurcacao,T-T,ganchos,T-gancho,seccionamento"),
            ("score_bruto", None),
            ("cardinalidade", "indeterminada"),
        ),
    )


def _point(value: Any) -> _Point:
    return float(value.x), float(value.y)


def _color(value: object) -> tuple[float, ...] | None:
    if not isinstance(value, (tuple, list)):
        return None
    try:
        return tuple(float(channel) for channel in value)
    except (TypeError, ValueError):
        return None


def _circle_fit(samples: tuple[_Point, ...]) -> tuple[_Point, float] | None:
    """Centre and radius when every sample is equidistant from the mean point."""
    center = (
        sum(point[0] for point in samples) / len(samples),
        sum(point[1] for point in samples) / len(samples),
    )
    distances = tuple(math.dist(point, center) for point in samples)
    radius = sum(distances) / len(distances)
    if radius <= 0.2 or max(abs(value - radius) for value in distances) > max(0.1, radius * 0.06):
        return None
    return center, radius


def _bezier_middle(item: Any) -> _Point:
    p0, p1, p2, p3 = (_point(value) for value in item[1:5])
    return (
        (p0[0] + 3 * p1[0] + 3 * p2[0] + p3[0]) / 8,
        (p0[1] + 3 * p1[1] + 3 * p2[1] + p3[1]) / 8,
    )


def _ring(drawing_index: int, drawing: dict[str, Any]) -> _Ring | None:
    """A Bézier circle, or a closed polygon of many sides equidistant from its centre."""
    items = tuple(drawing.get("items") or ())
    curves = tuple((index, item) for index, item in enumerate(items) if item[0] == "c")
    lines = tuple((index, item) for index, item in enumerate(items) if item[0] == "l")
    closed = bool(drawing.get("closePath"))
    if len(curves) >= 3 and not lines:
        closed = closed or math.dist(_point(curves[0][1][1]), _point(curves[-1][1][4])) <= 1.5
        members = curves
        samples = tuple(
            point for _, item in curves for point in (_point(item[1]), _bezier_middle(item))
        )
    elif len(lines) >= _RING_SIDES_MIN and not curves:
        closed = closed or math.dist(_point(lines[0][1][1]), _point(lines[-1][1][2])) <= 0.5
        members = lines
        samples = tuple(_point(item[1]) for _, item in lines)
    else:
        return None
    fit = _circle_fit(samples) if closed else None
    if fit is None:
        return None
    center, radius = fit
    # Long chords make a coarse star or frame, not a drawn circle.
    if any(math.dist(_point(item[1]), _point(item[2])) > radius * 0.7 for _, item in lines):
        return None
    clip = drawing.get("scissor")
    bounds = pymupdf.Rect(
        center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius
    )
    if clip is not None and not pymupdf.Rect(clip).contains(bounds):
        return None
    return _Ring(
        center,
        radius,
        tuple((drawing_index, index) for index, _ in members),
        str(drawing.get("layer") or ""),
        _color(drawing.get("color")),
        float(drawing["width"]) if drawing.get("width") is not None else None,
    )


def _visible_stroke(drawing: dict[str, Any]) -> bool:
    # The line items of a filled path are contour instructions, not visible
    # strokes. Alpha zero and white on the normal white PDF page add no ink.
    if str(drawing.get("type") or "") not in {"s", "fs"}:
        return False
    opacity = drawing.get("stroke_opacity")
    if opacity is not None and float(opacity) <= 0.01:
        return False
    color = _color(drawing.get("color"))
    return not (color is not None and color and min(color) >= 0.985)


def _extract(
    drawings: tuple[dict[str, Any], ...],
) -> tuple[tuple[_Stroke, ...], tuple[_Hook, ...], tuple[_Ring, ...]]:
    strokes: list[_Stroke] = []
    hooks: list[_Hook] = []
    rings: list[_Ring] = []
    for drawing_index, drawing in enumerate(drawings):
        if not _visible_stroke(drawing):
            continue
        color = _color(drawing.get("color"))
        layer = str(drawing.get("layer") or "")
        clip = drawing.get("scissor")
        items = tuple(drawing.get("items") or ())
        ring = _ring(drawing_index, drawing)
        if ring is not None:
            rings.append(ring)
        # A circle/closed contour is not a free terminal hook. PyMuPDF emits
        # its quadrants as separate cubic items, each resembling a hook.
        curves = tuple(item for item in items if item[0] == "c")
        closed_curves = len(curves) >= 3 and (
            bool(drawing.get("closePath"))
            or math.dist(_point(curves[0][1]), _point(curves[-1][4])) <= 1.5
        )
        for item_index, item in enumerate(items):
            if item[0] == "l":
                start, end = _point(item[1]), _point(item[2])
                if math.dist(start, end) < 0.2:
                    continue
                points = (start, end)
                if clip is not None and not pymupdf.Rect(clip).contains(_bounds(points)):
                    continue
                strokes.append(
                    _Stroke(
                        start,
                        end,
                        (drawing_index, item_index),
                        layer,
                        color,
                        float(drawing["width"]) if drawing.get("width") is not None else None,
                        bool(str(drawing.get("dashes") or "").strip() not in {"", "[] 0"}),
                    )
                )
            elif item[0] == "c":
                if closed_curves:
                    continue
                curve_points = tuple(_point(value) for value in item[1:5])
                if len(curve_points) != 4 or math.dist(curve_points[0], curve_points[3]) < 2:
                    continue
                if clip is not None and not pymupdf.Rect(clip).contains(_bounds(curve_points)):
                    continue
                hooks.append(
                    _Hook(
                        (curve_points[0], curve_points[3]),
                        (curve_points[1], curve_points[2]),
                        (drawing_index, item_index),
                        layer,
                    )
                )
    return tuple(strokes), tuple(hooks), tuple(rings)


def _bounds(points: tuple[_Point, ...]) -> pymupdf.Rect:
    return pymupdf.Rect(
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def _unit(start: _Point, end: _Point) -> _Point:
    length = math.dist(start, end)
    return (end[0] - start[0]) / length, (end[1] - start[1]) / length


def _dot(a: _Point, b: _Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: _Point, b: _Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _axes(strokes: tuple[_Stroke, ...]) -> tuple[_Axis, ...]:
    """Keep original axes and joins across a short seccionamento gap."""
    long = tuple(stroke for stroke in strokes if _AXIS_MIN <= stroke.length <= 700)
    result: list[_Axis] = []
    endpoints: dict[tuple[int, int], set[int]] = {}
    for index, stroke in enumerate(long):
        for point in (stroke.start, stroke.end):
            key = math.floor(point[0] / 34), math.floor(point[1] / 34)
            endpoints.setdefault(key, set()).add(index)
    for stroke in long:
        result.append(_Axis((stroke.start, stroke.end), (stroke,)))
    for index, first in enumerate(long):
        direction = _unit(first.start, first.end)
        near: set[int] = set()
        for point in (first.start, first.end):
            x, y = math.floor(point[0] / 34), math.floor(point[1] / 34)
            near.update(
                other
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                for other in endpoints.get((x + dx, y + dy), ())
                if other > index
            )
        for other_index in sorted(near):
            second = long[other_index]
            if first.layer != second.layer or first.source == second.source:
                continue
            parallel = abs(_dot(direction, _unit(second.start, second.end)))
            if parallel < 0.985:
                continue
            if (
                max(
                    abs(_cross(direction, (point[0] - first.start[0], point[1] - first.start[1])))
                    for point in (second.start, second.end)
                )
                > 2.5
            ):
                continue
            # Join only end-to-end strokes. Overprinted duplicate linework stays
            # an alternative representation, not an extra mechanical relation.
            joins = (
                (
                    math.dist(first.end, second.start),
                    (first.start, first.end, second.start, second.end),
                    (first, second),
                ),
                (
                    math.dist(first.end, second.end),
                    (first.start, first.end, second.end, second.start),
                    (first, second),
                ),
                (
                    math.dist(first.start, second.start),
                    (second.end, second.start, first.start, first.end),
                    (second, first),
                ),
                (
                    math.dist(first.start, second.end),
                    (second.start, second.end, first.start, first.end),
                    (second, first),
                ),
            )
            gap, points, members = min(joins, key=lambda item: item[0])
            if gap > 34 or math.dist(points[0], points[-1]) < 65:
                continue
            if gap < 1.5 and min(first.length, second.length) < 15:
                continue
            # A gap greater than 1.5 requires its own short cut markers before
            # the axis is admitted by _find_guys.
            result.append(_Axis(points, members, gap))
    return tuple(result)


def _terminal_bar(axis: _Axis, at_start: bool, strokes: tuple[_Stroke, ...]) -> _Terminal | None:
    endpoint = axis.start if at_start else axis.end
    direction = _unit(axis.start, axis.end)
    candidates: list[tuple[float, _Stroke]] = []
    for stroke in strokes:
        if (
            stroke.source in {member.source for member in axis.strokes}
            or stroke.layer != axis.layer
        ):
            continue
        if not 8 <= stroke.length <= min(65, axis.length * 0.36):
            continue
        vector = _unit(stroke.start, stroke.end)
        if abs(_dot(direction, vector)) > 0.26:
            continue
        middle = ((stroke.start[0] + stroke.end[0]) / 2, (stroke.start[1] + stroke.end[1]) / 2)
        distance = math.dist(middle, endpoint)
        if distance <= max(2.0, min(5.0, axis.length * 0.035)):
            candidates.append((distance, stroke))
    if not candidates:
        return None
    _, chosen = min(candidates, key=lambda item: (item[0], item[1].source))
    return _Terminal("cruzeta", (chosen.source,), (chosen.start, chosen.end))


def _terminal_hook(axis: _Axis, at_start: bool, hooks: tuple[_Hook, ...]) -> _Terminal | None:
    endpoint = axis.start if at_start else axis.end
    direction = _unit(axis.start, axis.end)
    candidates: list[tuple[float, _Hook]] = []
    for hook in hooks:
        if hook.layer != axis.layer or not 8 <= hook.size <= min(75, axis.length * 0.8):
            continue
        chord = _unit(*hook.endpoints)
        if abs(_dot(direction, chord)) > 0.32:
            continue
        distance = math.dist(hook.middle, endpoint)
        if distance > max(3, min(7, axis.length * 0.055)):
            continue
        # A straight cubic segment is a path fragment, not a terminal hook.
        bulge = max(
            abs(
                _cross(
                    chord, (control[0] - hook.endpoints[0][0], control[1] - hook.endpoints[0][1])
                )
            )
            for control in hook.controls
        )
        if bulge < hook.size * 0.13:
            continue
        candidates.append((distance, hook))
    if not candidates:
        return None
    _, chosen = min(candidates, key=lambda item: (item[0], item[1].source))
    return _Terminal("poste", (chosen.source,), (*chosen.endpoints, *chosen.controls))


def _same_ink(first: _Stroke, second: _Stroke | _Ring) -> bool:
    """The shaft and both tines must be one visible mechanical stroke."""
    if first.color is not None and second.color is not None:
        a = first.color * 3 if len(first.color) == 1 else first.color
        b = second.color * 3 if len(second.color) == 1 else second.color
        if len(a) != len(b) or max(abs(x - y) for x, y in zip(a, b, strict=True)) > 0.15:
            return False
    return not (
        first.width is not None
        and second.width is not None
        and max(first.width, second.width) > 2.2 * max(0.05, min(first.width, second.width))
    )


_Branch = tuple[_Stroke, _Point, _Point]


def _compact(axis: _Axis) -> bool:
    return axis.length < _AXIS_MIN


def _branch_limits(axis: _Axis) -> tuple[float, float]:
    """Tine length range; a compact block keeps tines relative to its shaft."""
    if _compact(axis):
        return max(3.0, axis.length * 0.3), axis.length * 0.9
    return 9, min(75, axis.length * 0.42)


def _fork_direction(projection: float, lateral: float, compact: bool) -> bool:
    # A compact block only opens forward; a tiny backward V is an arrowhead.
    if compact:
        return 0.25 <= projection <= 0.95 and lateral >= 0.25
    forward_fork = 0.25 <= projection <= 0.9 and lateral >= 0.25
    backward_fork = -0.995 <= projection <= -0.25 and lateral >= 0.14
    return forward_fork or backward_fork


def _anchor_branches(
    axis: _Axis, endpoint: _Point, direction: _Point, strokes: tuple[_Stroke, ...]
) -> list[_Branch]:
    branches: list[_Branch] = []
    shortest, longest = _branch_limits(axis)
    for stroke in strokes:
        if (
            stroke.source in {member.source for member in axis.strokes}
            or stroke.layer != axis.layer
        ):
            continue
        if not shortest <= stroke.length <= longest:
            continue
        near, tip = (
            (stroke.start, stroke.end)
            if math.dist(stroke.start, endpoint) <= math.dist(stroke.end, endpoint)
            else (stroke.end, stroke.start)
        )
        if math.dist(near, endpoint) > max(_ENDPOINT_TOLERANCE, min(5.0, axis.length * 0.035)):
            continue
        vector = _unit(near, tip)
        if not _fork_direction(
            _dot(direction, vector), abs(_cross(direction, vector)), _compact(axis)
        ):
            continue
        branches.append((stroke, near, tip))
    return branches


def _vertex_directions(
    axis: _Axis, vertex: _Point, strokes: tuple[_Stroke, ...], minimum: float
) -> int:
    """Distinct outgoing directions at a vertex; overprinted copies count once."""
    angles: list[float] = []
    for stroke in strokes:
        if stroke.layer != axis.layer or stroke.length < minimum:
            continue
        if math.dist(stroke.start, vertex) <= _ENDPOINT_TOLERANCE:
            other = stroke.end
        elif math.dist(stroke.end, vertex) <= _ENDPOINT_TOLERANCE:
            other = stroke.start
        else:
            continue
        angle = math.atan2(other[1] - vertex[1], other[0] - vertex[0])
        if all(
            abs((angle - prior + math.pi) % (2 * math.pi) - math.pi) > math.pi / 18
            for prior in angles
        ):
            angles.append(angle)
    return len(angles)


def _fork_projections(
    axis: _Axis, direction: _Point, first: _Branch, second: _Branch
) -> tuple[float, float] | None:
    """Projections of two symmetric tines of the shaft's ink, or None otherwise."""
    if not all(
        _same_ink(member, tine) for member in axis.strokes for tine in (first[0], second[0])
    ):
        return None
    v1, v2 = _unit(first[1], first[2]), _unit(second[1], second[2])
    if _cross(direction, v1) * _cross(direction, v2) >= 0:
        return None
    if not 0.72 <= first[0].length / second[0].length <= 1.4:
        return None
    projection1, projection2 = _dot(direction, v1), _dot(direction, v2)
    if projection1 * projection2 <= 0 or not 0.6 <= projection1 / projection2 <= 1.7:
        return None
    return projection1, projection2


def _anchor_crossbars(
    axis: _Axis,
    direction: _Point,
    strokes: tuple[_Stroke, ...],
    first: _Branch,
    second: _Branch,
    tip_span: float,
) -> tuple[_Stroke, ...]:
    tip_middle = ((first[2][0] + second[2][0]) / 2, (first[2][1] + second[2][1]) / 2)
    return tuple(
        stroke
        for stroke in strokes
        if stroke.layer == axis.layer
        and stroke.source not in {member.source for member in axis.strokes}
        and stroke.source not in {first[0].source, second[0].source}
        and stroke.length >= tip_span * 0.65
        and abs(_dot(direction, _unit(stroke.start, stroke.end))) < 0.3
        and math.dist(
            (
                (stroke.start[0] + stroke.end[0]) / 2,
                (stroke.start[1] + stroke.end[1]) / 2,
            ),
            tip_middle,
        )
        <= max(6, first[0].length * 0.45)
    )


def _dimension_extensions(
    axis: _Axis, direction: _Point, strokes: tuple[_Stroke, ...], tip_span: float
) -> tuple[_Point, ...]:
    return tuple(
        endpoint_marker
        for endpoint_marker in (axis.start, axis.end)
        if any(
            stroke.layer == axis.layer
            and stroke.source not in {member.source for member in axis.strokes}
            and stroke.length >= tip_span * 1.5
            and abs(_dot(direction, _unit(stroke.start, stroke.end))) < 0.3
            and math.dist(
                (
                    (stroke.start[0] + stroke.end[0]) / 2,
                    (stroke.start[1] + stroke.end[1]) / 2,
                ),
                endpoint_marker,
            )
            <= 4
            for stroke in strokes
        )
    )


def _closed_arrowhead(cap: _Stroke, first: _Branch, second: _Branch, tip_span: float) -> bool:
    closures = (
        max(math.dist(cap.start, first[2]), math.dist(cap.end, second[2])),
        max(math.dist(cap.start, second[2]), math.dist(cap.end, first[2])),
    )
    return min(closures) <= max(1.0, tip_span * 0.08)


def _branch_continued(
    axis: _Axis,
    strokes: tuple[_Stroke, ...],
    first: _Branch,
    second: _Branch,
    cap: _Stroke | None,
    outward: _Point,
) -> bool:
    return any(
        stroke.layer == axis.layer
        and stroke.source not in {member.source for member in axis.strokes}
        and stroke.source not in {first[0].source, second[0].source}
        and (cap is None or stroke.source != cap.source)
        and stroke.length > min(first[0].length, second[0].length) * 0.8
        and _extends_beyond(stroke, tip, outward, min(first[0].length, second[0].length))
        for tip in (first[2], second[2])
        for stroke in strokes
    )


def _compact_fork(
    axis: _Axis,
    endpoint: _Point,
    strokes: tuple[_Stroke, ...],
    first: _Branch,
    second: _Branch,
    projections: tuple[float, float],
) -> bool:
    """A compact anchor is a symmetric CAD block with a three-way vertex.

    Unequal or unevenly opened tines are chance junctions of short linework;
    more outgoing directions make a compass rose or a star of short rays.
    """
    shortest = min(first[0].length, second[0].length)
    if not 0.85 <= first[0].length / second[0].length <= 1 / 0.85:
        return False
    if abs(projections[0] - projections[1]) > 0.06:
        return False
    return _vertex_directions(axis, endpoint, strokes, shortest * 0.5) <= 3


def _anchor_from_pair(
    axis: _Axis,
    endpoint: _Point,
    direction: _Point,
    strokes: tuple[_Stroke, ...],
    first: _Branch,
    second: _Branch,
) -> _Terminal | None:
    projections = _fork_projections(axis, direction, first, second)
    if projections is None:
        return None
    projection1, _ = projections
    if _compact(axis) and not _compact_fork(axis, endpoint, strokes, first, second, projections):
        return None
    tip_span = math.dist(first[2], second[2])
    crossbars = _anchor_crossbars(axis, direction, strokes, first, second, tip_span)
    # Dimension extension lines protrude much farther than the fork.
    if any(stroke.length > tip_span * 1.6 for stroke in crossbars):
        return None
    # A second extension line at the other end makes a dimension mark,
    # even when the fork points back along the axis.
    if len(_dimension_extensions(axis, direction, strokes, tip_span)) == 2:
        return None
    cap = min(crossbars, key=lambda stroke: stroke.source) if crossbars else None
    # A closed triangular arrowhead is a directed mark, not a guy.
    if cap is not None and _closed_arrowhead(cap, first, second, tip_span):
        return None
    # Two outgoing continuations indicate a branched conductor.
    outward = direction if projection1 > 0 else (-direction[0], -direction[1])
    if _branch_continued(axis, strokes, first, second, cap, outward):
        return None
    return _Terminal(
        "ancora",
        tuple(sorted((first[0].source, second[0].source, *((cap.source,) if cap else ())))),
        (endpoint, first[2], second[2], *((cap.start, cap.end) if cap else ())),
    )


def _terminal_anchor(axis: _Axis, strokes: tuple[_Stroke, ...]) -> _Terminal | None:
    endpoint = axis.end
    direction = _unit(axis.start, axis.end)
    branches = _anchor_branches(axis, endpoint, direction, strokes)
    for index, first in enumerate(branches):
        for second in branches[index + 1 :]:
            anchor = _anchor_from_pair(axis, endpoint, direction, strokes, first, second)
            if anchor is not None:
                return anchor
    return None


def _extends_beyond(stroke: _Stroke, tip: _Point, direction: _Point, branch_length: float) -> bool:
    if math.dist(stroke.start, tip) <= 2:
        farther = stroke.end
    elif math.dist(stroke.end, tip) <= 2:
        farther = stroke.start
    else:
        return False
    return _dot(direction, (farther[0] - tip[0], farther[1] - tip[1])) > branch_length * 0.5


def _cut_markers(axis: _Axis, strokes: tuple[_Stroke, ...]) -> tuple[_Source, ...]:
    if not 4 <= axis.gap <= 34 or len(axis.strokes) != 2:
        return ()
    first_end, second_start = axis.points[1], axis.points[2]
    direction = _unit(axis.start, axis.end)
    near: list[_Stroke] = []
    for stroke in strokes:
        if stroke.layer != axis.layer or stroke.source in {
            member.source for member in axis.strokes
        }:
            continue
        if not 5 <= stroke.length <= 32:
            continue
        vector = _unit(stroke.start, stroke.end)
        if abs(_dot(direction, vector)) > 0.85 or abs(_dot(direction, vector)) < 0.2:
            continue
        if (
            min(
                math.dist(stroke.start, first_end),
                math.dist(stroke.end, first_end),
                math.dist(stroke.start, second_start),
                math.dist(stroke.end, second_start),
            )
            <= 3.5
        ):
            near.append(stroke)
    # Two oblique strokes distinguish a sectionalized guy from a broken line.
    if len(near) < 2:
        return ()
    return tuple(sorted(stroke.source for stroke in near[:2]))


def _parallel_bundle(axis: _Axis, strokes: tuple[_Stroke, ...]) -> bool:
    """Reject a network corridor with other long conductors beside the T-T axis."""
    direction = _unit(axis.start, axis.end)
    neighbors = []
    for stroke in strokes:
        if stroke.layer != axis.layer or stroke.source in {
            member.source for member in axis.strokes
        }:
            continue
        if not 0.72 * axis.length <= stroke.length <= 1.4 * axis.length:
            continue
        vector = _unit(stroke.start, stroke.end)
        if abs(_dot(direction, vector)) < 0.985:
            continue
        offsets = (
            _cross(direction, (point[0] - axis.start[0], point[1] - axis.start[1]))
            for point in (stroke.start, stroke.end)
        )
        offset = sum(offsets) / 2
        if not 3 <= abs(offset) <= min(32, axis.length * 0.2):
            continue
        projection = (
            _dot(direction, (point[0] - axis.start[0], point[1] - axis.start[1]))
            for point in (stroke.start, stroke.end)
        )
        first, second = sorted(projection)
        if min(axis.length, second) - max(0, first) < axis.length * 0.65:
            continue
        neighbors.append(stroke)
    return len(neighbors) >= 2 or any(stroke.dashed for stroke in neighbors)


_Neighbor = tuple[float, float, float, bool]


def _corridor_neighbors(
    axis: _Axis, direction: _Point, strokes: tuple[_Stroke, ...]
) -> list[_Neighbor]:
    members = {stroke.source for stroke in axis.strokes}
    shaft_width = max((stroke.width or 0 for stroke in axis.strokes), default=0)
    neighbors: list[_Neighbor] = []
    for stroke in strokes:
        if stroke.layer != axis.layer or stroke.source in members:
            continue
        if abs(_dot(direction, _unit(stroke.start, stroke.end))) < 0.985:
            continue
        displacement = (
            stroke.start[0] - axis.start[0],
            stroke.start[1] - axis.start[1],
        )
        offset = _cross(direction, displacement)
        # Exact overprint shares a centerline; a separate narrow strand may
        # sit much closer than three PDF points to a thin shaft.
        minimum_offset = max(0.75, 1.2 * max(shaft_width, stroke.width or 0))
        if not minimum_offset <= abs(offset) <= min(32, axis.length * 0.2):
            continue
        first, last = sorted(
            _dot(direction, (point[0] - axis.start[0], point[1] - axis.start[1]))
            for point in (stroke.start, stroke.end)
        )
        first, last = max(0, first), min(axis.length, last)
        if last - first >= 3:
            neighbors.append((offset, first, last, stroke.dashed))
    return neighbors


def _corridor_groups(neighbors: list[_Neighbor]) -> list[list[_Neighbor]]:
    groups: list[list[_Neighbor]] = []
    for neighbor in sorted(neighbors):
        if groups and abs(neighbor[0] - groups[-1][-1][0]) <= 3.5:
            groups[-1].append(neighbor)
        else:
            groups.append([neighbor])
    return groups


def _merged_intervals(intervals: list[tuple[float, float]]) -> list[list[float]]:
    merged: list[list[float]] = []
    for first, last in intervals:
        if merged and first <= merged[-1][1] + 1:
            merged[-1][1] = max(last, merged[-1][1])
        else:
            merged.append([first, last])
    return merged


def _parallel_corridor(axis: _Axis, strokes: tuple[_Stroke, ...]) -> bool:
    """Recognize other conductors beside an anchor-like shaft.

    Coverage is assembled from collinear fragments, since dashed network
    linework can be emitted as many short vector strokes. Coincident
    overprinting of an isolated guy is deliberately excluded by offset.
    """
    direction = _unit(axis.start, axis.end)
    neighbors = _corridor_neighbors(axis, direction, strokes)
    if not neighbors:
        return False
    substantial = 0
    for group in _corridor_groups(neighbors):
        intervals = sorted((first, last) for _, first, last, _ in group)
        merged = _merged_intervals(intervals)
        coverage = sum(last - first for first, last in merged)
        span = max(last for _, last in intervals) - min(first for first, _ in intervals)
        if coverage >= axis.length * 0.6:
            substantial += 1
            if any(dashed for *_, dashed in group) or any(member.dashed for member in axis.strokes):
                return True
        # Repeated separated strokes are a dashed conductor even if the PDF
        # encoded each dash independently instead of using a dash style.
        if len(merged) >= 3 and coverage >= axis.length * 0.35 and span >= axis.length * 0.7:
            return True
    return substantial >= 2


def _interior_bar(axis: _Axis, strokes: tuple[_Stroke, ...]) -> bool:
    """Intermediate crossarms belong to a run of network supports."""
    direction = _unit(axis.start, axis.end)
    for stroke in strokes:
        if stroke.layer != axis.layer or not 7 <= stroke.length <= 65:
            continue
        if abs(_dot(direction, _unit(stroke.start, stroke.end))) > 0.3:
            continue
        center = ((stroke.start[0] + stroke.end[0]) / 2, (stroke.start[1] + stroke.end[1]) / 2)
        displacement = (center[0] - axis.start[0], center[1] - axis.start[1])
        projection = _dot(direction, displacement)
        if (
            axis.length * 0.12 <= projection <= axis.length * 0.88
            and abs(_cross(direction, displacement)) <= 4
        ):
            return True
    return False


def _radial_hub(axis: _Axis, strokes: tuple[_Stroke, ...]) -> bool:
    """A symmetric collection of spokes is a compass, even with open tips."""
    # Opposite spokes may have become one joined axis. Retain the original
    # join points as possible hubs, as well as the free shaft endpoint.
    for hub in (axis.start, *axis.points[1:-1]):
        angles: list[float] = []
        for stroke in strokes:
            if (
                stroke.layer != axis.layer
                or not 0.3 * axis.length <= stroke.length <= 1.6 * axis.length
            ):
                continue
            if math.dist(stroke.start, hub) <= 3:
                other = stroke.end
            elif math.dist(stroke.end, hub) <= 3:
                other = stroke.start
            else:
                continue
            angle = math.atan2(other[1] - hub[1], other[0] - hub[0]) % (2 * math.pi)
            if all(
                abs((angle - prior + math.pi) % (2 * math.pi) - math.pi) > math.pi / 9
                for prior in angles
            ):
                angles.append(angle)
        if len(angles) < 4:
            continue
        ordered = sorted(angles)
        gaps = [
            (ordered[(index + 1) % len(ordered)] - angle) % (2 * math.pi)
            for index, angle in enumerate(ordered)
        ]
        if max(gaps) <= 2.3:
            return True
    return False


def _oriented_axes(axes: tuple[_Axis, ...]) -> tuple[_Axis, ...]:
    """Each candidate axis in its own direction, then reversed."""
    return tuple(
        axis
        for candidate in axes
        for axis in (
            candidate,
            _Axis(tuple(reversed(candidate.points)), candidate.strokes, candidate.gap),
        )
    )


def _crossbars_on_axis(axis: _Axis, local: tuple[_Stroke, ...]) -> int:
    direction = _unit(axis.start, axis.end)
    on_axis = 0
    for stroke in local:
        if stroke.layer != axis.layer or not 7 <= stroke.length <= 65:
            continue
        if abs(_dot(direction, _unit(stroke.start, stroke.end))) > 0.3:
            continue
        center = ((stroke.start[0] + stroke.end[0]) / 2, (stroke.start[1] + stroke.end[1]) / 2)
        projection = _dot(direction, (center[0] - axis.start[0], center[1] - axis.start[1]))
        offset = abs(_cross(direction, (center[0] - axis.start[0], center[1] - axis.start[1])))
        if 0 <= projection <= axis.length and offset <= 4:
            on_axis += 1
    return on_axis


@dataclass(frozen=True, slots=True)
class _AxisTerminals:
    start_bar: _Terminal | None
    end_bar: _Terminal | None
    start_hook: _Terminal | None
    end_hook: _Terminal | None
    anchor: _Terminal | None
    cut: tuple[_Source, ...]


def _admits_cruzeta_cruzeta(
    axis: _Axis,
    start_bar: _Terminal,
    end_bar: _Terminal,
    local: tuple[_Stroke, ...],
    long_index: _StrokeIndex,
    all_index: _StrokeIndex,
) -> bool:
    return (
        min(math.dist(*start_bar.points), math.dist(*end_bar.points)) >= axis.length * 0.1
        and not _interior_bar(axis, local)
        and not _parallel_bundle(axis, long_index.rectangle(_bounds(axis.points)))
        and not _parallel_corridor(axis, all_index.rectangle(_bounds(axis.points)))
    )


def _mixed_guy(axis: _Axis, terminals: _AxisTerminals) -> _Guy | None:
    start_bar, end_bar = terminals.start_bar, terminals.end_bar
    start_hook, end_hook = terminals.start_hook, terminals.end_hook
    if not (
        (start_bar and end_hook and not end_bar and not start_hook)
        or (start_hook and end_bar and not start_bar and not end_hook)
    ):
        return None
    chosen = tuple(
        terminal
        for terminal in ((start_bar, end_hook) if start_bar else (start_hook, end_bar))
        if terminal is not None
    )
    cut = terminals.cut
    return _Guy("cruzeta_poste_seccionado" if cut else "cruzeta_poste", axis, chosen, cut)


def _classify_axis(
    axis: _Axis,
    local: tuple[_Stroke, ...],
    hooks: tuple[_Hook, ...],
    long_index: _StrokeIndex,
    all_index: _StrokeIndex,
) -> _Guy | None:
    terminals = _AxisTerminals(
        start_bar=_terminal_bar(axis, True, local),
        end_bar=_terminal_bar(axis, False, local),
        start_hook=_terminal_hook(axis, True, hooks),
        end_hook=_terminal_hook(axis, False, hooks),
        anchor=_terminal_anchor(axis, local),
        cut=_cut_markers(axis, local),
    )
    start_bar, end_bar = terminals.start_bar, terminals.end_bar
    start_hook, end_hook = terminals.start_hook, terminals.end_hook
    if terminals.anchor and not start_bar and not start_hook and not end_hook:
        return _Guy("ancora", axis, (terminals.anchor,))
    if (
        start_bar
        and end_bar
        and not start_hook
        and not end_hook
        and _admits_cruzeta_cruzeta(axis, start_bar, end_bar, local, long_index, all_index)
    ):
        return _Guy("cruzeta_cruzeta", axis, (start_bar, end_bar))
    if start_hook and end_hook and not start_bar and not end_bar:
        return _Guy("poste_poste", axis, (start_hook, end_hook))
    return _mixed_guy(axis, terminals)


def _select_guys(
    found: dict[tuple[_Source, ...], _Guy],
    strokes: tuple[_Stroke, ...],
    all_index: _StrokeIndex,
) -> list[_Guy]:
    ordered = sorted(
        found.values(), key=lambda guy: (-guy.axis.length, guy.axis.start, guy.sources)
    )
    selected: list[_Guy] = []
    for guy in ordered:
        # A compact block opens forward from a pole centre, where other guys,
        # earthing and service drops legitimately meet; its vertex is checked
        # against radial spokes in _anchor_from_pair instead.
        if guy.variant == "ancora" and (
            (not _compact(guy.axis) and _radial_hub(guy.axis, strokes))
            or _parallel_corridor(guy.axis, all_index.rectangle(_bounds(guy.axis.points)))
        ):
            continue
        core = {source for terminal in guy.terminals for source in terminal.sources}
        if any(_same_mark(guy, other, core) for other in selected):
            continue
        selected.append(guy)
    return selected


class _EndpointIndex:
    """Stroke endpoints by small cell, to pre-filter compact fork vertices."""

    _CELL = 4.0

    def __init__(self, strokes: tuple[_Stroke, ...], max_length: float) -> None:
        self.cells: dict[tuple[int, int], list[_Stroke]] = {}
        for stroke in strokes:
            if stroke.length > max_length:
                continue
            for point in (stroke.start, stroke.end):
                key = math.floor(point[0] / self._CELL), math.floor(point[1] / self._CELL)
                self.cells.setdefault(key, []).append(stroke)

    def near(self, point: _Point) -> tuple[_Stroke, ...]:
        x, y = math.floor(point[0] / self._CELL), math.floor(point[1] / self._CELL)
        found: dict[_Source, _Stroke] = {}
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for stroke in self.cells.get((x + dx, y + dy), ()):
                    if (
                        min(math.dist(stroke.start, point), math.dist(stroke.end, point))
                        <= _ENDPOINT_TOLERANCE
                    ):
                        found[stroke.source] = stroke
        return tuple(found.values())


def _compact_guys(strokes: tuple[_Stroke, ...], short_index: _StrokeIndex) -> list[_Guy]:
    """Compact anchor blocks: a short shaft whose free end opens in a fork."""
    endpoints = _EndpointIndex(strokes, max_length=_AXIS_MIN * 0.9)
    guys: list[_Guy] = []
    for stroke in strokes:
        if not _COMPACT_MIN <= stroke.length < _AXIS_MIN:
            continue
        for axis in _oriented_axes((_Axis((stroke.start, stroke.end), (stroke,)),)):
            shortest, longest = _branch_limits(axis)
            tines = sum(
                1
                for other in endpoints.near(axis.end)
                if other.source != stroke.source and shortest <= other.length <= longest
            )
            if tines < 2:
                continue
            anchor = _terminal_anchor(axis, short_index.rectangle(_bounds(axis.points)))
            if anchor is not None:
                guys.append(_Guy("ancora", axis, (anchor,)))
    return guys


class _RingIndex:
    """Rings by centre cell, searched around an anchor vertex."""

    _CELL = 32.0

    def __init__(self, rings: tuple[_Ring, ...]) -> None:
        self.cells: dict[tuple[int, int], list[_Ring]] = {}
        for ring in rings:
            key = math.floor(ring.center[0] / self._CELL), math.floor(ring.center[1] / self._CELL)
            self.cells.setdefault(key, []).append(ring)

    def near(self, point: _Point, reach: float) -> tuple[_Ring, ...]:
        x0, x1 = (math.floor((point[0] + delta) / self._CELL) for delta in (-reach, reach))
        y0, y1 = (math.floor((point[1] + delta) / self._CELL) for delta in (-reach, reach))
        return tuple(
            ring
            for x in range(x0, x1 + 1)
            for y in range(y0, y1 + 1)
            for ring in self.cells.get((x, y), ())
            if math.dist(ring.center, point) <= reach
        )


def _enclosing_ring(axis: _Axis, terminal: _Terminal, rings: _RingIndex) -> _Ring | None:
    """The circle drawn through the fork vertex and both tine tips, ahead of the shaft."""
    vertex, tips = axis.end, terminal.points[1:3]
    direction = _unit(axis.start, axis.end)
    branch = sum(math.dist(vertex, tip) for tip in tips) / len(tips)
    candidates: list[tuple[float, _Ring]] = []
    for ring in rings.near(vertex, branch * 1.2 + max(0.75, branch * 0.15)):
        if ring.layer != axis.layer or not all(_same_ink(member, ring) for member in axis.strokes):
            continue
        if not 0.45 <= ring.radius / branch <= 1.2:
            continue
        tolerance = max(0.75, ring.radius * 0.12)
        deviation = max(abs(math.dist(tip, ring.center) - ring.radius) for tip in tips)
        if deviation > tolerance or math.dist(vertex, ring.center) > ring.radius + tolerance:
            continue
        if _dot(direction, (ring.center[0] - vertex[0], ring.center[1] - vertex[1])) <= 0:
            continue
        candidates.append((deviation, ring))
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item[0], item[1].sources))[1]


def _with_ring(guy: _Guy, rings: _RingIndex) -> _Guy:
    """An anchor's enclosing ring joins its terminal, sources and primitives."""
    if guy.variant != "ancora":
        return guy
    terminal = guy.terminals[0]
    ring = _enclosing_ring(guy.axis, terminal, rings)
    if ring is None:
        return guy
    sources = tuple(sorted({*terminal.sources, *ring.sources}))
    return _Guy(
        guy.variant,
        guy.axis,
        (_Terminal(terminal.kind, sources, terminal.points), *guy.terminals[1:]),
        guy.cut_sources,
    )


def _find_guys(
    strokes: tuple[_Stroke, ...], hooks: tuple[_Hook, ...], rings: tuple[_Ring, ...]
) -> tuple[_Guy, ...]:
    found: dict[tuple[_Source, ...], _Guy] = {}
    all_index = _StrokeIndex(strokes)
    short_index = _StrokeIndex(strokes, max_length=85)
    long_index = _StrokeIndex(strokes, min_length=26)
    axes = _axes(strokes)
    for axis in _oriented_axes(axes):
        local = short_index.rectangle(_bounds(axis.points))
        if axis.gap > 1.5 and not _cut_markers(axis, local):
            continue
        # A long fence has many repeated crossbars: it is not a single T-T guy.
        if _crossbars_on_axis(axis, local) > 3:
            continue
        guy = _classify_axis(axis, local, hooks, long_index, all_index)
        if guy is None:
            continue
        # Complete axes win over their fragments; overprinting only contributes
        # redundant sources and must not multiply the observation.
        found[guy.sources] = guy
    for guy in _compact_guys(strokes, short_index):
        found.setdefault(guy.sources, guy)
    ring_index = _RingIndex(rings)
    selected = [_with_ring(guy, ring_index) for guy in _select_guys(found, strokes, all_index)]
    return tuple(
        sorted(
            selected,
            key=lambda guy: (
                min(guy.axis.start[1], guy.axis.end[1]),
                min(guy.axis.start[0], guy.axis.end[0]),
            ),
        )
    )


def _same_mark(guy: _Guy, other: _Guy, core: set[_Source]) -> bool:
    if guy.variant != other.variant:
        return False
    other_core = {source for terminal in other.terminals for source in terminal.sources}
    if core & other_core:
        return True
    endpoints = ((guy.axis.start, other.axis.start), (guy.axis.end, other.axis.end))
    reverse = ((guy.axis.start, other.axis.end), (guy.axis.end, other.axis.start))
    return (
        min(
            max(math.dist(*pair) for pair in endpoints),
            max(math.dist(*pair) for pair in reverse),
        )
        <= 1.5
    )


def _references(variant: str) -> tuple[str, ...]:
    numbers = {
        "ancora": (1, 2, 3),
        "cruzeta_cruzeta": (4, 5, 6),
        "poste_poste": (7, 8, 9),
        "cruzeta_poste_seccionado": (10, 11, 12),
        "cruzeta_poste": (13, 14, 15),
    }[variant]
    refs = tuple(f"cemig-eo-r3-s14-v{number:03d}" for number in numbers)
    if variant == "ancora":
        return (*refs, "cemig-eo-r3-s15-v001")
    if variant == "poste_poste":
        return (*refs, "cemig-eo-r3-s15-v002")
    return refs


def _geometry(page: Any, axis: _Axis) -> GeometriaObservacaoSimbolo:
    points = axis.points if axis.gap > 1.5 else (axis.start, axis.end)
    normalized = _normalized_points(page, points)
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
    rotated = tuple(pymupdf.Point(*point) * page.rotation_matrix for point in points)
    limited = any(not (0 <= point.x <= width and 0 <= point.y <= height) for point in rotated)
    return GeometriaObservacaoSimbolo(
        tipo=TipoGeometria.POLILINHA,
        pontos_originais=tuple((Decimal(str(x)), Decimal(str(y))) for x, y in points),
        pontos_normalizados=normalized,
        transformacao=TransformacaoSimbolo(
            normalizada_para_original=matrix,
            sistema_original="pymupdf-page-unrotated:points:top-left",
        ),
        normalizacao_limitada=limited,
    )


def _observation(
    page: Any,
    guy: _Guy,
    drawings: tuple[dict[str, Any], ...],
    source: FonteObservacaoSimbolo,
    profile: PerfilMetodoSimbolos,
) -> ObservacaoSimbolo:
    components = [
        {"papel": "tracado", "fontes": [stroke.source for stroke in guy.axis.strokes]},
        *({"papel": terminal.kind, "fontes": terminal.sources} for terminal in guy.terminals),
    ]
    if guy.cut_sources:
        components.append({"papel": "seccionamento", "fontes": guy.cut_sources})
    role_start = guy.terminals[0].kind if len(guy.terminals) == 2 else "suporte_indeterminado"
    role_end = guy.terminals[-1].kind
    supports = (
        {"extremidade": "inicio", "tipo": role_start, "id_suporte": None, "vinculo": "possivel"},
        {"extremidade": "fim", "tipo": role_end, "id_suporte": None, "vinculo": "possivel"},
    )
    by_drawing: dict[int, set[int]] = {}
    for drawing_index, item_index in guy.sources:
        by_drawing.setdefault(drawing_index, set()).add(item_index)
    primitives = tuple(
        PrimitivaObservadaSimbolo(
            indice=str(index),
            camada=str(drawings[index].get("layer")) if drawings[index].get("layer") else None,
            pontos_originais=tuple(
                (Decimal(str(point[0])), Decimal(str(point[1])))
                for item_index, item in enumerate(drawings[index].get("items") or ())
                if item_index in indices
                for point in (
                    (_point(item[1]), _point(item[2]))
                    if item[0] == "l"
                    else tuple(_point(value) for value in item[1:5])
                    if item[0] == "c"
                    else ()
                )
            ),
        )
        for index, indices in sorted(by_drawing.items())
    )
    alternatives = [AlternativaClasseSimbolo(classe="ESTAI", subtipo=guy.variant)]
    if guy.variant in {"ancora", "poste_poste"}:
        alternatives.extend(
            (
                AlternativaClasseSimbolo(classe="ESTAI", subtipo=f"{guy.variant}_MT"),
                AlternativaClasseSimbolo(classe="ESTAI", subtipo=f"{guy.variant}_AT"),
            )
        )
    attrs = (
        ("familia_inventario", "family-f02-14"),
        (
            "familias_possiveis",
            json.dumps(
                ("family-f02-14", "family-f02-15")
                if guy.variant in {"ancora", "poste_poste"}
                else ("family-f02-14",)
            ),
        ),
        ("variante_grafica", guy.variant),
        ("referencias_possiveis", json.dumps(_references(guy.variant))),
        ("componentes", json.dumps(components, ensure_ascii=False)),
        ("suportes_possiveis", json.dumps(supports, ensure_ascii=False)),
        ("vinculo", "mecanico_possivel"),
        ("conectividade_eletrica", False),
        ("cardinalidade", "indeterminada"),
        ("quantidade_ativos", None),
        ("situacao_indeterminada", True),
        ("origem_simbologia", _SOURCE),
    )
    return ObservacaoSimbolo(
        fonte=source,
        metodo_assinatura=profile.assinatura(),
        geometria=_geometry(page, guy.axis),
        alternativas=tuple(alternatives),
        score_bruto=None,
        primitivas=primitives,
        situacao=None,
        atributos=tuple(sorted(attrs)),
        conteudo_bruto=None,
    )


def observar_estais(
    page: Any,
    *,
    documento_id: str,
    documento_sha256: str,
    pagina_numero: int,
) -> ResultadoMetodoSimbolos:
    """Observe estais na base, mesmo sem rótulo ou suporte desenhado.

    O chamador fornece e confere o SHA-256 do PDF. Não detecção declara só a
    saída deste método e nunca ausência física de estai.
    """
    if not all(
        math.isfinite(float(value)) and float(value) > 0
        for value in (page.rect.width, page.rect.height)
    ):
        raise ValueError("Página deve possuir dimensões positivas finitas")
    profile = perfil_estais()
    source = FonteObservacaoSimbolo(
        documento_id=documento_id,
        documento_sha256=documento_sha256,
        pagina_numero=pagina_numero,
        camada="base",
    )
    drawings = _inherit_clipping(_base_drawings(page))
    strokes, hooks, rings = _extract(drawings)
    guys = _find_guys(strokes, hooks, rings)
    observations = tuple(_observation(page, guy, drawings, source, profile) for guy in guys)
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
