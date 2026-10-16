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

_VERSION = "e05-transformadores-v5"
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
    width: float = 0.0

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
            (
                "assinaturas",
                "triangulo,laços-pareados,semicirculos,enrolamentos,"
                "triangulo-haste-externa,anel-poligonal",
            ),
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


@dataclass(frozen=True, slots=True)
class _EstiloDesenho:
    """Atributos de um desenho herdados por cada laço/arco extraído dele."""

    index: int
    layer: str
    color: tuple[float, ...] | None
    fill: tuple[float, ...] | None
    clip: Any


def _tracos_e_curvas(
    items: tuple[Any, ...],
    drawing_index: int,
    layer: str,
    color: tuple[float, ...] | None,
    lines: list[_Line],
    width: float = 0.0,
) -> list[tuple[int, tuple[_Point, ...]]]:
    """Acumula os segmentos em ``lines`` e devolve as curvas cúbicas do desenho."""
    curves: list[tuple[int, tuple[_Point, ...]]] = []
    for item_index, item in enumerate(items):
        operation = item[0]
        if operation == "l":
            start, end = ((float(point.x), float(point.y)) for point in item[1:3])
            if math.dist(start, end) > 0.01:
                lines.append(_Line(start, end, (drawing_index, item_index), layer, color, width))
        elif operation == "c":
            points = tuple((float(point.x), float(point.y)) for point in item[1:5])
            if len(points) == 4:
                curves.append((item_index, points))
        elif operation == "re":
            # A rectangle is context/negative geometry, never a triangular edge.
            continue
    return curves


def _laco_fechado(
    items: tuple[Any, ...],
    curves: list[tuple[int, tuple[_Point, ...]]],
    estilo: _EstiloDesenho,
) -> _Round | None:
    """Laço circular fechado só de curvas; ``None`` devolve as curvas à leitura de arcos."""
    if len(curves) < 3 or any(item[0] == "l" for item in items):
        return None
    sampled = tuple(_bezier_point(group, t) for _, group in curves for t in (0, 0.25, 0.5, 0.75, 1))
    bounds = _bounds(sampled)
    ratio = bounds.width / max(bounds.height, 0.01)
    endpoints = [curves[0][1][0], curves[-1][1][-1]]
    center = _center(bounds)
    radii = tuple(math.dist(point, center) for point in sampled)
    circular = min(radii) >= max(radii) * 0.82
    angular_bins = {
        int((math.atan2(point[1] - center[1], point[0] - center[0]) + math.pi) * 4 / math.pi) % 8
        for point in sampled
    }
    if not (
        0.75 <= ratio <= 1.3
        and bounds.width >= 2
        and math.dist(*endpoints) <= bounds.width * 0.08
        and circular
        and len(angular_bins) >= 7
        and (estilo.clip is None or pymupdf.Rect(estilo.clip).contains(bounds))
    ):
        return None
    return _Round(
        bounds,
        tuple((estilo.index, index) for index, _ in curves),
        estilo.layer,
        estilo.color,
        "loop",
        fill=estilo.fill,
    )


def _arco_curva(
    item_index: int, points: tuple[_Point, ...], estilo: _EstiloDesenho
) -> _Round | None:
    start, first, second, end = points
    chord = math.dist(start, end)
    if chord < 2:
        return None
    midpoint = tuple((start[i] + 3 * first[i] + 3 * second[i] + end[i]) / 8 for i in (0, 1))
    bulge = (
        abs(
            (end[0] - start[0]) * (midpoint[1] - start[1])
            - (end[1] - start[1]) * (midpoint[0] - start[0])
        )
        / chord
    )
    if not 0.12 <= bulge / chord <= 0.8:
        return None
    sampled = tuple(_bezier_point((start, first, second, end), t) for t in (0, 0.25, 0.5, 0.75, 1))
    bounds = _bounds(sampled)
    if estilo.clip is not None and not pymupdf.Rect(estilo.clip).contains(bounds):
        return None
    return _Round(
        bounds,
        ((estilo.index, item_index),),
        estilo.layer,
        estilo.color,
        "arc",
        math.atan2(end[1] - start[1], end[0] - start[0]) % math.pi,
        (
            (end[0] - start[0]) * (midpoint[1] - start[1])
            - (end[1] - start[1]) * (midpoint[0] - start[0])
        )
        / (chord * chord),
        (start, end),
        estilo.fill,
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
        width = float(drawing.get("width") or 0.0)
        curves = _tracos_e_curvas(items, drawing_index, layer, color, lines, width)
        if not curves:
            continue
        estilo = _EstiloDesenho(drawing_index, layer, color, fill, clip)
        loop = _laco_fechado(items, curves, estilo)
        if loop is not None:
            rounds.append(loop)
            continue
        for item_index, points in curves:
            arc = _arco_curva(item_index, points, estilo)
            if arc is not None:
                rounds.append(arc)
    return tuple(lines), tuple(rounds)


def _near_point(first: _Point, second: _Point, scale: float) -> bool:
    return math.dist(first, second) <= max(0.15, min(1.5, scale * 0.045))


def _triangle_axis(
    vertices: tuple[_Point, _Point, _Point],
    core: tuple[_Source, ...],
    lines: tuple[_Line, ...],
    layer: str,
) -> _Line | None:
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
                return line
    return None


_Triangle = tuple[_Point, _Point, _Point]


def _centroide(vertices: _Triangle) -> _Point:
    return (
        sum(point[0] for point in vertices) / 3,
        sum(point[1] for point in vertices) / 3,
    )


def _quase_equilatero(vertices: _Triangle) -> bool:
    """Pictograma de contorno sem eixo: lados parecidos e ângulos internos de 50° a 70°."""
    sides = tuple(math.dist(vertices[index], vertices[index - 1]) for index in range(3))
    if min(sides) <= 0 or max(sides) / min(sides) > 1.2:
        return False
    for index, vertex in enumerate(vertices):
        first, second = vertices[index - 1], vertices[(index + 1) % 3]
        a = (first[0] - vertex[0], first[1] - vertex[1])
        b = (second[0] - vertex[0], second[1] - vertex[1])
        cosine = (a[0] * b[0] + a[1] * b[1]) / (math.hypot(*a) * math.hypot(*b))
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
        if not 50 <= angle <= 70:
            return False
    return True


def _preenchimento_claro(fill: tuple[float, ...] | None) -> bool:
    return fill is None or (len(fill) >= 3 and min(fill[:3]) >= 0.9)


def _dentro_poligono(point: _Point, polygon: tuple[_Point, ...]) -> bool:
    inside = False
    x, y = point
    for index, first in enumerate(polygon):
        second = polygon[index - 1]
        if (first[1] > y) != (second[1] > y):
            crossing = first[0] + (y - first[1]) * (second[0] - first[0]) / (second[1] - first[1])
            if x < crossing:
                inside = not inside
    return inside


def _amostras_internas(vertices: _Triangle, steps: int = 6) -> tuple[_Point, ...]:
    origin, first, second = vertices
    return tuple(
        (
            origin[0] + u * (first[0] - origin[0]) + v * (second[0] - origin[0]),
            origin[1] + u * (first[1] - origin[1]) + v * (second[1] - origin[1]),
        )
        for row in range(steps)
        for column in range(steps - row)
        for u, v in (((row + 1 / 3) / steps, (column + 1 / 3) / steps),)
    )


def _interior_claro(
    vertices: _Triangle, core: tuple[_Source, ...], drawings: tuple[dict[str, Any], ...]
) -> bool:
    """Contorno sem preenchimento ou claro e nenhum preenchimento opaco escuro por dentro."""
    owners = {source[0] for source in core}
    if any(not _preenchimento_claro(_rgb(drawings[index].get("fill"))) for index in owners):
        return False
    bounds = _bounds(vertices)
    samples = _amostras_internas(vertices)
    for index, drawing in enumerate(drawings):
        fill = _rgb(drawing.get("fill"))
        if index in owners or _preenchimento_claro(fill):
            continue
        if float(drawing.get("fill_opacity") or 1.0) < 0.5:
            continue
        if not bounds.intersects(pymupdf.Rect(drawing.get("rect") or (0, 0, 0, 0))):
            continue
        polygon = _drawing_points(tuple(drawing.get("items") or ()))
        if len(polygon) < 3:
            continue
        covered = sum(1 for point in samples if _dentro_poligono(point, polygon))
        if covered >= 0.6 * len(samples):
            return False
    return True


def _haste_externa(
    vertices: _Triangle, core: tuple[_Source, ...], lines: tuple[_Line, ...], layer: str
) -> _Line | None:
    """Traço que continua a mediana para fora de um vértice, como a ligação do equipamento."""
    centroid = _centroide(vertices)
    side = sum(math.dist(vertices[index], vertices[index - 1]) for index in range(3)) / 3
    tolerance = max(0.4, min(2.0, side * 0.1))
    limit = math.cos(math.radians(15))
    for vertex in vertices:
        radial = (vertex[0] - centroid[0], vertex[1] - centroid[1])
        reach = math.hypot(*radial)
        for line in lines:
            if line.source in core or line.layer != layer or line.length < 0.5 * side:
                continue
            if _colored(line.color, "red"):
                continue
            for near, far in ((line.start, line.end), (line.end, line.start)):
                if math.dist(near, vertex) > tolerance or math.dist(far, centroid) <= reach:
                    continue
                direction = (far[0] - near[0], far[1] - near[1])
                cosine = (direction[0] * radial[0] + direction[1] * radial[1]) / (
                    line.length * reach
                )
                if cosine >= limit:
                    return line
    return None


def _suporte_triangulo(
    vertices: _Triangle,
    core: tuple[_Source, ...],
    lines: tuple[_Line, ...],
    layer: str,
    drawings: tuple[dict[str, Any], ...],
) -> tuple[str, _Line] | None:
    """Eixo interno do pictograma ou, no contorno claro equilátero, a haste externa."""
    axis = _triangle_axis(vertices, core, lines, layer)
    if axis is not None:
        return "eixo_interno", axis
    if not _quase_equilatero(vertices):
        return None
    stem = _haste_externa(vertices, core, lines, layer)
    if stem is None or not _interior_claro(vertices, core, drawings):
        return None
    return "haste_externa", stem


def _anel_poligonal(index: int, drawing: dict[str, Any]) -> _Round | None:
    """Envoltória desenhada como polilinha fechada de muitos segmentos retos."""
    items = tuple(drawing.get("items") or ())
    if len(items) < 16 or any(item[0] != "l" for item in items):
        return None
    points = tuple((float(point.x), float(point.y)) for item in items for point in item[1:3])
    bounds = _bounds(points)
    if bounds.width < 2 or not 0.8 <= bounds.width / max(bounds.height, 0.01) <= 1.25:
        return None
    if math.dist(points[0], points[-1]) > max(bounds.width, bounds.height) * 0.05:
        return None
    center = _center(bounds)
    radii = tuple(math.dist(point, center) for point in points)
    if min(radii) < 0.85 * max(radii):
        return None
    clip = drawing.get("scissor")
    if clip is not None and not pymupdf.Rect(clip).contains(bounds):
        return None
    return _Round(
        bounds,
        tuple((index, item_index) for item_index in range(len(items))),
        str(drawing.get("layer") or ""),
        _rgb(drawing.get("color") or drawing.get("fill")),
        "polygon_ring",
        fill=_rgb(drawing.get("fill")),
    )


def _aneis_poligonais(drawings: tuple[dict[str, Any], ...]) -> tuple[_Round, ...]:
    # Kept apart from ``rounds``: only a triangle's envelope may use these rings.
    return tuple(
        ring
        for index, drawing in enumerate(drawings)
        if (ring := _anel_poligonal(index, drawing)) is not None
    )


def _distancia_segmento(point: _Point, start: _Point, end: _Point) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    squared = dx * dx + dy * dy
    if squared <= 0:
        return math.dist(point, start)
    t = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / squared))
    return math.dist(point, (start[0] + t * dx, start[1] + t * dy))


def _sobre_guia(line: _Line, guides: tuple[_Line, ...], tolerance: float) -> bool:
    """Trecho colinear a uma aresta, ao eixo ou à haste: contorno, não traço do X."""
    return any(
        _distancia_segmento(line.start, guide.start, guide.end) <= tolerance
        and _distancia_segmento(line.end, guide.start, guide.end) <= tolerance
        for guide in guides
    )


def _cruzamento(first: _Line, second: _Line) -> _Point | None:
    dx1, dy1 = first.end[0] - first.start[0], first.end[1] - first.start[1]
    dx2, dy2 = second.end[0] - second.start[0], second.end[1] - second.start[1]
    denominator = dx1 * dy2 - dy1 * dx2
    if abs(denominator) <= 1e-9:
        return None
    ox, oy = second.start[0] - first.start[0], second.start[1] - first.start[1]
    t = (ox * dy2 - oy * dx2) / denominator
    u = (ox * dy1 - oy * dx1) / denominator
    if not (-0.02 <= t <= 1.02 and -0.02 <= u <= 1.02):
        return None
    return (first.start[0] + t * dx1, first.start[1] + t * dy1)


def _par_cruzado(
    candidates: tuple[_Line, ...], centroid: _Point, size: float
) -> tuple[_Line, _Line] | None:
    """Dois traços que se cruzam no pictograma; empate resolvido pelo traço mais espesso."""
    best: tuple[_Line, _Line] | None = None
    best_width = -1.0
    for index, first in enumerate(candidates):
        for second in candidates[index + 1 :]:
            if _angle_delta(_line_angle(first), _line_angle(second)) < math.radians(50):
                continue
            crossing = _cruzamento(first, second)
            if crossing is None or math.dist(crossing, centroid) > 0.6 * size:
                continue
            if first.width + second.width > best_width:
                best, best_width = (first, second), first.width + second.width
    return best


_Buckets = dict[tuple[int, int], list[int]]
_Markers = list[tuple[str, tuple[_Source, ...]]]


def _baldes_extremidades(lines: tuple[_Line, ...]) -> _Buckets:
    # Endpoint buckets avoid scanning every drawing against every other drawing.
    buckets: _Buckets = {}
    for index, line in enumerate(lines):
        if not 3 <= line.length <= 150:
            continue
        for point in (line.start, line.end):
            buckets.setdefault((round(point[0] / 2), round(point[1] / 2)), []).append(index)
    return buckets


def _adjacentes(buckets: _Buckets, point: _Point) -> set[int]:
    x, y = round(point[0] / 2), round(point[1] / 2)
    return {
        index
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        for index in buckets.get((x + dx, y + dy), ())
    }


def _segundo_lado(first: _Line, second: _Line, vertex: _Point) -> _Point | None:
    """Extremidade oposta de ``second`` quando ele parte de ``vertex``."""
    if second.layer != first.layer or not 0.45 <= second.length / first.length <= 2.2:
        return None
    if _near_point(vertex, second.start, min(first.length, second.length)):
        return second.end
    if _near_point(vertex, second.end, min(first.length, second.length)):
        return second.start
    return None


def _terceiro_lado_valido(
    first: _Line, third: _Line, vertex: _Point, opposite: _Point, other: _Point
) -> bool:
    if third.layer != first.layer:
        return False
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
        return False
    if not 0.45 <= third.length / first.length <= 2.2:
        return False
    area2 = abs(
        (opposite[0] - vertex[0]) * (other[1] - vertex[1])
        - (opposite[1] - vertex[1]) * (other[0] - vertex[0])
    )
    return not area2 < first.length**2 * 0.3


@dataclass(frozen=True, slots=True)
class _ContornoTriangular:
    """Contorno fechado e o traço que o confirma como pictograma (eixo ou haste)."""

    vertices: _Triangle
    edges: tuple[_Line, _Line, _Line]
    core: tuple[_Source, ...]
    support_role: str
    support: _Line

    @property
    def layer(self) -> str:
        return self.edges[0].layer


def _envoltoria(
    bounds: pymupdf.Rect,
    size: float,
    layer: str,
    rounds: tuple[_Round, ...],
    rings: tuple[_Round, ...],
) -> _Round | None:
    loops = [
        item
        for item in rounds
        if item.kind == "loop"
        and item.layer == layer
        and 1.05 <= item.size / size <= 2.7
        and item.bounds.contains(bounds)
    ]
    for ring in rings:
        if ring.layer != layer or not 1.05 <= ring.size / size <= 2.7:
            continue
        margin = ring.size * 0.03
        tolerant = pymupdf.Rect(
            ring.bounds.x0 - margin,
            ring.bounds.y0 - margin,
            ring.bounds.x1 + margin,
            ring.bounds.y1 + margin,
        )
        if tolerant.contains(bounds):
            loops.append(ring)
    return min(loops, key=lambda item: item.size) if loops else None


def _x_vermelho(
    contorno: _ContornoTriangular, bounds: pymupdf.Rect, size: float, lines: tuple[_Line, ...]
) -> tuple[_Line, _Line] | None:
    guides = (*contorno.edges, contorno.support)
    tolerance = max(0.3, size * 0.06)
    candidates = tuple(
        item
        for item in lines
        if item.source not in contorno.core
        and item.source != contorno.support.source
        and item.layer == contorno.layer
        and _colored(item.color, "red")
        and bounds.intersects(_bounds((item.start, item.end)))
        and 0.4 <= item.length / size <= 2.5
        and not _sobre_guia(item, guides, tolerance)
    )
    return _par_cruzado(candidates, _centroide(contorno.vertices), size)


def _marcadores_triangulo(
    contorno: _ContornoTriangular,
    lines: tuple[_Line, ...],
    rounds: tuple[_Round, ...],
    rings: tuple[_Round, ...],
) -> tuple[_Markers, list[_Point]]:
    # A triangle's enclosing circle/X is a modifier, not another asset.
    markers: _Markers = []
    points: list[_Point] = []
    bounds = _bounds(contorno.vertices)
    size = max(bounds.width, bounds.height)
    circle = _envoltoria(bounds, size, contorno.layer, rounds, rings)
    if circle is not None:
        markers.append(("envoltoria", circle.sources))
        points.extend((tuple(circle.bounds.tl), tuple(circle.bounds.br)))
    cross = _x_vermelho(contorno, bounds, size, lines)
    if cross is not None:
        markers.append(("x_vermelho", tuple(line.source for line in cross)))
        points.extend(point for line in cross for point in (line.start, line.end))
    return markers, points


def _toca_ciano(drawings: tuple[dict[str, Any], ...], bounds: pymupdf.Rect) -> bool:
    return any(
        _colored(_rgb(drawing.get("fill") or drawing.get("color")), "cyan")
        and bounds.intersects(pymupdf.Rect(drawing.get("rect") or bounds))
        for drawing in drawings
    )


def _fontes_preenchimento_ciano(
    drawings: tuple[dict[str, Any], ...], bounds: pymupdf.Rect
) -> tuple[_Source, ...]:
    return tuple(
        (index, item_index)
        for index, drawing in enumerate(drawings)
        if _colored(_rgb(drawing.get("fill")), "cyan")
        and bounds.intersects(pymupdf.Rect(drawing.get("rect") or bounds))
        for item_index, _ in enumerate(drawing.get("items") or ())
    )


def _referencias_triangulo(purple: bool, cyan: bool, markers: _Markers) -> tuple[str, ...]:
    ids: tuple[int, ...] = tuple(range(16, 19) if purple else range(1, 7) if cyan else range(7, 16))
    if markers:
        marker = "x_vermelho" if any(role == "x_vermelho" for role, _ in markers) else markers[0][0]
        target = 2 if marker == "x_vermelho" else 3
        ids = tuple(index for index in ids if (index - 1) % 3 + 1 == target)
    return tuple(f"cemig-eo-r3-s18-v{index:03}" for index in ids)


def _forma_triangular(
    contorno: _ContornoTriangular,
    lines: tuple[_Line, ...],
    rounds: tuple[_Round, ...],
    rings: tuple[_Round, ...],
    drawings: tuple[dict[str, Any], ...],
) -> _Shape:
    core = contorno.core
    bounds = _bounds(contorno.vertices)
    # The external stem is a connection: it confirms the drawing but stays out of the box.
    symbol_points: list[_Point] = list(contorno.vertices)
    markers, marker_points = _marcadores_triangulo(contorno, lines, rounds, rings)
    symbol_points.extend(marker_points)
    cyan = _toca_ciano(drawings, bounds)
    purple = any(_colored(line.color, "purple") for line in contorno.edges)
    variant = "triangulo_roxo" if purple else "triangulo_meio_ciano" if cyan else "triangulo"
    components = [
        ("contorno_triangular", core),
        (contorno.support_role, (contorno.support.source,)),
        *markers,
    ]
    if cyan:
        fill_sources = _fontes_preenchimento_ciano(drawings, bounds)
        if fill_sources:
            components.append(("preenchimento_ciano", fill_sources))
    sources = tuple(sorted({source for _, refs in components for source in refs}))
    return _Shape(
        variant,
        "family-f02-18",
        "TRANSFORMADOR",
        sources,
        tuple(components),
        _bounds(tuple(symbol_points)),
        _referencias_triangulo(purple, cyan, markers),
        core_area=float(bounds.width * bounds.height),
    )


def _mesmo_contorno(shape: _Shape, other: _Shape) -> bool:
    return bool(
        other.bounds.contains(shape.bounds)
        or (
            math.dist(_center(shape.bounds), _center(other.bounds))
            <= max(shape.bounds.width, shape.bounds.height) * 0.08
            and abs(shape.bounds.width - other.bounds.width)
            <= max(shape.bounds.width, other.bounds.width) * 0.08
            and abs(shape.bounds.height - other.bounds.height)
            <= max(shape.bounds.height, other.bounds.height) * 0.08
        )
    )


def _triangulos_distintos(found: dict[tuple[_Source, ...], _Shape]) -> list[_Shape]:
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
        if any(_mesmo_contorno(shape, other) for other in chosen):
            continue
        chosen.append(shape)
    return chosen


def _sem_arranjos_radiais(chosen: list[_Shape], rounds: tuple[_Round, ...]) -> tuple[_Shape, ...]:
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


def _triangle_shapes(
    lines: tuple[_Line, ...], rounds: tuple[_Round, ...], drawings: tuple[dict[str, Any], ...]
) -> tuple[_Shape, ...]:
    buckets = _baldes_extremidades(lines)
    rings = _aneis_poligonais(drawings)
    found: dict[tuple[_Source, ...], _Shape] = {}
    for first_index, first in enumerate(lines):
        if not 4 <= first.length <= 150:
            continue
        for vertex, opposite in ((first.start, first.end), (first.end, first.start)):
            for second_index in _adjacentes(buckets, vertex):
                if second_index == first_index:
                    continue
                second = lines[second_index]
                other = _segundo_lado(first, second, vertex)
                if other is None:
                    continue
                for third_index in _adjacentes(buckets, opposite) & _adjacentes(buckets, other):
                    if third_index in (first_index, second_index):
                        continue
                    third = lines[third_index]
                    if not _terceiro_lado_valido(first, third, vertex, opposite, other):
                        continue
                    triangle = (first, second, third)
                    core = tuple(sorted(line.source for line in triangle))
                    if core in found:
                        continue
                    vertices = (vertex, opposite, other)
                    support = _suporte_triangulo(vertices, core, lines, first.layer, drawings)
                    if support is None:
                        continue
                    contorno = _ContornoTriangular(vertices, triangle, core, *support)
                    found[core] = _forma_triangular(contorno, lines, rounds, rings, drawings)
    return _sem_arranjos_radiais(_triangulos_distintos(found), rounds)


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


@dataclass(frozen=True, slots=True)
class _Classificacao:
    """Leitura de um grupo de enrolamentos antes de virar ``_Shape``."""

    variant: str
    family: str
    class_code: str
    references: tuple[str, ...]
    possible: tuple[str, ...]
    support_lines: tuple[_Line, ...] = ()


def _redondos_vizinhos(first: _Round, second: _Round) -> bool:
    if second.kind != first.kind or second.layer != first.layer:
        return False
    ratio = first.size / max(second.size, 0.01)
    if not 0.6 <= ratio <= 1.67:
        return False
    distance = math.dist(first.center, second.center)
    minimum = 0.12 if first.kind == "arc" else 0.45
    maximum = 1.7 if first.kind == "arc" else 1.22
    if distance < minimum * min(first.size, second.size) and (
        first.kind != "arc" or first.curvature * second.curvature >= 0
    ):
        return False
    if distance > maximum * max(first.size, second.size):
        return False
    if first.kind == "arc":
        difference = abs(first.direction - second.direction) % math.pi
        if min(difference, math.pi - difference) > math.radians(25):
            return False
    return True


def _grupos_redondos(candidates: tuple[_Round, ...]) -> list[set[int]]:
    """Componentes conexos por vizinhança, na ordem da semente de menor índice."""
    remaining = set(range(len(candidates)))
    groups: list[set[int]] = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        group = {seed}
        frontier = [seed]
        while frontier:
            index = frontier.pop()
            first = candidates[index]
            for other_index in tuple(remaining):
                if not _redondos_vizinhos(first, candidates[other_index]):
                    continue
                remaining.remove(other_index)
                group.add(other_index)
                frontier.append(other_index)
        groups.append(group)
    return groups


def _circulo_fechado_por_arcos(members: tuple[_Round, ...]) -> bool:
    """Dois arcos opostos sobre a mesma corda formam um círculo, não enrolamentos."""
    if len(members) != 2 or members[0].kind != "arc":
        return False
    first, second = members
    if first.endpoints is None or second.endpoints is None:
        return False
    (a0, a1), (b0, b1) = first.endpoints, second.endpoints
    tolerance = min(first.size, second.size) * 0.04
    return (
        (math.dist(a0, b0) <= tolerance and math.dist(a1, b1) <= tolerance)
        or (math.dist(a0, b1) <= tolerance and math.dist(a1, b0) <= tolerance)
    ) and first.curvature * second.curvature < 0


def _limites_membros(members: tuple[_Round, ...]) -> tuple[_Point, ...]:
    return tuple(
        point for member in members for point in (tuple(member.bounds.tl), tuple(member.bounds.br))
    )


def _tracos_proximos(
    members: tuple[_Round, ...], lines: tuple[_Line, ...], bounds: pymupdf.Rect
) -> tuple[_Line, ...]:
    return tuple(
        line
        for line in lines
        if line.layer == members[0].layer
        and line.length <= members[0].size * 5
        and math.dist(_center(bounds), _center(_bounds((line.start, line.end))))
        <= max(bounds.width, bounds.height) * 1.2
    )


def _classificar_lacos(
    members: tuple[_Round, ...], nearby_lines: tuple[_Line, ...]
) -> _Classificacao | None:
    if len(members) not in (2, 3):
        return None
    if any(
        math.dist(first.center, second.center) > 0.95 * min(first.size, second.size)
        or not 0.8 <= first.size / max(second.size, 0.01) <= 1.25
        for index, first in enumerate(members)
        for second in members[index + 1 :]
    ):
        return None
    if not _coherent_circular_windings(members, nearby_lines):
        return None
    return _Classificacao(
        "enrolamentos_circulares" if len(members) == 2 else "enrolamentos_multiplos",
        "family-f02-18" if len(members) == 2 else "family-f02-24",
        "TRANSFORMADOR",
        (
            ("cemig-eo-r3-s18-v019",)
            if len(members) == 2
            else ("cemig-eo-r3-s24-v001", "cemig-eo-r3-s25-v004")
        ),
        ("family-f02-25",) if len(members) > 2 else (),
    )


def _arcos_terciarios(
    members: tuple[_Round, ...], nonred: tuple[_Line, ...], bounds: pymupdf.Rect
) -> _Classificacao | None:
    if len(members) != 6 or len(_arc_pairs(members)) != 3:
        return None
    bridge = next(
        (
            line
            for line in nonred
            if line.length >= members[0].size * 2
            and _angle_delta(_line_angle(line), members[0].direction) <= math.radians(20)
            and math.dist(_center(_bounds((line.start, line.end))), _center(bounds))
            <= max(bounds.width, bounds.height) * 0.3
        ),
        None,
    )
    composite = bridge is not None
    return _Classificacao(
        "conjunto_medicao" if composite else "enrolamentos_terciarios",
        "family-f02-25" if composite else "family-f02-24",
        "CONJUNTO_EO" if composite else "TRANSFORMADOR",
        ("cemig-eo-r3-s25-v004",) if composite else ("cemig-eo-r3-s24-v001",),
        ("family-f02-24",) if composite else ("family-f02-25",),
        (bridge,) if bridge is not None else (),
    )


def _arcos_pares(
    members: tuple[_Round, ...],
    nonred: tuple[_Line, ...],
    red: tuple[_Line, ...],
    bounds: pymupdf.Rect,
) -> _Classificacao | None:
    if len(_arc_pairs(members)) != 2:
        return None
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
        and _angle_delta(_line_angle(cross[0]), _line_angle(cross[1])) >= math.radians(70)
        else ()
    )
    references = (
        ("cemig-eo-r3-s18-v023",)
        if angular and marker
        else ("cemig-eo-r3-s18-v022",)
        if angular
        else ("cemig-eo-r3-s18-v019",)
    )
    return _Classificacao(
        "enrolamentos_angulares" if angular else "enrolamentos_pares",
        "family-f02-18",
        "TRANSFORMADOR",
        references,
        (),
        ((diagonal,) if diagonal is not None else ()) + marker,
    )


def _arcos_derivacao(
    members: tuple[_Round, ...], nonred: tuple[_Line, ...]
) -> _Classificacao | None:
    leads = _terminal_leads(members, nonred)
    if not leads:
        return None
    multiple_taps = len(leads) >= 2
    return _Classificacao(
        "enrolamento_derivacoes" if multiple_taps else "enrolamento_derivacao",
        "family-f02-24" if multiple_taps else "family-f02-18",
        "TRANSFORMADOR",
        ("cemig-eo-r3-s24-v002",) if multiple_taps else ("cemig-eo-r3-s18-v020",),
        ("family-f02-18",) if multiple_taps else ("family-f02-24",),
        leads,
    )


def _arcos_semicirculos(
    members: tuple[_Round, ...], nonred: tuple[_Line, ...]
) -> _Classificacao | None:
    if len(_arc_pairs(members)) != 1:
        return None
    ground = _ground_terminal(members, nonred)
    leads = () if ground else _terminal_leads(members, nonred)
    if not ground and not leads:
        return None
    grounded = bool(ground)
    opposed = len(leads) >= 2 and not grounded
    lateral = (
        opposed and max(line.length for line in leads) > min(line.length for line in leads) * 1.4
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
    references = (
        ("cemig-eo-r3-s18-v021",)
        if grounded
        else ("cemig-eo-r3-s25-v003",)
        if lateral
        else ("cemig-eo-r3-s25-v001",)
        if opposed
        else ("cemig-eo-r3-s25-v002", "cemig-eo-r3-s25-v003")
    )
    return _Classificacao(
        variant,
        "family-f02-18" if grounded else "family-f02-25",
        "TRANSFORMADOR",
        references,
        ("family-f02-25",) if grounded else ("family-f02-18",),
        ground or leads,
    )


def _classificar_arcos(
    members: tuple[_Round, ...], nearby_lines: tuple[_Line, ...], bounds: pymupdf.Rect
) -> _Classificacao | None:
    count = len(members)
    nonred = tuple(line for line in nearby_lines if not _colored(line.color, "red"))
    red = tuple(line for line in nearby_lines if _colored(line.color, "red"))
    if count >= 5:
        return _arcos_terciarios(members, nonred, bounds)
    if count == 4:
        return _arcos_pares(members, nonred, red, bounds)
    if count == 3:
        return _arcos_derivacao(members, nonred)
    if count == 2:
        return _arcos_semicirculos(members, nonred)
    return None


def _forma_enrolamentos(members: tuple[_Round, ...], leitura: _Classificacao) -> _Shape:
    support_lines = leitura.support_lines
    symbol_bounds = _bounds(
        _limites_membros(members)
        + tuple(point for line in support_lines for point in (line.start, line.end))
    )
    component_sources = tuple(sorted({source for member in members for source in member.sources}))
    line_sources = tuple(line.source for line in support_lines)
    all_sources = tuple(sorted({*component_sources, *line_sources}))
    components: tuple[tuple[str, tuple[_Source, ...]], ...] = tuple(
        ("enrolamento", member.sources) for member in members
    )
    if line_sources:
        components += (("tracos_associados", line_sources),)
    return _Shape(
        leitura.variant,
        leitura.family,
        leitura.class_code,
        all_sources,
        components,
        symbol_bounds,
        leitura.references,
        leitura.possible,
    )


def _round_shapes(
    rounds: tuple[_Round, ...], lines: tuple[_Line, ...], used: set[_Source]
) -> tuple[_Shape, ...]:
    candidates = tuple(
        item
        for item in rounds
        if not set(item.sources) & used
        and not (item.kind == "loop" and _colored(item.color, "red"))
    )
    shapes: list[_Shape] = []
    for group in _grupos_redondos(candidates):
        if len(group) < 2:
            continue
        members = tuple(candidates[index] for index in sorted(group))
        if _circulo_fechado_por_arcos(members):
            continue
        bounds = _bounds(_limites_membros(members))
        nearby_lines = _tracos_proximos(members, lines, bounds)
        if members[0].kind == "loop":
            leitura = _classificar_lacos(members, nearby_lines)
        else:
            leitura = _classificar_arcos(members, nearby_lines, bounds)
        if leitura is None:
            continue
        shapes.append(_forma_enrolamentos(members, leitura))
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
