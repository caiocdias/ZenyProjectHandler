# mypy: disable-error-code="no-untyped-call"
"""E11: isolated, locally trained raster window detector (never a product method).

The F07 Faster R-CNN/FPN candidate requires torch/torchvision, which are not
present in the pinned local environment. This CPU experiment trains a linear
visual classifier on the author-owned E02 development images. Its scores are
raw classifier outputs, not calibrated probabilities.
"""

from __future__ import annotations

import argparse
import ctypes
import importlib
import json
import math
import os
import platform
import random
import sys
from ctypes import wintypes
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

import pymupdf
from PIL import Image

from scripts.symbol_benchmark_evaluator import evaluate
from scripts.symbol_benchmark_runner import canonical_json, write_json

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_REFERENCE = ROOT / "tests" / "fixtures" / "symbols" / "reference-development.json"
METHOD_ID = "e11-linear-raster-windows"
FAMILY = {
    "ATERRAMENTO": "family-f02-19",
    "PARA_RAIOS_MT": "family-f02-21",
    "PARA_RAIOS_BT": "family-f02-21",
    "TRANSFORMADOR": "family-f02-18",
    "ESTAI_MT": "family-f02-14",
}
SEED = 20260924
FEATURE_SIDE = 12
MAX_IMAGE_SIDE = 900
THRESHOLD = 0.8  # Fixed before viewing calibration/examples.
MAX_PREDICTIONS_PER_PAGE = 40  # Global cap fixed before any calibration/real evaluation.
Record = dict[str, Any]


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _source_sha() -> str:
    return sha256(
        Path(__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
    ).hexdigest()


def _rss_bytes(*, peak: bool = False) -> int | None:
    """Working set (or peak) on Windows, max RSS on POSIX; includes native memory."""
    if os.name == "nt":

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        process = kernel32.GetCurrentProcess()
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        success = psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
        if not success:
            return None
        return int(counters.PeakWorkingSetSize if peak else counters.WorkingSetSize)
    try:
        resource = importlib.import_module("resource")
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value * (1024 if sys.platform != "darwin" else 1))
    except ImportError:
        return None


def _render(page: Any) -> Image.Image:
    scale = min(2.0, MAX_IMAGE_SIDE / max(float(page.rect.width), float(page.rect.height)))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False, annots=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")


def _box_pixels(box: list[float], image: Image.Image) -> tuple[int, int, int, int]:
    width, height = image.size
    x0, y0, x1, y1 = box
    return (
        max(0, math.floor(x0 * width) - 2),
        max(0, math.floor(y0 * height) - 2),
        min(width, math.ceil(x1 * width) + 2),
        min(height, math.ceil(y1 * height) + 2),
    )


def _features(image: Image.Image, box: tuple[int, int, int, int]) -> list[float]:
    sample = image.crop(box).resize((FEATURE_SIDE, FEATURE_SIDE), Image.Resampling.BILINEAR)
    values = [(255 - value) / 255 for value in sample.tobytes()]
    return [*values, sum(values) / len(values)]


def _overlap_ratio(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = ix * iy
    area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
    return intersection / (area_a + area_b - intersection)


def _data_from_reference(reference: Record, root: Path) -> list[tuple[Record, list[Image.Image]]]:
    results = []
    for doc in reference["documents"]:
        source = root / Path(doc["path"]).name
        if not source.is_file() or _sha(source) != doc["sha256"]:
            raise ValueError(f"Missing or modified E02 development PDF: {doc['id']}")
        with pymupdf.open(source) as pdf:
            if len(pdf) != len(doc["pages"]):
                raise ValueError(f"Page count changed: {doc['id']}")
            images = [_render(page) for page in pdf]
        results.append((doc, images))
    return results


def prepare(output: Path) -> Record:
    """Materialize only public E02 development/calibration; never touch reserve."""
    from tests.symbol_benchmark_fixtures import build_corpus, portable_reference

    output.mkdir(parents=True, exist_ok=True)
    results: Record = {}
    for split in ("development", "calibration"):
        directory = output / split
        reference = portable_reference(build_corpus(directory, split=split))
        write_json(directory / "reference.json", reference)
        results[split] = {
            "documents": len(reference["documents"]),
            "pages": sum(len(doc["pages"]) for doc in reference["documents"]),
            "reference_sha256": _sha(directory / "reference.json"),
        }
    write_json(output / "manifest.json", results)
    return results


def _validate_training_reference(reference: Record) -> None:
    public = json.loads(PUBLIC_REFERENCE.read_text(encoding="utf-8"))
    if reference != public:
        raise ValueError("Training requires the exact public E02 development reference")
    if reference.get("annotation_scope", "complete") != "complete":
        raise ValueError("Partial annotations cannot train E11")
    if any(doc.get("split") != "development" for doc in reference["documents"]):
        raise ValueError("Only development may train E11")
    if len({doc["ancestor_id"] for doc in reference["documents"]}) != 1:
        raise ValueError("Unexpected development ancestry")


def _train_linear(
    positives: list[list[float]], negatives: list[list[float]], seed: int
) -> tuple[list[float], float]:
    """Deterministic balanced logistic SGD; fixed epochs and learning rate."""
    rng = random.Random(seed)
    data = [(feature, 1.0) for feature in positives] + [(feature, 0.0) for feature in negatives]
    weights = [0.0] * len(positives[0])
    bias = 0.0
    for _ in range(50):
        rng.shuffle(data)
        for feature, label in data:
            logit = max(
                -30.0,
                min(30.0, sum(w * x for w, x in zip(weights, feature, strict=True)) + bias),
            )
            error = label - 1 / (1 + math.exp(-logit))
            for index, value in enumerate(feature):
                weights[index] += 0.06 * (error * value - 0.001 * weights[index])
            bias += 0.06 * error
    return [round(weight, 9) for weight in weights], round(bias, 9)


def train(reference_path: Path, root: Path, output: Path, seed: int = SEED) -> Record:
    started = perf_counter()
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    _validate_training_reference(reference)
    sources = _data_from_reference(reference, root)
    image_by_page = {
        (doc["id"], index): image
        for doc, images in sources
        for index, image in enumerate(images, start=1)
    }
    occurrences = [
        item
        for item in reference["occurrences"]
        if item["layer"] == "base"
        and item["context"] == "operational"
        and item["evaluability"] == "confirmed"
        and item["class_id"] in FAMILY
    ]
    # Exclude every annotated object, including ambiguity/negative/legend, from
    # random background samples to avoid assigning uncertain regions a label.
    all_boxes: dict[tuple[str, int], list[tuple[int, int, int, int]]] = {}
    for item in reference["occurrences"]:
        if item["layer"] != "base":
            continue
        key = (item["document_id"], item["page"])
        all_boxes.setdefault(key, []).append(_box_pixels(item["bbox"], image_by_page[key]))
    rng = random.Random(seed)
    classifiers: Record = {}
    for class_index, class_id in enumerate(FAMILY):
        relevant = [item for item in occurrences if item["class_id"] == class_id]
        if not relevant:
            continue
        positive: list[list[float]] = []
        dimensions: list[tuple[int, int]] = []
        for item in relevant:
            image = image_by_page[(item["document_id"], item["page"])]
            box = _box_pixels(item["bbox"], image)
            dimensions.append((box[2] - box[0], box[3] - box[1]))
            positive.append(_features(image, box))
            # Translation augmentation uses only the development image/label.
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                shifted = (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)
                if (
                    shifted[0] >= 0
                    and shifted[1] >= 0
                    and shifted[2] <= image.width
                    and shifted[3] <= image.height
                ):
                    positive.append(_features(image, shifted))
        window = (
            max(8, int(median(x for x, _ in dimensions))),
            max(8, int(median(y for _, y in dimensions))),
        )
        negatives: list[list[float]] = []
        attempts = 0
        pages = list(image_by_page.items())
        while len(negatives) < max(60, len(positive) * 3) and attempts < 10000:
            attempts += 1
            key, image = pages[rng.randrange(len(pages))]
            if image.width <= window[0] or image.height <= window[1]:
                continue
            x = rng.randrange(image.width - window[0])
            y = rng.randrange(image.height - window[1])
            box = (x, y, x + window[0], y + window[1])
            if any(_overlap_ratio(box, other) > 0.03 for other in all_boxes.get(key, [])):
                continue
            feature = _features(image, box)
            if feature[-1] > 0.01:  # Include meaningful background ink, not only white.
                negatives.append(feature)
        if not negatives:
            raise ValueError(f"No background examples for {class_id}")
        weights, bias = _train_linear(positive, negatives, seed + class_index)
        classifiers[class_id] = {
            "weights": weights,
            "bias": bias,
            "window": window,
            "positive_samples": len(positive),
            "negative_samples": len(negatives),
            "source_occurrences": [item["id"] for item in relevant],
        }
    if not classifiers:
        raise ValueError("No confirmed operational E02 development labels")
    output.mkdir(parents=True, exist_ok=True)
    model = {
        "schema_version": 1,
        "method_id": METHOD_ID,
        "algorithm": "12x12 grayscale linear logistic raster windows; scratch initialization",
        "source_sha256_lf": _source_sha(),
        "reference_sha256": _sha(reference_path),
        "public_reference_sha256": _sha(PUBLIC_REFERENCE),
        "seed": seed,
        "training_split": "development",
        "training_ancestors": sorted({doc["ancestor_id"] for doc in reference["documents"]}),
        "training_documents": [
            {"id": doc["id"], "sha256": doc["sha256"]} for doc in reference["documents"]
        ],
        "classifiers": classifiers,
        "threshold": THRESHOLD,
        "max_image_side": MAX_IMAGE_SIDE,
        "feature_side": FEATURE_SIDE,
    }
    write_json(output / "model.json", model)
    manifest = {
        "model_sha256": _sha(output / "model.json"),
        "reference_sha256": _sha(reference_path),
        "code_sha256_lf": _source_sha(),
        "python": sys.version,
        "platform": platform.platform(),
        "pymupdf": pymupdf.VersionBind,
        "pillow": version("Pillow"),
        "elapsed_seconds": perf_counter() - started,
        "working_set_bytes": _rss_bytes(),
        "peak_working_set_bytes": _rss_bytes(peak=True),
        "samples_by_class": {
            name: {key: value for key, value in item.items() if key.endswith("samples")}
            for name, item in classifiers.items()
        },
        "determinism": (
            "CPU; seeded Python random; fixed order; model JSON should be byte identical"
        ),
    }
    write_json(output / "train-manifest.json", manifest)
    return manifest


def _integral(image: Image.Image) -> list[list[int]]:
    width, height = image.size
    pixels = image.tobytes()
    table = [[0] * (width + 1)]
    for y in range(height):
        row = [0]
        running = 0
        previous = table[-1]
        for x in range(width):
            running += int(pixels[y * width + x] < 225)
            row.append(running + previous[x + 1])
        table.append(row)
    return table


def _ink(table: list[list[int]], box: tuple[int, int, int, int]) -> int:
    x0, y0, x1, y1 = box
    return table[y1][x1] - table[y0][x1] - table[y1][x0] + table[y0][x0]


def _score(weights: list[float], bias: float, features: list[float]) -> float:
    logit = max(-30.0, min(30.0, sum(w * x for w, x in zip(weights, features, strict=True)) + bias))
    return 1 / (1 + math.exp(-logit))


def detect_page(image: Image.Image, model: Record, *, stats: Record | None = None) -> list[Record]:
    table = _integral(image)
    candidates: list[Record] = []
    above_threshold = 0
    nms_suppressed = 0
    local_cap_suppressed = 0
    scanned_windows = 0
    for class_id, classifier in model["classifiers"].items():
        width, height = classifier["window"]
        if width > image.width or height > image.height:
            continue
        stride = max(6, min(width, height) // 3)
        windows = []
        for y in range(0, image.height - height + 1, stride):
            for x in range(0, image.width - width + 1, stride):
                box = (x, y, x + width, y + height)
                if _ink(table, box) < max(2, int(width * height * 0.008)):
                    continue
                scanned_windows += 1
                score = _score(classifier["weights"], classifier["bias"], _features(image, box))
                if score >= model["threshold"]:
                    windows.append((score, box))
                    above_threshold += 1
        windows.sort(key=lambda item: (-item[0], item[1]))
        accepted: list[tuple[float, tuple[int, int, int, int]]] = []
        for window_index, (score, box) in enumerate(windows):
            if any(_overlap_ratio(box, existing) >= 0.3 for _, existing in accepted):
                nms_suppressed += 1
                continue
            accepted.append((score, box))
            if len(accepted) == MAX_PREDICTIONS_PER_PAGE:
                local_cap_suppressed += len(windows) - window_index - 1
                break
        for score, box in accepted:
            candidates.append(
                {
                    "class_id": class_id,
                    "family": FAMILY[class_id],
                    "bbox": [
                        box[0] / image.width,
                        box[1] / image.height,
                        box[2] / image.width,
                        box[3] / image.height,
                    ],
                    "score": round(score, 9),
                }
            )
    candidates.sort(key=lambda item: (-item["score"], item["class_id"], item["bbox"]))
    global_suppressed = max(0, len(candidates) - MAX_PREDICTIONS_PER_PAGE)
    if stats is not None:
        stats.update(
            {
                "scanned_ink_windows": scanned_windows,
                "above_threshold": above_threshold,
                "nms_suppressed": nms_suppressed,
                "local_cap_suppressed": local_cap_suppressed,
                "global_cap_suppressed": global_suppressed,
                "global_cap": MAX_PREDICTIONS_PER_PAGE,
                "raster_size": list(image.size),
                "full_page_rendered": True,
            }
        )
    return candidates[:MAX_PREDICTIONS_PER_PAGE]


def _pdfs(root: Path) -> list[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    )


def infer(
    model_path: Path, root: Path, output: Path, document_id_prefix: str | None = None
) -> Record:
    started = perf_counter()
    model = json.loads(model_path.read_text(encoding="utf-8"))
    if model.get("method_id") != METHOD_ID or model.get("source_sha256_lf") != _source_sha():
        raise ValueError("Model architecture/source differs from the current E11 code")
    if document_id_prefix is None:
        document_id_prefix = "example:" if root.name.casefold() == "examples" else ""
    sources = _pdfs(root)
    output.mkdir(parents=True, exist_ok=True)
    predictions: Record = {
        "schema_version": 1,
        "documents": [],
        "methods": [
            {
                "id": METHOD_ID,
                "version": "e11-linear-1",
                "algorithm_family": "trained-linear-raster-window",
                "shared_sources": ["pymupdf:page-raster", "E02:development"],
                "supported_classes": list(model["classifiers"]),
                "supported_layers": ["base"],
                "model_sha256": _sha(model_path),
                "score_kind": "raw logistic classifier output; not calibrated probability",
            }
        ],
        "predictions": [],
        "executions": [],
    }
    manifest: Record = {
        "status": "completed" if sources else "no_examples",
        "completed": bool(sources),
        "model_sha256": _sha(model_path),
        "method_id": METHOD_ID,
        "code_sha256_lf": _source_sha(),
        "root": str(root.resolve()),
        "documents": [],
        "counts": {
            "pdfs": len(sources),
            "pages": 0,
            "predictions": 0,
            "failed_pages": 0,
            "failed_documents": 0,
            "documents_unknown_page_count": 0,
        },
    }
    for source in sources:
        relative = source.relative_to(root).as_posix()
        document_id = document_id_prefix + (relative if document_id_prefix else Path(relative).stem)
        source_hash = _sha(source)
        predictions["documents"].append({"id": document_id, "sha256": source_hash})
        entry: Record = {
            "id": document_id,
            "path": relative,
            "sha256_before": source_hash,
            "pages": [],
            "status": "executed",
        }
        try:
            with pymupdf.open(source) as pdf:
                for index, page in enumerate(pdf, start=1):
                    page_started = perf_counter()
                    try:
                        image = _render(page)
                        detection_stats: Record = {}
                        found = detect_page(image, model, stats=detection_stats)
                        for ordinal, item in enumerate(found, start=1):
                            predictions["predictions"].append(
                                {
                                    "id": f"{document_id}:p{index}:e11:{ordinal:04d}",
                                    "method_id": METHOD_ID,
                                    "document_id": document_id,
                                    "page": index,
                                    "layer": "base",
                                    "family": item["family"],
                                    "class_id": item["class_id"],
                                    "bbox": item["bbox"],
                                    "score": item["score"],
                                    "context": "operational",
                                    "situation": None,
                                    "quantity": None,
                                    "association": None,
                                    "review_required": True,
                                    "provenance": {
                                        "model_sha256": _sha(model_path),
                                        "document_sha256": source_hash,
                                        "score_kind": "uncalibrated classifier output",
                                    },
                                }
                            )
                        status, reason = "executed", None
                    except Exception as error:
                        found = []
                        detection_stats = {}
                        status, reason = "failed", f"{type(error).__name__}: {error}"
                        manifest["counts"]["failed_pages"] += 1
                        entry["status"] = "failed"
                    predictions["executions"].extend(
                        [
                            {
                                "document_id": document_id,
                                "page": index,
                                "layer": "base",
                                "method_id": METHOD_ID,
                                "status": status,
                                "reason": reason,
                                "prediction_count": len(found),
                            },
                            {
                                "document_id": document_id,
                                "page": index,
                                "layer": "annotation",
                                "method_id": METHOD_ID,
                                "status": "not_applicable",
                                "reason": "E11 raster excludes PDF annotation layer",
                            },
                        ]
                    )
                    entry["pages"].append(
                        {
                            "number": index,
                            "status": status,
                            "reason": reason,
                            "predictions": len(found),
                            "elapsed_seconds": perf_counter() - page_started,
                            "working_set_bytes": _rss_bytes(),
                            "peak_working_set_bytes": _rss_bytes(peak=True),
                            "detection": detection_stats,
                        }
                    )
                    manifest["counts"]["pages"] += 1
                    manifest["counts"]["predictions"] += len(found)
        except Exception as error:
            entry["status"] = "failed"
            entry["error"] = f"{type(error).__name__}: {error}"
            manifest["counts"]["failed_documents"] += 1
            if not entry["pages"]:
                manifest["counts"]["documents_unknown_page_count"] += 1
        entry["sha256_after"] = _sha(source)
        if entry["sha256_after"] != source_hash:
            entry["status"] = "failed"
            entry["error"] = "Source PDF changed during inference"
        manifest["documents"].append(entry)
    manifest["completed"] = bool(sources) and all(
        item["status"] == "executed" for item in manifest["documents"]
    )
    manifest["status"] = (
        "completed" if manifest["completed"] else ("no_examples" if not sources else "failed")
    )
    manifest["elapsed_seconds"] = perf_counter() - started
    manifest["working_set_bytes"] = _rss_bytes()
    manifest["peak_working_set_bytes"] = _rss_bytes(peak=True)
    write_json(output / "predictions.json", predictions)
    write_json(output / "manifest.json", manifest)
    return manifest


def compare(
    baseline_path: Path,
    learned_path: Path,
    output: Path,
    reference_path: Path | None = None,
) -> Record:
    """Preserve the candidate union and let the frozen E02 evaluator score it."""
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    learned = json.loads(learned_path.read_text(encoding="utf-8"))
    if baseline.get("schema_version") != 1 or learned.get("schema_version") != 1:
        raise ValueError("Both predictions must follow E02 schema 1")
    sources = [item.get("documents") for item in (baseline, learned)]
    if any(not isinstance(item, list) for item in sources):
        raise ValueError("Both predictions must bind document IDs and SHA-256")

    def source_map(items: list[Record]) -> dict[str, str]:
        result = {item["id"]: item["sha256"] for item in items}
        if len(result) != len(items):
            raise ValueError("Duplicate document ID")
        return result

    if source_map(sources[0]) != source_map(sources[1]):
        raise ValueError("Baseline and learned source PDFs differ")
    for key, identity in (("methods", "id"), ("predictions", "id")):
        items = [*baseline[key], *learned[key]]
        if len({item[identity] for item in items}) != len(items):
            raise ValueError(f"Duplicate {key} identity")
    executions = [*baseline["executions"], *learned["executions"]]
    execution_keys = [
        (item["document_id"], item["page"], item["layer"], item["method_id"]) for item in executions
    ]
    if len(set(execution_keys)) != len(execution_keys):
        raise ValueError("Duplicate method execution")
    merged = {
        **baseline,
        "documents": baseline["documents"],
        "methods": [*baseline["methods"], *learned["methods"]],
        "predictions": [*baseline["predictions"], *learned["predictions"]],
        "executions": executions,
    }
    report = None
    if reference_path is not None:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        report = evaluate(reference, merged)
    summary: Record = {
        "baseline_sha256": _sha(baseline_path),
        "learned_sha256": _sha(learned_path),
        "merged_sha256": sha256(canonical_json(merged).encode("utf-8")).hexdigest(),
        "methods": [item["id"] for item in merged["methods"]],
        "documents": len(merged["documents"]),
        "predictions": len(merged["predictions"]),
        "policy": "raw candidate union; no voting, filtering, or probability conversion",
    }
    if report is not None:
        assert reference_path is not None
        summary["reference_sha256"] = _sha(reference_path)
        summary["micro"] = report["compositions"]["raw_union"]["micro"]
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "predictions.json", merged)
    if report is not None:
        write_json(output / "report.json", report)
    write_json(output / "manifest.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--output", type=Path, required=True)
    train_parser = commands.add_parser("train")
    train_parser.add_argument("--reference", type=Path, required=True)
    train_parser.add_argument("--root", type=Path, required=True)
    train_parser.add_argument("--output", type=Path, required=True)
    train_parser.add_argument("--seed", type=int, default=SEED)
    infer_parser = commands.add_parser("infer")
    infer_parser.add_argument("--model", type=Path, required=True)
    infer_parser.add_argument("--root", type=Path, required=True)
    infer_parser.add_argument("--output", type=Path, required=True)
    infer_parser.add_argument("--document-id-prefix", type=str)
    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("--baseline", type=Path, required=True)
    compare_parser.add_argument("--learned", type=Path, required=True)
    compare_parser.add_argument("--output", type=Path, required=True)
    compare_parser.add_argument("--reference", type=Path)
    options = parser.parse_args(argv)
    if options.mode == "prepare":
        result = prepare(options.output)
    elif options.mode == "train":
        result = train(options.reference, options.root, options.output, options.seed)
    elif options.mode == "infer":
        result = infer(options.model, options.root, options.output, options.document_id_prefix)
    else:
        result = compare(options.baseline, options.learned, options.output, options.reference)
    print(canonical_json(result), end="")
    return 0 if result.get("completed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
