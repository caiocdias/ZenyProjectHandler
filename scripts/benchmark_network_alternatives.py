"""Opt-in E12A experiments. Private outputs belong in tmp/; no production writes."""

from __future__ import annotations

import argparse
import json
import platform
from dataclasses import asdict
from hashlib import sha256
from importlib import metadata
from pathlib import Path
from time import perf_counter
from typing import Any

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from scripts.experiments.global_graph import run_graph
from scripts.experiments.rapid_ocr import RapidLocalOcr, map_quad
from zeny_project_handler.adapters.analysis import TesseractCliOcr
from zeny_project_handler.adapters.analysis.tesseract_runtime import inspect_tesseract_runtime
from zeny_project_handler.ports.analysis import MotorOcrPort, PaginaRasterOcr


def identity(path: Path) -> dict[str, Any]:
    return {
        "sha256": sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "mtime_ns": path.stat().st_mtime_ns,
    }


def save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def raster(image: Image.Image) -> PaginaRasterOcr:
    return PaginaRasterOcr(
        pagina_numero=1,
        largura_pixels=image.width,
        altura_pixels=image.height,
        stride=image.width * 3,
        dados_rgb=image.convert("RGB").tobytes(),
        dpi=600,
    )


def controls(engine: MotorOcrPort) -> list[dict[str, Any]]:
    """Development-only controls, unrelated to E10's reserved generator families."""
    rows: list[dict[str, Any]] = []
    for label, color, strike in (
        ("TESTE 12345", "black", False),
        ("N3(2)", "green", False),
        ("TR-3-45", "black", False),
        ("10-150", "red", True),
        ("ABC-2 CAA", "black", False),
        ("ALTURA 12m", "black", False),
        ("", "black", False),
    ):
        picture = Image.new("RGB", (650, 110), "white")
        draw = ImageDraw.Draw(picture)
        draw.text((25, 25), label, fill=color, font=ImageFont.load_default(size=48))
        if strike:
            draw.line((20, 53, 210, 53), fill=color, width=2)
        if not label:
            draw.rectangle((20, 15, 620, 95), outline="black", width=2)
        result = engine.reconhecer(raster(picture))
        observed = " ".join(item.texto for item in result)
        rows.append(
            {
                "expected": label,
                "observed": observed,
                "exact": observed == label,
                "negative": not label,
                "geometry": [asdict(item) for item in result],
            }
        )
    # Technical accuracy failures are measured, not hidden as runtime failure.
    if not any("12345" in row["observed"] for row in rows):
        raise RuntimeError("Real engine failed functional positive control")
    return rows


def ocr_experiment(source: Path, output: Path, runtime: Path) -> dict[str, Any]:
    before = identity(source)
    engine = RapidLocalOcr()
    report: dict[str, Any] = {
        "schema": 1,
        "adapter": engine.versao,
        "source": before,
        "completed": False,
        "experimental": True,
        "python": platform.python_version(),
        "models": engine.models,
        "capability": asdict(engine.capability),
        "dependencies": {
            name: metadata.version(name)
            for name in (
                "rapidocr-onnxruntime",
                "onnxruntime",
                "numpy",
                "scipy",
                "opencv-python",
                "pymupdf",
                "pillow",
                "pyclipper",
                "shapely",
                "pyyaml",
            )
        },
        "controls": {"rapid": controls(engine)},
        "tiles": [],
        "readings": [],
        "policy": "Fixed 3x4 overlapping tiles, 600 DPI, both layers, no reference input",
    }
    tess = inspect_tesseract_runtime(runtime)
    if not tess.portugues_pronto or tess.executavel is None:
        raise RuntimeError("Tesseract control runtime unavailable")
    report["controls"]["tesseract"] = controls(
        TesseractCliOcr(
            tess.executavel,
            language="+".join(tess.idiomas_selecionados),
            tessdata_directory=tess.diretorio_tessdata,
        )
    )
    engine.calls.clear()
    save(output, report)
    started = perf_counter()
    # These tiles are independent of the reference ROIs and cover the entire page.
    with pymupdf.open(source) as document:  # type: ignore[no-untyped-call]
        for page in document:
            for annotations in (False, True):
                for row in range(4):
                    for column in range(3):
                        clip = pymupdf.Rect(  # type: ignore[no-untyped-call]
                            max(0, column / 3 - 0.02) * page.rect.width,
                            max(0, row / 4 - 0.02) * page.rect.height,
                            min(1, (column + 1) / 3 + 0.02) * page.rect.width,
                            min(1, (row + 1) / 4 + 0.02) * page.rect.height,
                        )
                        if (clip.width * 600 / 72 + 2) * (clip.height * 600 / 72 + 2) > 8_000_000:
                            raise ValueError("Tile exceeds 8 MP; explicit partial run, no success")
                        pix = page.get_pixmap(dpi=600, clip=clip, annots=annotations, alpha=False)
                        tile_id = f"p{page.number + 1}-{annotations}-{row}-{column}"
                        result = engine.recognize_quads(
                            PaginaRasterOcr(
                                pagina_numero=page.number + 1,
                                largura_pixels=pix.width,
                                altura_pixels=pix.height,
                                stride=pix.stride,
                                dados_rgb=pix.samples,
                                dpi=600,
                            )
                        )
                        for index, item in enumerate(result):
                            report["readings"].append(
                                {
                                    **item,
                                    "id": f"{tile_id}-{index}",
                                    "page": page.number + 1,
                                    "annotations": annotations,
                                    "tile": tile_id,
                                    "quad": map_quad(
                                        item["quad"],
                                        raster_origin=(pix.x, pix.y),
                                        scale=600 / 72,
                                        page_size=(page.rect.width, page.rect.height),
                                    ),
                                }
                            )
                        report["tiles"].append(
                            {
                                "id": tile_id,
                                "clip": [clip.x0, clip.y0, clip.x1, clip.y1],
                                "raster_sha256": sha256(pix.samples).hexdigest(),
                                **engine.calls[-1],
                            }
                        )
                        del pix
                        save(output, report)
                        print(f"Completed {tile_id}: {len(result)} readings", flush=True)
    report.update(seconds=perf_counter() - started, source_unchanged=identity(source) == before)
    if not report["source_unchanged"]:
        raise RuntimeError("Source changed during experiment")
    report["completed"] = True
    save(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("ocr", "graph"))
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-directory", type=Path, default=Path("tmp/e01/runtime"))
    options = parser.parse_args()
    if options.source.resolve() == options.output.resolve():
        raise ValueError("Output must not overwrite source")
    if options.mode == "ocr":
        ocr_experiment(options.source, options.output, options.runtime_directory)
    else:
        before = identity(options.source)
        snapshot = json.loads(options.source.read_text(encoding="utf-8"))
        started = perf_counter()
        graph = run_graph(snapshot["ocr"])
        graph.update(
            input=before,
            source_sha256=snapshot["source_sha256"],
            seconds=perf_counter() - started,
            completed=True,
        )
        if identity(options.source) != before:
            raise RuntimeError("Snapshot changed")
        save(options.output, graph)
        print(f"Graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} supported edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
