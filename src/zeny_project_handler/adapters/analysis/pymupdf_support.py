# mypy: disable-error-code="no-untyped-call"
"""Conversões geométricas e serialização leve compartilhadas pelos extratores PDF."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any, cast

import pymupdf

from zeny_project_handler.domain.catalog import ExtraAttributes, JsonPrimitive
from zeny_project_handler.domain.enums import TipoGeometria
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.analysis import GeometriaNormalizada


def _box_geometry(
    page: Any, rect_like: Any, *, pdf_coordinates: bool = False
) -> GeometriaNormalizada:
    rect = pymupdf.Rect(rect_like)
    points = _normalized_points(
        page,
        (rect.tl, rect.tr, rect.br, rect.bl),
        pdf_coordinates=pdf_coordinates,
    )
    x_values = [point.x for point in points]
    y_values = [point.y for point in points]
    x0, x1 = min(x_values), max(x_values)
    y0, y1 = min(y_values), max(y_values)
    if x0 == x1 or y0 == y1:
        unique = _without_consecutive_duplicates(points)
        if len(unique) >= 2:
            return GeometriaNormalizada(tipo=TipoGeometria.POLILINHA, pontos=unique)
        return GeometriaNormalizada(tipo=TipoGeometria.PONTO, pontos=(unique[0],))
    return GeometriaNormalizada(
        tipo=TipoGeometria.CAIXA,
        pontos=(PontoNormalizado(x0, y0), PontoNormalizado(x1, y1)),
    )


def _normalized_points(
    page: Any,
    raw_points: Iterable[Any],
    *,
    pdf_coordinates: bool = False,
) -> tuple[PontoNormalizado, ...]:
    result = []
    for raw_point in raw_points:
        point = pymupdf.Point(raw_point)
        if pdf_coordinates:
            point = point * page.transformation_matrix
        point = point * page.rotation_matrix
        result.append(
            _normalized_point(point.x / float(page.rect.width), point.y / float(page.rect.height))
        )
    return tuple(result)


def _normalized_point(x: float, y: float) -> PontoNormalizado:
    clipped_x = min(1.0, max(0.0, float(x)))
    clipped_y = min(1.0, max(0.0, float(y)))
    return PontoNormalizado(Decimal(str(clipped_x)), Decimal(str(clipped_y)))


def _without_consecutive_duplicates(
    points: tuple[PontoNormalizado, ...],
) -> tuple[PontoNormalizado, ...]:
    result: list[PontoNormalizado] = []
    for point in points:
        if not result or result[-1] != point:
            result.append(point)
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    return tuple(result)


def _extras(**values: JsonPrimitive) -> ExtraAttributes:
    return tuple(sorted(values.items()))


def _srgb_color(value: object) -> str | None:
    if value is None:
        return None
    return f"#{int(str(value)):06X}"


def _pdf_color(value: object) -> str | None:
    if value is None:
        return None
    components = tuple(float(str(component)) for component in cast(Iterable[object], value))
    if len(components) == 1:
        components = components * 3
    if len(components) < 3:
        return None
    rgb = tuple(max(0, min(255, round(component * 255))) for component in components[:3])
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _pdf_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "x0"):
        rectangle = cast(Any, value)
        return [
            float(rectangle.x0),
            float(rectangle.y0),
            float(rectangle.x1),
            float(rectangle.y1),
        ]
    if hasattr(value, "x"):
        point = cast(Any, value)
        return [float(point.x), float(point.y)]
    if isinstance(value, Iterable):
        return [_pdf_value(item) for item in value]
    return str(value)


def _optional_string(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _decimal_or_zero(value: object) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal(0)


def _stream_bytes(document: Any, xref: int) -> bytes:
    try:
        return bytes(document.xref_stream(xref) or b"")
    except Exception:
        return b""
