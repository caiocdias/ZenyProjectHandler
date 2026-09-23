"""Author-owned E06 guy benchmark, with labels withheld from inference.

The fixture/reference builder runs in a separate process. The runner receives
only the generated PDF and an opaque document ID. It persists predictions
before this process reads the reference. The E16 reserve is never opened.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

import pymupdf

DOCUMENT_ID = "e06-author-guys"
Record = dict[str, Any]


def _family(variant_id: str | None) -> str:
    if variant_id is None:
        return "family-f02-14"
    section = variant_id.split("-s", 1)[1].split("-", 1)[0]
    return f"family-f02-{section}"


def _build(output: Path) -> None:
    from tests.fixtures.guys.fixtures import HEIGHT, WIDTH, build_fixture

    output.mkdir(parents=True, exist_ok=True)
    source = output / "corpus" / f"{DOCUMENT_ID}.pdf"
    cases = build_fixture(source)
    with pymupdf.open(source) as document:
        pages = [
            {"number": number + 1, "width_pt": WIDTH, "height_pt": HEIGHT}
            for number in range(len(document))
        ]
    occurrences = []
    for index, case in enumerate(cases):
        positive = case.variant_id is not None
        occurrences.append(
            {
                "id": f"{DOCUMENT_ID}-p{case.page_number}-o{index:02d}",
                "document_id": DOCUMENT_ID,
                "page": case.page_number,
                "layer": "base",
                "family": _family(case.variant_id),
                "class_id": "ESTAI" if positive else "NON_SYMBOL",
                "bbox": list(case.bbox),
                "context": "operational" if positive else "negative",
                "evaluability": "confirmed",
                "situation": None,
                "quantity": None,
                "association": None,
                "strata": [case.stratum, *([case.variant_id] if case.variant_id else [])],
                "variant_id": case.variant_id,
                "notes": (
                    "Author-owned drawing; mechanical relation does not imply an electrical span"
                ),
            }
        )
    reference: Record = {
        "schema_version": 1,
        "annotation_scope": "complete",
        "families": [f"family-f02-{number:02d}" for number in range(1, 34)],
        "documents": [
            {
                "id": DOCUMENT_ID,
                "sha256": sha256(source.read_bytes()).hexdigest(),
                "path": source.name,
                "split": "development",
                "ancestor_id": DOCUMENT_ID + "-v1",
                "template_family": "author-guy-geometries-v1",
                "pages": pages,
            }
        ],
        "occurrences": occurrences,
        "provenance": {
            "generator": "tests/fixtures/guys/fixtures.py",
            "ownership": "Author-owned synthetic development controls",
            "reference_role": "Evaluation only; never passed to inference",
            "limitations": "No field-generalization or normative equivalence estimate",
        },
    }
    (output / "reference.json").write_text(
        json.dumps(reference, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run(output: Path) -> Record:
    from scripts.symbol_benchmark_evaluator import evaluate
    from scripts.symbol_benchmark_runner import GUY_METHOD_ID, _run, file_sha256, write_json

    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "scripts.benchmark_guys_e06", "--build", str(output)],
        check=True,
    )
    source = output / "corpus" / f"{DOCUMENT_ID}.pdf"
    manifest = _run(
        [(source, DOCUMENT_ID)], output, mode="synthetic-development", include_guys=True
    )
    # The prediction artifact is complete before the first reference read here.
    predictions = json.loads((output / "predictions.json").read_text(encoding="utf-8"))
    reference = json.loads((output / "reference.json").read_text(encoding="utf-8"))
    report = evaluate(reference, predictions)
    write_json(output / "report.json", report)
    inventory_path = Path(__file__).resolve().parents[1] / "docs/data/inventario-simbologia-v1.json"
    variants = tuple(
        item["id"]
        for item in json.loads(inventory_path.read_text(encoding="utf-8"))["variants"]
        if item.get("owner_stage") == "E06"
    )
    measured = report["methods"][GUY_METHOD_ID]["by_stratum"]
    by_variant = {
        variant: measured.get(variant, {"tp": 0, "fp": 0, "fn": 1}) for variant in variants
    }
    missing = [variant for variant, values in by_variant.items() if values["tp"] < 1]
    summary = {
        "variant_denominator": len(variants),
        "variants_with_observation": len(variants) - len(missing),
        "missing_variants": missing,
        "by_variant": by_variant,
        "method_micro": report["methods"][GUY_METHOD_ID]["micro"],
        "confirmed_operational": report["denominators"]["confirmed_operational"],
        "union_micro": report["compositions"]["raw_union"]["micro"],
        "legacy_micro": report["methods"]["legacy-vector-symbols"]["micro"],
        "source_sha256": file_sha256(source),
        "reference_sha256": file_sha256(output / "reference.json"),
        "predictions_sha256": file_sha256(output / "predictions.json"),
        "report_sha256": file_sha256(output / "report.json"),
        "completed_inference": manifest["completed"],
    }
    write_json(output / "summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--build", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.build is not None:
        _build(args.build)
        return 0
    if args.output is None:
        parser.error("--output is required")
    summary = run(args.output)
    print(json.dumps({key: value for key, value in summary.items() if key != "by_variant"}))
    method = summary["method_micro"]
    passed = (
        summary["completed_inference"]
        and not summary["missing_variants"]
        and method["tp"] == summary["confirmed_operational"]
        and method["fp"] == 0
        and method["fn"] == 0
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
