# mypy: disable-error-code="no-untyped-call"
"""PDFs autorais E05. As referências são somente para testes e avaliação.

As formas seguem as notas visuais do registro E01, sem copiar assets normativos.
Nenhum detector importa este módulo, e a reserva E16 não é aberta aqui.
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
INK = (0.12, 0.12, 0.12)
CYAN = (0.0, 0.7, 0.8)
PURPLE = (0.55, 0.2, 0.65)
RED = (0.82, 0.1, 0.12)


@dataclass(frozen=True)
class Variant:
    id: str
    shape: str
    marker: str = "base"
    style: str = "outline"
    expected_class: str = "TRANSFORMADOR"


@dataclass(frozen=True)
class FixtureOccurrence:
    page_number: int
    variant_id: str | None
    class_id: str | None
    bbox: Bounds
    context: str = "operational"
    stratum: str = "author_owned"
    evaluability: str = "confirmed"
    asset_count: None = None


def _variant(number: int) -> Variant:
    variant_id = f"cemig-eo-r3-s18-v{number:03d}"
    if number <= 15:
        marker = ("base", "remove", "install")[(number - 1) % 3]
        style = "cyan" if number <= 6 else "outline"
        return Variant(variant_id, "triangle", marker, style)
    if number <= 18:
        return Variant(
            variant_id, "triangle", ("base", "remove", "install")[number - 16], "service"
        )
    return Variant(
        variant_id,
        {
            19: "windings_pair",
            20: "winding_tap",
            21: "winding_ground",
            22: "windings_angular",
            23: "windings_angular",
        }[number],
        "remove" if number == 23 else "base",
    )


VARIANTS: tuple[Variant, ...] = (
    *(_variant(number) for number in range(1, 24)),
    Variant("cemig-eo-r3-s24-v001", "windings_tertiary"),
    Variant("cemig-eo-r3-s24-v002", "winding_multi_tap"),
    Variant("cemig-eo-r3-s25-v001", "windings_opposed"),
    Variant("cemig-eo-r3-s25-v002", "semicircles"),
    Variant("cemig-eo-r3-s25-v003", "semicircles_lateral"),
    Variant("cemig-eo-r3-s25-v004", "measurement_set", expected_class="CONJUNTO_EO"),
)


def _transform(point: Point, center: Point, scale: float, angle: float) -> Point:
    radians = math.radians(angle)
    x, y = point
    return (
        center[0] + scale * (x * math.cos(radians) - y * math.sin(radians)),
        center[1] + scale * (x * math.sin(radians) + y * math.cos(radians)),
    )


def _line(
    page: pymupdf.Page,
    first: Point,
    second: Point,
    points: list[Point],
    *,
    color: tuple[float, float, float] = INK,
    width: float = 1.2,
) -> None:
    page.draw_line(first, second, color=color, width=width)
    points.extend((first, second))


def _bezier(
    page: pymupdf.Page,
    points: list[Point],
    center: Point,
    radius: float,
    *,
    upward: bool = True,
) -> None:
    x, y = center
    sign = -1 if upward else 1
    start = (x - radius, y)
    end = (x + radius, y)
    control_a = (x - radius, y + sign * radius * 1.12)
    control_b = (x + radius, y + sign * radius * 1.12)
    page.draw_bezier(start, control_a, control_b, end, color=INK, width=1.2)
    points.extend((start, control_a, control_b, end))


def _triangle(
    page: pymupdf.Page,
    center: Point,
    scale: float,
    angle: float,
    style: str,
    points: list[Point],
) -> None:
    vertices = [
        _transform(point, center, scale, angle)
        for point in ((0.0, -23.0), (26.0, 22.0), (-26.0, 22.0))
    ]
    color = PURPLE if style == "service" else INK
    if style == "cyan":
        half = [vertices[0], vertices[2], _transform((0.0, 22.0), center, scale, angle)]
        page.draw_polyline(half, color=CYAN, fill=CYAN, closePath=True, width=0.6)
        points.extend(half)
    page.draw_polyline(vertices, color=color, closePath=True, width=1.2)
    points.extend(vertices)
    _line(
        page,
        vertices[0],
        _transform((0.0, 22.0), center, scale, angle),
        points,
        color=color,
    )
    if style == "service":
        # O S é componente do pictograma, não literal externo de transformador.
        page.insert_text((center[0] - 4 * scale, center[1] + 10 * scale), "S", fontsize=13 * scale)


def _windings(page: pymupdf.Page, shape: str, center: Point, points: list[Point]) -> None:
    x, y = center
    if shape == "windings_pair":
        for cx in (x - 11, x + 11):
            _bezier(page, points, (cx, y - 2), 10)
            _bezier(page, points, (cx, y + 10), 10, upward=False)
    elif shape in {"winding_tap", "winding_multi_tap"}:
        for cy in (y - 11, y, y + 11):
            _bezier(page, points, (x, cy), 12)
        taps = (-6, 6) if shape == "winding_multi_tap" else (0,)
        for offset in taps:
            _line(page, (x + 12, y + offset), (x + 27, y + offset), points)
    elif shape == "winding_ground":
        _bezier(page, points, (x, y - 5), 13)
        _bezier(page, points, (x, y + 9), 13, upward=False)
        _line(page, (x, y + 9), (x, y + 29), points)
        for half_width, yy in ((10, y + 29), (7, y + 33), (4, y + 37)):
            _line(page, (x - half_width, yy), (x + half_width, yy), points)
    elif shape == "windings_angular":
        for cx, cy in ((x - 12, y - 8), (x + 12, y + 8)):
            _bezier(page, points, (cx, cy), 11)
            _bezier(page, points, (cx, cy + 10), 11, upward=False)
        _line(page, (x - 25, y + 9), (x + 25, y - 9), points)
    elif shape == "windings_tertiary":
        for cx, cy in ((x - 15, y - 7), (x + 15, y - 7), (x, y + 18)):
            _bezier(page, points, (cx, cy), 10)
            _bezier(page, points, (cx, cy + 9), 10, upward=False)
    elif shape == "windings_opposed":
        _bezier(page, points, (x, y - 7), 16, upward=False)
        _bezier(page, points, (x, y + 7), 16)
        _line(page, (x - 25, y), (x - 16, y), points)
        _line(page, (x + 16, y), (x + 25, y), points)
    elif shape in {"semicircles", "semicircles_lateral"}:
        _bezier(page, points, (x, y - 5), 17)
        _bezier(page, points, (x, y + 5), 17, upward=False)
        _line(page, (x - 26, y), (x - 17, y), points)
        if shape == "semicircles_lateral":
            _line(page, (x + 17, y), (x + 34, y), points)
    elif shape == "measurement_set":
        for cx, cy in ((x - 16, y - 7), (x + 16, y - 7), (x, y + 17)):
            _bezier(page, points, (cx, cy), 10)
            _bezier(page, points, (cx, cy + 9), 10, upward=False)
        _line(page, (x - 26, y + 3), (x + 26, y + 3), points)
    else:
        raise ValueError(shape)


def _draw_variant(
    page: pymupdf.Page,
    variant: Variant,
    *,
    center: Point = (180.0, 130.0),
    scale: float = 1.0,
    angle: float = 0.0,
) -> Bounds:
    points: list[Point] = []
    if variant.shape == "triangle":
        _triangle(page, center, scale, angle, variant.style, points)
    else:
        _windings(page, variant.shape, center, points)
    x, y = center
    if variant.marker == "remove":
        _line(page, (x - 34, y - 34), (x + 34, y + 34), points, color=RED)
        _line(page, (x + 34, y - 34), (x - 34, y + 34), points, color=RED)
    elif variant.marker == "install":
        page.draw_circle(center, 39, color=INK, width=1.1)
        points.extend(((x - 39, y - 39), (x + 39, y + 39)))
    return _bounds(points)


def _bounds(points: list[Point]) -> Bounds:
    return (
        min(point[0] for point in points) / WIDTH,
        min(point[1] for point in points) / HEIGHT,
        max(point[0] for point in points) / WIDTH,
        max(point[1] for point in points) / HEIGHT,
    )


def _draw_round_cyan_sector(page: pymupdf.Page, center: Point) -> Bounds:
    """Representação circular autoral, distinta do contorno triangular E01."""
    x, y = center
    page.draw_sector(center, (x, y - 29), 180, color=CYAN, fill=CYAN, width=0.5)
    page.draw_circle(center, 29, color=INK, width=1.3)
    page.draw_line((x, y - 29), (x, y + 29), color=INK, width=0.9)
    return _bounds([(x - 29, y - 29), (x + 29, y + 29)])


def _draw_compass_rose(page: pymupdf.Page) -> Bounds:
    center = (180.0, 132.0)
    x, y = center
    page.draw_circle(center, 36, color=INK, width=0.8)
    for angle in (0, 90, 180, 270):
        arrow = [_transform(point, center, 1.0, angle) for point in ((-12, -8), (0, -43), (12, -8))]
        page.draw_polyline(arrow, color=INK, fill=(0.8, 0.8, 0.8), closePath=True, width=0.8)
        page.draw_line(
            _transform((0, -8), center, 1.0, angle),
            _transform((0, -43), center, 1.0, angle),
            color=INK,
            width=0.5,
        )
        page.draw_line(
            _transform((0, -43), center, 1.0, angle),
            _transform((0, -61), center, 1.0, angle),
            color=INK,
            width=0.8,
        )
    page.draw_circle(center, 6, color=INK, fill=(1, 1, 1), width=0.8)
    page.insert_text((176, 57), "N", fontsize=12)
    return _bounds([(x - 61, y - 75), (x + 61, y + 61)])


def _draw_pole_circles(page: pymupdf.Page) -> Bounds:
    points: list[Point] = []
    for x in (115.0, 245.0):
        y = 116.0
        _bezier(page, points, (x, y), 15)
        _bezier(page, points, (x, y), 15, upward=False)
        _line(page, (x, y + 15), (x, y + 63), points)
        for half_width, row in ((11, y + 45), (7, y + 50), (4, y + 55)):
            _line(page, (x - half_width, row), (x + half_width, row), points)
    page.draw_line((70, 83), (290, 83), color=(0.25, 0.4, 0.25), width=1.4)
    return _bounds(points)


def _draw_green_pole_markers(page: pymupdf.Page) -> Bounds:
    green = (0.08, 0.56, 0.18)
    page.draw_line((54, 153), (306, 153), color=green, width=1.8)
    for x in (92.0, 180.0, 268.0):
        page.draw_circle((x, 153), 8, color=INK, width=0.8)
        marker = [(x - 10, 128), (x, 110), (x + 10, 128)]
        page.draw_polyline(marker, color=green, fill=green, closePath=True, width=0.7)
        page.draw_line((x, 128), (x, 144), color=green, width=0.7)
    return _bounds([(54, 102), (306, 162)])


def _draw_repeated_details(page: pymupdf.Page) -> Bounds:
    page.draw_rect(pymupdf.Rect(42, 74, 318, 204), color=(0.35, 0.35, 0.35), width=0.6)
    page.insert_text((53, 90), "DETALHES", fontsize=9)
    points: list[Point] = []
    for row in range(3):
        y = 113 + 36 * row
        page.draw_line((53, y + 18), (307, y + 18), color=(0.35, 0.35, 0.35), width=0.5)
        for column in range(5):
            x = 71 + 53 * column
            _bezier(page, points, (x, y), 9)
            _line(page, (x - 11, y + 4), (x + 11, y + 4), points, width=0.6)
    return _bounds([(42, 74), (318, 204)])


def _draw_red_protection_annotation(page: pymupdf.Page) -> Bounds:
    red = (0.82, 0.13, 0.16)
    for x, glyph in ((110.0, "4F"), (250.0, "4FF")):
        page.draw_circle((x, 130), 25, color=red, width=1.1)
        page.insert_text((x - 10, 135), glyph, fontsize=12, color=red)
        page.draw_line((x + 25, 130), (x + 50, 130), color=red, width=0.8)
    return _bounds([(85, 105), (300, 155)])


def build_fixture(path: Path) -> tuple[FixtureOccurrence, ...]:
    """Cria corpus E05 determinístico e devolve referência fora da inferência."""
    cases: list[FixtureOccurrence] = []
    with pymupdf.open() as document:
        for variant in VARIANTS:
            page = document.new_page(width=WIDTH, height=HEIGHT)
            bbox = _draw_variant(page, variant)
            cases.append(
                FixtureOccurrence(
                    page.number + 1, variant.id, variant.expected_class, bbox, stratum=variant.shape
                )
            )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        duplicate = VARIANTS[6]
        box = _draw_variant(page, duplicate)
        _draw_variant(page, duplicate)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                duplicate.id,
                duplicate.expected_class,
                box,
                stratum="duplicate_overprint",
            )
        )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        left = VARIANTS[6]
        right = VARIANTS[18]
        for variant, center in ((left, (105.0, 130.0)), (right, (255.0, 130.0))):
            box = _draw_variant(page, variant, center=center)
            cases.append(
                FixtureOccurrence(
                    page.number + 1, variant.id, variant.expected_class, box, stratum="neighbors"
                )
            )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        page.draw_rect(pymupdf.Rect(90, 68, 270, 205), color=(0.5, 0.5, 0.5), width=0.5)
        page.insert_text((105, 85), "LEGENDA", fontsize=10)
        legend = VARIANTS[6]
        box = _draw_variant(page, legend, center=(180.0, 140.0))
        cases.append(
            FixtureOccurrence(
                page.number + 1, legend.id, legend.expected_class, box, "legend", "legend"
            )
        )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        conflict = VARIANTS[6]
        box = _draw_variant(page, conflict)
        page.insert_text((217, 132), "POSTE P7 / 75 kVA", fontsize=9)
        cases.append(
            FixtureOccurrence(
                page.number + 1, conflict.id, conflict.expected_class, box, stratum="text_conflict"
            )
        )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        rotated = VARIANTS[6]
        box = _draw_variant(page, rotated, scale=0.72, angle=38.0)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                rotated.id,
                rotated.expected_class,
                box,
                stratum="rotation_scale",
            )
        )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        page.draw_circle((70, 95), 21, color=INK)
        page.draw_circle((145, 95), 14, color=INK)
        page.draw_line((145, 109), (145, 145), color=INK)
        page.insert_text((215, 100), "S", fontsize=30)
        page.draw_circle((70, 195), 13, color=INK)
        page.draw_circle((120, 195), 13, color=INK)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                None,
                None,
                (0.10, 0.20, 0.82, 0.88),
                "negative",
                "circles_post_glyph",
            )
        )

        # Controles B2: desenhos independentes por categoria visual, sem ROI privado.
        page = document.new_page(width=WIDTH, height=HEIGHT)
        round_cyan = VARIANTS[0]
        box = _draw_round_cyan_sector(page, (180.0, 130.0))
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                round_cyan.id,
                round_cyan.expected_class,
                box,
                stratum="round_cyan_sector",
            )
        )

        negative_drawings = (
            ("compass_rose", _draw_compass_rose),
            ("pole_circles", _draw_pole_circles),
            ("green_pole_markers", _draw_green_pole_markers),
            ("repeated_details", _draw_repeated_details),
            ("red_protection_annotation", _draw_red_protection_annotation),
        )
        for stratum, draw in negative_drawings:
            page = document.new_page(width=WIDTH, height=HEIGHT)
            box = draw(page)
            cases.append(FixtureOccurrence(page.number + 1, None, None, box, "negative", stratum))

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(document.tobytes(garbage=4, deflate=True, no_new_id=True))
    return tuple(cases)


def build_generalization_fixture(path: Path) -> tuple[FixtureOccurrence, ...]:
    """Segundo documento autoral B3: outros arranjos, sem reutilizar ROIs de B2."""
    cases: list[FixtureOccurrence] = []
    with pymupdf.open() as document:
        # Dois lóbulos afastados pertencem à estrutura de um poste, não a enrolamentos.
        page = document.new_page(width=WIDTH, height=HEIGHT)
        page.draw_line((68, 92), (292, 92), color=(0.12, 0.48, 0.18), width=1.4)
        page.draw_circle((180, 112), 8, color=INK, width=0.8)
        page.draw_line((180, 120), (180, 204), color=INK, width=1.1)
        for pole_x in (160, 200):
            page.draw_circle((pole_x, 150), 13, color=INK, width=0.8)
            page.draw_line((pole_x, 163), (pole_x, 182), color=INK, width=0.7)
        for offset in (0, 5, 10):
            page.draw_line((166 + offset, 190), (194 - offset, 190), color=INK, width=0.6)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                None,
                None,
                _bounds([(68, 92), (292, 204)]),
                "negative",
                "disconnected_pole_lobes",
            )
        )

        # Rosa circular com pétalas separadas e eixos cardeais, sem triângulo fechado.
        page = document.new_page(width=WIDTH, height=HEIGHT)
        center = (180.0, 135.0)
        page.draw_circle(center, 47, color=(0.2, 0.2, 0.2), width=0.7)
        page.draw_circle(center, 6, color=INK, fill=(1, 1, 1), width=0.7)
        for dx, dy in ((0, -32), (32, 0), (0, 32), (-32, 0)):
            petal = (center[0] + dx, center[1] + dy)
            page.draw_circle(petal, 10, color=INK, width=0.8)
            page.draw_line(center, petal, color=INK, width=0.7)
        page.insert_text((176, 70), "N", fontsize=11)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                None,
                None,
                _bounds([(133, 70), (227, 182)]),
                "negative",
                "disconnected_compass_lobes",
            )
        )

        # Anotações de proteção embutidas em molduras de equipamento, com líderes.
        page = document.new_page(width=WIDTH, height=HEIGHT)
        red = (0.82, 0.13, 0.16)
        for annotation_x, glyph in ((105.0, "4F"), (255.0, "4FF")):
            page.draw_rect(
                pymupdf.Rect(annotation_x - 38, 95, annotation_x + 38, 175),
                color=INK,
                width=0.6,
            )
            page.draw_circle((annotation_x, 134), 19, color=red, width=1.1)
            page.insert_text((annotation_x - 9, 139), glyph, fontsize=10, color=red)
            page.draw_line((annotation_x + 19, 134), (annotation_x + 37, 134), color=red, width=0.8)
            page.draw_line((annotation_x - 38, 184), (annotation_x + 38, 184), color=INK, width=0.6)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                None,
                None,
                _bounds([(67, 95), (293, 184)]),
                "negative",
                "embedded_red_protection",
            )
        )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        sector_x, sector_y, sector_radius = 180.0, 130.0, 13.0
        page.draw_line((140, sector_y), (sector_x - sector_radius, sector_y), color=INK, width=0.8)
        page.draw_sector(
            (sector_x, sector_y),
            (sector_x, sector_y - sector_radius),
            180,
            color=CYAN,
            fill=CYAN,
            width=0.5,
        )
        page.draw_circle((sector_x, sector_y), sector_radius, color=INK, width=1.1)
        page.draw_line(
            (sector_x, sector_y - sector_radius),
            (sector_x, sector_y + sector_radius),
            color=INK,
            width=0.6,
        )
        page.draw_line((sector_x + sector_radius, sector_y), (220, sector_y), color=INK, width=0.8)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                VARIANTS[0].id,
                "TRANSFORMADOR",
                _bounds(
                    [
                        (sector_x - sector_radius, sector_y - sector_radius),
                        (sector_x + sector_radius, sector_y + sector_radius),
                    ]
                ),
                stratum="small_cyan_sector",
            )
        )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        sector_x, sector_y, sector_radius = 180.0, 130.0, 24.0
        page.draw_sector(
            (sector_x, sector_y),
            (sector_x, sector_y - sector_radius),
            180,
            color=CYAN,
            fill=CYAN,
            width=0.5,
        )
        page.draw_rect(pymupdf.Rect(158, 112, 176, 150), color=None, fill=(1, 1, 1))
        page.draw_circle((sector_x, sector_y), sector_radius, color=INK, width=1.1)
        page.draw_line(
            (sector_x, sector_y - sector_radius),
            (sector_x, sector_y + sector_radius),
            color=INK,
            width=0.7,
        )
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                VARIANTS[0].id,
                "TRANSFORMADOR",
                _bounds(
                    [
                        (sector_x - sector_radius, sector_y - sector_radius),
                        (sector_x + sector_radius, sector_y + sector_radius),
                    ]
                ),
                stratum="occluded_cyan_sector",
            )
        )

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(document.tobytes(garbage=4, deflate=True, no_new_id=True))
    return tuple(cases)


def build_circular_stem_fixture(path: Path) -> tuple[FixtureOccurrence, ...]:
    """Terceiro documento autoral B4, independente das formas B2/B3."""
    cases: list[FixtureOccurrence] = []
    with pymupdf.open() as document:
        page = document.new_page(width=WIDTH, height=HEIGHT)
        page.draw_line((72, 86), (288, 86), color=(0.14, 0.5, 0.2), width=1.2)
        page.draw_circle((162, 130), 15, color=INK, width=1.1)
        page.draw_line((162, 145), (162, 185), color=INK, width=1.0)
        page.draw_circle((195, 130), 17, color=RED, width=1.1)
        page.draw_line((195, 147), (209, 159), color=RED, width=0.7)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                None,
                None,
                _bounds([(72, 86), (288, 185)]),
                "negative",
                "multicolor_unconnected_pole_circles",
            )
        )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        center = (180.0, 122.0)
        page.draw_sector(
            center,
            (201.0, 122.0),
            338,
            color=INK,
            width=1.3,
            fullSector=False,
            closePath=False,
        )
        page.draw_line((180, 143), (180, 182), color=INK, width=1.1)
        page.draw_line((163, 182), (197, 182), color=INK, width=0.6)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                None,
                None,
                _bounds([(159, 101), (201, 182)]),
                "negative",
                "open_pole_ring_with_stem",
            )
        )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        page.draw_circle((180, 125), 22, color=RED, width=1.0)
        page.draw_line((180, 147), (180, 176), color=RED, width=0.9)
        page.draw_circle((180, 187), 6, color=INK, width=0.7)
        page.insert_text((171, 129), "4FF", fontsize=9, color=RED)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                None,
                None,
                _bounds([(158, 103), (202, 193)]),
                "negative",
                "red_protection_ring_with_stem",
            )
        )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        page.draw_circle((166, 130), 19, color=INK, width=1.1)
        page.draw_circle((194, 130), 19, color=INK, width=1.1)
        page.draw_line((174, 130), (186, 130), color=INK, width=0.8)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                "cemig-eo-r3-s18-v019",
                "TRANSFORMADOR",
                _bounds([(147, 111), (213, 149)]),
                stratum="connected_overlapping_windings",
            )
        )

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(document.tobytes(garbage=4, deflate=True, no_new_id=True))
    return tuple(cases)


def build_fill_morphology_fixture(path: Path) -> tuple[FixtureOccurrence, ...]:
    """Quarto documento autoral B5: preenchimento e terminal versus laços vazados."""
    cases: list[FixtureOccurrence] = []
    with pymupdf.open() as document:
        page = document.new_page(width=WIDTH, height=HEIGHT)
        page.draw_line((66, 92), (294, 92), color=(0.12, 0.46, 0.18), width=1.4)
        page.draw_circle((166, 132), 18, color=INK, fill=(0.25, 0.17, 0.31), width=1.0)
        page.draw_circle((194, 132), 18, color=INK, fill=RED, width=1.0)
        page.draw_line((166, 150), (166, 191), color=INK, width=1.0)
        page.draw_line((194, 150), (194, 177), color=RED, width=0.9)
        page.draw_line((152, 191), (180, 191), color=INK, width=0.6)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                None,
                None,
                _bounds([(66, 92), (294, 191)]),
                "negative",
                "filled_multicolor_post_marks",
            )
        )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        page.draw_line((79, 130), (220, 130), color=INK, width=1.2)
        page.draw_circle((220, 130), 6, color=INK, fill=INK, width=0.8)
        page.draw_line((220, 130), (220, 174), color=INK, width=0.8)
        page.draw_circle((220, 174), 4, color=RED, fill=RED, width=0.6)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                None,
                None,
                _bounds([(79, 124), (226, 178)]),
                "negative",
                "small_filled_terminal_point",
            )
        )

        page = document.new_page(width=WIDTH, height=HEIGHT)
        page.draw_line((120, 130), (152, 130), color=INK, width=0.8)
        page.draw_circle((170, 130), 18, color=INK, fill=None, width=1.1)
        page.draw_circle((194, 130), 18, color=INK, fill=None, width=1.1)
        page.draw_line((212, 130), (244, 130), color=INK, width=0.8)
        cases.append(
            FixtureOccurrence(
                page.number + 1,
                "cemig-eo-r3-s18-v019",
                "TRANSFORMADOR",
                _bounds([(152, 112), (212, 148)]),
                stratum="hollow_connected_windings",
            )
        )

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(document.tobytes(garbage=4, deflate=True, no_new_id=True))
    return tuple(cases)
