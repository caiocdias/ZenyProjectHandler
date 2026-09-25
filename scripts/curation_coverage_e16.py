"""Plan an E07 curation round from E16 gaps and compare its coverage checkpoints.

This reads coverage evidence only. It does not label PDFs, enable packages, or
grant E07/E16 acceptance. Keep outputs under the local curation run directory.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any

from scripts.coverage_matrix_e16 import STATUS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "docs/data/matriz-simbologia-e16.csv"
GAP_STATES = {"alternativa_sem_id_resolvido", "ainda_nao_suportado", "nao_avaliavel"}
ROUTES = {
    "E04": "ID/classe: evidência discriminante e contrato do detector legado",
    "E05": "transformador: detector, contexto e positivos/negativos independentes",
    "E06": "estai: detector, contexto e positivos/negativos independentes",
    "E07": "pacote declarativo e fixture autoral da família",
    "E10": "convenção documental: revisar papel informativo, sem promover ativo",
}


def read_matrix(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"empty coverage matrix: {path}")
    required = {"id", "family_id", "class_code", "owner_stage", "status", "package_status"}
    if not required <= rows[0].keys():
        raise ValueError(f"missing coverage matrix columns: {sorted(required - rows[0].keys())}")
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        identity = row["id"]
        if not identity or identity in indexed:
            raise ValueError(f"blank or duplicate coverage ID: {identity}")
        if row["status"] not in STATUS:
            raise ValueError(f"invalid coverage status for {identity}: {row['status']}")
        if row["owner_stage"] not in ROUTES:
            raise ValueError(f"unknown owner for {identity}: {row['owner_stage']}")
        if row["package_status"] == "pending" and row["status"] == "reconhecido_exato":
            raise ValueError(f"pending package counted as exact recognition: {identity}")
        indexed[identity] = row
    return indexed


def read_demand(path: Path | None, rows: dict[str, dict[str, str]]) -> set[str]:
    if path is None:
        return set()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("ids"), list):
        raise ValueError("demand must be an object with an ids array")
    ids = value["ids"]
    if any(not isinstance(item, str) for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("demand IDs must be unique strings")
    missing = sorted(set(ids) - set(rows))
    if missing:
        raise ValueError(f"demand IDs outside E01 inventory: {missing}")
    return set(ids)


def plan(rows: dict[str, dict[str, str]], demand_ids: set[str]) -> dict[str, Any]:
    targets = []
    for identity, row in rows.items():
        if row["status"] not in GAP_STATES and identity not in demand_ids:
            continue
        targets.append(
            {
                "id": identity,
                "family_id": row["family_id"],
                "class_code": row["class_code"],
                "owner_stage": row["owner_stage"],
                "current_status": row["status"],
                "demanded_by_review": identity in demand_ids,
                "route": ROUTES[row["owner_stage"]],
            }
        )
    targets.sort(
        key=lambda item: (
            not item["demanded_by_review"],
            item["family_id"],
            item["id"],
        )
    )
    counts = Counter(row["status"] for row in rows.values())
    return {
        "denominator_ids": len(rows),
        "status_counts": {status: counts[status] for status in STATUS},
        "gap_ids": sum(counts[status] for status in GAP_STATES),
        "demand_ids": sorted(demand_ids),
        "targets": targets,
        "limits": [
            "Targets are work candidates, not recognized IDs or labels for a detector.",
            "Only reviewed evidence and passing independent gates may change coverage.",
        ],
    }


def compare(before: dict[str, dict[str, str]], after: dict[str, dict[str, str]]) -> dict[str, Any]:
    removed = sorted(set(before) - set(after))
    if removed:
        raise ValueError(f"frozen E01 IDs disappeared from coverage: {removed}")
    transitions = [
        {"id": identity, "from": before[identity]["status"], "to": after[identity]["status"]}
        for identity in sorted(set(before) & set(after))
        if before[identity]["status"] != after[identity]["status"]
    ]
    before_counts = Counter(row["status"] for row in before.values())
    after_counts = Counter(row["status"] for row in after.values())
    added = sorted(set(after) - set(before))
    newly_exact = [item["id"] for item in transitions if item["to"] == "reconhecido_exato"]
    newly_exact.extend(
        identity for identity in added if after[identity]["status"] == "reconhecido_exato"
    )
    lost_exact = [item["id"] for item in transitions if item["from"] == "reconhecido_exato"]
    return {
        "before_denominator_ids": len(before),
        "after_denominator_ids": len(after),
        "added_ids": added,
        "before_status_counts": {status: before_counts[status] for status in STATUS},
        "after_status_counts": {status: after_counts[status] for status in STATUS},
        "transitions": transitions,
        "newly_exact_ids": newly_exact,
        "lost_exact_ids": lost_exact,
        "net_exact_change": after_counts["reconhecido_exato"] - before_counts["reconhecido_exato"],
        "before_gap_ids": sum(before_counts[status] for status in GAP_STATES),
        "after_gap_ids": sum(after_counts[status] for status in GAP_STATES),
        "limits": [
            "A matrix transition is catalogue coverage evidence, not real-world recall.",
            "FP/FN, exclusive hits, UI/exports, and E16 reserve gates require separate reports.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    plan_parser.add_argument("--demand", type=Path)
    plan_parser.add_argument("--output", type=Path, required=True)
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--before", type=Path, required=True)
    compare_parser.add_argument("--after", type=Path, required=True)
    compare_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "plan":
        rows = read_matrix(args.matrix)
        result = plan(rows, read_demand(args.demand, rows))
        result["matrix_sha256"] = sha256(args.matrix.read_bytes()).hexdigest()
    else:
        result = compare(read_matrix(args.before), read_matrix(args.after))
        result["before_sha256"] = sha256(args.before.read_bytes()).hexdigest()
        result["after_sha256"] = sha256(args.after.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    headline = {"gap_ids", "net_exact_change", "after_gap_ids", "denominator_ids"}
    print(json.dumps({key: result[key] for key in result if key in headline}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
