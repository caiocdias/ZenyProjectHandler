"""Author-owned E05 transformer benchmark; the E16 reserve is never opened.

The fixture/reference builder runs in a separate process. Inference receives
only the generated PDF path and an opaque document ID; the reference is loaded
after predictions have been persisted.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

import pymupdf

DOCUMENT_ID = "e05-author-transformers"
GENERALIZATION_ID = "e05-author-transformers-generalization"
CIRCULAR_ID = "e05-author-transformers-circular-stems"
FILL_ID = "e05-author-transformers-filled-marks"
Record = dict[str, Any]


def _family(variant_id: str | None) -> str:
    if variant_id is None:
        return "family-f02-33"
    section = variant_id.split("-s", 1)[1].split("-", 1)[0]
    return f"family-f02-{section}"


def _build(output: Path) -> None:
    from tests.fixtures.transformers.fixtures import (
        HEIGHT,
        WIDTH,
        build_circular_stem_fixture,
        build_fill_morphology_fixture,
        build_fixture,
        build_generalization_fixture,
    )

    builders = (
        (DOCUMENT_ID, build_fixture),
        (GENERALIZATION_ID, build_generalization_fixture),
        (CIRCULAR_ID, build_circular_stem_fixture),
        (FILL_ID, build_fill_morphology_fixture),
    )
    documents = []
    occurrences = []
    for document_id, builder in builders:
        source = output / "corpus" / f"{document_id}.pdf"
        cases = builder(source)
        with pymupdf.open(source) as document:
            pages = [
                {"number": index + 1, "width_pt": WIDTH, "height_pt": HEIGHT}
                for index in range(len(document))
            ]
        documents.append(
            {
                "id": document_id,
                "sha256": sha256(source.read_bytes()).hexdigest(),
                "path": source.name,
                "split": "development",
                "ancestor_id": document_id + "-v1",
                "template_family": document_id + "-v1",
                "pages": pages,
            }
        )
        for index, case in enumerate(cases):
            fields = asdict(case)
            variant_id = fields["variant_id"]
            occurrences.append(
                {
                    "id": f"{document_id}-p{case.page_number}-o{index:02d}",
                    "document_id": document_id,
                    "page": case.page_number,
                    "layer": "base",
                    "family": _family(variant_id),
                    "class_id": case.class_id or "NON_SYMBOL",
                    "bbox": list(case.bbox),
                    "context": case.context,
                    "evaluability": case.evaluability,
                    "situation": None,
                    "quantity": None,
                    "association": None,
                    "strata": [
                        case.stratum,
                        *(
                            [variant_id]
                            if document_id == DOCUMENT_ID and variant_id and index < 29
                            else []
                        ),
                    ],
                    "notes": "Author-owned E05 drawing; components do not establish asset quantity",
                }
            )
    reference: Record = {
        "schema_version": 1,
        "annotation_scope": "complete",
        "families": [f"family-f02-{number:02d}" for number in range(1, 34)],
        "documents": documents,
        "occurrences": occurrences,
        "provenance": {
            "generator": "tests/fixtures/transformers/fixtures.py",
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
    from scripts.symbol_benchmark_runner import (
        TRANSFORMER_METHOD_ID,
        _run,
        file_sha256,
        write_json,
    )

    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "scripts.benchmark_transformers_e05", "--build", str(output)],
        check=True,
    )
    sources = [
        (output / "corpus" / f"{document_id}.pdf", document_id)
        for document_id in (DOCUMENT_ID, GENERALIZATION_ID, CIRCULAR_ID, FILL_ID)
    ]
    manifest = _run(sources, output, mode="synthetic-development", include_transformers=True)
    # Persisted predictions precede the first reference read in this process.
    predictions = json.loads((output / "predictions.json").read_text(encoding="utf-8"))
    reference = json.loads((output / "reference.json").read_text(encoding="utf-8"))
    report = evaluate(reference, predictions)
    write_json(output / "report.json", report)
    inventory_path = Path(__file__).resolve().parents[1] / "docs/data/inventario-simbologia-v1.json"
    variants = tuple(
        item["id"]
        for item in json.loads(inventory_path.read_text(encoding="utf-8"))["variants"]
        if item.get("owner_stage") == "E05"
    )
    measured = report["methods"][TRANSFORMER_METHOD_ID]["by_stratum"]
    by_variant = {
        variant: measured.get(variant, {"tp": 0, "fp": 0, "fn": 1}) for variant in variants
    }
    missing = [variant for variant, values in by_variant.items() if values["tp"] < 1]
    summary = {
        "variant_denominator": len(variants),
        "variants_with_observation": len(variants) - len(missing),
        "missing_variants": missing,
        "by_variant": by_variant,
        "method_micro": report["methods"][TRANSFORMER_METHOD_ID]["micro"],
        "confirmed_operational": report["denominators"]["confirmed_operational"],
        "union_micro": report["compositions"]["raw_union"]["micro"],
        "legacy_micro": report["methods"]["legacy-vector-symbols"]["micro"],
        "source_sha256": {document_id: file_sha256(source) for source, document_id in sources},
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
