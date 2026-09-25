"""Freeze and run the independent E16R2 synthetic reserve exactly once.

The public manifest is safe to inspect before freezing. The sealed PDFs are
extracted only after a code/config checkpoint, and labels are released only
after complete inference and a prediction receipt have been written.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from tests.fixtures.symbols.e16r2.sealed_access import (
    extract_corpus,
    public_manifest,
    release_reference,
)

from scripts.reconcile_symbol_benchmark import _adopted_predictions, compose
from scripts.symbol_benchmark_evaluator import _evaluation, evaluate
from scripts.symbol_benchmark_runner import _run, file_sha256, write_json

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = ("structural-raster-graph", "structural-vector-graph")
CONFIG: dict[str, Any] = {
    "include_transformers": True,
    "include_guys": True,
    "include_packages": True,
    "include_raster": True,
    "include_structural": True,
    "include_legend": True,
    "include_legend_ocr": False,
    "excluded_experimental_methods": list(EXCLUDED),
    "opencv_optional_runtime": "absent",
}
Record = dict[str, Any]


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _code_hash() -> str:
    """Bind all shipped inference/evaluation code and the sealed accessor."""
    files = [
        path
        for base in (ROOT / "src", ROOT / "scripts")
        for path in base.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    ]
    files.append(ROOT / "tests" / "fixtures" / "symbols" / "e16r2" / "sealed_access.py")
    hashes = {path.relative_to(ROOT).as_posix(): file_sha256(path) for path in sorted(files)}
    return sha256(_canonical(hashes)).hexdigest()


def _config_hash() -> str:
    return sha256(_canonical(CONFIG)).hexdigest()


def _require_optional_runtime_absent() -> None:
    if importlib.util.find_spec("cv2") is not None:
        raise RuntimeError("E16R2 checkpoint excludes optional OpenCV/Hough runtime")


def freeze(checkpoint_path: Path) -> Record:
    if checkpoint_path.exists():
        raise FileExistsError("frozen checkpoint must be a new file")
    _require_optional_runtime_absent()
    manifest = public_manifest()
    checkpoint: Record = {
        "checkpoint_id": "e16r2-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "code_sha256": _code_hash(),
        "config_sha256": _config_hash(),
        "archive_sha256": manifest["archive"]["sha256"],
        "manifest_sha256": file_sha256(
            ROOT / "tests" / "fixtures" / "symbols" / "e16r2" / "manifest.json"
        ),
        "configuration": CONFIG,
    }
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(checkpoint_path, checkpoint)
    return checkpoint


def _verify_checkpoint(checkpoint_path: Path) -> Record:
    checkpoint: Record = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    manifest = public_manifest()
    _require_optional_runtime_absent()
    if (
        checkpoint["archive_sha256"] != manifest["archive"]["sha256"]
        or checkpoint["manifest_sha256"]
        != file_sha256(ROOT / "tests" / "fixtures" / "symbols" / "e16r2" / "manifest.json")
        or checkpoint["code_sha256"] != _code_hash()
        or checkpoint["config_sha256"] != _config_hash()
        or checkpoint["configuration"] != CONFIG
    ):
        raise ValueError("E16R2 code, configuration, manifest or archive changed after freeze")
    return checkpoint


def run(checkpoint_path: Path, output: Path) -> Record:
    _verify_checkpoint(checkpoint_path)
    output = output.resolve()
    if output.exists():
        raise FileExistsError("E16R2 reserve output must be new; no silent rerun")
    manifest = public_manifest()
    claim = checkpoint_path.with_name(checkpoint_path.name + ".used.json")
    with claim.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "checkpoint_sha256": file_sha256(checkpoint_path),
                "claimed_at_utc": datetime.now(UTC).isoformat(),
                "output": str(output),
                "status": "claimed-before-corpus-access",
            },
            stream,
            sort_keys=True,
        )
    extract_corpus(checkpoint_path, output)
    sources = [(output / "corpus" / item["path"], item["id"]) for item in manifest["documents"]]
    prediction_manifest = _run(
        sources,
        output,
        mode="e16r2-reserve-one-shot",
        include_transformers=True,
        include_guys=True,
        include_packages=True,
        include_raster=True,
        include_structural=True,
        include_legend=True,
    )
    if not prediction_manifest["completed"]:
        raise RuntimeError("reserve inference incomplete; labels remain unread")
    for document in prediction_manifest["documents"]:
        document["split"] = "reserve"
    write_json(output / "manifest.json", prediction_manifest)
    predictions_path = output / "predictions.json"
    predictions_hash = file_sha256(predictions_path)
    raw = json.loads(predictions_path.read_text(encoding="utf-8"))
    composition = compose(raw, EXCLUDED)
    write_json(output / "composition.json", composition)
    _verify_checkpoint(checkpoint_path)
    release = output / "reference-release"
    release_reference(
        checkpoint_path,
        output / "corpus-receipt.json",
        output / "manifest.json",
        predictions_path,
        release,
        acknowledge=True,
    )
    if file_sha256(predictions_path) != predictions_hash:
        raise RuntimeError("predictions changed after reference release")
    reference = json.loads((release / "reference.json").read_text(encoding="utf-8"))
    full = evaluate(reference, raw, allow_reserve=True)
    adopted = evaluate(reference, _adopted_predictions(raw, EXCLUDED), allow_reserve=True)
    baseline_exclusions = tuple(
        item["id"] for item in raw["methods"] if item["id"] != "legacy-vector-symbols"
    )
    baseline = evaluate(
        reference, _adopted_predictions(raw, baseline_exclusions), allow_reserve=True
    )
    exact = [item for item in composition["candidates"] if item["class_id"] and item["family"]]
    classes = {item["class_id"] for item in reference["occurrences"]} | {
        item["class_id"] for item in exact
    }
    final = _evaluation(exact, reference, classes, curves=False)
    for name, value in (
        ("report-all.json", full),
        ("report-adopted.json", adopted),
        ("report-baseline.json", baseline),
        ("report-final-exact.json", final),
    ):
        write_json(output / name, value)
    summary: Record = {
        "denominators": adopted["denominators"],
        "baseline": baseline["compositions"]["raw_union"]["micro"],
        "all_methods_raw_union": full["compositions"]["raw_union"]["micro"],
        "adopted_raw_union": adopted["compositions"]["raw_union"]["micro"],
        "final_exact_class": final["micro"],
        "unresolved_candidates": len(composition["candidates"]) - len(exact),
        "experimental_excluded": list(EXCLUDED),
        "predictions_sha256": predictions_hash,
        "reference_sha256": file_sha256(release / "reference.json"),
        "composition_sha256": file_sha256(output / "composition.json"),
        "checkpoint_sha256": file_sha256(checkpoint_path),
    }
    write_json(output / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    frozen = modes.add_parser("freeze")
    frozen.add_argument("--checkpoint", type=Path, required=True)
    reserved = modes.add_parser("run")
    reserved.add_argument("--checkpoint", type=Path, required=True)
    reserved.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = freeze(args.checkpoint) if args.mode == "freeze" else run(args.checkpoint, args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
