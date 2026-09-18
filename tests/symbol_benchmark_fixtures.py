# mypy: disable-error-code="no-untyped-call"
"""Author-owned PDF controls, independent of detector code and private examples.

Only development and calibration are materialized here. The E16 reserve is an
opaque, hash-locked archive: normal imports, tests and benchmark runs never open it.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "symbols"
FAMILIES = tuple(f"family-f02-{number:02d}" for number in range(1, 34))
CLASS_FAMILY = {
    "ATERRAMENTO": "family-f02-19",
    "PARA_RAIOS_MT": "family-f02-21",
    "PARA_RAIOS_BT": "family-f02-21",
    "TRANSFORMADOR": "family-f02-18",
    "ESTAI_MT": "family-f02-14",
    "POSTE": "family-f02-03",
    "NON_SYMBOL": "family-f02-33",
}
Point = tuple[float, float]
Segment = tuple[Point, Point]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_sha256(path: Path) -> str:
    """Code hashes ignore Git checkout line endings; PDF hashes remain byte-exact."""
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _segments(class_id: str) -> list[Segment]:
    if class_id in {"ATERRAMENTO", "PARA_RAIOS_MT"}:
        count = 3 if class_id == "ATERRAMENTO" else 4
        result: list[Segment] = [((0, 0), (15, 0))]
        for index, length in enumerate((10.0, 7.0, 4.0, 7.0)[:count]):
            center = 15 + index * 4
            result.append(((center, -length / 2), (center, length / 2)))
        return result
    if class_id == "PARA_RAIOS_BT":
        return [
            ((0, 0), (15, 0)),
            ((15, -1.5), (24, -1.5)),
            ((24, -1.5), (24, 1.5)),
            ((24, 1.5), (15, 1.5)),
            ((15, 1.5), (15, -1.5)),
            ((15, -3.5), (24, 3.5)),
        ]
    if class_id == "TRANSFORMADOR":
        return [
            ((0, 8), (15, -10)),
            ((15, -10), (30, 8)),
            ((30, 8), (0, 8)),
            ((15, -10), (15, 8)),
        ]
    if class_id == "ESTAI_MT":
        return [((0, 0), (70, 0)), ((60, -2), (70, 0)), ((60, 2), (70, 0))]
    raise ValueError(class_id)


def _draw_symbol(
    page: Any,
    class_id: str,
    x: float,
    y: float,
    *,
    scale: float = 1,
    angle: float = 0,
    color: tuple[float, float, float] = (0, 0, 0),
    fragmented: bool = False,
    annotation: bool = False,
    grouped: bool = False,
) -> list[float]:
    rad = math.radians(angle)

    def transform(point: Point) -> Point:
        px, py = point
        return (
            x + scale * (px * math.cos(rad) - py * math.sin(rad)),
            y + scale * (px * math.sin(rad) + py * math.cos(rad)),
        )

    strokes = [(transform(a), transform(b)) for a, b in _segments(class_id)]
    if fragmented:
        strokes = [
            piece
            for a, b in strokes
            for piece in (
                (a, (a[0] + (b[0] - a[0]) * 0.46, a[1] + (b[1] - a[1]) * 0.46)),
                ((a[0] + (b[0] - a[0]) * 0.54, a[1] + (b[1] - a[1]) * 0.54), b),
            )
        ]
    if annotation:
        annot = page.add_ink_annot([[a, b] for a, b in strokes])
        annot.set_colors(stroke=color)
        annot.set_border(width=0.5)
        annot.update()
    elif grouped:
        shape = page.new_shape()
        for a, b in strokes:
            shape.draw_line(a, b)
        shape.finish(color=color, width=0.5, closePath=False)
        shape.commit()
    elif class_id == "PARA_RAIOS_BT" and angle == 0 and not fragmented:
        page.draw_line(strokes[0][0], strokes[0][1], color=color, width=0.5)
        page.draw_rect(pymupdf.Rect(strokes[1][0], strokes[2][1]), color=color, width=0.5)
        page.draw_line(strokes[-1][0], strokes[-1][1], color=color, width=0.5)
    else:
        for a, b in strokes:
            page.draw_line(a, b, color=color, width=0.5)
    points = [point for stroke in strokes for point in stroke]
    return [
        min(p[0] for p in points) / 400,
        min(p[1] for p in points) / 300,
        max(p[0] for p in points) / 400,
        max(p[1] for p in points) / 300,
    ]


def _occurrence(
    document_id: str,
    number: int,
    class_id: str,
    bbox: list[float],
    index: int,
    **fields: Any,
) -> dict[str, Any]:
    return {
        "id": f"{document_id}-p{number}-o{index:02d}",
        "document_id": document_id,
        "page": number,
        "layer": "base",
        "family": CLASS_FAMILY[class_id],
        "class_id": class_id,
        "bbox": bbox,
        "context": "operational",
        "evaluability": "confirmed",
        "situation": None,
        "quantity": None if class_id in {"TRANSFORMADOR", "ESTAI_MT", "NON_SYMBOL"} else 1,
        "association": None,
        "strata": ["vector", "author_owned"],
        "notes": "Author-owned synthetic control; not a normative variant or asset count",
        **fields,
    }


def _save(
    document: Any, output: Path, document_id: str, ancestor: str, split: str
) -> dict[str, Any]:
    path = output / f"{document_id}.pdf"
    document.set_metadata({"producer": "Zeny E02 author-owned fixtures v1"})
    path.write_bytes(document.tobytes(garbage=4, deflate=True, no_new_id=True))
    result = {
        "id": document_id,
        "sha256": sha256(path),
        "path": str(path),
        "split": split,
        "ancestor_id": ancestor,
        "template_family": ancestor,
        "pages": [
            {"number": index + 1, "width_pt": 400, "height_pt": 300}
            for index in range(len(document))
        ],
    }
    document.close()
    return result


def _development(output: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    documents: list[dict[str, Any]] = []
    occurrences: list[dict[str, Any]] = []
    document_id = "dev-symbols"
    document = pymupdf.open()
    classes = ["ATERRAMENTO", "PARA_RAIOS_MT", "PARA_RAIOS_BT", "TRANSFORMADOR", "ESTAI_MT"]
    for number in (1, 2):
        page = document.new_page(width=400, height=300)
        for index, class_id in enumerate(classes):
            angle = 0 if number == 1 else (90, 180, 45, 270, 0)[index]
            scale = 1 if number == 1 else (0.6, 1.8, 1.3, 0.8, 1.5)[index]
            color = ((0, 0, 0), (0, 0.5, 0), (1, 0, 0), (0.5, 0.5, 0.5), (0, 0, 0))[index]
            bbox = _draw_symbol(
                page, class_id, 70, 45 + index * 48, scale=scale, angle=angle, color=color
            )
            occurrences.append(
                _occurrence(
                    document_id,
                    number,
                    class_id,
                    bbox,
                    index,
                    situation=("EXISTENTE", "INSTALAR", "REMOVER", None, None)[index],
                    strata=["vector", "canonical" if number == 1 else "scale_rotation", "color"],
                )
            )
    documents.append(_save(document, output, document_id, "dev-author-layout-v1", "development"))

    raster = pymupdf.open()
    with pymupdf.open(output / "dev-symbols.pdf") as source:
        image = source[0].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).tobytes("png")
    raster.new_page(width=400, height=300).insert_image(pymupdf.Rect(0, 0, 400, 300), stream=image)
    for original in list(occurrences[:5]):
        item = dict(original)
        item.update(
            id=original["id"].replace("dev-symbols", "dev-raster"),
            document_id="dev-raster",
            strata=["raster", "degraded_108dpi"],
        )
        occurrences.append(item)
    documents.append(_save(raster, output, "dev-raster", "dev-author-layout-v1", "development"))

    document_id = "dev-contexts"
    document = pymupdf.open()
    page = document.new_page(width=400, height=300)
    for index, fields in enumerate(
        (
            {"fragmented": True},
            {"grouped": True},
            {},
            {},
            {"annotation": True},
        )
    ):
        x, y = ((50, 50), (150, 50), (50, 110), (71, 110), (50, 180))[index]
        box = _draw_symbol(
            page,
            "ATERRAMENTO",
            x,
            y,
            fragmented=fields.get("fragmented", False),
            grouped=fields.get("grouped", False),
            annotation=fields.get("annotation", False),
        )
        occurrences.append(
            _occurrence(
                document_id,
                1,
                "ATERRAMENTO",
                box,
                index,
                layer="annotation" if index == 4 else "base",
                strata=[
                    ("fragmentation", "grouped", "neighbors", "neighbors", "annotation")[index]
                ],
            )
        )
    box = _draw_symbol(page, "TRANSFORMADOR", 180, 160)
    page.draw_line((170, 150), (220, 178), color=(0.7, 0.7, 0.7), width=2)
    occurrences.append(
        _occurrence(document_id, 1, "TRANSFORMADOR", box, 5, strata=["overlap"], quantity=None)
    )
    # Same geometry on a separate page is a distinct identity, not a duplicate.
    page = document.new_page(width=400, height=300)
    box = _draw_symbol(page, "ATERRAMENTO", 50, 50)
    occurrences.append(
        _occurrence(document_id, 2, "ATERRAMENTO", box, 0, strata=["different_page"])
    )
    box = _draw_symbol(page, "TRANSFORMADOR", 180, 160, fragmented=True)
    occurrences.append(
        _occurrence(
            document_id,
            2,
            "TRANSFORMADOR",
            box,
            1,
            evaluability="ambiguous",
            strata=["ambiguous"],
            quantity=None,
        )
    )
    documents.append(_save(document, output, document_id, "dev-author-layout-v1", "development"))

    document_id = "dev-negatives"
    document = pymupdf.open()
    page = document.new_page(width=400, height=300)
    page.insert_text((32, 24), "LEGENDA", fontsize=9)
    box = _draw_symbol(page, "ATERRAMENTO", 40, 45)
    occurrences.append(
        _occurrence(
            document_id, 1, "ATERRAMENTO", box, 0, context="legend", strata=["critical_legend"]
        )
    )
    page.insert_text((40, 95), "E F H III", fontsize=18)
    occurrences.append(
        _occurrence(
            document_id,
            1,
            "NON_SYMBOL",
            [0.09, 0.24, 0.31, 0.33],
            1,
            context="negative",
            strata=["critical_glyph"],
        )
    )
    for row in range(4):
        page.draw_line((40, 135 + row * 10), (130, 135 + row * 10), width=0.5)
    for column in range(4):
        page.draw_line((40 + column * 30, 135), (40 + column * 30, 165), width=0.5)
    occurrences.append(
        _occurrence(
            document_id,
            1,
            "NON_SYMBOL",
            [0.1, 0.45, 0.325, 0.55],
            2,
            context="negative",
            strata=["critical_table"],
        )
    )
    page.draw_line((40, 225), (190, 225), width=0.5)
    for x in range(40, 191, 10):
        page.draw_line((x, 218), (x, 232), width=0.5)
    occurrences.append(
        _occurrence(
            document_id,
            1,
            "NON_SYMBOL",
            [0.1, 0.725, 0.475, 0.775],
            3,
            context="negative",
            strata=["critical_fence"],
        )
    )
    documents.append(_save(document, output, document_id, "dev-author-layout-v1", "development"))
    return documents, occurrences


def _calibration(output: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Distinct pole and transformer templates; no development geometry reused."""
    documents: list[dict[str, Any]] = []
    occurrences: list[dict[str, Any]] = []
    for suffix in ("vector", "raster"):
        document_id = f"cal-{suffix}"
        document = pymupdf.open()
        page = document.new_page(width=400, height=300)
        page.draw_circle((80, 70), 7, color=(0, 0, 0), width=0.7)
        page.draw_line((73, 70), (87, 70), width=0.7)
        page.draw_circle((160, 140), 10, color=(0, 0, 0), width=0.7)
        page.draw_circle((174, 140), 10, color=(0, 0, 0), width=0.7)
        if suffix == "raster":
            raster_bytes = page.get_pixmap(alpha=False).tobytes("png")
            document.close()
            document = pymupdf.open()
            document.new_page(width=400, height=300).insert_image(
                pymupdf.Rect(0, 0, 400, 300), stream=raster_bytes
            )
        occurrences.extend(
            [
                _occurrence(
                    document_id,
                    1,
                    "POSTE",
                    [73 / 400, 63 / 300, 87 / 400, 77 / 300],
                    0,
                    strata=[suffix, "independent_drawing"],
                ),
                _occurrence(
                    document_id,
                    1,
                    "TRANSFORMADOR",
                    [0.375, 130 / 300, 0.46, 0.5],
                    1,
                    strata=[suffix, "independent_drawing"],
                ),
            ]
        )
        documents.append(
            _save(document, output, document_id, "cal-author-circles-v1", "calibration")
        )
    return documents, occurrences


def build_corpus(output_dir: Path, *, split: str = "development") -> dict[str, Any]:
    """Materialize deterministic public controls without accessing ``examples/``.

    Paths returned to the runner locate actual PDFs. A persisted portable reference
    should make those paths relative to its own directory before publication.
    """
    if split not in {"development", "calibration"}:
        raise ValueError("Reserve is sealed until E16; only development/calibration are public")
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    documents, occurrences = (
        _development(output) if split == "development" else _calibration(output)
    )
    return {
        "schema_version": 1,
        "families": list(FAMILIES),
        "documents": documents,
        "occurrences": occurrences,
        "provenance": {
            "generator": "tests/symbol_benchmark_fixtures.py",
            "generator_sha256": source_sha256(Path(__file__)),
            "generator_hash_normalization": "UTF-8 text with LF line endings",
            "seed": 20260918,
            "randomness": "none; coordinates and serialization fixed",
            "ownership": "Author-owned controls, not normative symbol reproductions",
            "limitations": "Synthetic diagnostic set; no field generalization estimate",
        },
    }


def portable_reference(reference: dict[str, Any]) -> dict[str, Any]:
    """Strip machine paths for the versioned manifest without changing source hashes."""
    result: dict[str, Any] = json.loads(json.dumps(reference))
    for document in result["documents"]:
        document["path"] = Path(document["path"]).name
    return result
