# mypy: disable-error-code="no-untyped-call"
"""Audit E07 package coverage against the frozen E01 inventory.

This checks declaration integrity, not recognition accuracy. Pending variants are
reported separately and cannot satisfy the E07 acceptance gate.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/data/inventario-simbologia-v1.json"
PACKAGES = ROOT / "src/zeny_project_handler/adapters/analysis/symbol_packages"


def audit(
    inventory_path: Path = INVENTORY,
    package_dir: Path = PACKAGES,
    *,
    source_pdf: Path | None = None,
) -> dict[str, Any]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    expected = {item["id"]: item for item in inventory["variants"] if item["owner_stage"] == "E07"}
    sources = {item["id"]: item for item in inventory["sources"]}
    profiles = {item["id"] for item in inventory["profiles"]}
    errors: list[str] = []
    actual: dict[str, dict[str, Any]] = {}
    families: dict[str, dict[str, Any]] = {}
    for path in sorted(package_dir.glob("*.json")):
        package = json.loads(path.read_text(encoding="utf-8"))
        family_id = package.get("family_id")
        if family_id in families:
            errors.append(f"duplicate family: {family_id}")
        if family_id != path.stem:
            errors.append(f"{path.name}: file/family mismatch")
        if package.get("profile_id") not in profiles:
            errors.append(f"{path.name}: unknown profile")
        if package.get("source_id") not in sources:
            errors.append(f"{path.name}: unknown source")
        statuses: Counter[str] = Counter()
        for item in package.get("variants", []):
            identity = item.get("id")
            if identity in actual:
                errors.append(f"duplicate variant: {identity}")
            actual[identity] = item
            status = item.get("recognition", {}).get("status")
            statuses[status] += 1
            reference = expected.get(identity)
            if reference is None:
                errors.append(f"unexpected variant: {identity}")
                continue
            if reference["family_id"] != family_id:
                errors.append(f"{identity}: family mismatch")
            if reference["profile_id"] != package.get("profile_id"):
                errors.append(f"{identity}: profile mismatch")
            if reference["class_code"] != item.get("class_code"):
                errors.append(f"{identity}: class mismatch")
            if reference["destination"] != item.get("destination"):
                errors.append(f"{identity}: destination mismatch")
            if reference["source_refs"][0] != item.get("source_ref"):
                errors.append(f"{identity}: source locator mismatch")
            role = (
                "informative"
                if reference["function"] in {"convention", "non_asset"}
                else "operational"
            )
            if role != item.get("role"):
                errors.append(f"{identity}: role mismatch")
            if status == "enabled" and not item["recognition"].get("grammar"):
                errors.append(f"{identity}: enabled without grammar")
            if status == "pending" and not item["recognition"].get("reason"):
                errors.append(f"{identity}: pending without reason")
            if status not in {"enabled", "pending"}:
                errors.append(f"{identity}: invalid recognition status")
        families[family_id] = {
            "file": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "variants": sum(statuses.values()),
            "enabled": statuses["enabled"],
            "pending": statuses["pending"],
        }
    for identity in sorted(set(expected) - set(actual)):
        errors.append(f"missing variant: {identity}")
    expected_families = {item["family_id"] for item in expected.values()}
    for identity in sorted(expected_families - set(families)):
        errors.append(f"missing family: {identity}")
    verified_source: dict[str, Any] | None = None
    if source_pdf is not None:
        import pymupdf

        source_path = source_pdf.resolve(strict=True)
        source_id = "F02"
        actual_hash = sha256(source_path.read_bytes()).hexdigest()
        expected_hash = sources[source_id]["sha256"]
        with pymupdf.open(source_path) as document:
            page_count = len(document)
        verified_source = {
            "source_id": source_id,
            "path": str(source_path),
            "sha256": actual_hash,
            "expected_sha256": expected_hash,
            "page_count": page_count,
        }
        if actual_hash != expected_hash:
            errors.append(f"{source_id}: source PDF hash mismatch")
        for identity, variant in actual.items():
            reference = variant.get("source_ref", {})
            if reference.get("source_id") != source_id:
                errors.append(f"{identity}: not located in {source_id}")
            page = reference.get("pdf_page")
            if type(page) is not int or not 1 <= page <= page_count:
                errors.append(f"{identity}: page outside source PDF")
    return {
        "inventory_version": inventory["inventory_version"],
        "inventory_sha256": sha256(inventory_path.read_bytes()).hexdigest(),
        "expected_families": len(expected_families),
        "expected_variants": len(expected),
        "package_families": len(families),
        "package_variants": len(actual),
        "enabled": sum(item["enabled"] for item in families.values()),
        "pending": sum(item["pending"] for item in families.values()),
        "families_without_recognition": sorted(
            identity for identity, item in families.items() if item["enabled"] == 0
        ),
        "verified_source": verified_source,
        "families": families,
        "errors": errors,
        "complete_recognition": not errors
        and len(actual) == len(expected)
        and all(item["pending"] == 0 for item in families.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--source-pdf", type=Path)
    args = parser.parse_args(argv)
    result = audit(source_pdf=args.source_pdf)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "expected_families",
                    "expected_variants",
                    "package_families",
                    "package_variants",
                    "enabled",
                    "pending",
                    "families_without_recognition",
                    "verified_source",
                    "errors",
                    "complete_recognition",
                )
            },
            ensure_ascii=False,
        )
    )
    return int(
        bool(result["errors"]) or (args.require_complete and not result["complete_recognition"])
    )


if __name__ == "__main__":
    raise SystemExit(main())
