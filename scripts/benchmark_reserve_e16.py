"""One-shot E16 reserve gate: infer first, then reveal labels for measurement.

The E02 ZIP remains refused by ordinary runners and evaluator calls. This
command requires a fresh output directory and verifies every sealed PDF against
the frozen manifest before invoking the unchanged inference runner. It never
passes a reference or reviewer ROI to a detector.
"""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from scripts.reconcile_symbol_benchmark import _adopted_predictions, compose
from scripts.symbol_benchmark_evaluator import _evaluation, evaluate
from scripts.symbol_benchmark_runner import _run, file_sha256, write_json

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "symbols"
EXCLUDED = ("structural-raster-graph", "structural-vector-graph")
Record = dict[str, Any]


def _archive_member(archive: ZipFile, name: str) -> str:
    matches = [
        item.filename
        for item in archive.infolist()
        if not item.is_dir() and Path(item.filename).name == name
    ]
    if len(matches) != 1:
        raise ValueError(f"reserve archive requires one {name!r}; found {len(matches)}")
    return matches[0]


def _verified_documents(manifest: Record, archive: ZipFile, corpus: Path) -> list[tuple[Path, str]]:
    partition = next((item for item in manifest["partitions"] if item["split"] == "reserve"), None)
    if partition is None or len(partition["documents"]) != manifest["reserve"]["documents"]:
        raise ValueError("frozen reserve document manifest is inconsistent")
    sources: list[tuple[Path, str]] = []
    for document in partition["documents"]:
        member = _archive_member(archive, Path(document["path"]).name)
        raw = archive.read(member)
        if sha256(raw).hexdigest() != document["sha256"]:
            raise ValueError(f"sealed PDF hash mismatch: {document['id']}")
        target = corpus / Path(document["path"]).name
        target.write_bytes(raw)
        sources.append((target, document["id"]))
    return sources


def run(output: Path) -> Record:
    output = output.resolve()
    if output.exists():
        raise FileExistsError("E16 reserve output must be a new directory; no silent rerun")
    manifest_path = FIXTURES / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if file_sha256(FIXTURES / manifest["reserve"]["path"]) != manifest["reserve"]["sha256"]:
        raise ValueError("sealed archive hash mismatch")
    if (
        file_sha256(ROOT / "docs" / "data" / "inventario-simbologia-v1.json")
        != manifest["inventory_sha256"]
    ):
        raise ValueError("E01 inventory changed since the reserve was sealed")
    output.mkdir(parents=True)
    corpus = output / "corpus"
    corpus.mkdir()
    archive_path = FIXTURES / manifest["reserve"]["path"]
    with ZipFile(archive_path) as archive:
        sources = _verified_documents(manifest, archive, corpus)
    prediction_manifest = _run(
        sources,
        output,
        mode="e16-reserve-one-shot",
        include_transformers=True,
        include_guys=True,
        include_packages=True,
        include_raster=True,
        include_structural=True,  # evaluated as an E09 control, excluded from adoption
        include_legend=True,
    )
    if not prediction_manifest["completed"]:
        raise RuntimeError("reserve inference incomplete; labels remain unread")
    # The generic E02 runner records every corpus as development. Correct that
    # metadata from the sealed source manifest before the reference is opened.
    for document in prediction_manifest["documents"]:
        document["split"] = "reserve"
    write_json(output / "manifest.json", prediction_manifest)
    predictions_path = output / "predictions.json"
    prediction_digest = file_sha256(predictions_path)
    receipt = {
        "archive_sha256": manifest["reserve"]["sha256"],
        "inventory_sha256": manifest["inventory_sha256"],
        "prediction_sha256_before_reference": prediction_digest,
        "runner_manifest_sha256_before_reference": file_sha256(output / "manifest.json"),
        "method_flags": [
            "include_transformers",
            "include_guys",
            "include_packages",
            "include_raster",
            "include_structural_experimental",
            "include_legend",
        ],
        "reference_read": False,
    }
    write_json(output / "pre_reference_receipt.json", receipt)
    raw = json.loads(predictions_path.read_text(encoding="utf-8"))
    composition = compose(raw, EXCLUDED)
    write_json(output / "composition.json", composition)
    # The frozen prediction and composition artifacts now exist on disk. Only
    # this measurement phase reads the reference bytes from the sealed ZIP.
    with ZipFile(archive_path) as archive:
        reference_bytes = archive.read(_archive_member(archive, "reference.json"))
    reference = json.loads(reference_bytes)
    write_json(output / "reference.json", reference)
    if file_sha256(predictions_path) != prediction_digest:
        raise RuntimeError("predictions changed after the reference was opened")
    reserve_partition = next(item for item in manifest["partitions"] if item["split"] == "reserve")
    expected = {document["id"]: document for document in reserve_partition["documents"]}
    if {document["id"] for document in reference["documents"]} != set(expected):
        raise ValueError("reserve reference document IDs differ from frozen manifest")
    for document in reference["documents"]:
        if (
            document["split"] != "reserve"
            or document["sha256"] != expected[document["id"]]["sha256"]
        ):
            raise ValueError(f"reserve reference source mismatch: {document['id']}")
    full = evaluate(reference, raw, allow_reserve=True)
    adopted_raw = _adopted_predictions(raw, EXCLUDED)
    adopted = evaluate(reference, adopted_raw, allow_reserve=True)
    baseline_raw = _adopted_predictions(
        raw, tuple(item["id"] for item in raw["methods"] if item["id"] != "legacy-vector-symbols")
    )
    baseline = evaluate(reference, baseline_raw, allow_reserve=True)
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
    summary = {
        "denominators": adopted["denominators"],
        "baseline": baseline["compositions"]["raw_union"]["micro"],
        "all_methods_raw_union": full["compositions"]["raw_union"]["micro"],
        "adopted_raw_union": adopted["compositions"]["raw_union"]["micro"],
        "final_exact_class": final["micro"],
        "unresolved_candidates": len(composition["candidates"]) - len(exact),
        "experimental_excluded": list(EXCLUDED),
        "predictions_sha256": prediction_digest,
        "reference_sha256": sha256(reference_bytes).hexdigest(),
        "composition_sha256": file_sha256(output / "composition.json"),
    }
    write_json(output / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
