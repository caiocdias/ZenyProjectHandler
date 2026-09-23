# mypy: disable-error-code="no-untyped-call"
"""Desenhos vetoriais autorais E06; expectativas ficam fora da inferência.

Os quatro padrões resumem as notas geométricas do inventário E01. As células
de situação preservam IDs próprios, mas cores e rótulos não criam uma classe
geométrica nova. Nenhum desenho ou ROI normativo é redistribuído aqui.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pymupdf

WIDTH = 360.0
HEIGHT = 260.0
Point = tuple[float, float]
Bounds = tuple[float, float, float, float]
INK = (0.14, 0.14, 0.14)
GREEN = (0.06, 0.48, 0.20)
RED = (0.78, 0.14, 0.16)


@dataclass(frozen=True)
class Variant:
    id: str
    shape: str
    situation: str = "existing"
    label: str | None = None


@dataclass(frozen=True)
class FixtureOccurrence:
    page_number: int
    variant_id: str | None
    shape: str | None
    bbox: Bounds
    stratum: str


VARIANTS: tuple[Variant, ...] = (
    *(
        Variant(f"cemig-eo-r3-s14-v{number:03d}", "anchor", situation)
        for number, situation in enumerate(("existing", "install", "remove"), 1)
    ),
    *(
        Variant(f"cemig-eo-r3-s14-v{number:03d}", "crossarm_crossarm", situation, "CZ-CZ")
        for number, situation in enumerate(("existing", "install", "remove"), 4)
    ),
    *(
        Variant(f"cemig-eo-r3-s14-v{number:03d}", "pole_pole", situation, "P-P")
        for number, situation in enumerate(("existing", "install", "remove"), 7)
    ),
    *(
        Variant(f"cemig-eo-r3-s14-v{number:03d}", "crossarm_pole_cut", situation, "CZ-P SECC")
        for number, situation in enumerate(("existing", "install", "remove"), 10)
    ),
    *(
        Variant(f"cemig-eo-r3-s14-v{number:03d}", "crossarm_pole", situation, "CZ-P")
        for number, situation in enumerate(("existing", "install", "remove"), 13)
    ),
    Variant("cemig-eo-r3-s15-v001", "anchor"),
    Variant("cemig-eo-r3-s15-v002", "pole_pole"),
)


def _bounds(points: list[Point]) -> Bounds:
    return (
        min(point[0] for point in points) / WIDTH,
        min(point[1] for point in points) / HEIGHT,
        max(point[0] for point in points) / WIDTH,
        max(point[1] for point in points) / HEIGHT,
    )


def _line(
    page: pymupdf.Page,
    a: Point,
    b: Point,
    points: list[Point],
    *,
    color: tuple[float, float, float],
    dashed: bool = False,
) -> None:
    page.draw_line(a, b, color=color, width=1.3, dashes="[5 3] 0" if dashed else None)
    points.extend((a, b))


def _hook(
    page: pymupdf.Page,
    x: float,
    y: float,
    points: list[Point],
    *,
    color: tuple[float, float, float],
    right: bool,
) -> None:
    side = 1.0 if right else -1.0
    start = (x, y - 15)
    end = (x, y + 15)
    control_a = (x + side * 13, y - 15)
    control_b = (x + side * 13, y + 15)
    page.draw_bezier(start, control_a, control_b, end, color=color, width=1.3)
    points.extend((start, control_a, control_b, end))


def _draw_guy(
    page: pymupdf.Page,
    shape: str,
    *,
    color: tuple[float, float, float] = INK,
    dashed: bool = False,
    label: str | None = None,
    support: bool = True,
    anchor_bar: bool = True,
    center: Point = (180.0, 130.0),
) -> Bounds:
    shift = center[0] - 180.0, center[1] - 130.0

    def pt(x: float, y: float) -> Point:
        return x + shift[0], y + shift[1]

    points: list[Point] = []
    if shape == "anchor":
        _line(page, pt(100, 130), pt(219, 130), points, color=color, dashed=dashed)
        _line(page, pt(219, 130), pt(243, 111), points, color=color)
        _line(page, pt(219, 130), pt(243, 149), points, color=color)
        if anchor_bar:
            _line(page, pt(239, 105), pt(239, 155), points, color=color)
    elif shape == "crossarm_crossarm":
        _line(page, pt(104, 130), pt(238, 130), points, color=color, dashed=dashed)
        for x in (104, 238):
            _line(page, pt(x, 111), pt(x, 149), points, color=color)
    elif shape == "pole_pole":
        _line(page, pt(106, 130), pt(234, 130), points, color=color, dashed=dashed)
        _hook(page, *pt(106, 130), points, color=color, right=False)
        _hook(page, *pt(234, 130), points, color=color, right=True)
    elif shape in {"crossarm_pole", "crossarm_pole_cut"}:
        _line(page, pt(104, 130), pt(160, 130), points, color=color, dashed=dashed)
        if shape == "crossarm_pole_cut":
            _line(page, pt(160, 130), pt(170, 117), points, color=color)
            _line(page, pt(174, 143), pt(184, 130), points, color=color)
            _line(page, pt(184, 130), pt(234, 130), points, color=color, dashed=dashed)
        else:
            _line(page, pt(160, 130), pt(234, 130), points, color=color, dashed=dashed)
        _line(page, pt(104, 111), pt(104, 149), points, color=color)
        _hook(page, *pt(234, 130), points, color=color, right=True)
    else:
        raise ValueError(shape)
    if support:
        page.draw_circle(pt(85, 130), 8, color=INK, width=0.8)
        _line(page, pt(93, 130), pt(100, 130), points, color=color)
    if label:
        page.insert_text(pt(147, 85), label, fontsize=9, color=color)
    return _bounds(points)


def _draw_backward_v(
    page: pymupdf.Page,
    *,
    scale: float = 1.0,
    angle: float = 0.0,
    branch_run: float = 22.0,
    branch_rise: float = 19.0,
) -> Bounds:
    """Âncora autoral com ramos chegando por trás ao fim da haste."""
    radians = math.radians(angle)

    def transform(point: Point) -> Point:
        x, y = point[0] - 180, point[1] - 130
        return (
            180 + scale * (x * math.cos(radians) - y * math.sin(radians)),
            130 + scale * (x * math.sin(radians) + y * math.cos(radians)),
        )

    points: list[Point] = []
    for a, b in (
        ((90, 130), (230, 130)),
        ((230 - branch_run, 130 - branch_rise), (230, 130)),
        ((230 - branch_run, 130 + branch_rise), (230, 130)),
    ):
        _line(page, transform(a), transform(b), points, color=INK)
    return _bounds(points)


def _draw_negative(page: pymupdf.Page, stratum: str) -> Bounds:
    points: list[Point] = []
    if stratum == "dashed_conductor":
        _line(page, (60, 130), (300, 130), points, color=INK, dashed=True)
        for x in (60, 300):
            page.draw_circle((x, 130), 8, color=INK, width=0.8)
            points.extend(((x - 8, 122), (x + 8, 138)))
    elif stratum == "fence":
        _line(page, (58, 150), (302, 150), points, color=INK)
        for x in range(60, 301, 20):
            _line(page, (x, 139), (x, 161), points, color=INK)
    elif stratum == "leader":
        _line(page, (70, 184), (160, 130), points, color=INK)
        _line(page, (160, 130), (265, 130), points, color=INK)
        page.insert_text((170, 122), "NOTA", fontsize=9)
    elif stratum == "dimension":
        _line(page, (67, 130), (293, 130), points, color=INK)
        for x in (67, 293):
            _line(page, (x - 8, 141), (x + 8, 119), points, color=INK)
        page.insert_text((170, 123), "10 m", fontsize=9)
    elif stratum == "pole_link":
        _line(page, (84, 130), (276, 130), points, color=INK)
        for x in (76, 284):
            page.draw_circle((x, 130), 8, color=INK, width=0.8)
            points.extend(((x - 8, 122), (x + 8, 138)))
    elif stratum == "counterpole_only":
        page.draw_circle((170, 110), 9, color=INK, width=0.8)
        _line(page, (170, 119), (170, 188), points, color=INK)
        _line(page, (170, 148), (220, 188), points, color=INK)
        _line(page, (156, 188), (234, 188), points, color=INK)
    elif stratum == "leader_y":
        page.draw_rect(pymupdf.Rect(42, 48, 130, 80), color=INK, width=0.8)
        page.insert_text((50, 68), "NOTA 7", fontsize=10)
        _line(page, (130, 64), (218, 130), points, color=INK)
        _line(page, (218, 130), (239, 115), points, color=INK)
        _line(page, (218, 130), (239, 145), points, color=INK)
    elif stratum == "dimension_y":
        _line(page, (100, 130), (219, 130), points, color=INK)
        _line(page, (219, 130), (243, 111), points, color=INK)
        _line(page, (219, 130), (243, 149), points, color=INK)
        for x in (100, 243):
            _line(page, (x, 93), (x, 167), points, color=INK)
        page.insert_text((150, 120), "12 m", fontsize=9)
    elif stratum == "conductor_y":
        _line(page, (66, 130), (219, 130), points, color=INK)
        _line(page, (219, 130), (243, 111), points, color=INK)
        _line(page, (219, 130), (243, 149), points, color=INK)
        _line(page, (243, 111), (294, 111), points, color=INK)
        _line(page, (243, 149), (294, 149), points, color=INK)
        for x, y in ((66, 130), (294, 111), (294, 149)):
            page.draw_circle((x, y), 7, color=INK, width=0.8)
    elif stratum == "dimension_backward_v":
        _line(page, (90, 130), (230, 130), points, color=INK)
        _line(page, (208, 111), (230, 130), points, color=INK)
        _line(page, (208, 149), (230, 130), points, color=INK)
        _line(page, (90, 92), (90, 168), points, color=INK)
        _line(page, (230, 92), (230, 168), points, color=INK)
        _line(page, (90, 130), (112, 111), points, color=INK)
        _line(page, (90, 130), (112, 149), points, color=INK)
        page.insert_text((155, 119), "15 m", fontsize=9)
    elif stratum == "conductor_backward_v":
        _line(page, (65, 130), (230, 130), points, color=INK)
        for y in (111, 149):
            _line(page, (168, y), (208, y), points, color=INK)
            _line(page, (208, y), (230, 130), points, color=INK)
            page.draw_circle((168, y), 7, color=INK, width=0.8)
        page.draw_circle((65, 130), 7, color=INK, width=0.8)
    elif stratum == "dimension_shallow_v":
        _line(page, (90, 130), (230, 130), points, color=INK)
        _line(page, (195, 123), (230, 130), points, color=INK)
        _line(page, (195, 137), (230, 130), points, color=INK)
        for x in (90, 230):
            _line(page, (x, 100), (x, 160), points, color=INK)
        page.insert_text((150, 119), "6 m", fontsize=9)
    elif stratum == "conductor_shallow_v":
        _line(page, (65, 130), (230, 130), points, color=INK)
        for y in (123, 137):
            _line(page, (165, y), (195, y), points, color=INK)
            _line(page, (195, y), (230, 130), points, color=INK)
            page.draw_circle((165, y), 7, color=INK, width=0.8)
        page.draw_circle((65, 130), 7, color=INK, width=0.8)
    elif stratum == "closed_triangle_arrow":
        _line(page, (90, 130), (230, 130), points, color=INK)
        page.draw_polyline(
            [(195, 123), (230, 130), (195, 137)], color=INK, closePath=True, width=1.1
        )
        points.extend(((195, 123), (195, 137)))
    elif stratum == "repeated_closed_triangle_arrows":
        for y in (74, 111, 148, 185):
            _line(page, (65, y), (265, y), points, color=INK)
            page.draw_polyline(
                [(230, y - 7), (265, y), (230, y + 7)],
                color=INK,
                fill=INK,
                closePath=True,
                width=0.6,
            )
            points.extend(((230, y - 7), (230, y + 7)))
    elif stratum == "conductor_parallel_labeled":
        for y in (112, 130, 148):
            _line(page, (70, y), (290, y), points, color=INK, dashed=y == 130)
        for x in (65, 295):
            page.draw_circle((x, 130), 9, color=INK, width=0.8)
        page.insert_text((145, 96), "CABO 4#", fontsize=9)
    elif stratum == "leader_terminal_dot":
        page.draw_rect(pymupdf.Rect(43, 74, 127, 100), color=INK, width=0.7)
        page.insert_text((49, 92), "NOTA", fontsize=9)
        _line(page, (127, 87), (201, 129), points, color=INK)
        _line(page, (201, 129), (258, 129), points, color=INK)
        page.draw_circle((258, 129), 3, color=INK, fill=INK, width=0.5)
    elif stratum == "invisible_backward_v":
        white = (1.0, 1.0, 1.0)
        _line(page, (90, 130), (230, 130), points, color=white)
        _line(page, (195, 123), (230, 130), points, color=white)
        _line(page, (195, 137), (230, 130), points, color=white)
    elif stratum == "transparent_backward_v":
        for a, b in (
            ((90, 130), (230, 130)),
            ((195, 123), (230, 130)),
            ((195, 137), (230, 130)),
        ):
            page.draw_line(a, b, color=INK, width=1.3, stroke_opacity=0.0)
            points.extend((a, b))
    elif stratum == "long_dashed_pole_span":
        for y in (117, 130, 143):
            _line(page, (55, y), (305, y), points, color=INK, dashed=y != 130)
        for x in (47, 313):
            page.draw_circle((x, 130), 8, color=INK, width=0.8)
        page.insert_text((145, 107), "REDE MT", fontsize=9)
    elif stratum == "network_span_t_t":
        for y in (118, 130, 142):
            _line(page, (85, y), (275, y), points, color=INK, dashed=y == 118)
        for x in (85, 275):
            _line(page, (x, 108), (x, 152), points, color=INK)
            page.draw_circle((x, 130), 5, color=INK, width=0.8)
        page.insert_text((154, 100), "REDE", fontsize=9)
    elif stratum == "dense_conductor_corridor":
        for index, y in enumerate((77, 97, 117, 137, 157, 177)):
            _line(page, (43, y), (317, y), points, color=INK, dashed=index % 3 == 1)
        for x in (72, 288):
            _line(page, (x, 68), (x, 186), points, color=INK)
            page.draw_circle((x, 137), 7, color=INK, width=0.8)
        _line(page, (193, 117), (226, 137), points, color=INK)
        _line(page, (193, 157), (226, 137), points, color=INK)
        page.insert_text((139, 62), "REDE 13,8 kV", fontsize=8)
    elif stratum == "compass_rose":
        center = (180, 130)
        page.draw_circle(center, 19, color=INK, width=0.8)
        for endpoint, rear_a, rear_b in (
            ((180, 34), (172, 66), (188, 66)),
            ((310, 130), (278, 122), (278, 138)),
            ((180, 226), (172, 194), (188, 194)),
            ((50, 130), (82, 122), (82, 138)),
        ):
            _line(page, center, endpoint, points, color=INK)
            page.draw_polyline([rear_a, endpoint, rear_b], color=INK, fill=INK, closePath=True)
            points.extend((rear_a, rear_b))
        for label, point in (
            ("N", (176, 27)),
            ("S", (176, 246)),
            ("L", (322, 134)),
            ("O", (31, 134)),
        ):
            page.insert_text(point, label, fontsize=9)
    elif stratum == "electric_symbol_ticks":
        for y in (122, 138):
            _line(page, (44, y), (316, y), points, color=INK)
        page.draw_polyline(
            [(153, 103), (180, 158), (207, 103)],
            color=INK,
            fill=(0.82, 0.82, 0.82),
            closePath=True,
            width=1.0,
        )
        points.extend(((153, 103), (207, 158)))
        for x in (96, 118, 241, 263):
            _line(page, (x, 114), (x, 146), points, color=INK)
        _line(page, (241, 114), (255, 107), points, color=INK)
        _line(page, (241, 146), (255, 153), points, color=INK)
        page.draw_circle((283, 130), 10, color=INK, width=0.8)
    elif stratum == "dense_corridor_shallow_branch":
        for y in (96, 116, 136, 156, 176):
            _line(page, (43, y), (317, y), points, color=INK, dashed=y in (116, 156))
        _line(page, (196, 129), (231, 136), points, color=INK)
        _line(page, (196, 143), (231, 136), points, color=INK)
        for x in (71, 289):
            page.draw_circle((x, 136), 7, color=INK, width=0.8)
        page.insert_text((148, 83), "ALIMENTADOR", fontsize=8)
    elif stratum == "compass_rose_open":
        center = (180, 130)
        page.draw_circle(center, 12, color=INK, width=0.8)
        for endpoint, rear_a, rear_b in (
            ((180, 35), (173, 70), (187, 70)),
            ((310, 130), (275, 123), (275, 137)),
            ((180, 225), (173, 190), (187, 190)),
            ((50, 130), (85, 123), (85, 137)),
        ):
            _line(page, center, endpoint, points, color=INK)
            _line(page, rear_a, endpoint, points, color=INK)
            _line(page, rear_b, endpoint, points, color=INK)
        for label, point in (
            ("N", (176, 27)),
            ("S", (176, 246)),
            ("L", (322, 134)),
            ("O", (31, 134)),
        ):
            page.insert_text(point, label, fontsize=9)
    elif stratum == "electric_symbol_stubs":
        _line(page, (45, 130), (315, 130), points, color=INK)
        page.draw_polyline(
            [(151, 103), (180, 159), (209, 103)],
            color=INK,
            fill=(0.82, 0.82, 0.82),
            closePath=True,
            width=1.0,
        )
        for a, b in (
            ((87, 107), (111, 107)),
            ((111, 97), (111, 117)),
            ((218, 107), (242, 107)),
            ((245, 111), (245, 137)),
            ((262, 107), (283, 107)),
        ):
            _line(page, a, b, points, color=INK)
        page.draw_circle((285, 130), 9, color=INK, width=0.8)
    elif stratum == "corridor_short_t_t":
        for y in (112, 130, 148):
            _line(page, (45, y), (315, y), points, color=INK, dashed=y == 112)
        for x in (65, 295):
            _line(page, (x, 125), (x, 135), points, color=INK)
            page.draw_circle((x, 130), 7, color=INK, width=0.8)
        page.insert_text((150, 98), "REDE BT", fontsize=8)
    elif stratum == "closed_pole_loops":
        _line(page, (76, 130), (284, 130), points, color=INK)
        for x in (65, 295):
            page.draw_circle((x, 130), 18, color=INK, width=1.1)
            _line(page, (x, 148), (x, 176), points, color=INK)
        _line(page, (48, 176), (82, 176), points, color=INK)
        _line(page, (278, 176), (312, 176), points, color=INK)
    elif stratum == "compass_symmetric_radials":
        center = (180, 130)
        page.draw_circle(center, 14, color=INK, width=0.8)
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0), (1, -1), (1, 1), (-1, 1), (-1, -1)):
            norm = math.hypot(dx, dy)
            ex, ey = 180 + 105 * dx / norm, 130 + 105 * dy / norm
            _line(page, center, (ex, ey), points, color=INK)
            if dx == 0 or dy == 0:
                px, py = -dy / norm, dx / norm
                _line(
                    page,
                    (ex - 20 * dx / norm + 7 * px, ey - 20 * dy / norm + 7 * py),
                    (ex, ey),
                    points,
                    color=INK,
                )
                _line(
                    page,
                    (ex - 20 * dx / norm - 7 * px, ey - 20 * dy / norm - 7 * py),
                    (ex, ey),
                    points,
                    color=INK,
                )
        page.insert_text((175, 18), "N", fontsize=10)
    elif stratum == "inconsistent_stroke_guy_shape":
        page.draw_line((90, 130), (230, 130), color=INK, width=2.7)
        points.extend(((90, 130), (230, 130)))
        for endpoint in ((195, 123), (195, 137)):
            page.draw_line(endpoint, (230, 130), color=RED, width=0.35)
            points.append(endpoint)
    elif stratum == "parallel_solid_dashed_anchor_like":
        _line(page, (55, 130), (235, 130), points, color=INK)
        _line(page, (200, 123), (235, 130), points, color=INK)
        _line(page, (200, 137), (235, 130), points, color=INK)
        _line(page, (242, 130), (305, 130), points, color=INK)
        _line(page, (55, 145), (305, 145), points, color=INK, dashed=True)
        for x in (55, 305):
            page.draw_circle((x, 137), 8, color=INK, width=0.8)
            _line(page, (x, 120), (x, 154), points, color=INK)
    elif stratum == "near_parallel_solid_dashed_anchor_like":
        _line(page, (51, 130), (238, 130), points, color=INK)
        _line(page, (203, 123), (238, 130), points, color=INK)
        _line(page, (203, 137), (238, 130), points, color=INK)
        _line(page, (244, 130), (309, 130), points, color=INK)
        _line(page, (51, 133.2), (309, 133.2), points, color=INK, dashed=True)
        for x in (51, 309):
            page.draw_circle((x, 131.6), 8, color=INK, width=0.8)
            _line(page, (x, 116), (x, 148), points, color=INK)
    elif stratum == "text_only":
        page.insert_text((100, 130), "ESTAI CZ-CZ", fontsize=12)
        points.extend(((100, 115), (250, 140)))
    else:
        raise ValueError(stratum)
    return _bounds(points)


def build_fixture(path: Path) -> tuple[FixtureOccurrence, ...]:
    """Cria corpus determinístico; a lista de casos não entra no detector."""
    cases: list[FixtureOccurrence] = []
    with pymupdf.open() as document:
        for variant in VARIANTS:
            page = document.new_page(width=WIDTH, height=HEIGHT)
            color = {"existing": INK, "install": GREEN, "remove": RED}[variant.situation]
            bbox = _draw_guy(page, variant.shape, color=color, label=variant.label)
            cases.append(
                FixtureOccurrence(page.number + 1, variant.id, variant.shape, bbox, "variant")
            )

        for stratum in ("dashed_anchor", "no_support", "overprint", "counterpole"):
            page = document.new_page(width=WIDTH, height=HEIGHT)
            dashed = stratum == "dashed_anchor"
            support = stratum != "no_support"
            bbox = _draw_guy(page, "anchor", dashed=dashed, support=support)
            if stratum == "overprint":
                _draw_guy(page, "anchor", dashed=dashed, support=support)
            elif stratum == "counterpole":
                page.draw_circle((258, 130), 8, color=INK, width=0.8)
                page.draw_line((258, 138), (258, 185), color=INK, width=1.2)
            cases.append(
                FixtureOccurrence(page.number + 1, VARIANTS[0].id, "anchor", bbox, stratum)
            )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        bbox = _draw_guy(page, "anchor", support=False, anchor_bar=False)
        cases.append(FixtureOccurrence(page.number + 1, VARIANTS[0].id, "anchor", bbox, "simple_y"))

        for stratum, scale, angle in (
            ("backward_v", 1.0, 0.0),
            ("backward_v_rotated", 0.82, 27.0),
        ):
            page = document.new_page(width=WIDTH, height=HEIGHT)
            bbox = _draw_backward_v(page, scale=scale, angle=angle)
            cases.append(
                FixtureOccurrence(page.number + 1, VARIANTS[0].id, "anchor", bbox, stratum)
            )

        for stratum, scale in (("shallow_v", 1.0), ("shallow_v_small", 0.68)):
            page = document.new_page(width=WIDTH, height=HEIGHT)
            bbox = _draw_backward_v(page, scale=scale, branch_run=35, branch_rise=7)
            cases.append(
                FixtureOccurrence(page.number + 1, VARIANTS[0].id, "anchor", bbox, stratum)
            )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        bbox = _draw_backward_v(page, branch_run=35, branch_rise=7)
        _draw_backward_v(page, branch_run=35, branch_rise=7)
        cases.append(
            FixtureOccurrence(page.number + 1, VARIANTS[0].id, "anchor", bbox, "shallow_overprint")
        )

        for variant in (VARIANTS[3], VARIANTS[6], VARIANTS[9], VARIANTS[12]):
            page = document.new_page(width=WIDTH, height=HEIGHT)
            bbox = _draw_guy(page, variant.shape, support=False)
            cases.append(
                FixtureOccurrence(
                    page.number + 1,
                    variant.id,
                    variant.shape,
                    bbox,
                    f"no_text_{variant.shape}",
                )
            )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        for variant, center in ((VARIANTS[0], (103, 130)), (VARIANTS[6], (257, 130))):
            bbox = _draw_guy(page, variant.shape, center=center, support=False)
            cases.append(
                FixtureOccurrence(page.number + 1, variant.id, variant.shape, bbox, "neighbors")
            )

        for stratum in (
            "dashed_conductor",
            "fence",
            "leader",
            "dimension",
            "pole_link",
            "counterpole_only",
            "text_only",
            "leader_y",
            "dimension_y",
            "conductor_y",
            "dimension_backward_v",
            "conductor_backward_v",
            "dimension_shallow_v",
            "conductor_shallow_v",
            "closed_triangle_arrow",
            "repeated_closed_triangle_arrows",
            "conductor_parallel_labeled",
            "leader_terminal_dot",
            "invisible_backward_v",
            "transparent_backward_v",
            "long_dashed_pole_span",
            "network_span_t_t",
            "dense_conductor_corridor",
            "compass_rose",
            "electric_symbol_ticks",
            "dense_corridor_shallow_branch",
            "compass_rose_open",
            "electric_symbol_stubs",
            "corridor_short_t_t",
            "closed_pole_loops",
            "compass_symmetric_radials",
            "inconsistent_stroke_guy_shape",
            "parallel_solid_dashed_anchor_like",
            "near_parallel_solid_dashed_anchor_like",
        ):
            page = document.new_page(width=WIDTH, height=HEIGHT)
            bbox = _draw_negative(page, stratum)
            cases.append(FixtureOccurrence(page.number + 1, None, None, bbox, stratum))

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(document.tobytes(garbage=4, deflate=True, no_new_id=True))
    return tuple(cases)
