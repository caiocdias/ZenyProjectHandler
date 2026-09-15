"""Post-inference E12B audit; reference data never enters the extraction pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.experiments.compare import box_distance, literal_links, operational, readings
from zeny_project_handler.application.method_reconciliation import (
    coordinate_literal,
    coordinate_value,
)


def audit(
    reference: dict[str, Any],
    vertical: dict[str, Any],
    combined: dict[str, Any],
    neural_only: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if vertical["source_sha256"] != combined["source_sha256"]:
        raise ValueError("Source mismatch")
    if not all(s.get("source_unchanged") for s in (vertical, combined)):
        raise ValueError("Unverified source")
    result: dict[str, Any] = {"reference_rows": len(reference["items"]), "methods": {}}
    variants = [("vertical", vertical), ("combined", combined)]
    if neural_only is not None:
        if neural_only["source_sha256"] != combined["source_sha256"] or not neural_only.get(
            "source_unchanged"
        ):
            raise ValueError("Unverified isolated source")
        variants.append(("neural_only", {**neural_only, "ocr": neural_only["native"]}))
    for name, snapshot in variants:
        if snapshot["ocr"]["counts"]["diagnostics"]:
            raise ValueError("Incomplete extraction/interpretation")
        metrics = operational(reference, snapshot)
        proposals = snapshot["ocr"]["semantic"]["elementos"]
        by_id = {p["id"]: p for p in proposals}
        confirmed = {p["id"] for p in proposals if p["estado_revisao"] == "CONFIRMADA"}
        bad = {r["proposal_id"] for r in metrics["rows"] if r.get("proposal_id") and not r["joint"]}
        bad.update(p for group in metrics["classes"].values() for p in group["duplicates"])
        correct = {r["proposal_id"] for r in metrics["rows"] if r["joint"]}
        review = [
            r["id"]
            for r in metrics["rows"]
            if r.get("proposal_id") and by_id[r["proposal_id"]]["estado_revisao"] != "CONFIRMADA"
        ]
        selected = snapshot["ocr"]["results"].get("method_readings", [])
        candidates = readings(snapshot)
        auxiliary = [
            {
                "id": r["identity"],
                "text": r["literal"],
                "quad": r["geometry"],
                "annotations": r["layer"] != "base",
            }
            for r in selected
            if r["layer"] == "base"
        ]
        documents = [i for i in reference["items"] if i["kind"] == "documentation"]
        coordinate_refs = [i for i in documents if coordinate_literal(i.get("code") or "")]
        coordinate_coverage = {
            label: [
                i["id"]
                for i in coordinate_refs
                if any(
                    box_distance(i["center"], reading["quad"]) <= 0.012
                    and coordinate_value(i["code"]) == coordinate_value(reading["text"])
                    for reading in source_readings
                )
            ]
            for label, source_readings in (
                ("base", candidates),
                ("auxiliary", auxiliary),
                ("combined", [*candidates, *auxiliary]),
            )
        }
        reading_audit = []
        for reading in auxiliary:
            nearby = [
                i
                for i in reference["items"]
                if coordinate_literal(i.get("code") or "")
                and box_distance(i["center"], reading["quad"]) <= 0.012
            ]
            reading_audit.append(
                {
                    "reading_id": reading["id"],
                    "nearby_reference_ids": [i["id"] for i in nearby],
                    "exact_reference_ids": [
                        i["id"]
                        for i in nearby
                        if coordinate_value(i["code"]) == coordinate_value(reading["text"])
                    ],
                    "negative_reference_ids": [i["id"] for i in nearby if i["kind"] == "negative"],
                }
            )
        # Keep all 139 records, including non-documentary strata, in the audit.
        rows = [
            {
                "id": i["id"],
                "base": literal_links(i, candidates),
                "auxiliary": literal_links(i, auxiliary),
            }
            for i in reference["items"]
        ]
        result["methods"][name] = {
            "operational": metrics,
            "rows": rows,
            "confirmations": len(confirmed),
            "known_incorrect_confirmations": sorted(bad & confirmed),
            "known_error_rate": len(bad & confirmed) / len(confirmed) if confirmed else None,
            "correct_confirmed_fields": len(correct & confirmed),
            "correct_confirmed_fields_coverage": len(correct & confirmed) / 29,
            "fully_verified_automatic_coverage": 0,
            "exact_project": 0,
            "core_review_ids": review,
            "core_review_rate": len(review) / 29,
            "all_proposals_review_rate": (
                sum(p["estado_revisao"] != "CONFIRMADA" for p in proposals) / len(proposals)
            )
            if proposals
            else None,
            "coordinate_reference_count": len(coordinate_refs),
            "base_auxiliary_reading_audit": reading_audit,
            "coordinate_literal_coverage": coordinate_coverage,
            "document_reference_count": len(documents),
            "auxiliary_readings_requiring_review": len(selected),
            "auxiliary_confirmations": 0,
            "auxiliary_confirmation_error_rate": None,
            "new_literal_reference_ids": [
                r["id"]
                for r in rows
                if r["auxiliary"]["exact_literal_candidates"]
                and not r["base"]["exact_literal_candidates"]
            ],
        }
    first, second = result["methods"]["vertical"], result["methods"]["combined"]
    # Same paired occurrence fields and decisions, not merely equal aggregate counts.
    result["core_unchanged"] = first["operational"] == second["operational"]
    result["new_confirmation_errors"] = sorted(
        set(second["known_incorrect_confirmations"]) - set(first["known_incorrect_confirmations"])
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--vertical", type=Path, required=True)
    parser.add_argument("--combined", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--neural-only", type=Path)
    args = parser.parse_args()
    if args.output.resolve() in {
        p.resolve() for p in (args.reference, args.vertical, args.combined)
    }:
        raise ValueError("Output cannot replace inputs")
    if args.neural_only and args.output.resolve() == args.neural_only.resolve():
        raise ValueError("Output cannot replace isolated input")
    inputs = [
        json.loads(path.read_text(encoding="utf-8-sig"))
        for path in (args.reference, args.vertical, args.combined)
    ]
    result = audit(
        inputs[0],
        inputs[1],
        inputs[2],
        neural_only=json.loads(args.neural_only.read_text(encoding="utf-8-sig"))
        if args.neural_only
        else None,
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "core_unchanged": result["core_unchanged"],
                "new_confirmation_errors": result["new_confirmation_errors"],
                "methods": {
                    k: {
                        key: value
                        for key, value in data.items()
                        if key not in ("rows", "operational", "base_auxiliary_reading_audit")
                    }
                    for k, data in result["methods"].items()
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
