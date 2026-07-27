# mypy: disable-error-code="no-untyped-call"
"""Reconhecimento geométrico de equipamentos representados apenas por símbolos."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
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


@dataclass(frozen=True, slots=True)
class _VectorPrimitive:
    index: int
    bounds: Any
    center: tuple[float, float]
    angle: float
    major_length: float
    minor_length: float
    color: str


@dataclass(frozen=True, slots=True)
class _SymbolMatch:
    code: str
    class_code: str
    situation: SituacaoProjeto
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
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    """Converta assinaturas vetoriais conhecidas em evidências semânticas."""
    primitives = tuple(
        primitive
        for index, drawing in enumerate(page.get_drawings(extended=True))
        if (primitive := _primitive_from_drawing(index, drawing)) is not None
    )
    matches = _deduplicate_matches(
        (
            *_ground_and_mt_arrester_matches(primitives),
            *_bt_arrester_matches(primitives),
        )
    )
    return tuple(
        CandidatoEvidenciaDocumento(
            chave_estavel=(
                f"p{page_number}:simbolo-vetorial:{match.class_code.casefold()}:"
                + "-".join(str(item.index) for item in match.primitives)
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
                situacao_projeto_forcada=match.situation.value,
                simbolo_cemig=match.code,
                vetores_origem=",".join(str(item.index) for item in match.primitives),
            ),
        )
        for match in matches
    )


def _primitive_from_drawing(index: int, drawing: dict[str, Any]) -> _VectorPrimitive | None:
    points = _drawing_points(tuple(drawing.get("items") or ()))
    if len(points) < 2:
        return None
    color = _canonical_symbol_color(drawing.get("color"), drawing.get("fill"))
    if color is None:
        return None
    bounds = drawing.get("rect") or drawing.get("scissor")
    if bounds is None:
        return None
    angle, major, minor = _principal_axis(points)
    if not 0 < major <= _MAXIMUM_PRIMITIVE_LENGTH:
        return None
    return _VectorPrimitive(
        index=index,
        bounds=bounds,
        center=((bounds.x0 + bounds.x1) / 2, (bounds.y0 + bounds.y1) / 2),
        angle=angle,
        major_length=major,
        minor_length=minor,
        color=color,
    )


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


def _canonical_symbol_color(stroke: object, fill: object) -> str | None:
    for raw in (stroke, fill):
        rgb = _rgb255(raw)
        if rgb is None:
            continue
        red, green, blue = rgb
        if max(rgb) <= 40:
            return "#000000"
        if red >= 96 and red >= green * 2 and red >= blue * 2:
            return "#FF0000"
        if green >= 64 and green >= red * 2 and green >= blue * 2:
            return "#008000"
    return None


def _rgb255(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, tuple) or len(value) < 3:
        return None
    channels = tuple(round(float(channel) * 255) for channel in value[:3])
    return channels[0], channels[1], channels[2]


def _ground_and_mt_arrester_matches(
    primitives: tuple[_VectorPrimitive, ...],
) -> tuple[_SymbolMatch, ...]:
    lines = tuple(
        item
        for item in primitives
        if item.major_length >= 1 and item.minor_length <= max(1.2, item.major_length * 0.22)
    )
    matches: list[_SymbolMatch] = []
    for stem in lines:
        if stem.major_length < 6:
            continue
        axis = math.cos(stem.angle), math.sin(stem.angle)
        normal = -axis[1], axis[0]
        bars_by_side: dict[int, list[_VectorPrimitive]] = {-1: [], 1: []}
        for candidate in lines:
            if candidate.index == stem.index or candidate.color != stem.color:
                continue
            if abs(_angle_difference(stem.angle, candidate.angle) - math.pi / 2) > (
                _ANGLE_TOLERANCE
            ):
                continue
            offset, lateral = _relative_position(stem.center, candidate.center, axis, normal)
            if (
                abs(lateral) <= max(1.5, candidate.major_length * 0.2)
                and stem.major_length * 0.35 <= abs(offset) <= stem.major_length * 1.35
            ):
                bars_by_side[1 if offset > 0 else -1].append(candidate)
        for bars in bars_by_side.values():
            if len(bars) < 3:
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


def _bt_arrester_matches(
    primitives: tuple[_VectorPrimitive, ...],
) -> tuple[_SymbolMatch, ...]:
    matches: list[_SymbolMatch] = []
    for stem in primitives:
        if not 6 <= stem.major_length <= _MAXIMUM_PRIMITIVE_LENGTH or stem.minor_length > max(
            1.2, stem.major_length * 0.15
        ):
            continue
        axis = math.cos(stem.angle), math.sin(stem.angle)
        normal = -axis[1], axis[0]
        nearby = tuple(
            candidate
            for candidate in primitives
            if candidate.index != stem.index
            and candidate.color == stem.color
            and _is_near_stem_end(stem, candidate, axis, normal)
        )
        bodies = tuple(
            item
            for item in nearby
            if stem.major_length * 0.5 <= item.major_length <= stem.major_length * 1.1
            and 2 <= item.major_length / max(item.minor_length, 0.01) <= 4.5
            and _angle_difference(stem.angle, item.angle) <= 0.2
        )
        diagonals = tuple(
            item
            for item in nearby
            if stem.major_length * 0.55 <= item.major_length <= stem.major_length * 1.15
            and item.minor_length <= item.major_length * 0.2
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


def _situation_from_color(color: str) -> SituacaoProjeto:
    return {
        "#008000": SituacaoProjeto.INSTALAR,
        "#FF0000": SituacaoProjeto.REMOVER,
    }.get(color, SituacaoProjeto.EXISTENTE)


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
                and (
                    len(
                        {item.index for item in existing.primitives}
                        & {item.index for item in match.primitives}
                    )
                    >= 2
                    or math.dist(existing.center, match.center)
                    <= max(_match_scale(existing), _match_scale(match)) * 0.45
                )
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
    bounds = pymupdf.Rect(primitives[0].bounds)
    for primitive in primitives[1:]:
        bounds |= primitive.bounds
    return bounds
