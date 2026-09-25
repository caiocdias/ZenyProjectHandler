"""Operational access gate for the E16R2 reserve.

The ZIP is integrity sealed, not cryptographically encrypted. Ordinary use
only reports status. Corpus extraction requires a frozen inference checkpoint;
reference release additionally requires complete predictions and a receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "manifest.json"
Record = dict[str, Any]


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> Record:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("expected a JSON object")
    return result


def public_manifest() -> Record:
    manifest = read_json(MANIFEST)
    archive = HERE / manifest["archive"]["path"]
    if digest(archive.read_bytes()) != manifest["archive"]["sha256"]:
        raise ValueError("sealed archive SHA-256 mismatch")
    return manifest


def validate_checkpoint(checkpoint: Record, manifest: Record) -> None:
    required = ("checkpoint_id", "frozen_at_utc", "code_sha256", "config_sha256")
    if not all(isinstance(checkpoint.get(key), str) and checkpoint[key] for key in required):
        raise ValueError("frozen inference checkpoint is missing required fields")
    for key in ("code_sha256", "config_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", checkpoint[key]):
            raise ValueError(f"invalid {key}")
    if checkpoint.get("archive_sha256") != manifest["archive"]["sha256"]:
        raise ValueError("checkpoint must bind this exact sealed archive")


def extract_corpus(checkpoint_path: Path, output: Path) -> Record:
    manifest = public_manifest()
    if not checkpoint_path.is_file():
        raise PermissionError("sealed corpus requires a frozen inference checkpoint")
    checkpoint = read_json(checkpoint_path)
    validate_checkpoint(checkpoint, manifest)
    if output.exists():
        raise FileExistsError("output must be new; no silent overwrite")
    archive = HERE / manifest["archive"]["path"]
    payloads = []
    with ZipFile(archive) as source:
        expected = {f"corpus/{item['path']}" for item in manifest["documents"]} | {"reference.json"}
        if set(source.namelist()) != expected:
            raise ValueError("archive entries differ from manifest")
        for item in manifest["documents"]:
            data = source.read("corpus/" + item["path"])
            if digest(data) != item["sha256"]:
                raise ValueError("source PDF hash mismatch")
            payloads.append((item["path"], data))
    output.mkdir(parents=True)
    corpus = output / "corpus"
    corpus.mkdir()
    for name, raw in payloads:
        (corpus / name).write_bytes(raw)
    receipt = {
        "stage": "e16r2-corpus-after-checkpoint",
        "archive_sha256": manifest["archive"]["sha256"],
        "manifest_sha256": digest(MANIFEST.read_bytes()),
        "checkpoint_sha256": digest(checkpoint_path.read_bytes()),
        "checkpoint_id": checkpoint["checkpoint_id"],
        "documents": [{"path": name, "sha256": digest(raw)} for name, raw in payloads],
        "reference_read": False,
    }
    (output / "corpus-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def release_reference(
    checkpoint_path: Path,
    corpus_receipt_path: Path,
    prediction_manifest_path: Path,
    predictions_path: Path,
    output: Path,
    acknowledge: bool,
) -> Record:
    if not acknowledge:
        raise PermissionError("reference release requires explicit acknowledgement")
    manifest = public_manifest()
    checkpoint = read_json(checkpoint_path)
    validate_checkpoint(checkpoint, manifest)
    receipt = read_json(corpus_receipt_path)
    if receipt.get("stage") != "e16r2-corpus-after-checkpoint":
        raise ValueError("invalid corpus receipt stage")
    if receipt.get("archive_sha256") != manifest["archive"]["sha256"]:
        raise ValueError("corpus receipt archive mismatch")
    if receipt.get("manifest_sha256") != digest(MANIFEST.read_bytes()):
        raise ValueError("corpus receipt manifest mismatch")
    if receipt.get("checkpoint_sha256") != digest(checkpoint_path.read_bytes()):
        raise ValueError("corpus receipt checkpoint mismatch")
    if receipt.get("reference_read") is not False:
        raise ValueError("corpus receipt says reference was already read")
    expected_sources = {item["sha256"] for item in manifest["documents"]}
    if {item["sha256"] for item in receipt.get("documents", [])} != expected_sources:
        raise ValueError("corpus receipt does not cover all source PDFs")
    prediction_manifest = read_json(prediction_manifest_path)
    predictions = read_json(predictions_path)
    counts = prediction_manifest.get("counts", {})
    if (
        prediction_manifest.get("completed") is not True
        or counts.get("pdfs") != manifest["counts"]["documents"]
        or counts.get("pages_attempted") != manifest["counts"]["pages"]
        or counts.get("documents_failed") != 0
        or counts.get("pages_failed") != 0
    ):
        raise ValueError("inference is not complete for all reserved pages")
    if {item.get("sha256") for item in predictions.get("documents", [])} != expected_sources:
        raise ValueError("predictions do not bind every reserved PDF SHA-256")
    if output.exists():
        raise FileExistsError("reference output must be new")
    output.mkdir(parents=True)
    pre = {
        "stage": "e16r2-pre-reference",
        "archive_sha256": manifest["archive"]["sha256"],
        "corpus_receipt_sha256": digest(corpus_receipt_path.read_bytes()),
        "prediction_manifest_sha256": digest(prediction_manifest_path.read_bytes()),
        "predictions_sha256": digest(predictions_path.read_bytes()),
        "reference_read": False,
    }
    (output / "pre-reference-receipt.json").write_text(
        json.dumps(pre, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with ZipFile(HERE / manifest["archive"]["path"]) as source:
        raw = source.read("reference.json")
    if digest(raw) != manifest["archive"]["reference_sha256"]:
        raise ValueError("sealed reference hash mismatch")
    (output / "reference.json").write_bytes(raw)
    post = {**pre, "reference_read": True, "reference_sha256": digest(raw)}
    (output / "release-receipt.json").write_text(
        json.dumps(post, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return post


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_subparsers(dest="action", required=True)
    action.add_parser("status", help="verify only public hashes and counts")
    extract = action.add_parser("extract-corpus", help="requires frozen checkpoint")
    extract.add_argument("--checkpoint", type=Path, required=True)
    extract.add_argument("--output", type=Path, required=True)
    release = action.add_parser("release-reference", help="requires completed predictions")
    release.add_argument("--checkpoint", type=Path, required=True)
    release.add_argument("--corpus-receipt", type=Path, required=True)
    release.add_argument("--prediction-manifest", type=Path, required=True)
    release.add_argument("--predictions", type=Path, required=True)
    release.add_argument("--output", type=Path, required=True)
    release.add_argument("--acknowledge-reference-release", action="store_true")
    args = parser.parse_args()
    if args.action == "status":
        manifest = public_manifest()
        print(
            json.dumps(
                {
                    "archive_sha256": manifest["archive"]["sha256"],
                    "counts": manifest["counts"],
                    "strata_counts": manifest["strata_counts"],
                },
                sort_keys=True,
            )
        )
    elif args.action == "extract-corpus":
        result = extract_corpus(args.checkpoint, args.output)
        print(
            json.dumps(
                {
                    "archive_sha256": result["archive_sha256"],
                    "reference_read": result["reference_read"],
                },
                sort_keys=True,
            )
        )
    else:
        result = release_reference(
            args.checkpoint,
            args.corpus_receipt,
            args.prediction_manifest,
            args.predictions,
            args.output,
            args.acknowledge_reference_release,
        )
        print(
            json.dumps(
                {
                    "predictions_sha256": result["predictions_sha256"],
                    "reference_sha256": result["reference_sha256"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
