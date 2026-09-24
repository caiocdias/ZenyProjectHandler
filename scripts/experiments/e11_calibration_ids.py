"""Rebind E02 example-runner IDs to the frozen calibration document IDs.

Only source metadata is consulted. Labels and occurrence boxes are not read.
The inference output and its candidate identities remain otherwise unchanged.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.symbol_benchmark_runner import write_json

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tests" / "fixtures" / "symbols" / "manifest.json"


def rebind(raw_path: Path, output_path: Path) -> dict[str, Any]:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    calibration = next(part for part in manifest["partitions"] if part["split"] == "calibration")
    expected = {doc["id"]: doc["sha256"] for doc in calibration["documents"]}
    source = {doc["id"]: doc["sha256"] for doc in raw["documents"]}
    rename = {f"example:{doc_id}.pdf": doc_id for doc_id in expected}
    if len(source) != len(raw["documents"]) or set(source) != set(rename):
        raise ValueError("E02 output does not contain exactly the calibration PDFs")
    if {rename[doc_id]: digest for doc_id, digest in source.items()} != expected:
        raise ValueError("Calibration source hash differs from E02 manifest")
    for key in ("documents", "predictions", "executions"):
        for item in raw[key]:
            field = "id" if key == "documents" else "document_id"
            if item[field] not in rename:
                raise ValueError(f"Unexpected {key} document ID")
            item[field] = rename[item[field]]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, raw)
    return {"documents": len(source), "predictions": len(raw["predictions"]), "mapping": rename}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(rebind(args.raw, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
