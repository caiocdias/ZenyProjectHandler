# mypy: disable-error-code="no-untyped-call"
"""Reconhecimento geométrico de equipamentos representados apenas por símbolos."""

from __future__ import annotations

import json
import math
from bisect import bisect_left, bisect_right, insort
from dataclasses import dataclass, replace
from decimal import Decimal
from itertools import pairwise
from typing import Any

import pymupdf

from zeny_project_handler.domain.analysis import OrigemObjetoPdf
from zeny_project_handler.domain.enums import SituacaoProjeto, TipoEvidencia
from zeny_project_handler.ports.analysis import CandidatoEvidenciaDocumento

from .pymupdf_support import _box_geometry, _extras

_SYMBOL_SOURCE = "SIMBOLOGIA.pdf"
_SYMBOL_CONFIDENCE = Decimal("0.88")
_MAXIMUM_PRIMITIVE_LENGTH = 60.0
_ANGLE_TOLERANCE = math.radians(11)
_SYMBOL_VERSION = "1.19.3:vetorial-5"
_SYMBOL_NORMALIZATIONS = frozenset({"grouping", "fragments", "scale", "styles"})


class _PrimitiveIndex:
    """Multiscale spatial lookup without candidate caps."""

    def __init__(self, primitives: tuple[_VectorPrimitive, ...] = ()) -> None:
        self.cells: dict[int, dict[int, dict[int, list[_VectorPrimitive]]]] = {}
        self.columns: dict[int, list[int]] = {}
        self.rows: dict[tuple[int, int], list[int]] = {}
        for primitive in primitives:
            self.add(primitive)

    def add(self, primitive: _VectorPrimitive) -> None:
        level = math.floor(math.log2(max(primitive.major_length, 0.01)))
        size = 2.0**level
        x, y = math.floor(primitive.center[0] / size), math.floor(primitive.center[1] / size)
        columns = self.cells.setdefault(level, {})
        if x not in columns:
            columns[x] = {}
            insort(self.columns.setdefault(level, []), x)
            self.rows[level, x] = []
        if y not in columns[x]:
            columns[x][y] = []
            insort(self.rows[level, x], y)
        columns[x][y].append(primitive)

    def near(
        self, center: tuple[float, float], radius: float, *, extent: bool = False
    ) -> tuple[_VectorPrimitive, ...]:
        result: list[_VectorPrimitive] = []
        for level, cells in self.cells.items():
            size = 2.0**level
            reach = radius + (size if extent else 0)
            x0, x1 = math.floor((center[0] - reach) / size), math.floor((center[0] + reach) / size)
            y0, y1 = math.floor((center[1] - reach) / size), math.floor((center[1] + reach) / size)
            columns = self.columns[level]
            groups = (
                cells[x][y]
                for x in columns[bisect_left(columns, x0) : bisect_right(columns, x1)]
                for y in self.rows[level, x][
                    bisect_left(self.rows[level, x], y0) : bisect_right(self.rows[level, x], y1)
                ]
            )
            result.extend(
                item
                for group in groups
                for item in group
                if abs(item.center[0] - center[0]) <= reach
                and abs(item.center[1] - center[1]) <= reach
            )
        return tuple(result)


@dataclass(frozen=True, slots=True)
class _VectorPrimitive:
    index: int
    bounds: Any
    center: tuple[float, float]
    angle: float
    major_length: float
    minor_length: float
    color: str
    linear: bool
    rectangular: bool
    sources: tuple[tuple[int, int], ...] = ()
    layer: str = ""


@dataclass(frozen=True, slots=True)
class _SymbolMatch:
    code: str
    class_code: str
    situation: SituacaoProjeto | None
    color: str
    primitives: tuple[_VectorPrimitive, ...]
    confidence: Decimal = _SYMBOL_CONFIDENCE

    @property
    def center(self) -> tuple[float, float]:
        bounds = _union_bounds(self.primitives)
        return (bounds.x0 + bounds.x1) / 2, (bounds.y0 + bounds.y1) / 2


def _extract_symbolic_equipment(
    page: Any,
    page_number: int,
    *,
    normalizations: frozenset[str] | None = None,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    """Converta assinaturas vetoriais conhecidas em evidências semânticas."""
    enabled = _SYMBOL_NORMALIZATIONS if normalizations is None else normalizations
    if enabled - _SYMBOL_NORMALIZATIONS:
        raise ValueError("Normalização vetorial desconhecida")
    drawings = _base_drawings(page)
    drawings = _inherit_clipping(drawings)
    primitives = _normalized_primitives(drawings, enabled)
    matches = _deduplicate_matches(
        (
            *_ground_and_mt_arrester_matches(primitives, scale="scale" in enabled),
            *_bt_arrester_matches(primitives, scale="scale" in enabled),
        )
    )
    return tuple(
        CandidatoEvidenciaDocumento(
            chave_estavel=(
                f"p{page_number}:simbolo-vetorial:{match.class_code.casefold()}:"
                + "-".join(f"{drawing}.{item}" for drawing, item in _match_sources(match))
            ),
            pagina_numero=page_number,
            tipo=TipoEvidencia.VETOR,
            geometria=_box_geometry(page, _union_bounds(match.primitives)),
            origem_pdf=OrigemObjetoPdf(),
            conteudo_bruto=match.code,
            atributos_extraidos=_extras(
                classe_equipamento=match.class_code,
                confianca=match.confidence,
                cor=match.color,
                origem_simbologia=_SYMBOL_SOURCE,
                reconhecido_por_simbologia=True,
                situacao_projeto_forcada=match.situation.value if match.situation else None,
                situacao_indeterminada=match.situation is None,
                simbolo_cemig=match.code,
                vetores_origem=",".join(
                    str(index) for index in sorted({source[0] for source in _match_sources(match)})
                ),
                primitives_origem=json.dumps(_match_sources(match)),
                simbolo_limites_originais=json.dumps(list(_union_bounds(match.primitives))),
                normalizacoes_simbolo=",".join(sorted(enabled)),
                versao_simbolo=_SYMBOL_VERSION,
                recorte_vetorial_limitado=any(
                    drawings[index].get("scissor") is not None for index, _ in _match_sources(match)
                ),
                estilos_originais=json.dumps(
                    {
                        str(index): {
                            "color": drawings[index].get("color"),
                            "fill": drawings[index].get("fill"),
                            "width": drawings[index].get("width"),
                            "dashes": drawings[index].get("dashes"),
                            "layer": drawings[index].get("layer"),
                        }
                        for index in sorted({source[0] for source in _match_sources(match)})
                    }
                ),
            ),
        )
        for match in matches
    )


def _primitive_from_drawing(
    index: int, drawing: dict[str, Any], *, scale: bool = False, styles: bool = False
) -> _VectorPrimitive | None:
    items = tuple(drawing.get("items") or ())
    points = _drawing_points(items)
    if len(points) < 2:
        return None
    color = _canonical_symbol_color(drawing.get("color"), drawing.get("fill"), styles=styles)
    if color is None:
        return None
    bounds = drawing.get("rect") or drawing.get("scissor")
    if bounds is None:
        return None
    angle, major, minor = _principal_axis(points)
    if major <= 0 or (not scale and major > _MAXIMUM_PRIMITIVE_LENGTH):
        return None
    return _VectorPrimitive(
        index=index,
        bounds=bounds,
        center=((bounds.x0 + bounds.x1) / 2, (bounds.y0 + bounds.y1) / 2),
        angle=angle,
        major_length=major,
        minor_length=minor,
        color=color,
        linear=(all(item[0] == "l" for item in items) and minor <= 0.01)
        or (_is_rectangle(items) and minor <= major * 0.1),
        rectangular=_is_rectangle(items),
        layer=str(drawing.get("layer") or ""),
    )


def _match_sources(match: _SymbolMatch) -> tuple[tuple[int, int], ...]:
    return tuple(sorted({source for item in match.primitives for source in item.sources}))


def _base_drawings(page: Any) -> tuple[dict[str, Any], ...]:
    """Keep original drawing indices while excluding annotation appearances.

    PyMuPDF's drawing API runs the complete page, including annotations. A
    contents-only copy is needed only when annotations exist; no source is edited.
    """
    drawings = tuple(page.get_drawings(extended=True))
    if not hasattr(page, "annot_xrefs") or not page.annot_xrefs():
        return drawings
    # Copying only a page with insert_pdf can alter transparency groups/OCGs.
    # Retaining the full document catalog keeps the content hierarchy identical.
    with pymupdf.open(stream=page.parent.tobytes(no_new_id=True), filetype="pdf") as base:
        base_page = base[page.number]
        base.xref_set_key(base_page.xref, "Annots", "[]")
        base_page = base.reload_page(base_page)
        clean = tuple(base_page.get_drawings(extended=True))
    # Removing appearances may remove a page-wide transparency group and change
    # levels/clip records. Painted contents retain seqno and exact path/style.
    painted_types = {"s", "f", "fs"}
    originals: dict[int, dict[str, Any]] = {}
    for drawing in drawings:
        if drawing.get("type") in painted_types:
            sequence = int(drawing["seqno"])
            if sequence in originals:
                raise ValueError("Sequência vetorial original ambígua")
            originals[sequence] = drawing
    retained: set[int] = set()
    keys = (
        "items",
        "type",
        "color",
        "fill",
        "width",
        "layer",
        "dashes",
        "stroke_opacity",
        "fill_opacity",
    )
    for drawing in clean:
        if drawing.get("type") not in painted_types:
            continue
        sequence = int(drawing["seqno"])
        original = originals.get(sequence)
        if original is None or any(drawing.get(key) != original.get(key) for key in keys):
            raise ValueError("Não foi possível preservar índices vetoriais da camada base")
        retained.add(sequence)
    return tuple(
        drawing
        if drawing.get("type") not in painted_types or drawing.get("seqno") in retained
        else {**drawing, "items": ()}
        for drawing in drawings
    )


def _inherit_clipping(drawings: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    """Resolve extended drawing hierarchy; clip records are not painted paths."""
    stack: list[tuple[int, Any]] = []
    result = []
    for drawing in drawings:
        level = int(drawing.get("level", 0))
        stack = [(depth, bounds) for depth, bounds in stack if depth < level]
        kind = str(drawing.get("type", ""))
        clip = drawing.get("scissor")
        inherited = pymupdf.Rect(stack[-1][1]) if stack else None
        if clip is not None:
            inherited = pymupdf.Rect(clip) if inherited is None else inherited & clip
        if kind.startswith("clip"):
            if inherited is not None:
                stack.append((level, inherited))
            result.append({**drawing, "items": ()})
        elif kind == "group":
            result.append({**drawing, "items": ()})
        else:
            result.append({**drawing, "scissor": inherited})
    return tuple(result)


def _normalized_primitives(
    drawings: tuple[dict[str, Any], ...], enabled: frozenset[str]
) -> tuple[_VectorPrimitive, ...]:
    primitives: list[_VectorPrimitive] = []
    for drawing_index, drawing in enumerate(drawings):
        items = tuple(drawing.get("items") or ())
        # Filled arbitrary contours may be letters. Only rectangles and stroked
        # linework can be decomposed without inventing independent bars.
        split = (
            "grouping" in enabled
            and not _is_rectangle(items)
            and (drawing.get("fill") is None or all(item[0] in {"re", "qu"} for item in items))
        )
        groups = (
            _connected_item_groups(items, close_path=bool(drawing.get("closePath")))
            if split
            else ((tuple(range(len(items))), items),)
        )
        for source_items, group in groups:
            points = _drawing_points(group)
            if not points:
                continue
            bounds = pymupdf.Rect(
                min(x for x, _ in points),
                min(y for _, y in points),
                max(x for x, _ in points),
                max(y for _, y in points),
            )
            clip = drawing.get("scissor")
            if clip is not None and (
                bounds.x0 < clip.x0 - 0.001
                or bounds.x1 > clip.x1 + 0.001
                or bounds.y0 < clip.y0 - 0.001
                or bounds.y1 > clip.y1 + 0.001
            ):
                continue
            primitive = _primitive_from_drawing(
                len(primitives),
                {**drawing, "items": group, "rect": bounds},
                scale="scale" in enabled,
                styles="styles" in enabled,
            )
            if primitive is not None:
                sources = tuple((drawing_index, index) for index in source_items)
                primitives.append(replace(primitive, sources=sources))
    if "fragments" in enabled:
        original_count = len(primitives)
        merged = _merge_fragments(primitives)
        original_sources = {original.sources for original in primitives}
        # A join is an alternative support, not permission to erase nearby bars.
        primitives += [
            item
            for item in merged
            if len(item.sources) > 1 and item.sources not in original_sources
        ]
        primitives = [replace(item, index=index) for index, item in enumerate(primitives)]
        # Contacts must see reconstructed terminal bars before identifying
        # redundant stems. Every original item remains in their source union.
        primitives = _coalesce_overprinted_lines(
            primitives, scale="scale" in enabled, original_count=original_count
        )
        primitives = [replace(item, index=index) for index, item in enumerate(primitives)]
    if "grouping" in enabled:
        primitives = _recover_rectangles(primitives)
    return tuple(replace(item, index=index) for index, item in enumerate(primitives))


def _connected_item_groups(
    items: tuple[Any, ...],
    *,
    close_path: bool = False,
) -> tuple[tuple[tuple[int, ...], tuple[Any, ...]], ...]:
    """Split disconnected paths, never turn a connected outline into symbol bars."""
    groups: list[tuple[tuple[int, ...], tuple[Any, ...]]] = []
    indices: list[int] = []
    path: list[Any] = []
    endpoint: tuple[float, float] | None = None
    for index, item in enumerate(items):
        points = _drawing_points((item,))
        connected = (
            item[0] in {"l", "c"}
            and endpoint is not None
            and math.dist(endpoint, points[0]) <= 0.001
        )
        if not connected and path:
            groups.append((tuple(indices), tuple(path)))
            indices, path = [], []
        indices.append(index)
        path.append(item)
        endpoint = points[-1] if item[0] in {"l", "c"} else None
    if path:
        groups.append((tuple(indices), tuple(path)))
    result = []
    for position, (source_items, group) in enumerate(groups):
        points = _drawing_points(group)
        closed = len(group) >= 3 and (
            math.dist(points[0], points[-1]) <= 0.001
            or (close_path and position == len(groups) - 1)
        )
        if closed or any(item[0] == "c" for item in group):
            result.append((source_items, group))
        else:
            result.extend(
                ((index,), (item,)) for index, item in zip(source_items, group, strict=True)
            )
    return tuple(result)


def _merge_fragments(primitives: list[_VectorPrimitive]) -> list[_VectorPrimitive]:
    """Join collinear touching fragments, preserving every original item reference."""
    selected: dict[int, _VectorPrimitive] = {}
    spatial = _PrimitiveIndex()
    for primitive in primitives:
        if not primitive.linear:
            selected[id(primitive)] = primitive
            continue
        current = primitive
        while True:
            compatible = next(
                (
                    id(other)
                    for other in spatial.near(
                        current.center, current.major_length * 0.7, extent=True
                    )
                    if id(other) in selected and _fragments_connect(current, other)
                ),
                None,
            )
            if compatible is None:
                break
            other = selected.pop(compatible)
            axis = math.cos(current.angle), math.sin(current.angle)
            points = tuple(
                (
                    item.center[0] + sign * axis[0] * item.major_length / 2,
                    item.center[1] + sign * axis[1] * item.major_length / 2,
                )
                for item in (current, other)
                for sign in (-1, 1)
            )
            positions = [x * axis[0] + y * axis[1] for x, y in points]
            low, high = (
                points[positions.index(min(positions))],
                points[positions.index(max(positions))],
            )
            bounds = _union_bounds((current, other))
            current = replace(
                current,
                bounds=bounds,
                center=((low[0] + high[0]) / 2, (low[1] + high[1]) / 2),
                major_length=max(positions) - min(positions),
                sources=tuple(sorted(set(current.sources + other.sources))),
            )
        selected[id(current)] = current
        spatial.add(current)
    return list(selected.values())


def _coalesce_overprinted_lines(
    primitives: list[_VectorPrimitive], *, scale: bool, original_count: int
) -> list[_VectorPrimitive]:
    """Coalesce redundant strokes sharing an endpoint; keep intersecting neighbors."""
    contacts: dict[int, set[tuple[tuple[int, int], ...]]] = {}
    for match in (
        *_ground_and_mt_arrester_matches(tuple(primitives), scale=scale),
        *_bt_arrester_matches(tuple(primitives), scale=scale),
    ):
        contacts.setdefault(match.primitives[0].index, set()).add(match.primitives[1].sources)
    selected: dict[int, _VectorPrimitive] = {}
    spatial = _PrimitiveIndex()
    for primitive in primitives:
        current = primitive
        if current.linear and current.index < original_count:
            for other in spatial.near(current.center, current.major_length / 2, extent=True):
                if (
                    id(other) not in selected
                    or not contacts.get(current.index, set()) & contacts.get(other.index, set())
                    or not _same_terminal_stroke(current, other)
                ):
                    continue
                selected.pop(id(other))
                longer = current if current.major_length >= other.major_length else other
                current = replace(
                    longer, sources=tuple(sorted(set(current.sources + other.sources)))
                )
        selected[id(current)] = current
        if current.linear and current.index < original_count:
            spatial.add(current)
    return list(selected.values())


def _same_terminal_stroke(first: _VectorPrimitive, second: _VectorPrimitive) -> bool:
    if first.color != second.color or first.layer != second.layer or not second.linear:
        return False
    if _angle_difference(first.angle, second.angle) > 0.001:
        return False
    first_ends, second_ends = _endpoints(first), _endpoints(second)
    tolerance = max(first.major_length, second.major_length) * 0.001
    if min(math.dist(a, b) for a in first_ends for b in second_ends) > tolerance:
        return False
    axis = math.cos(first.angle), math.sin(first.angle)
    offset, lateral = _relative_position(first.center, second.center, axis, (-axis[1], axis[0]))
    return abs(lateral) <= tolerance and (
        abs(offset) + min(first.major_length, second.major_length) / 2
        <= max(first.major_length, second.major_length) / 2 + tolerance
    )


def _fragments_connect(first: _VectorPrimitive, second: _VectorPrimitive) -> bool:
    if not second.linear or first.color != second.color or first.layer != second.layer:
        return False
    if _angle_difference(first.angle, second.angle) > 0.01:
        return False
    axis = math.cos(first.angle), math.sin(first.angle)
    offset, lateral = _relative_position(first.center, second.center, axis, (-axis[1], axis[0]))
    tolerance = min(first.major_length, second.major_length) * 0.2
    return (
        abs(lateral) <= max(0.001, min(first.major_length, second.major_length) * 0.005)
        and abs(offset) <= (first.major_length + second.major_length) / 2 + tolerance
    )


def _is_rectangle(items: tuple[Any, ...]) -> bool:
    if len(items) == 4 and all(item[0] == "l" for item in items):
        points = tuple((float(item[1].x), float(item[1].y)) for item in items)
        edges = tuple(
            (float(item[2].x) - point[0], float(item[2].y) - point[1])
            for item, point in zip(items, points, strict=True)
        )
        for index, (dx, dy) in enumerate(edges):
            following = edges[(index + 1) % 4]
            length = math.hypot(dx, dy)
            next_length = math.hypot(*following)
            if min(length, next_length) <= 0:
                return False
            endpoint = (points[index][0] + dx, points[index][1] + dy)
            if math.dist(endpoint, points[(index + 1) % 4]) > min(length, next_length) * 0.001:
                return False
            if abs(dx * following[0] + dy * following[1]) > length * next_length * 0.01:
                return False
        return True
    if len(items) != 1:
        return False
    if items[0][0] == "re":
        return True
    if items[0][0] != "qu":
        return False
    quad = pymupdf.Quad(items[0][1])
    return bool(quad.is_rectangular)


def _endpoints(item: _VectorPrimitive) -> tuple[tuple[float, float], tuple[float, float]]:
    dx = math.cos(item.angle) * item.major_length / 2
    dy = math.sin(item.angle) * item.major_length / 2
    return ((item.center[0] - dx, item.center[1] - dy), (item.center[0] + dx, item.center[1] + dy))


def _recover_rectangles(primitives: list[_VectorPrimitive]) -> list[_VectorPrimitive]:
    """Keep closed outlines intact across drawing boundaries; classify rectangles."""
    lines = [item for item in primitives if item.linear and not item.rectangular]
    spatial = _PrimitiveIndex(tuple(lines))
    bodies: list[_VectorPrimitive] = []
    consumed: set[int] = set()
    for first in lines:
        if first.index in consumed:
            continue
        start, end = _endpoints(first)
        tolerance = max(0.001, first.major_length * 0.001)
        chain = [first]
        points = [start, end]
        for _ in range(len(lines)):
            options = []
            for line in spatial.near(points[-1], tolerance, extent=True):
                if (
                    line in chain
                    or any(set(line.sources) & set(member.sources) for member in chain)
                    or line.color != first.color
                    or line.layer != first.layer
                    or line.index in consumed
                ):
                    continue
                for near, far in (_endpoints(line), tuple(reversed(_endpoints(line)))):
                    if math.dist(points[-1], near) <= tolerance:
                        options.append((line, far))
            if len(options) != 1:
                break
            line, far = options[0]
            chain.append(line)
            points.append(far)
            if math.dist(points[-1], start) <= tolerance:
                break
        if len(chain) < 3 or math.dist(points[-1], start) > tolerance:
            continue
        items = tuple(
            ("l", pymupdf.Point(points[index]), pymupdf.Point(points[index + 1]))
            for index in range(len(chain))
        )
        rectangular = _is_rectangle(items)
        angle, major, minor = _principal_axis(tuple(points[:-1]))
        bounds = _union_bounds(tuple(chain))
        bodies.append(
            replace(
                first,
                bounds=bounds,
                center=((bounds.x0 + bounds.x1) / 2, (bounds.y0 + bounds.y1) / 2),
                angle=angle,
                major_length=major,
                minor_length=minor,
                linear=rectangular and minor <= major * 0.1,
                rectangular=rectangular,
                sources=tuple(sorted({source for line in chain for source in line.sources})),
            )
        )
        consumed.update(item.index for item in chain)
    return [item for item in primitives if item.index not in consumed] + bodies


def _drawing_points(items: tuple[Any, ...]) -> tuple[tuple[float, float], ...]:
    points: list[tuple[float, float]] = []
    for item in items:
        operation = str(item[0])
        raw_points: tuple[Any, ...] = ()
        if operation == "l":
            raw_points = tuple(item[1:3])
        elif operation == "c":
            raw_points = tuple(item[1:5])
        elif operation == "re":
            rectangle = pymupdf.Rect(item[1])
            raw_points = (rectangle.tl, rectangle.tr, rectangle.br, rectangle.bl)
        elif operation == "qu":
            quad = pymupdf.Quad(item[1])
            raw_points = (quad.ul, quad.ur, quad.lr, quad.ll)
        points.extend((float(point.x), float(point.y)) for point in raw_points)
    return tuple(points)


def _principal_axis(points: tuple[tuple[float, float], ...]) -> tuple[float, float, float]:
    mean_x = sum(point[0] for point in points) / len(points)
    mean_y = sum(point[1] for point in points) / len(points)
    xx = sum((point[0] - mean_x) ** 2 for point in points)
    yy = sum((point[1] - mean_y) ** 2 for point in points)
    xy = sum((point[0] - mean_x) * (point[1] - mean_y) for point in points)
    angle = 0.5 * math.atan2(2 * xy, xx - yy)
    axis = math.cos(angle), math.sin(angle)
    normal = -axis[1], axis[0]
    major_values = [point[0] * axis[0] + point[1] * axis[1] for point in points]
    minor_values = [point[0] * normal[0] + point[1] * normal[1] for point in points]
    major = max(major_values) - min(major_values)
    minor = max(minor_values) - min(minor_values)
    if minor > major:
        major, minor = minor, major
        angle += math.pi / 2
    return angle % math.pi, major, minor


def _canonical_symbol_color(stroke: object, fill: object, *, styles: bool = False) -> str | None:
    for raw in (stroke, fill):
        rgb = _rgb255(raw)
        if rgb is None:
            continue
        red, green, blue = rgb
        if max(rgb) <= 40:
            return "#000000"
        if styles and max(rgb) - min(rgb) <= 8 and max(rgb) < 245:
            return "#000000"
        if red >= 96 and red >= green * 2 and red >= blue * 2:
            return "#FF0000"
        if green >= 64 and green >= red * 2 and green >= blue * 2:
            return "#008000"
    return None


def _rgb255(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, (tuple, list)) or len(value) not in (1, 3):
        return None
    if len(value) == 1:
        value = tuple(value) * 3
    channels = tuple(round(float(channel) * 255) for channel in value[:3])
    return channels[0], channels[1], channels[2]


def _ground_and_mt_arrester_matches(
    primitives: tuple[_VectorPrimitive, ...],
    *,
    scale: bool = False,
) -> tuple[_SymbolMatch, ...]:
    lines = tuple(
        item for item in primitives if item.linear and item.major_length >= (0.01 if scale else 1)
    )
    matches: list[_SymbolMatch] = []
    spatial = _PrimitiveIndex(lines)
    for stem in lines:
        if stem.major_length < (0.01 if scale else 6):
            continue
        axis = math.cos(stem.angle), math.sin(stem.angle)
        normal = -axis[1], axis[0]
        bars_by_side: dict[int, list[_VectorPrimitive]] = {-1: [], 1: []}
        for candidate in spatial.near(stem.center, stem.major_length * 1.7):
            if (
                candidate.index == stem.index
                or candidate.color != stem.color
                or candidate.layer != stem.layer
            ):
                continue
            if abs(_angle_difference(stem.angle, candidate.angle) - math.pi / 2) > (
                _ANGLE_TOLERANCE
            ):
                continue
            offset, lateral = _relative_position(stem.center, candidate.center, axis, normal)
            if (
                abs(lateral)
                <= max(stem.major_length * 0.1 if scale else 1.5, candidate.major_length * 0.2)
                and stem.major_length * 0.35 <= abs(offset) <= stem.major_length * 1.35
                and candidate.major_length <= stem.major_length * 1.5
            ):
                bars_by_side[1 if offset > 0 else -1].append(candidate)
        for bars in bars_by_side.values():
            # Whole and fragmented versions of one bar have the same longitudinal
            # position. Prefer the support centered on the stem's axis.
            ordered = sorted(
                bars,
                key=lambda item: (
                    abs(_relative_position(stem.center, item.center, axis, normal)[1]),
                    -item.major_length,
                ),
            )
            bars = []
            for bar in ordered:
                if not any(
                    set(other.sources) & set(bar.sources)
                    or abs(_relative_position(other.center, bar.center, axis, normal)[0])
                    <= stem.major_length * 0.01
                    for other in bars
                ):
                    bars.append(bar)
            bars.sort(
                key=lambda item: abs(_relative_position(stem.center, item.center, axis, normal)[0])
            )
            if bars:
                first = min(
                    bars,
                    key=lambda item: (
                        abs(
                            abs(_relative_position(stem.center, item.center, axis, normal)[0])
                            - stem.major_length / 2
                        ),
                        -item.major_length,
                    ),
                )
                bars = bars[bars.index(first) :]
            if not _ground_bar_signature(stem, bars, axis, normal):
                continue
            code, class_code = (
                ("PARA RAIOS MT", "PARA_RAIOS_MT")
                if len(bars) >= 4
                else ("ATERRAMENTO", "ATERRAMENTO")
            )
            matches.append(
                _SymbolMatch(
                    code=code,
                    class_code=class_code,
                    situation=_situation_from_color(stem.color),
                    color=stem.color,
                    primitives=(stem, *bars),
                )
            )
    return tuple(matches)


def _ground_bar_signature(
    stem: _VectorPrimitive,
    bars: list[_VectorPrimitive],
    axis: tuple[float, float],
    normal: tuple[float, float],
) -> bool:
    """Validate the terminal taper, not merely a count of nearby parallel strokes."""
    if len(bars) < 3:
        return False
    offsets = [abs(_relative_position(stem.center, bar.center, axis, normal)[0]) for bar in bars]
    if abs(offsets[0] - stem.major_length / 2) > stem.major_length * 0.15:
        return False
    if not stem.major_length * 0.3 <= bars[0].major_length <= stem.major_length * 1.5:
        return False
    if bars[0].major_length < max(bar.major_length for bar in bars) * 0.9:
        return False
    if len(bars) == 3 and not (
        bars[0].major_length > bars[1].major_length * 1.1
        and bars[1].major_length > bars[2].major_length * 1.1
    ):
        return False
    gaps = [right - left for left, right in pairwise(offsets)]
    return all(stem.major_length * 0.1 <= gap <= stem.major_length * 0.45 for gap in gaps)


def _bt_arrester_matches(
    primitives: tuple[_VectorPrimitive, ...],
    *,
    scale: bool = False,
) -> tuple[_SymbolMatch, ...]:
    matches: list[_SymbolMatch] = []
    spatial = _PrimitiveIndex(primitives)
    for stem in primitives:
        if not stem.linear or (
            not scale and not 6 <= stem.major_length <= _MAXIMUM_PRIMITIVE_LENGTH
        ):
            continue
        axis = math.cos(stem.angle), math.sin(stem.angle)
        normal = -axis[1], axis[0]
        nearby = tuple(
            candidate
            for candidate in spatial.near(stem.center, stem.major_length * 1.8)
            if candidate.index != stem.index
            and candidate.color == stem.color
            and candidate.layer == stem.layer
            and _is_near_stem_end(stem, candidate, axis, normal)
        )
        bodies = tuple(
            item
            for item in nearby
            if item.rectangular
            and abs(_relative_position(stem.center, item.center, axis, normal)[1])
            <= stem.major_length * 0.1
            and stem.major_length * 0.5 <= item.major_length <= stem.major_length * 1.1
            and 2 <= item.major_length / max(item.minor_length, 0.01) <= 4.5
            and _angle_difference(stem.angle, item.angle) <= 0.2
        )
        diagonals = tuple(
            item
            for item in nearby
            if item.linear
            and stem.major_length * 0.55 <= item.major_length <= stem.major_length * 1.15
            and 0.4 <= _angle_difference(stem.angle, item.angle) <= 1.2
        )
        for body in bodies:
            diagonal = min(
                (
                    item
                    for item in diagonals
                    if math.dist(item.center, body.center) <= stem.major_length * 0.2
                ),
                key=lambda item: math.dist(item.center, body.center),
                default=None,
            )
            if diagonal is None:
                continue
            matches.append(
                _SymbolMatch(
                    code="PARA RAIOS BT",
                    class_code="PARA_RAIOS_BT",
                    situation=_situation_from_color(stem.color),
                    color=stem.color,
                    primitives=(stem, body, diagonal),
                )
            )
    return tuple(matches)


def _is_near_stem_end(
    stem: _VectorPrimitive,
    candidate: _VectorPrimitive,
    axis: tuple[float, float],
    normal: tuple[float, float],
) -> bool:
    offset, lateral = _relative_position(stem.center, candidate.center, axis, normal)
    return (
        stem.major_length * 0.35 <= abs(offset) <= stem.major_length * 1.4
        and abs(lateral) <= stem.major_length
    )


def _relative_position(
    source: tuple[float, float],
    target: tuple[float, float],
    axis: tuple[float, float],
    normal: tuple[float, float],
) -> tuple[float, float]:
    delta = target[0] - source[0], target[1] - source[1]
    return (
        delta[0] * axis[0] + delta[1] * axis[1],
        delta[0] * normal[0] + delta[1] * normal[1],
    )


def _angle_difference(first: float, second: float) -> float:
    difference = abs(first - second) % math.pi
    return min(difference, math.pi - difference)


def _situation_from_color(color: str) -> SituacaoProjeto | None:
    return {
        "#008000": SituacaoProjeto.INSTALAR,
        "#FF0000": SituacaoProjeto.REMOVER,
    }.get(color)


def _deduplicate_matches(matches: tuple[_SymbolMatch, ...]) -> tuple[_SymbolMatch, ...]:
    selected: list[_SymbolMatch] = []
    for match in sorted(
        matches,
        key=lambda item: (
            item.class_code,
            item.center,
            len(item.primitives),
            tuple(primitive.index for primitive in item.primitives),
        ),
    ):
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(selected)
                if existing.class_code == match.class_code
                and existing.situation is match.situation
                and set(existing.primitives[0].sources) & set(match.primitives[0].sources)
                and (len(set(_match_sources(existing)) & set(_match_sources(match))) >= 2)
            ),
            None,
        )
        if duplicate_index is None:
            selected.append(match)
            continue
        existing = selected[duplicate_index]
        if _match_quality(match) < _match_quality(existing):
            selected[duplicate_index] = match
    return tuple(selected)


def _match_scale(match: _SymbolMatch) -> float:
    bounds = _union_bounds(match.primitives)
    return max(float(bounds.width), float(bounds.height), 1.0)


def _match_quality(match: _SymbolMatch) -> tuple[int, float, tuple[int, ...]]:
    return (
        len(match.primitives),
        _match_scale(match),
        tuple(item.index for item in match.primitives),
    )


def _union_bounds(primitives: tuple[_VectorPrimitive, ...]) -> Any:
    # Rect union treats zero-width/height line bounds as empty and discards them.
    # Explicit extrema preserve the actual support of horizontal/vertical symbols.
    return pymupdf.Rect(
        min(item.bounds.x0 for item in primitives),
        min(item.bounds.y0 for item in primitives),
        max(item.bounds.x1 for item in primitives),
        max(item.bounds.y1 for item in primitives),
    )
