# mypy: disable-error-code="no-untyped-call"
"""Desenhos vetoriais autorais E06; expectativas ficam fora da inferência.

Os quatro padrões resumem as notas geométricas do inventário E01. As células
de situação preservam IDs próprios, mas cores e rótulos não criam uma classe
geométrica nova. Nenhum desenho ou ROI normativo é redistribuído aqui.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
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
    width: float = 1.3,
) -> None:
    page.draw_line(a, b, color=color, width=width, dashes="[5 3] 0" if dashed else None)
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


THIN = 0.15
COMPACT_NEGATIVES = (
    "ring_with_bar",
    "compact_closed_triangle",
    "compact_star_hub",
    "compact_star_mixed",
    "compact_branch_conductor",
    "compact_equal_y",
    "tiny_glyph_y",
    "compact_uneven_y",
    "compact_dimension",
)


def _polar(origin: Point, angle: float, length: float) -> Point:
    radians = math.radians(angle)
    return origin[0] + length * math.cos(radians), origin[1] + length * math.sin(radians)


@dataclass(frozen=True)
class CompactFork:
    """Bloco autoral de âncora: haste saindo do poste e forquilha de dois ramos."""

    center: Point = (180.0, 130.0)
    angle: float = 0.0
    scale: float = 1.0
    shaft: float = 18.0
    branch: float = 13.0
    opening: float = 27.0
    color: tuple[float, float, float] = INK
    pole: bool = True
    circle: bool = False
    tines: bool = True


def fork_points(fork: CompactFork) -> list[Point]:
    """Centro do poste, vértice e pontas: a caixa sem nenhum círculo."""
    vertex = _polar(fork.center, fork.angle, fork.shaft * fork.scale)
    tips = [
        _polar(vertex, fork.angle + side * fork.opening, fork.branch * fork.scale)
        for side in ((-1, 1) if fork.tines else ())
    ]
    return [fork.center, vertex, *tips]


def _through_tips(fork: CompactFork) -> float:
    """Raio do círculo que passa pelo vértice e pelas duas pontas."""
    return fork.branch * fork.scale / (2 * math.cos(math.radians(fork.opening)))


@dataclass(frozen=True)
class RingSpec:
    """Círculo autoral no referencial do vértice: ``forward`` ao longo da haste.

    Sem ``forward``, o centro é o do círculo pelo vértice e pelas pontas; sem
    ``radius``, o contorno passa pelas pontas. ``sides`` desenha um polígono
    regular e ``gapped`` abre duas lacunas laterais (cordas longas).
    """

    forward: float | None = None
    lateral: float = 0.0
    radius: float | None = None
    color: tuple[float, float, float] | None = None
    layer: str | None = None
    sides: int | None = None
    gapped: bool = False


@dataclass(frozen=True)
class RingCase:
    """Forquilha com um círculo; ``criterion`` nomeia o que impede a anexação."""

    fork: CompactFork
    ring: RingSpec
    attached: bool
    criterion: str


def ring_circle(fork: CompactFork, ring: RingSpec) -> tuple[Point, float]:
    """Centro e raio do círculo autoral."""
    vertex = _polar(fork.center, fork.angle, fork.shaft * fork.scale)
    forward = _through_tips(fork) if ring.forward is None else ring.forward
    center = _polar(_polar(vertex, fork.angle, forward), fork.angle + 90, ring.lateral)
    radius = math.dist(center, fork_points(fork)[-1]) if ring.radius is None else ring.radius
    return center, radius


def _ring_polygon(fork: CompactFork, ring: RingSpec, center: Point, radius: float) -> list[Point]:
    assert ring.sides is not None
    if not ring.gapped:
        step = 360 / ring.sides
        return [
            _polar(center, fork.angle + 180 + index * step, radius) for index in range(ring.sides)
        ]
    # Dois arcos opostos de 135°, separados por lacunas laterais de 45°: as
    # duas cordas medem 0,765 r, contra lados curtos de 0,335 r nos arcos.
    per_arc = ring.sides // 2
    step = 135 / (per_arc - 1)
    return [
        _polar(center, fork.angle + middle - 67.5 + index * step, radius)
        for middle in (0.0, 180.0)
        for index in range(per_arc)
    ]


def _draw_ring(page: pymupdf.Page, fork: CompactFork, ring: RingSpec) -> tuple[Point, float]:
    center, radius = ring_circle(fork, ring)
    color = fork.color if ring.color is None else ring.color
    layer = page.parent.add_ocg(ring.layer, on=True) if ring.layer else 0
    if ring.sides is None:
        page.draw_circle(center, radius, color=color, width=THIN, oc=layer)
    else:
        polygon = _ring_polygon(fork, ring, center, radius)
        page.draw_polyline(polygon, color=color, width=THIN, closePath=True, oc=layer)
    return center, radius


def _draw_compact_fork(page: pymupdf.Page, fork: CompactFork, points: list[Point]) -> Point:
    if fork.pole:
        page.draw_circle(fork.center, 2, color=fork.color, width=THIN)
        points.extend(((fork.center[0] - 2, fork.center[1] - 2), fork.center))
    vertex = _polar(fork.center, fork.angle, fork.shaft * fork.scale)
    _line(page, fork.center, vertex, points, color=fork.color, width=THIN)
    for tip in fork_points(fork)[2:]:
        _line(page, vertex, tip, points, color=fork.color, width=THIN)
    if fork.circle:
        # Polígono de 32 lados pelo vértice e (quase exatamente) pelas pontas;
        # o anel envolvente pertence à âncora e entra na caixa autoral.
        radius = _through_tips(fork)
        middle = _polar(vertex, fork.angle, radius)
        polygon = [_polar(middle, fork.angle + 180 + index * 11.25, radius) for index in range(32)]
        page.draw_polyline(polygon, color=fork.color, width=THIN, closePath=True)
        points.extend(polygon)
    return vertex


HALF_FORK = CompactFork(angle=128.0, scale=0.55, color=GREEN, circle=True)
# Forquilha base dos anéis: a 0°, a caixa de haste e ramos não cobre o anel.
RING_FORK = CompactFork(angle=0.0, shaft=7.0, branch=6.0, color=GREEN)
_R0 = _through_tips(RING_FORK)
_TIP_RUN = RING_FORK.branch * math.cos(math.radians(RING_FORK.opening))
_TIP_RISE = RING_FORK.branch * math.sin(math.radians(RING_FORK.opening))
# Cada negativo viola um único critério de anexação; os demais valem.
RING_CASES = {
    "compact_fork_ring": RingCase(RING_FORK, RingSpec(), True, "anexa"),
    "compact_fork_polygon_ring": RingCase(RING_FORK, RingSpec(sides=32), True, "anexa"),
    "compact_fork_side_ring": RingCase(
        RING_FORK, RingSpec(forward=-3.5, lateral=_R0, radius=_R0), False, "varios"
    ),
    "compact_fork_pole_ring": RingCase(
        RING_FORK, RingSpec(forward=-7.0, radius=7.0), False, "varios"
    ),
    "compact_fork_ink_ring": RingCase(RING_FORK, RingSpec(color=INK), False, "tinta"),
    "compact_fork_layer_ring": RingCase(
        RING_FORK, RingSpec(layer="ANEL AUXILIAR"), False, "camada"
    ),
    "compact_fork_decagon_ring": RingCase(RING_FORK, RingSpec(sides=10), False, "poucos lados"),
    "compact_fork_gapped_ring": RingCase(
        RING_FORK, RingSpec(sides=16, gapped=True), False, "lados longos"
    ),
    "compact_fork_offset_ring": RingCase(
        RING_FORK, RingSpec(forward=1.5, radius=3.3), False, "pontas fora do contorno"
    ),
    "compact_fork_beyond_ring": RingCase(
        RING_FORK,
        RingSpec(forward=_TIP_RUN + math.sqrt(_R0**2 - _TIP_RISE**2)),
        False,
        "vertice fora",
    ),
    "compact_fork_rear_ring": RingCase(RING_FORK, RingSpec(forward=-0.7), False, "centro atras"),
    "compact_fork_small_ring": RingCase(
        CompactFork(angle=0.0, shaft=7.0, branch=6.0, opening=20.0, color=GREEN),
        RingSpec(forward=3.2, radius=2.65),
        False,
        "raio pequeno",
    ),
    "compact_fork_large_ring": RingCase(
        CompactFork(angle=0.0, shaft=7.0, branch=6.0, opening=70.0, color=GREEN),
        RingSpec(forward=7.5),
        False,
        "raio grande",
    ),
}
COMPACT_POSITIVES = ("compact_fork", "compact_fork_half", "compact_fork_remove", *RING_CASES)


def _draw_compact(page: pymupdf.Page, stratum: str) -> list[Bounds]:
    """Positivos compactos; cada forquilha vira uma ocorrência própria."""
    points: list[Point] = []
    if stratum == "compact_fork":
        _draw_compact_fork(page, CompactFork(angle=37.0), points)
    elif stratum == "compact_fork_half":
        _draw_compact_fork(page, HALF_FORK, points)
    elif stratum in RING_CASES:
        case = RING_CASES[stratum]
        _draw_compact_fork(page, case.fork, points)
        (x, y), radius = _draw_ring(page, case.fork, case.ring)
        if case.attached:
            points.extend(((x - radius, y - radius), (x + radius, y + radius)))
    elif stratum == "compact_fork_remove":
        _draw_compact_fork(page, CompactFork(angle=200.0, opening=25.0, color=GREEN), points)
        red = CompactFork(center=(180.3, 130.0), angle=200.0, opening=25.0, color=RED)
        _draw_compact_fork(page, red, points)
        middle = _polar((180.3, 130.0), 200.0, 9.0)
        for arm in (45.0, 135.0):
            a, b = _polar(middle, 200.0 + arm, 4.0), _polar(middle, 200.0 + arm + 180, 4.0)
            _line(page, a, b, points, color=RED, width=1.2)
    elif stratum == "compact_fork_hub":
        bounds = []
        for angle in (0.0, 90.0, 180.0, 270.0):
            fork_points: list[Point] = []
            _draw_compact_fork(page, CompactFork(angle=angle, pole=angle == 0.0), fork_points)
            bounds.append(_bounds(fork_points))
        _line(page, (180.0, 130.0), _polar((180.0, 130.0), 135.0, 11.0), [], color=INK, width=THIN)
        return bounds
    else:
        raise ValueError(stratum)
    return [_bounds(points)]


def _draw_compact_negative(page: pymupdf.Page, stratum: str) -> Bounds:
    points: list[Point] = []
    center = (180.0, 130.0)
    if stratum == "ring_with_bar":
        # Haste até um círculo à frente, sem forquilha: não há âncora.
        _draw_compact_fork(page, replace(RING_FORK, tines=False), points)
        _draw_ring(page, RING_FORK, RingSpec())
    elif stratum == "compact_closed_triangle":
        _draw_compact_fork(page, CompactFork(angle=-20.0), points)
        vertex = _polar(center, -20.0, 18.0)
        tips = [_polar(vertex, -20.0 + side * 27.0, 13.0) for side in (-1, 1)]
        _line(page, tips[0], tips[1], points, color=INK, width=THIN)
    elif stratum in {"compact_star_hub", "compact_star_mixed"}:
        page.draw_circle(center, 2, color=INK, width=THIN)
        for index in range(8):
            length = 13.0 if stratum == "compact_star_mixed" and index % 2 else 18.0
            _line(page, center, _polar(center, index * 45.0, length), points, width=THIN, color=INK)
    elif stratum == "compact_branch_conductor":
        _draw_compact_fork(page, CompactFork(angle=0.0), points)
        vertex = _polar(center, 0.0, 18.0)
        for side in (-1, 1):
            tip = _polar(vertex, side * 27.0, 13.0)
            _line(page, tip, (tip[0] + 60.0, tip[1]), points, color=INK, width=THIN)
    elif stratum == "compact_equal_y":
        _draw_compact_fork(page, CompactFork(angle=60.0, shaft=17.0, branch=17.0), points)
    elif stratum == "compact_uneven_y":
        # Junção casual de traços curtos: ramos desiguais e abertura desigual.
        vertex = _polar(center, 150.0, 18.0)
        _line(page, center, vertex, points, color=INK, width=THIN)
        for turn, length in ((20.0, 13.0), (-34.0, 10.5)):
            _line(page, vertex, _polar(vertex, 150.0 + turn, length), points, color=INK, width=THIN)
    elif stratum == "tiny_glyph_y":
        _draw_compact_fork(page, CompactFork(angle=90.0, shaft=3.0, branch=2.2, pole=False), points)
    elif stratum == "compact_dimension":
        _draw_compact_fork(page, CompactFork(angle=0.0, pole=False), points)
        for x in (180.0, 198.0):
            _line(page, (x, 115.0), (x, 145.0), points, color=INK, width=THIN)
    else:
        raise ValueError(stratum)
    return _bounds(points)


def _build_compact(document: pymupdf.Document, cases: list[FixtureOccurrence]) -> None:
    variant_by_color = {
        "compact_fork_half": VARIANTS[1].id,
        "compact_fork_remove": VARIANTS[2].id,
        **dict.fromkeys(RING_CASES, VARIANTS[1].id),
    }
    for stratum in (*COMPACT_POSITIVES, "compact_fork_hub"):
        page = document.new_page(width=WIDTH, height=HEIGHT)
        variant_id = variant_by_color.get(stratum, VARIANTS[0].id)
        cases.extend(
            FixtureOccurrence(page.number + 1, variant_id, "anchor", bbox, stratum)
            for bbox in _draw_compact(page, stratum)
        )
    for stratum in COMPACT_NEGATIVES:
        page = document.new_page(width=WIDTH, height=HEIGHT)
        bbox = _draw_compact_negative(page, stratum)
        cases.append(FixtureOccurrence(page.number + 1, None, None, bbox, stratum))


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

        _build_compact(document, cases)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(document.tobytes(garbage=4, deflate=True, no_new_id=True))
    return tuple(cases)
