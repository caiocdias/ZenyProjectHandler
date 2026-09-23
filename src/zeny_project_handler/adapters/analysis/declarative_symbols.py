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
}
_INFORMATIVE_DESTINATIONS = {"informative_only", "document_convention"}


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _validate_package(package: Any, path: Path) -> Package:
    if not isinstance(package, dict):
        raise ValueError(f"{path}: package must be an object")
    if set(package) != {"schema_version", "family_id", "profile_id", "source_id", "variants"}:
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
    seen: set[str] = set()
    for variant in variants:
        if not isinstance(variant, dict) or set(variant) != {
            "id",
            "class_code",
            "role",
            "destination",
            "source_ref",
            "visual_note",
            "recognition",
        }:
            raise ValueError(f"{path}: variant fields disagree with schema")
        variant_id = _required_text(variant["id"], "variant.id")
        if variant_id in seen:
            raise ValueError(f"{path}: duplicate variant {variant_id}")
        seen.add(variant_id)
        _required_text(variant["class_code"], "class_code")
        role = variant["role"]
        destination = _required_text(variant["destination"], "destination")
        if role not in _ROLES or (destination in _INFORMATIVE_DESTINATIONS) != (
            role == "informative"
        ):
            raise ValueError(f"{path}: invalid role/destination for {variant_id}")
        _required_text(variant["visual_note"], "visual_note")
        ref = variant["source_ref"]
        if not isinstance(ref, dict) or set(ref) != {
            "source_id",
            "pdf_page",
            "locator",
            "review_status",
        }:
            raise ValueError(f"{path}: invalid source_ref for {variant_id}")
        if ref["source_id"] != source_id or type(ref["pdf_page"]) is not int or ref["pdf_page"] < 1:
            raise ValueError(f"{path}: source mismatch for {variant_id}")
        _required_text(ref["locator"], "source_ref.locator")
        if ref["review_status"] not in {"visual_checked", "synthetic_fixture"}:
            raise ValueError(f"{path}: source is not reviewed for {variant_id}")
        recognition = variant["recognition"]
        if not isinstance(recognition, dict):
            raise ValueError(f"{path}: missing recognition for {variant_id}")
        negatives = recognition.get("negative_examples")
        if (
            not isinstance(negatives, list)
            or not negatives
            or any(not isinstance(item, str) or len(item.strip()) < 3 for item in negatives)
            or len(set(negatives)) != len(negatives)
        ):
            raise ValueError(f"{path}: invalid negative examples for {variant_id}")
        if recognition.get("status") == "pending":
            if (
                set(recognition) != {"status", "reason", "negative_examples"}
                or len(_required_text(recognition["reason"], "recognition.reason")) < 12
            ):
                raise ValueError(f"{path}: pending row lacks reason for {variant_id}")
            continue
        if recognition.get("status") != "enabled" or set(recognition) != {
            "status",
            "grammar",
            "negative_examples",
        }:
            raise ValueError(f"{path}: invalid recognition status for {variant_id}")
        grammar = recognition["grammar"]
        if not isinstance(grammar, dict) or grammar.get("kind") not in _GRAMMARS:
            raise ValueError(f"{path}: unsupported grammar for {variant_id}")
        if grammar["kind"] == "label_in_frame":
            valid = (
                {"kind", "frame", "label", "max_span"} <= set(grammar)
                and set(grammar)
                <= {
                    "kind",
                    "frame",
                    "label",
                    "max_span",
                    "max_aspect",
                    "empty_interior",
                    "nested_frame",
                    "inner_fill",
                }
                and grammar["frame"] in {"rectangle", "ellipse"}
                and isinstance(grammar["label"], str)
                and bool(re.fullmatch(r"[A-Z0-9]{1,4}", grammar["label"]))
                and (
                    "max_aspect" not in grammar
                    or (
                        isinstance(grammar["max_aspect"], (int, float))
                        and not isinstance(grammar["max_aspect"], bool)
                        and 1 <= grammar["max_aspect"] <= 4
                    )
                )
                and ("empty_interior" not in grammar or grammar["empty_interior"] is True)
                and (
                    ("nested_frame" not in grammar and "inner_fill" not in grammar)
                    or (grammar.get("nested_frame") is True and grammar.get("inner_fill") == "gray")
                )
            )
        elif grammar["kind"] == "triangle_in_frame":
            valid = (
                set(grammar) == {"kind", "frame", "fill", "max_span"}
                and grammar["frame"] == "rectangle"
                and grammar["fill"] in {"empty", "solid"}
            )
        elif grammar["kind"] == "framed_diagonals":
            valid = (
                set(grammar) == {"kind", "frame", "min_diagonals", "max_span"}
                and grammar["frame"] == "rectangle"
                and grammar["min_diagonals"] == 2
            )
        elif grammar["kind"] == "nested_rectangles_bar":
            valid = (
                set(grammar) == {"kind", "frame", "central_bar", "max_span"}
                and grammar["frame"] == "rectangle"
                and grammar["central_bar"] is True
            )
        else:
            valid = (
                set(grammar) == {"kind", "frame", "dot_count", "max_span"}
                and grammar["frame"] == "diamond"
                and grammar["dot_count"] == 3
            )
        span = grammar.get("max_span")
        max_allowed_span = 96 if grammar["kind"] == "label_in_frame" else 72
        if (
            not valid
            or isinstance(span, bool)
            or not isinstance(span, (int, float))
            or not (0 < span <= max_allowed_span)
        ):
            raise ValueError(f"{path}: invalid grammar fields for {variant_id}")
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
        versao="1.0.0",
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
    if not math.isfinite(float(page.rect.width)) or float(page.rect.width) <= 0:
        raise ValueError("Page width must be positive and finite")
    if not math.isfinite(float(page.rect.height)) or float(page.rect.height) <= 0:
        raise ValueError("Page height must be positive and finite")
    loaded = carregar_pacotes() if pacotes is None else pacotes
    profile = perfil_pacotes(loaded)
    source = FonteObservacaoSimbolo(
        documento_id=documento_id,
        documento_sha256=documento_sha256,
        pagina_numero=pagina_numero,
        camada="base",
    )
    drawings = tuple(page.get_drawings(extended=True))
    frames = _frame_candidates(drawings)
    observations = []
    seen: set[tuple[str, tuple[float, float, float, float]]] = set()
    for package, variant in _enabled(loaded):
        grammar = variant["recognition"]["grammar"]
        for frame, rect, index in frames:
            if not _frame_ok(frame, rect, grammar):
                continue
            if grammar["kind"] == "label_in_frame":
                matched = (
                    _label_in_frame(page, rect, grammar["label"])
                    and (
                        not grammar.get("empty_interior")
                        or not _proposal_mark(rect, index, drawings)
                    )
                    and (
                        not grammar.get("nested_frame")
                        or _nested_gray_frame(page, rect, index, grammar["label"], frames, drawings)
                    )
                )
            elif grammar["kind"] == "triangle_in_frame":
                matched = _triangle_in_frame(rect, grammar["fill"], drawings)
            elif grammar["kind"] == "framed_diagonals":
                matched = (
                    not _frame_has_text(page, rect)
                    and _diagonal_count(rect, drawings) >= grammar["min_diagonals"]
                )
            elif grammar["kind"] == "nested_rectangles_bar":
                matched = _nested_rectangles_bar(rect, frames, drawings)
            else:
                matched = _diamond_three_dots(rect, frames)
            if not matched:
                continue
            key = (
                str(variant["id"]),
                (
                    round(rect.x0, 3),
                    round(rect.y0, 3),
                    round(rect.x1, 3),
                    round(rect.y1, 3),
                ),
            )
            if key in seen:
                continue
            seen.add(key)
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
            observations.append(
                ObservacaoSimbolo(
                    fonte=source,
                    metodo_assinatura=profile.assinatura(),
                    geometria=_geometry(page, rect),
                    alternativas=(AlternativaClasseSimbolo(classe=variant["class_code"]),),
                    score_bruto=None,
                    primitivas=(
                        PrimitivaObservadaSimbolo(
                            indice=str(index),
                            camada=str(drawings[index]["layer"])
                            if drawings[index].get("layer")
                            else None,
                            pontos_originais=tuple(
                                (Decimal(str(point.x)), Decimal(str(point.y)))
                                for point in (rect.tl, rect.tr, rect.br, rect.bl)
                            ),
                        ),
                    ),
                    template=variant["id"],
                    atributos=attributes,
                )
            )
    for supplied in regioes_desconhecidas:
        region = pymupdf.Rect(supplied)
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
        kind, rect, index = matching[0]
        if any(
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
        ):
            continue
        key = (
            "unknown",
            (round(rect.x0, 3), round(rect.y0, 3), round(rect.x1, 3), round(rect.y1, 3)),
        )
        if key in seen:
            continue
        seen.add(key)
        observations.append(
            ObservacaoSimbolo(
                fonte=source,
                metodo_assinatura=profile.assinatura(),
                geometria=_geometry(page, rect),
                alternativas=(AlternativaClasseSimbolo(classe=None),),
                primitivas=(
                    PrimitivaObservadaSimbolo(
                        indice=str(index),
                        camada=str(drawings[index]["layer"])
                        if drawings[index].get("layer")
                        else None,
                        pontos_originais=tuple(
                            (Decimal(str(point.x)), Decimal(str(point.y)))
                            for point in (rect.tl, rect.tr, rect.br, rect.bl)
                        ),
                    ),
                ),
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
    if observations:
        coverage_state = EstadoMetodoSimbolos.CONCLUIDO
    elif not profile.classes_suportadas:
        coverage_state = EstadoMetodoSimbolos.FORA_DOMINIO
    else:
        coverage_state = EstadoMetodoSimbolos.NAO_DETECCAO
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
