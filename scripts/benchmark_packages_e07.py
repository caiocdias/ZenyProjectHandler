"""E07 authored benchmark: frozen inference before reading independent labels."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from scripts.symbol_benchmark_runner import (
    PACKAGE_METHOD_ID,
    ROOT,
    file_sha256,
    infer_pdf,
    package_method_metadata,
    write_json,
)


def benchmark(output: Path) -> dict[str, Any]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = output / "e07-author-packages.pdf"
    reference_path = output / "reference.json"
    construction = (
        "import json,sys; from pathlib import Path; "
        "from tests.fixtures.declarative_symbols.corpus import build_enabled_corpus; "
        "reference=build_enabled_corpus(Path(sys.argv[1])); "
        "Path(sys.argv[2]).write_text(json.dumps(reference, ensure_ascii=False), encoding='utf-8')"
    )
    subprocess.run(
        [sys.executable, "-c", construction, str(source), str(reference_path)],
        check=True,
        cwd=ROOT,
    )
    method = package_method_metadata()
    manifest, predictions, executions = infer_pdf(source, "e07-author", include_packages=True)
    package_predictions = [item for item in predictions if item["method_id"] == PACKAGE_METHOD_ID]
    frozen = {
        "schema_version": 1,
        "source_sha256": file_sha256(source),
        "method": method,
        "manifest": manifest,
        "executions": executions,
        "predictions": package_predictions,
    }
    write_json(output / "predictions.json", frozen)
    prediction_sha256 = file_sha256(output / "predictions.json")
    # The only label-bearing input is read after the complete inference artifact exists.
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    if reference["pdf_sha256"] != frozen["source_sha256"]:
        raise ValueError("E07 authored source hash changed after inference")
    if reference["pages"] != manifest.get("page_count"):
        raise ValueError("E07 authored page count mismatch")
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in package_predictions:
        by_page[item["page"]].append(item)
    by_family: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "positive_cases": 0,
            "negative_cases": 0,
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "duplicates": 0,
        }
    )
    decisions = []
    for case in reference["cases"]:
        expected = set(case["expected_variant_ids"])
        observed_list = [item["provenance"]["variant_id"] for item in by_page[case["page"]]]
        observed = set(observed_list)
        duplicates = len(observed_list) - len(observed)
        family = by_family[case["family_id"]]
        family["positive_cases" if expected else "negative_cases"] += 1
        family["tp"] += len(expected & observed)
        family["fp"] += len(observed - expected) + duplicates
        family["fn"] += len(expected - observed)
        family["duplicates"] += duplicates
        decisions.append(
            {
                "page": case["page"],
                "family_id": case["family_id"],
                "variant_id": case["variant_id"],
                "stratum": case["stratum"],
                "expected": sorted(expected),
                "observed": sorted(observed),
                "tp": sorted(expected & observed),
                "fp": sorted(observed - expected),
                "fn": sorted(expected - observed),
                "duplicates": duplicates,
            }
        )
    report = {
        "schema_version": 1,
        "source_sha256": frozen["source_sha256"],
        "reference_sha256": file_sha256(reference_path),
        "predictions_sha256": prediction_sha256,
        "package_sha256": method["package_sha256"],
        "complete_inference": manifest["status"] == "executed" and not manifest["failures"],
        "by_family": dict(sorted(by_family.items())),
        "decisions": decisions,
        "limitations": [
            "Only enabled E07 grammars have authored positives/negatives.",
            "Pending inventory variants do not count as recognized or benchmarked.",
            "All pages derive from one authored document; no field calibration is inferred.",
        ],
    }
    write_json(output / "report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args(argv)
    report = benchmark(options.output)
    total = {
        key: sum(item[key] for item in report["by_family"].values())
        for key in ("positive_cases", "negative_cases", "tp", "fp", "fn", "duplicates")
    }
    print(json.dumps({"families": len(report["by_family"]), **total}))
    return int(not report["complete_inference"] or total["fp"] > 0 or total["fn"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
