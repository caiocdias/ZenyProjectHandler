# mypy: disable-error-code="no-untyped-call"
"""Independent positive and near-miss drawings for enabled E07 grammars.

The manifest is a reviewer reference. Pass only the PDF to an inference runner;
compare predictions with the returned manifest after inference has completed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf


@dataclass(frozen=True)
class EnabledCase:
    variant_id: str
    family_id: str
    kind: str
    frame: str
    label: str = ""
    style: str = ""
    fill: str = ""


_INITIAL_ENABLED_CASES = (
    EnabledCase("cemig-eo-r3-s05-v004", "family-f02-05", "nested_rectangles_bar", "rectangle"),
    EnabledCase("cemig-eo-r3-s07-v003", "family-f02-07", "label_in_frame", "rectangle", "QDP"),
    EnabledCase("cemig-eo-r3-s07-v004", "family-f02-07", "label_in_frame", "rectangle", "GDM"),
    EnabledCase("cemig-eo-r3-s07-v005", "family-f02-07", "label_in_frame", "rectangle", "QDM"),
    EnabledCase("cemig-eo-r3-s11-v001", "family-f02-11", "framed_diagonals", "rectangle"),
    EnabledCase("cemig-eo-r3-s27-v005", "family-f02-27", "diamond_three_dots", "diamond"),
    EnabledCase("cemig-eo-r3-s28-v002", "family-f02-28", "label_in_frame", "rectangle", "EC"),
    EnabledCase("cemig-eo-r3-s28-v003", "family-f02-28", "label_in_frame", "ellipse", "EC"),
    EnabledCase("cemig-eo-r3-s28-v004", "family-f02-28", "label_in_frame", "ellipse", "ES"),
    EnabledCase("cemig-eo-r3-s29-v001", "family-f02-29", "label_in_frame", "ellipse", "M"),
    EnabledCase("cemig-eo-r3-s30-v001", "family-f02-30", "label_in_frame", "rectangle", "CP"),
    EnabledCase("cemig-eo-r3-s31-v001", "family-f02-31", "label_in_frame", "rectangle", "CS"),
)

# Inspected independently on F02 PDF pages 10-11 (SHA-256 begins 0e29f0ea).
WAVE2_CASES = (
    EnabledCase(
        "cemig-eo-r3-s06-v001", "family-f02-06", "label_in_frame", "rectangle", "CT", "chamber"
    ),
    EnabledCase(
        "cemig-eo-r3-s06-v004", "family-f02-06", "label_in_frame", "rectangle", "CL", "chamber"
    ),
    EnabledCase(
        "cemig-eo-r3-s06-v007", "family-f02-06", "label_in_frame", "rectangle", "CM", "chamber"
    ),
    EnabledCase(
        "cemig-eo-r3-s07-v001", "family-f02-07", "triangle_in_frame", "rectangle", fill="empty"
    ),
    EnabledCase(
        "cemig-eo-r3-s07-v002", "family-f02-07", "triangle_in_frame", "rectangle", fill="solid"
    ),
)

# Source F02 PDF pages 29-30: four multiliteral associated-equipment symbols.
# The other short labels in §23 remain pending because their simple text/box
# combinations are more ambiguous outside the source table.
WAVE3_CASES = (
    EnabledCase(
        "cemig-eo-r3-s23-v002", "family-f02-23", "label_in_frame", "rectangle", "EH", "associated"
    ),
    EnabledCase(
        "cemig-eo-r3-s23-v005", "family-f02-23", "label_in_frame", "rectangle", "SF6", "associated"
    ),
    EnabledCase(
        "cemig-eo-r3-s23-v011", "family-f02-23", "label_in_frame", "rectangle", "BTX", "associated"
    ),
    EnabledCase(
        "cemig-eo-r3-s23-v012", "family-f02-23", "label_in_frame", "rectangle", "BQX", "associated"
    ),
)
ENABLED_CASES = _INITIAL_ENABLED_CASES + WAVE2_CASES + WAVE3_CASES


def negative_kinds(case: EnabledCase) -> tuple[str, ...]:
    common = ("unframed", "north")
    if case.kind == "label_in_frame":
        if case.style == "associated":
            return (*common, "simple_frame", "no_gray", "wrong_label", "table_text")
        if case.style == "chamber":
            return (*common, "empty_frame", "wrong_label", "filled_triangle", "crossed")
        return (*common, "empty_frame", "wrong_label")
    if case.kind == "triangle_in_frame":
        return (*common, "empty_frame", "wrong_fill")
    if case.kind == "framed_diagonals":
        return (*common, "one_diagonal", "labeled_x")
    if case.kind == "nested_rectangles_bar":
        return (*common, "without_inner", "without_bar")
    if case.kind == "diamond_three_dots":
        return (*common, "two_dots")
    raise AssertionError(f"No negative drawing for {case.kind}")


def draw_symbol(page: pymupdf.Page, case: EnabledCase, *, negative: str = "") -> None:
    if case.style == "associated":
        if negative == "table_text":
            page.draw_rect(pymupdf.Rect(80, 95, 220, 180), color=(0, 0, 0), width=1)
            page.draw_line((80, 135), (220, 135), color=(0, 0, 0), width=1)
            page.insert_text((118, 124), case.label, fontsize=11)
            return
        if negative != "unframed":
            page.draw_rect(pymupdf.Rect(108, 108, 168, 168), color=(0, 0, 0), width=1)
        if negative not in {"unframed", "simple_frame"}:
            page.draw_rect(
                pymupdf.Rect(114, 114, 162, 162),
                color=(0, 0, 0),
                fill=None if negative == "no_gray" else (0.86, 0.86, 0.88),
                width=1,
            )
        page.insert_text((119, 144), "ZZ" if negative == "wrong_label" else case.label, fontsize=11)
        return
    outer = (
        pymupdf.Rect(101, 115, 169, 149)
        if case.style == "chamber"
        else pymupdf.Rect(110, 110, 158, 158)
    )
    if case.kind == "diamond_three_dots":
        if negative != "unframed":
            shape = page.new_shape()
            shape.draw_polyline([(134, 110), (158, 134), (134, 158), (110, 134), (134, 110)])
            shape.finish(color=(0, 0, 0), width=1)
            shape.commit()
        dot_centers = ((126, 134), (134, 134), (142, 134))
        for x, y in dot_centers[: 2 if negative == "two_dots" else 3]:
            page.draw_circle((x, y), 3, color=(0, 0, 0), width=1)
        return

    if negative != "unframed":
        if case.frame == "ellipse":
            page.draw_oval(outer, color=(0, 0, 0), width=1)
        else:
            page.draw_rect(outer, color=(0, 0, 0), width=1)
    if case.kind == "label_in_frame":
        if negative != "empty_frame":
            position = (107, 140) if case.style == "chamber" else (116, 139)
            page.insert_text(
                position, "ZZ" if negative == "wrong_label" else case.label, fontsize=11
            )
        if case.style == "chamber":
            page.draw_line((143, 130), (149, 130), color=(1, 0.4, 1), width=1)
            page.draw_line((146, 127), (146, 133), color=(1, 0.4, 1), width=1)
            if negative == "filled_triangle":
                shape = page.new_shape()
                shape.draw_polyline([(136, 116), (168, 116), (168, 148), (136, 116)])
                shape.finish(color=(0.7, 0, 0), fill=(0.7, 0, 0), width=1)
                shape.commit()
            elif negative == "crossed":
                page.draw_line((101, 115), (169, 149), color=(0.7, 0, 0), width=1)
                page.draw_line((169, 115), (101, 149), color=(0.7, 0, 0), width=1)
    elif case.kind == "triangle_in_frame":
        if negative != "empty_frame":
            fill = case.fill != "empty"
            if negative == "wrong_fill":
                fill = not fill
            shape = page.new_shape()
            shape.draw_polyline([(134, 112), (156, 156), (112, 156), (134, 112)])
            shape.finish(color=(0.7, 0, 0), fill=(0.7, 0, 0) if fill else None, width=1)
            shape.commit()
    elif case.kind == "framed_diagonals":
        page.draw_line((111, 111), (157, 157), color=(0, 0, 0), width=1)
        if negative != "one_diagonal":
            page.draw_line((157, 111), (111, 157), color=(0, 0, 0), width=1)
        if negative == "labeled_x":
            page.insert_text((116, 139), "CT", fontsize=11)
    elif case.kind == "nested_rectangles_bar":
        if negative != "without_inner":
            page.draw_rect(pymupdf.Rect(118, 118, 150, 150), color=(0, 0, 0), width=1)
        if negative != "without_bar":
            page.draw_line((119, 134), (149, 134), color=(0, 0, 0), width=1)
    else:
        raise AssertionError(f"No positive drawing for {case.kind}")


def draw_north_negative(page: pymupdf.Page) -> None:
    page.insert_text((30, 38), "N", fontsize=13)
    page.draw_line((38, 48), (38, 100), color=(0, 0, 0), width=1)
    page.draw_line((38, 48), (32, 62), color=(0, 0, 0), width=1)
    page.draw_line((38, 48), (44, 62), color=(0, 0, 0), width=1)


def build_enabled_corpus(path: Path) -> dict[str, Any]:
    """Write one positive and several negative pages per enabled E07 variant."""
    rows: list[dict[str, Any]] = []
    with pymupdf.open() as document:
        for case in ENABLED_CASES:
            for negative in ("", *negative_kinds(case)):
                page = document.new_page(width=300, height=300)
                if negative == "north":
                    draw_north_negative(page)
                else:
                    draw_symbol(page, case, negative=negative)
                expected = [case.variant_id] if not negative else []
                if case.kind == "triangle_in_frame" and negative == "wrong_fill":
                    expected = [
                        "cemig-eo-r3-s07-v002" if case.fill == "empty" else "cemig-eo-r3-s07-v001"
                    ]
                rows.append(
                    {
                        "page": len(document),
                        "family_id": case.family_id,
                        "variant_id": case.variant_id,
                        "stratum": negative if negative else "positive",
                        "expected_variant_ids": expected,
                    }
                )
        document.save(path)
    return {
        "schema_version": 1,
        "pdf_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "pages": len(rows),
        "cases": rows,
    }
