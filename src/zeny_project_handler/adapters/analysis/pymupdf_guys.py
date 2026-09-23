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

_VERSION = "e06-estais-v1"
_SOURCE = "cemig-eo-r3:it-eo-008:f02:inventario-v1"
_Point = tuple[float, float]
_Source = tuple[int, int]


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


def _extract(drawings: tuple[dict[str, Any], ...]) -> tuple[tuple[_Stroke, ...], tuple[_Hook, ...]]:
    strokes: list[_Stroke] = []
    hooks: list[_Hook] = []
    for drawing_index, drawing in enumerate(drawings):
        # The line items of a filled path are contour instructions, not visible
        # strokes. Alpha zero and white on the normal white PDF page add no ink.
        if str(drawing.get("type") or "") not in {"s", "fs"}:
            continue
        opacity = drawing.get("stroke_opacity")
        if opacity is not None and float(opacity) <= 0.01:
            continue
        color = _color(drawing.get("color"))
        if color is not None and color and min(color) >= 0.985:
            continue
        layer = str(drawing.get("layer") or "")
        clip = drawing.get("scissor")
        items = tuple(drawing.get("items") or ())
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
    return tuple(strokes), tuple(hooks)


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
    long = tuple(stroke for stroke in strokes if 26 <= stroke.length <= 700)
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


def _same_ink(first: _Stroke, second: _Stroke) -> bool:
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


def _terminal_anchor(axis: _Axis, strokes: tuple[_Stroke, ...]) -> _Terminal | None:
    endpoint = axis.end
    direction = _unit(axis.start, axis.end)
    branches: list[tuple[_Stroke, _Point, _Point]] = []
    for stroke in strokes:
        if (
            stroke.source in {member.source for member in axis.strokes}
            or stroke.layer != axis.layer
        ):
            continue
        if not 9 <= stroke.length <= min(75, axis.length * 0.42):
            continue
        near, tip = (
            (stroke.start, stroke.end)
            if math.dist(stroke.start, endpoint) <= math.dist(stroke.end, endpoint)
            else (stroke.end, stroke.start)
        )
        if math.dist(near, endpoint) > max(2.0, min(5.0, axis.length * 0.035)):
            continue
        vector = _unit(near, tip)
        projection = _dot(direction, vector)
        lateral = abs(_cross(direction, vector))
        forward_fork = 0.25 <= projection <= 0.9 and lateral >= 0.25
        backward_fork = -0.995 <= projection <= -0.25 and lateral >= 0.14
        if not (forward_fork or backward_fork):
            continue
        branches.append((stroke, near, tip))
    for index, first in enumerate(branches):
        for second in branches[index + 1 :]:
            if not all(
                _same_ink(member, tine) for member in axis.strokes for tine in (first[0], second[0])
            ):
                continue
            v1, v2 = _unit(first[1], first[2]), _unit(second[1], second[2])
            if _cross(direction, v1) * _cross(direction, v2) >= 0:
                continue
            if not 0.72 <= first[0].length / second[0].length <= 1.4:
                continue
            projection1, projection2 = _dot(direction, v1), _dot(direction, v2)
            if projection1 * projection2 <= 0 or not 0.6 <= projection1 / projection2 <= 1.7:
                continue
            tip_middle = ((first[2][0] + second[2][0]) / 2, (first[2][1] + second[2][1]) / 2)
            tip_span = math.dist(first[2], second[2])
            crossbars = tuple(
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
            # Dimension extension lines protrude much farther than the fork.
            if any(stroke.length > tip_span * 1.6 for stroke in crossbars):
                continue
            # A second extension line at the other end makes a dimension mark,
            # even when the fork points back along the axis.
            extensions = tuple(
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
            if len(extensions) == 2:
                continue
            cap = min(crossbars, key=lambda stroke: stroke.source) if crossbars else None
            if cap is not None:
                closures = (
                    max(math.dist(cap.start, first[2]), math.dist(cap.end, second[2])),
                    max(math.dist(cap.start, second[2]), math.dist(cap.end, first[2])),
                )
                # A closed triangular arrowhead is a directed mark, not a guy.
                if min(closures) <= max(1.0, tip_span * 0.08):
                    continue
            # Two outgoing continuations indicate a branched conductor.
            outward = direction if projection1 > 0 else (-direction[0], -direction[1])
            continued = any(
                stroke.layer == axis.layer
                and stroke.source not in {member.source for member in axis.strokes}
                and stroke.source not in {first[0].source, second[0].source}
                and (cap is None or stroke.source != cap.source)
                and stroke.length > min(first[0].length, second[0].length) * 0.8
                and _extends_beyond(stroke, tip, outward, min(first[0].length, second[0].length))
                for tip in (first[2], second[2])
                for stroke in strokes
            )
            if continued:
                continue
            return _Terminal(
                "ancora",
                tuple(sorted((first[0].source, second[0].source, *((cap.source,) if cap else ())))),
                (endpoint, first[2], second[2], *((cap.start, cap.end) if cap else ())),
            )
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


def _parallel_corridor(axis: _Axis, strokes: tuple[_Stroke, ...]) -> bool:
    """Recognize other conductors beside an anchor-like shaft.

    Coverage is assembled from collinear fragments, since dashed network
    linework can be emitted as many short vector strokes. Coincident
    overprinting of an isolated guy is deliberately excluded by offset.
    """
    direction = _unit(axis.start, axis.end)
    members = {stroke.source for stroke in axis.strokes}
    shaft_width = max((stroke.width or 0 for stroke in axis.strokes), default=0)
    neighbors: list[tuple[float, float, float, bool]] = []
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
    if not neighbors:
        return False
    groups: list[list[tuple[float, float, float, bool]]] = []
    for neighbor in sorted(neighbors):
        if groups and abs(neighbor[0] - groups[-1][-1][0]) <= 3.5:
            groups[-1].append(neighbor)
        else:
            groups.append([neighbor])
    substantial = 0
    for group in groups:
        intervals = sorted((first, last) for _, first, last, _ in group)
        merged: list[list[float]] = []
        for first, last in intervals:
            if merged and first <= merged[-1][1] + 1:
                merged[-1][1] = max(last, merged[-1][1])
            else:
                merged.append([first, last])
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


def _find_guys(strokes: tuple[_Stroke, ...], hooks: tuple[_Hook, ...]) -> tuple[_Guy, ...]:
    found: dict[tuple[_Source, ...], _Guy] = {}
    all_index = _StrokeIndex(strokes)
    short_index = _StrokeIndex(strokes, max_length=85)
    long_index = _StrokeIndex(strokes, min_length=26)
    axes = _axes(strokes)
    oriented = (
        axis
        for candidate in axes
        for axis in (
            candidate,
            _Axis(tuple(reversed(candidate.points)), candidate.strokes, candidate.gap),
        )
    )
    for axis in oriented:
        local = short_index.rectangle(_bounds(axis.points))
        if axis.gap > 1.5 and not _cut_markers(axis, local):
            continue
        # A long fence has many repeated crossbars: it is not a single T-T guy.
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
        if on_axis > 3:
            continue
        start_bar = _terminal_bar(axis, True, local)
        end_bar = _terminal_bar(axis, False, local)
        start_hook = _terminal_hook(axis, True, hooks)
        end_hook = _terminal_hook(axis, False, hooks)
        anchor = _terminal_anchor(axis, local)
        cut = _cut_markers(axis, local)
        if anchor and not start_bar and not start_hook and not end_hook:
            guy = _Guy("ancora", axis, (anchor,))
        elif (
            start_bar
            and end_bar
            and not start_hook
            and not end_hook
            and min(math.dist(*start_bar.points), math.dist(*end_bar.points)) >= axis.length * 0.1
            and not _interior_bar(axis, local)
            and not _parallel_bundle(axis, long_index.rectangle(_bounds(axis.points)))
            and not _parallel_corridor(axis, all_index.rectangle(_bounds(axis.points)))
        ):
            guy = _Guy("cruzeta_cruzeta", axis, (start_bar, end_bar))
        elif start_hook and end_hook and not start_bar and not end_bar:
            guy = _Guy("poste_poste", axis, (start_hook, end_hook))
        elif (start_bar and end_hook and not end_bar and not start_hook) or (
            start_hook and end_bar and not start_bar and not end_hook
        ):
            terminals = tuple(
                terminal
                for terminal in ((start_bar, end_hook) if start_bar else (start_hook, end_bar))
                if terminal is not None
            )
            guy = _Guy("cruzeta_poste_seccionado" if cut else "cruzeta_poste", axis, terminals, cut)
        else:
            continue
        # Complete axes win over their fragments; overprinting only contributes
        # redundant sources and must not multiply the observation.
        found[guy.sources] = guy
    ordered = sorted(
        found.values(), key=lambda guy: (-guy.axis.length, guy.axis.start, guy.sources)
    )
    selected: list[_Guy] = []
    for guy in ordered:
        if guy.variant == "ancora" and (
            _radial_hub(guy.axis, strokes)
            or _parallel_corridor(guy.axis, all_index.rectangle(_bounds(guy.axis.points)))
        ):
            continue
        core = {source for terminal in guy.terminals for source in terminal.sources}
        if any(_same_mark(guy, other, core) for other in selected):
            continue
        selected.append(guy)
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
    strokes, hooks = _extract(drawings)
    guys = _find_guys(strokes, hooks)
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
