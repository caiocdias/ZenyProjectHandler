"""E02 symbol benchmark: portable synthetic baseline and local recursive PDF audit.

Examples (repository root, installed development/server dependencies):
  python -m scripts.benchmark_symbols synthetic --output tmp/e02-simbologia/baseline
  python -m scripts.benchmark_symbols examples --root examples --output tmp/e02/predictions
  python -m scripts.benchmark_symbols evaluate --reference reference.json
      --predictions predictions.json --output report.json

The reserve remains sealed until E16. No command here opens or evaluates it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.symbol_benchmark_runner import evaluate_files, run_examples, run_synthetic


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    synthetic = modes.add_parser(
        "synthetic", help="portable development corpus; no examples required"
    )
    synthetic.add_argument("--output", type=Path, required=True)
    examples = modes.add_parser(
        "examples", help="all recursive PDFs/pages; independent visual review still required"
    )
    examples.add_argument("--root", type=Path, default=Path("examples"))
    examples.add_argument("--output", type=Path, required=True)
    comparison = modes.add_parser(
        "evaluate", help="compare frozen JSON artifacts without inference"
    )
    comparison.add_argument("--reference", type=Path, required=True)
    comparison.add_argument("--predictions", type=Path, required=True)
    comparison.add_argument("--output", type=Path, required=True)
    options = parser.parse_args(argv)
    if options.mode == "synthetic":
        result = run_synthetic(options.output)
        print(
            json.dumps(
                {
                    "counts": result["manifest"]["counts"],
                    "micro": result["report"]["compositions"]["raw_union"]["micro"],
                }
            )
        )
        return 0 if result["manifest"]["completed"] else 1
    if options.mode == "examples":
        manifest = run_examples(options.root, options.output)
        print(
            json.dumps(
                {
                    "status": manifest["status"],
                    "counts": manifest["counts"],
                    "visual_review": manifest["visual_review"],
                }
            )
        )
        return 0 if manifest["completed"] else 1
    report = evaluate_files(options.reference, options.predictions, options.output)
    print(
        json.dumps(
            {
                "denominators": report["denominators"],
                "micro": report["compositions"]["raw_union"]["micro"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
