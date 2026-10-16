# mypy: disable-error-code="no-untyped-call"
"""Opt-in vector grammars for versioned E01 symbol packages.

An inventory row is never a detection. Only an enabled grammar that matches
page geometry emits a known-class observation. Pending rows remain auditable
in the package data and do not enter the method's evaluated classes.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
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
    PontoOriginalSimbolo,
    PrimitivaObservadaSimbolo,
    ResultadoMetodoSimbolos,
    TransformacaoSimbolo,
)
from zeny_project_handler.domain.values import PontoNormalizado

from .pymupdf_support import _box_geometry

Package = dict[str, Any]
_PACKAGE_DIR = Path(__file__).with_name("symbol_packages")
_ROLES = {"operational", "informative"}
_GRAMMARS = {
    "label_in_frame",
    "triangle_in_frame",
    "framed_diagonals",
    "nested_rectangles_bar",
    "diamond_three_dots",
    "terminal_disc",
}
_INFORMATIVE_DESTINATIONS = {"informative_only", "document_convention"}


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


_PACKAGE_FIELDS = {"schema_version", "family_id", "profile_id", "source_id", "variants"}
_VARIANT_FIELDS = {
    "id",
    "class_code",
    "role",
    "destination",
    "source_ref",
    "visual_note",
    "recognition",
}
_SOURCE_REF_FIELDS = {"source_id", "pdf_page", "locator", "review_status"}
_LABEL_IN_FRAME_FIELDS = {
    "kind",
    "frame",
    "label",
    "max_span",
    "max_aspect",
    "empty_interior",
    "nested_frame",
    "inner_fill",
}


def _label_in_frame_aspect_ok(grammar: Package) -> bool:
    return "max_aspect" not in grammar or (
        isinstance(grammar["max_aspect"], (int, float))
        and not isinstance(grammar["max_aspect"], bool)
        and 1 <= grammar["max_aspect"] <= 4
    )


def _label_in_frame_nested_ok(grammar: Package) -> bool:
    return ("nested_frame" not in grammar and "inner_fill" not in grammar) or (
        grammar.get("nested_frame") is True and grammar.get("inner_fill") == "gray"
    )


def _label_in_frame_grammar_ok(grammar: Package) -> bool:
    return (
        {"kind", "frame", "label", "max_span"} <= set(grammar)
        and set(grammar) <= _LABEL_IN_FRAME_FIELDS
        and grammar["frame"] in {"rectangle", "ellipse"}
        and isinstance(grammar["label"], str)
        and bool(re.fullmatch(r"[A-Z0-9]{1,4}", grammar["label"]))
        and _label_in_frame_aspect_ok(grammar)
        and ("empty_interior" not in grammar or grammar["empty_interior"] is True)
        and _label_in_frame_nested_ok(grammar)
    )


def _triangle_in_frame_grammar_ok(grammar: Package) -> bool:
    return (
        set(grammar) == {"kind", "frame", "fill", "max_span"}
        and grammar["frame"] == "rectangle"
        and grammar["fill"] in {"empty", "solid"}
    )


def _framed_diagonals_grammar_ok(grammar: Package) -> bool:
    return (
        set(grammar) == {"kind", "frame", "min_diagonals", "max_span"}
        and grammar["frame"] == "rectangle"
        and grammar["min_diagonals"] == 2
    )


def _nested_rectangles_bar_grammar_ok(grammar: Package) -> bool:
    return (
        set(grammar) == {"kind", "frame", "central_bar", "max_span"}
        and grammar["frame"] == "rectangle"
        and grammar["central_bar"] is True
    )


def _diamond_three_dots_grammar_ok(grammar: Package) -> bool:
    return (
        set(grammar) == {"kind", "frame", "dot_count", "max_span"}
        and grammar["frame"] == "diamond"
        and grammar["dot_count"] == 3
    )


_RGB = tuple[float, float, float]
_TERMINAL_DISC_FIELDS = {"kind", "fill", "min_span", "max_span", "terminal_line"}
# Upper bound of any ``terminal_disc`` span; larger fills never become disc candidates.
_MAX_DISC_SPAN = 8.0


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _is_purple(rgb: _RGB) -> bool:
    """Dark purple: red and blue dominate green; light lilac and violet stay out."""
    red, green, blue = rgb
    return red > 0.2 and blue > 0.2 and green < 0.8 * min(red, blue) and max(rgb) <= 0.6


_DISC_FILLS: dict[str, Callable[[_RGB], bool]] = {"purple": _is_purple}


def _terminal_disc_grammar_ok(grammar: Package) -> bool:
    if set(grammar) != _TERMINAL_DISC_FIELDS:
        return False
    low, high = grammar["min_span"], grammar["max_span"]
    return (
        isinstance(grammar["fill"], str)
        and grammar["fill"] in _DISC_FILLS
        and grammar["terminal_line"] is True
        and _is_number(low)
        and _is_number(high)
        and 0.5 <= float(low) < float(high) <= _MAX_DISC_SPAN
    )


# Field validation per grammar kind; keys mirror ``_GRAMMARS``.
_GRAMMAR_FIELD_VALIDATORS: dict[str, Callable[[Package], bool]] = {
    "label_in_frame": _label_in_frame_grammar_ok,
    "triangle_in_frame": _triangle_in_frame_grammar_ok,
    "framed_diagonals": _framed_diagonals_grammar_ok,
    "nested_rectangles_bar": _nested_rectangles_bar_grammar_ok,
    "diamond_three_dots": _diamond_three_dots_grammar_ok,
    "terminal_disc": _terminal_disc_grammar_ok,
}


def _validate_package_header(package: Package, path: Path) -> str:
    """Validate top-level fields and return the package ``source_id``."""
    if set(package) != _PACKAGE_FIELDS:
        raise ValueError(f"{path}: package fields disagree with schema")
    if type(package["schema_version"]) is not int or package["schema_version"] != 1:
        raise ValueError(f"{path}: unsupported schema version")
    family = _required_text(package["family_id"], "family_id")
    if not re.fullmatch(r"family-[a-z0-9-]+", family):
        raise ValueError(f"{path}: invalid family_id")
    _required_text(package["profile_id"], "profile_id")
    source_id = _required_text(package["source_id"], "source_id")
    variants = package["variants"]
    if not isinstance(variants, list) or not variants:
        raise ValueError(f"{path}: variants must be a non-empty array")
    return source_id


def _validate_source_ref(ref: Any, path: Path, source_id: str, variant_id: str) -> None:
    if not isinstance(ref, dict) or set(ref) != _SOURCE_REF_FIELDS:
        raise ValueError(f"{path}: invalid source_ref for {variant_id}")
    if ref["source_id"] != source_id or type(ref["pdf_page"]) is not int or ref["pdf_page"] < 1:
        raise ValueError(f"{path}: source mismatch for {variant_id}")
    _required_text(ref["locator"], "source_ref.locator")
    if ref["review_status"] not in {"visual_checked", "synthetic_fixture"}:
        raise ValueError(f"{path}: source is not reviewed for {variant_id}")


def _negative_examples_ok(negatives: Any) -> bool:
    return not (
        not isinstance(negatives, list)
        or not negatives
        or any(not isinstance(item, str) or len(item.strip()) < 3 for item in negatives)
        or len(set(negatives)) != len(negatives)
    )


def _validate_grammar(grammar: Any, path: Path, variant_id: str) -> None:
    if not isinstance(grammar, dict) or grammar.get("kind") not in _GRAMMARS:
        raise ValueError(f"{path}: unsupported grammar for {variant_id}")
    valid = _GRAMMAR_FIELD_VALIDATORS[grammar["kind"]](grammar)
    span = grammar.get("max_span")
    max_allowed_span = 96 if grammar["kind"] == "label_in_frame" else 72
    if (
        not valid
        or isinstance(span, bool)
        or not isinstance(span, (int, float))
        or not (0 < span <= max_allowed_span)
    ):
        raise ValueError(f"{path}: invalid grammar fields for {variant_id}")


def _validate_recognition(recognition: Any, path: Path, variant_id: str) -> None:
    if not isinstance(recognition, dict):
        raise ValueError(f"{path}: missing recognition for {variant_id}")
    if not _negative_examples_ok(recognition.get("negative_examples")):
        raise ValueError(f"{path}: invalid negative examples for {variant_id}")
    if recognition.get("status") == "pending":
        if (
            set(recognition) != {"status", "reason", "negative_examples"}
            or len(_required_text(recognition["reason"], "recognition.reason")) < 12
        ):
            raise ValueError(f"{path}: pending row lacks reason for {variant_id}")
        return
    if recognition.get("status") != "enabled" or set(recognition) != {
        "status",
        "grammar",
        "negative_examples",
    }:
        raise ValueError(f"{path}: invalid recognition status for {variant_id}")
    _validate_grammar(recognition["grammar"], path, variant_id)


def _validate_variant(variant: Any, path: Path, source_id: str, seen: set[str]) -> None:
    if not isinstance(variant, dict) or set(variant) != _VARIANT_FIELDS:
        raise ValueError(f"{path}: variant fields disagree with schema")
    variant_id = _required_text(variant["id"], "variant.id")
    if variant_id in seen:
        raise ValueError(f"{path}: duplicate variant {variant_id}")
    seen.add(variant_id)
    _required_text(variant["class_code"], "class_code")
    role = variant["role"]
    destination = _required_text(variant["destination"], "destination")
    if role not in _ROLES or (destination in _INFORMATIVE_DESTINATIONS) != (role == "informative"):
        raise ValueError(f"{path}: invalid role/destination for {variant_id}")
    _required_text(variant["visual_note"], "visual_note")
    _validate_source_ref(variant["source_ref"], path, source_id, variant_id)
    _validate_recognition(variant["recognition"], path, variant_id)


def _validate_package(package: Any, path: Path) -> Package:
    if not isinstance(package, dict):
        raise ValueError(f"{path}: package must be an object")
    source_id = _validate_package_header(package, path)
    seen: set[str] = set()
    for variant in package["variants"]:
        _validate_variant(variant, path, source_id, seen)
    return package


def carregar_pacotes(*, packages_dir: Path | None = None) -> tuple[Package, ...]:
    """Load all packages; extra families are added by data, without a code table."""
    directory = _PACKAGE_DIR if packages_dir is None else Path(packages_dir)
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise ValueError(f"No symbol packages in {directory}")
    packages = []
    families: set[str] = set()
    variants: set[str] = set()
    for path in paths:
        try:
            package = _validate_package(json.loads(path.read_text(encoding="utf-8")), path)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot load package {path}") from exc
        if package["family_id"] in families or package["family_id"] != path.stem:
            raise ValueError(f"Duplicate or misnamed family package: {path}")
        families.add(package["family_id"])
        for variant in package["variants"]:
            if variant["id"] in variants:
                raise ValueError(f"Duplicate variant across packages: {variant['id']}")
            variants.add(variant["id"])
        packages.append(package)
    return tuple(packages)


def _enabled(pacotes: tuple[Package, ...]) -> tuple[tuple[Package, Package], ...]:
    return tuple(
        (package, variant)
        for package in pacotes
        for variant in package["variants"]
        if variant["recognition"]["status"] == "enabled"
    )


def perfil_pacotes(pacotes: tuple[Package, ...] | None = None) -> PerfilMetodoSimbolos:
    """Method signature includes data content, so changed grammars cannot share identity."""
    loaded = carregar_pacotes() if pacotes is None else pacotes
    canonical = json.dumps(loaded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    classes = tuple(sorted({variant["class_code"] for _, variant in _enabled(loaded)}))
    return PerfilMetodoSimbolos(
        metodo_id="declarative-vector-packages",
        versao="1.1.0",
        familia="gramatica-vetorial-declarativa",
        dominio_aplicacao="PDF vetorial com primitives e texto embutido; contexto não inferido",
        classes_suportadas=classes,
        camadas_suportadas=("base",),
        fontes_compartilhadas=("pymupdf:get_drawings:extended", "pymupdf:get_text:words"),
        perfil_referencia="E01:F02:IT-EO-008:revisao-3",
        parametros=(("package_sha256", digest), ("enabled_variants", len(_enabled(loaded)))),
    )


def _frame_candidates(
    drawings: tuple[dict[str, Any], ...],
) -> tuple[tuple[str, pymupdf.Rect, int], ...]:
    found = []
    for index, drawing in enumerate(drawings):
        if drawing.get("type") in {"clip", "group"}:
            continue
        items = drawing.get("items") or ()
        for item in items:
            if item[0] == "re":
                rect = pymupdf.Rect(item[1])
                if not rect.is_empty:
                    found.append(("rectangle", rect, index))
        curves = [item for item in items if item[0] == "c"]
        if len(curves) == 4 and len(items) == 4:
            candidate_rect = _drawing_bounds(drawing, items)
            if candidate_rect is not None:
                found.append(("ellipse", candidate_rect, index))
        lines = [item for item in items if item[0] == "l"]
        if len(lines) == 4 and len(items) == 4:
            candidate_rect = _drawing_bounds(drawing, items)
            if candidate_rect is not None and _is_diamond(
                [pymupdf.Point(point) for line in lines for point in line[1:3]], candidate_rect
            ):
                found.append(("diamond", candidate_rect, index))
        if len(items) == 1 and items[0][0] == "qu":  # type: ignore[misc]
            quad = items[0][1]  # type: ignore[misc]
            candidate_rect = _drawing_bounds(drawing, items)
            if candidate_rect is not None and _is_diamond(
                [pymupdf.Point(point) for point in (quad.ul, quad.ur, quad.ll, quad.lr)],
                candidate_rect,
            ):
                found.append(("diamond", candidate_rect, index))
    return tuple(found)


def _drawing_bounds(drawing: dict[str, Any], items: Any) -> pymupdf.Rect | None:
    raw = drawing.get("rect")
    if raw is not None:
        rect = pymupdf.Rect(raw)
    else:
        points: list[pymupdf.Point] = []
        for item in items:
            if item[0] in {"c", "l"}:
                points.extend(pymupdf.Point(value) for value in item[1:])
            elif item[0] == "qu":
                quad = item[1]
                points.extend(
                    pymupdf.Point(value) for value in (quad.ul, quad.ur, quad.ll, quad.lr)
                )
        if not points:
            return None
        xs = [point.x for point in points]
        ys = [point.y for point in points]
        if not all(math.isfinite(value) for value in (*xs, *ys)):
            return None
        rect = pymupdf.Rect(min(xs), min(ys), max(xs), max(ys))
    if rect.is_empty or not all(
        math.isfinite(value) for value in (rect.x0, rect.y0, rect.x1, rect.y1)
    ):
        return None
    return rect


def _is_diamond(ends: list[pymupdf.Point], rect: pymupdf.Rect) -> bool:
    if rect.width < 4 or rect.height < 4:
        return False
    corners = (
        pymupdf.Point((rect.x0 + rect.x1) / 2, rect.y0),
        pymupdf.Point(rect.x1, (rect.y0 + rect.y1) / 2),
        pymupdf.Point((rect.x0 + rect.x1) / 2, rect.y1),
        pymupdf.Point(rect.x0, (rect.y0 + rect.y1) / 2),
    )
    tolerance = max(1.0, min(rect.width, rect.height) * 0.08)
    expected_hits = 2 if len(ends) == 8 else 1
    return bool(
        all(
            sum(abs(point - corner) <= tolerance for point in ends) == expected_hits
            for corner in corners
        )
    )


def _frame_ok(frame: str, rect: pymupdf.Rect, grammar: Package) -> bool:
    if frame != grammar["frame"] or rect.width <= 0 or rect.height <= 0:
        return False
    if max(rect.width, rect.height) > grammar["max_span"] or min(rect.width, rect.height) < 4:
        return False
    aspect = rect.width / rect.height
    if frame in {"ellipse", "diamond"}:
        return bool(0.7 <= aspect <= 1.43)
    if grammar["kind"] == "framed_diagonals":
        return bool(0.8 <= aspect <= 1.25)
    maximum_aspect = grammar.get("max_aspect", 2.5)
    return bool(1 / maximum_aspect <= aspect <= maximum_aspect)


def _label_in_frame(page: Any, rect: pymupdf.Rect, label: str) -> bool:
    inset = min(rect.width, rect.height) * 0.05
    inside = pymupdf.Rect(rect.x0 + inset, rect.y0 + inset, rect.x1 - inset, rect.y1 - inset)
    for word in page.get_text("words"):
        if str(word[4]).upper().strip() != label:
            continue
        bounds = pymupdf.Rect(word[:4])
        if inside.contains(bounds.tl) and inside.contains(bounds.br):
            return True
    return False


def _nested_gray_frame(
    page: Any,
    outer: pymupdf.Rect,
    outer_index: int,
    label: str,
    frames: tuple[tuple[str, pymupdf.Rect, int], ...],
    drawings: tuple[dict[str, Any], ...],
) -> bool:
    for kind, inner, index in frames:
        if kind != "rectangle" or index == outer_index or not outer.contains(inner):
            continue
        if not (0.65 <= inner.width / outer.width <= 0.98):
            continue
        if not (0.65 <= inner.height / outer.height <= 0.98):
            continue
        if abs(inner.x0 + inner.x1 - outer.x0 - outer.x1) > outer.width * 0.1:
            continue
        if abs(inner.y0 + inner.y1 - outer.y0 - outer.y1) > outer.height * 0.1:
            continue
        fill = drawings[index].get("fill")
        if not isinstance(fill, (tuple, list)) or len(fill) < 3:
            continue
        channels = tuple(float(channel) for channel in fill[:3])
        if not all(0.15 <= channel <= 0.9 for channel in channels):
            continue
        if max(channels) - min(channels) > 0.12:
            continue
        if _label_in_frame(page, inner, label):
            return True
    return False


def _frame_has_text(page: Any, rect: pymupdf.Rect) -> bool:
    for word in page.get_text("words"):
        bounds = pymupdf.Rect(word[:4])
        center = pymupdf.Point((bounds.x0 + bounds.x1) / 2, (bounds.y0 + bounds.y1) / 2)
        if rect.contains(center):
            return True
    return False


def _proposal_mark(
    frame: pymupdf.Rect, frame_index: int, drawings: tuple[dict[str, Any], ...]
) -> bool:
    area = frame.width * frame.height
    for index, drawing in enumerate(drawings):
        if index == frame_index or drawing.get("type") in {"clip", "group"}:
            continue
        items = drawing.get("items") or ()
        bounds = _drawing_bounds(drawing, items)
        if bounds is None or not frame.intersects(bounds):
            continue
        if (
            drawing.get("fill") is not None
            and frame.contains(bounds)
            and bounds.width * bounds.height >= area * 0.06
        ):
            return True
        for item in items:
            if item[0] != "l":
                continue
            a, b = pymupdf.Point(item[1]), pymupdf.Point(item[2])
            line_bounds = pymupdf.Rect(min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y))
            if (
                abs(a.x - b.x) >= frame.width * 0.55
                and abs(a.y - b.y) >= frame.height * 0.55
                and frame.intersects(line_bounds)
            ):
                return True
    return False


def _triangle_in_frame(
    frame: pymupdf.Rect, fill: str, drawings: tuple[dict[str, Any], ...]
) -> bool:
    for drawing in drawings:
        if drawing.get("type") in {"clip", "group"}:
            continue
        items = drawing.get("items") or ()
        lines = [item for item in items if item[0] == "l"]
        if len(lines) != 3 or len(items) != 3:
            continue
        bounds = _drawing_bounds(drawing, items)
        if bounds is None or not frame.contains(bounds):
            continue
        if bounds.width < frame.width * 0.5 or bounds.height < frame.height * 0.5:
            continue
        points = {
            (round(point.x, 2), round(point.y, 2))
            for item in lines
            for point in (pymupdf.Point(item[1]), pymupdf.Point(item[2]))
        }
        if len(points) != 3:
            continue
        top = min(points, key=lambda point: point[1])
        base = sorted((point for point in points if point != top), key=lambda point: point[0])
        if (
            abs(top[0] - (bounds.x0 + bounds.x1) / 2) > bounds.width * 0.18
            or abs(base[0][1] - base[1][1]) > bounds.height * 0.15
            or abs(base[0][0] - bounds.x0) > bounds.width * 0.15
            or abs(base[1][0] - bounds.x1) > bounds.width * 0.15
        ):
            continue
        is_solid = drawing.get("fill") is not None
        if is_solid == (fill == "solid"):
            return True
    return False


def _diagonal_count(rect: pymupdf.Rect, drawings: tuple[dict[str, Any], ...]) -> int:
    corners = (rect.tl, rect.tr, rect.br, rect.bl)
    pairs = ((corners[0], corners[2]), (corners[1], corners[3]))
    count = 0
    tolerance = max(1.5, min(rect.width, rect.height) * 0.12)
    for start, end in pairs:
        for drawing in drawings:
            for item in drawing.get("items") or ():
                if item[0] != "l":
                    continue
                a, b = pymupdf.Point(item[1]), pymupdf.Point(item[2])
                if (abs(a - start) <= tolerance and abs(b - end) <= tolerance) or (
                    abs(a - end) <= tolerance and abs(b - start) <= tolerance
                ):
                    count += 1
                    break
            else:
                continue
            break
    return count


def _nested_rectangles_bar(
    outer: pymupdf.Rect,
    frames: tuple[tuple[str, pymupdf.Rect, int], ...],
    drawings: tuple[dict[str, Any], ...],
) -> bool:
    for kind, inner, _ in frames:
        if kind != "rectangle" or inner == outer or not outer.contains(inner):
            continue
        width_ratio, height_ratio = inner.width / outer.width, inner.height / outer.height
        if not (0.45 <= width_ratio <= 0.85 and 0.45 <= height_ratio <= 0.85):
            continue
        if abs(inner.x0 + inner.x1 - outer.x0 - outer.x1) > outer.width * 0.16:
            continue
        if abs(inner.y0 + inner.y1 - outer.y0 - outer.y1) > outer.height * 0.16:
            continue
        for drawing in drawings:
            for item in drawing.get("items") or ():
                if item[0] != "l":
                    continue
                a, b = pymupdf.Point(item[1]), pymupdf.Point(item[2])
                mid_y = (inner.y0 + inner.y1) / 2
                if (
                    abs(a.y - mid_y) <= inner.height * 0.12
                    and abs(b.y - mid_y) <= inner.height * 0.12
                    and abs(a.x - b.x) >= inner.width * 0.6
                    and min(a.x, b.x) >= outer.x0 - 1
                    and max(a.x, b.x) <= outer.x1 + 1
                ):
                    return True
    return False


def _diamond_three_dots(
    diamond: pymupdf.Rect, frames: tuple[tuple[str, pymupdf.Rect, int], ...]
) -> bool:
    dots = []
    for kind, rect, _ in frames:
        if kind != "ellipse" or not diamond.contains(rect):
            continue
        if not (0.06 <= rect.width / diamond.width <= 0.3):
            continue
        if not (0.06 <= rect.height / diamond.height <= 0.3):
            continue
        center = pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
        dx = abs(center.x - (diamond.x0 + diamond.x1) / 2) / (diamond.width / 2)
        dy = abs(center.y - (diamond.y0 + diamond.y1) / 2) / (diamond.height / 2)
        if dx + dy < 0.85:
            dots.append(rect)
    return len(dots) == 3


@dataclass(frozen=True, slots=True)
class _Disc:
    """A small filled round mark; ``members`` are the drawings that paint it."""

    rect: pymupdf.Rect
    index: int
    members: frozenset[int]
    fill: _RGB


_Band = tuple[pymupdf.Rect, int]
_Segment = tuple[pymupdf.Point, pymupdf.Point, int]


def _rgb(value: Any) -> _RGB | None:
    if not isinstance(value, (tuple, list)) or len(value) < 3:
        return None
    red, green, blue = (float(channel) for channel in value[:3])
    if not all(math.isfinite(channel) for channel in (red, green, blue)):
        return None
    return (red, green, blue)


def _round_aspect(rect: pymupdf.Rect) -> bool:
    if rect.is_empty or rect.width <= 0 or rect.height <= 0:
        return False
    return bool(
        0.8 <= rect.width / rect.height <= 1.25 and max(rect.width, rect.height) <= _MAX_DISC_SPAN
    )


def _ends_on_ellipse(curves: list[Any], rect: pymupdf.Rect) -> bool:
    center_x, center_y = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
    for curve in curves:
        for raw in (curve[1], curve[4]):
            point = pymupdf.Point(raw)
            dx = (point.x - center_x) / (rect.width / 2)
            dy = (point.y - center_y) / (rect.height / 2)
            if abs(math.hypot(dx, dy) - 1) > 0.12:
                return False
    return True


def _curve_disc(drawing: dict[str, Any], index: int) -> _Disc | None:
    """A filled path of four curves, optionally closed by one short line."""
    fill = _rgb(drawing.get("fill"))
    if fill is None or drawing.get("type") in {"clip", "group"}:
        return None
    items = drawing.get("items") or ()
    curves = [item for item in items if item[0] == "c"]
    others = [item for item in items if item[0] != "c"]
    if len(curves) != 4 or len(others) > 1 or any(item[0] != "l" for item in others):
        return None
    rect = _drawing_bounds(drawing, items)
    if rect is None or not _round_aspect(rect) or not _ends_on_ellipse(curves, rect):
        return None
    limit = min(rect.width, rect.height) * 0.25
    if any(abs(pymupdf.Point(item[1]) - pymupdf.Point(item[2])) > limit for item in others):
        return None
    return _Disc(rect, index, frozenset({index}), fill)


def _band_rects(drawing: dict[str, Any]) -> list[pymupdf.Rect]:
    """Thin filled horizontal bands painted by one drawing.

    Rectangles and quads count one band each; a line-only path (a polygon or a
    band tessellated into triangles) counts as one band by its bounds.
    """
    if drawing.get("type") in {"clip", "group"}:
        return []
    items = drawing.get("items") or ()
    kinds = {item[0] for item in items}
    if kinds == {"re"}:
        rects = [pymupdf.Rect(item[1]) for item in items]
    elif kinds == {"qu"}:
        rects = [pymupdf.Quad(item[1]).rect for item in items]
    elif kinds == {"l"} and len(items) >= 3:
        bounds = _drawing_bounds(drawing, items)
        rects = [] if bounds is None else [bounds]
    else:
        return []
    return [rect for rect in rects if 0 < rect.height <= 0.6 and 0 < rect.width <= _MAX_DISC_SPAN]


def _disc_profile(stack: list[_Band], union: pymupdf.Rect) -> bool:
    """Every band is centred and about as wide as the disc chord at its height."""
    center_x, center_y = (union.x0 + union.x1) / 2, (union.y0 + union.y1) / 2
    for rect, _ in stack:
        if abs((rect.x0 + rect.x1) / 2 - center_x) > union.width * 0.15:
            return False
        offset = ((rect.y0 + rect.y1) / 2 - center_y) / (union.height / 2)
        chord = union.width * math.sqrt(max(0.0, 1 - offset * offset))
        if abs(rect.width - chord) > union.width * 0.25:
            return False
    return True


def _stack_disc(stack: list[_Band], fill: _RGB) -> _Disc | None:
    if len(stack) < 5:
        return None
    union = pymupdf.Rect(stack[0][0])
    for rect, _ in stack[1:]:
        union |= rect
    if not _round_aspect(union) or not _disc_profile(stack, union):
        return None
    members = frozenset(index for _, index in stack)
    return _Disc(union, min(members), members, fill)


def _continues(stack: list[_Band], rect: pymupdf.Rect) -> bool:
    last = stack[-1][0]
    offset = abs((rect.x0 + rect.x1) / 2 - (last.x0 + last.x1) / 2)
    return abs(rect.y0 - last.y1) <= 0.15 and offset <= max(last.width, rect.width) * 0.5


def _band_stacks(bands: list[_Band]) -> Iterator[list[_Band]]:
    """Group same-colour bands into vertical stacks without gaps."""
    open_stacks: list[list[_Band]] = []
    for rect, index in sorted(bands, key=lambda band: (band[0].y0, band[0].x0)):
        still_open = []
        for stack in open_stacks:
            if stack[-1][0].y1 < rect.y0 - 0.15:
                yield stack
            else:
                still_open.append(stack)
        open_stacks = still_open
        target = next((stack for stack in open_stacks if _continues(stack, rect)), None)
        if target is None:
            open_stacks.append([(rect, index)])
        else:
            target.append((rect, index))
    yield from open_stacks


def _band_discs(drawings: tuple[dict[str, Any], ...]) -> list[_Disc]:
    bands_by_fill: dict[_RGB, list[_Band]] = {}
    for index, drawing in enumerate(drawings):
        fill = _rgb(drawing.get("fill"))
        if fill is not None:
            key = (round(fill[0], 3), round(fill[1], 3), round(fill[2], 3))
            bands_by_fill.setdefault(key, []).extend((rect, index) for rect in _band_rects(drawing))
    discs = []
    for fill, bands in bands_by_fill.items():
        for stack in _band_stacks(bands):
            disc = _stack_disc(stack, fill)
            if disc is not None:
                discs.append(disc)
    return discs


def _disc_candidates(drawings: tuple[dict[str, Any], ...]) -> tuple[_Disc, ...]:
    """Curve discs and banded discs, one per rounded box."""
    found: dict[tuple[float, float, float, float], _Disc] = {}
    curve_discs = [_curve_disc(drawing, index) for index, drawing in enumerate(drawings)]
    for disc in (*(disc for disc in curve_discs if disc is not None), *_band_discs(drawings)):
        found.setdefault(_rounded_box(disc.rect), disc)
    return tuple(found.values())


def _visible_segments(drawings: tuple[dict[str, Any], ...]) -> tuple[_Segment, ...]:
    """Stroked straight segments in a colour other than near white."""
    segments: list[_Segment] = []
    for index, drawing in enumerate(drawings):
        color = _rgb(drawing.get("color"))
        if "s" not in str(drawing.get("type") or "") or color is None or min(color) >= 0.9:
            continue
        segments.extend(
            (pymupdf.Point(item[1]), pymupdf.Point(item[2]), index)
            for item in drawing.get("items") or ()
            if item[0] == "l"
        )
    return tuple(segments)


def _has_terminal_line(segments: tuple[_Segment, ...], disc: _Disc, span: float) -> bool:
    """A line from elsewhere ends at the disc centre instead of passing through it."""
    center = (disc.rect.tl + disc.rect.br) / 2
    near, far = max(0.6, 0.35 * span), 2 * span
    for start, end, index in segments:
        if index in disc.members:
            continue
        closest, farthest = sorted((abs(start - center), abs(end - center)))
        if closest <= near and farthest > far:
            return True
    return False


def _covered_later(drawings: tuple[dict[str, Any], ...], disc: _Disc) -> bool:
    """A later opaque fill containing the disc hides it on the rendered page."""
    rect = disc.rect
    inner = pymupdf.Rect(rect.x0 + 0.01, rect.y0 + 0.01, rect.x1 - 0.01, rect.y1 - 0.01)
    for drawing in drawings[max(disc.members) + 1 :]:
        if drawing.get("type") in {"clip", "group"} or _rgb(drawing.get("fill")) is None:
            continue
        opacity = drawing.get("fill_opacity")
        if opacity is not None and float(opacity) < 0.99:
            continue
        bounds = _drawing_bounds(drawing, drawing.get("items") or ())
        if bounds is not None and bounds.contains(inner):
            return True
    return False


def _geometry(page: Any, rect: pymupdf.Rect) -> GeometriaObservacaoSimbolo:
    bounds = _box_geometry(page, rect)
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
    corners = (rect.tl, rect.tr, rect.br, rect.bl)
    transformed = tuple(point * page.rotation_matrix for point in corners)
    clipped = any(not (0 <= point.x <= width and 0 <= point.y <= height) for point in transformed)
    original: tuple[PontoOriginalSimbolo, ...] = tuple(
        (Decimal(str(point.x)), Decimal(str(point.y))) for point in corners
    )
    return GeometriaObservacaoSimbolo(
        tipo=TipoGeometria.CAIXA,
        pontos_originais=original,
        pontos_normalizados=bounds.pontos,
        transformacao=TransformacaoSimbolo(
            normalizada_para_original=matrix,
            sistema_original="pymupdf-page-unrotated:points:top-left",
        ),
        normalizacao_limitada=clipped,
    )


_ObservationKey = tuple[str, tuple[float, float, float, float]]
_Frame = tuple[str, pymupdf.Rect, int]


@dataclass(frozen=True, slots=True, kw_only=True)
class _ObservationContext:
    """Page inputs shared by the known-grammar and unknown-region paths."""

    page: Any
    source: FonteObservacaoSimbolo
    profile: PerfilMetodoSimbolos
    drawings: tuple[dict[str, Any], ...]
    frames: tuple[_Frame, ...]
    discs: tuple[_Disc, ...] = ()
    segments: tuple[_Segment, ...] = ()
    word_boxes: tuple[pymupdf.Rect, ...] = ()


def _validate_page_size(page: Any) -> None:
    if not math.isfinite(float(page.rect.width)) or float(page.rect.width) <= 0:
        raise ValueError("Page width must be positive and finite")
    if not math.isfinite(float(page.rect.height)) or float(page.rect.height) <= 0:
        raise ValueError("Page height must be positive and finite")


def _rounded_box(rect: pymupdf.Rect) -> tuple[float, float, float, float]:
    return (round(rect.x0, 3), round(rect.y0, 3), round(rect.x1, 3), round(rect.y1, 3))


def _label_in_frame_matches(
    context: _ObservationContext, grammar: Package, rect: pymupdf.Rect, index: int
) -> bool:
    page, drawings = context.page, context.drawings
    return (
        _label_in_frame(page, rect, grammar["label"])
        and (not grammar.get("empty_interior") or not _proposal_mark(rect, index, drawings))
        and (
            not grammar.get("nested_frame")
            or _nested_gray_frame(page, rect, index, grammar["label"], context.frames, drawings)
        )
    )


def _grammar_matches(
    context: _ObservationContext, grammar: Package, rect: pymupdf.Rect, index: int
) -> bool:
    if grammar["kind"] == "label_in_frame":
        return _label_in_frame_matches(context, grammar, rect, index)
    if grammar["kind"] == "triangle_in_frame":
        return _triangle_in_frame(rect, grammar["fill"], context.drawings)
    if grammar["kind"] == "framed_diagonals":
        return (
            not _frame_has_text(context.page, rect)
            and _diagonal_count(rect, context.drawings) >= grammar["min_diagonals"]
        )
    if grammar["kind"] == "nested_rectangles_bar":
        return _nested_rectangles_bar(rect, context.frames, context.drawings)
    return _diamond_three_dots(rect, context.frames)


def _terminal_disc_matches(context: _ObservationContext, grammar: Package, disc: _Disc) -> bool:
    span = max(disc.rect.width, disc.rect.height)
    if not grammar["min_span"] <= span <= grammar["max_span"]:
        return False
    if not _DISC_FILLS[grammar["fill"]](disc.fill):
        return False
    if any(disc.rect.contains((box.tl + box.br) / 2) for box in context.word_boxes):
        return False
    return _has_terminal_line(context.segments, disc, span) and not _covered_later(
        context.drawings, disc
    )


def _variant_matches(
    context: _ObservationContext, grammar: Package
) -> Iterator[tuple[pymupdf.Rect, int]]:
    if grammar["kind"] == "terminal_disc":
        for disc in context.discs:
            if _terminal_disc_matches(context, grammar, disc):
                yield disc.rect, disc.index
        return
    for frame, rect, index in context.frames:
        if _frame_ok(frame, rect, grammar) and _grammar_matches(context, grammar, rect, index):
            yield rect, index


def _primitive(
    drawings: tuple[dict[str, Any], ...], rect: pymupdf.Rect, index: int
) -> PrimitivaObservadaSimbolo:
    return PrimitivaObservadaSimbolo(
        indice=str(index),
        camada=str(drawings[index]["layer"]) if drawings[index].get("layer") else None,
        pontos_originais=tuple(
            (Decimal(str(point.x)), Decimal(str(point.y)))
            for point in (rect.tl, rect.tr, rect.br, rect.bl)
        ),
    )


def _known_observation(
    context: _ObservationContext,
    package: Package,
    variant: Package,
    grammar: Package,
    rect: pymupdf.Rect,
    index: int,
) -> ObservacaoSimbolo:
    ref = variant["source_ref"]
    attributes = tuple(
        sorted(
            {
                "familia_inventario": package["family_id"],
                "variante_inventario": variant["id"],
                "referencias_possiveis": variant["id"],
                "papel": variant["role"],
                "destino": variant["destination"],
                "contexto": "unknown",
                "fonte_referencia": ref["source_id"],
                "localizador_referencia": ref["locator"],
                "gramatica": grammar["kind"],
            }.items()
        )
    )
    return ObservacaoSimbolo(
        fonte=context.source,
        metodo_assinatura=context.profile.assinatura(),
        geometria=_geometry(context.page, rect),
        alternativas=(AlternativaClasseSimbolo(classe=variant["class_code"]),),
        score_bruto=None,
        primitivas=(_primitive(context.drawings, rect, index),),
        template=variant["id"],
        atributos=attributes,
    )


def _observe_variant(
    context: _ObservationContext,
    package: Package,
    variant: Package,
    observations: list[ObservacaoSimbolo],
    seen: set[_ObservationKey],
) -> None:
    grammar = variant["recognition"]["grammar"]
    for rect, index in _variant_matches(context, grammar):
        key = (str(variant["id"]), _rounded_box(rect))
        if key in seen:
            continue
        seen.add(key)
        observations.append(_known_observation(context, package, variant, grammar, rect, index))


def _unknown_frame(frames: tuple[_Frame, ...], region: pymupdf.Rect) -> _Frame:
    matching = [
        (kind, rect, index)
        for kind, rect, index in frames
        if max(rect.width, rect.height) <= 72
        and min(rect.width, rect.height) >= 4
        and abs(rect.x0 - region.x0) <= 1
        and abs(rect.y0 - region.y0) <= 1
        and abs(rect.x1 - region.x1) <= 1
        and abs(rect.y1 - region.y1) <= 1
    ]
    if not matching:
        raise ValueError("Unknown candidate must coincide with a compact closed vector frame")
    return matching[0]


def _coincides_with_observation(rect: pymupdf.Rect, observations: list[ObservacaoSimbolo]) -> bool:
    return any(
        all(
            abs(a - b) <= 1
            for a, b in zip(
                (rect.x0, rect.y0, rect.x1, rect.y1),
                (
                    float(known.geometria.pontos_originais[0][0]),
                    float(known.geometria.pontos_originais[0][1]),
                    float(known.geometria.pontos_originais[2][0]),
                    float(known.geometria.pontos_originais[2][1]),
                ),
                strict=True,
            )
        )
        for known in observations
    )


def _observe_unknown_region(
    context: _ObservationContext,
    supplied: pymupdf.Rect,
    observations: list[ObservacaoSimbolo],
    seen: set[_ObservationKey],
) -> None:
    region = pymupdf.Rect(supplied)
    kind, rect, index = _unknown_frame(context.frames, region)
    # Earlier unknown observations also count, as they were appended in order.
    if _coincides_with_observation(rect, observations):
        return
    key = ("unknown", _rounded_box(rect))
    if key in seen:
        return
    seen.add(key)
    observations.append(
        ObservacaoSimbolo(
            fonte=context.source,
            metodo_assinatura=context.profile.assinatura(),
            geometria=_geometry(context.page, rect),
            alternativas=(AlternativaClasseSimbolo(classe=None),),
            primitivas=(_primitive(context.drawings, rect, index),),
            atributos=tuple(
                sorted(
                    {
                        "papel": "unknown",
                        "destino": "review_only",
                        "contexto": "unknown",
                        "gramatica": f"unmatched_closed_{kind}",
                    }.items()
                )
            ),
        )
    )


def _coverage_state(
    observations: list[ObservacaoSimbolo], profile: PerfilMetodoSimbolos
) -> EstadoMetodoSimbolos:
    if observations:
        return EstadoMetodoSimbolos.CONCLUIDO
    if not profile.classes_suportadas:
        return EstadoMetodoSimbolos.FORA_DOMINIO
    return EstadoMetodoSimbolos.NAO_DETECCAO


def _page_context(
    page: Any,
    source: FonteObservacaoSimbolo,
    profile: PerfilMetodoSimbolos,
    drawings: tuple[dict[str, Any], ...],
    enabled: tuple[tuple[Package, Package], ...],
) -> _ObservationContext:
    """Collect disc inputs only when an enabled grammar needs them."""
    kinds = {variant["recognition"]["grammar"]["kind"] for _, variant in enabled}
    discs = _disc_candidates(drawings) if "terminal_disc" in kinds else ()
    words = page.get_text("words") if discs else ()
    return _ObservationContext(
        page=page,
        source=source,
        profile=profile,
        drawings=drawings,
        frames=_frame_candidates(drawings),
        discs=discs,
        segments=_visible_segments(drawings) if discs else (),
        word_boxes=tuple(pymupdf.Rect(word[:4]) for word in words),
    )


def observar_pacotes(
    page: Any,
    *,
    documento_id: str,
    documento_sha256: str,
    pagina_numero: int,
    pacotes: tuple[Package, ...] | None = None,
    regioes_desconhecidas: tuple[pymupdf.Rect, ...] = (),
) -> ResultadoMetodoSimbolos:
    """Run enabled grammars; explicit unmatched frames remain unknown candidates.

    A caller may submit candidate regions from an independent visual pass. The
    unknown path only accepts an actual compact closed frame in ``get_drawings``
    and never increases E01 known-class coverage. No reference ROI is read here.
    """
    _validate_page_size(page)
    loaded = carregar_pacotes() if pacotes is None else pacotes
    profile = perfil_pacotes(loaded)
    source = FonteObservacaoSimbolo(
        documento_id=documento_id,
        documento_sha256=documento_sha256,
        pagina_numero=pagina_numero,
        camada="base",
    )
    drawings = tuple(page.get_drawings(extended=True))
    enabled = _enabled(loaded)
    context = _page_context(page, source, profile, drawings, enabled)
    observations: list[ObservacaoSimbolo] = []
    seen: set[_ObservationKey] = set()
    for package, variant in enabled:
        _observe_variant(context, package, variant, observations, seen)
    for supplied in regioes_desconhecidas:
        _observe_unknown_region(context, supplied, observations, seen)
    coverage_state = _coverage_state(observations, profile)
    coverage = CoberturaMetodoSimbolos(
        fonte=source,
        regiao_normalizada=(
            PontoNormalizado(Decimal(0), Decimal(0)),
            PontoNormalizado(Decimal(1), Decimal(1)),
        ),
        classes_avaliadas=profile.classes_suportadas,
        estado=coverage_state,
        motivo=None if profile.classes_suportadas else "Nenhuma variante com gramática habilitada",
    )
    return ResultadoMetodoSimbolos(
        perfil=profile, coberturas=(coverage,), observacoes=tuple(observations)
    )
