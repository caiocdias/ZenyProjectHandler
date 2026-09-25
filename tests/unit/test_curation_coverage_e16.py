"""Curation feedback must report real matrix transitions without inventing acceptance."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from scripts.curation_coverage_e16 import compare, plan, read_demand, read_matrix


def _matrix(path: Path, rows: list[tuple[str, str, str]]) -> dict[str, dict[str, str]]:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "id",
                "family_id",
                "class_code",
                "owner_stage",
                "status",
                "package_status",
            ],
        )
        writer.writeheader()
        for identity, status, package_status in rows:
            writer.writerow(
                {
                    "id": identity,
                    "family_id": "family-f02-03",
                    "class_code": "POSTE",
                    "owner_stage": "E07",
                    "status": status,
                    "package_status": package_status,
                }
            )
    return read_matrix(path)


def test_plan_prioritizes_review_demand_and_compare_records_regression(tmp_path: Path) -> None:
    before = _matrix(
        tmp_path / "before.csv",
        [
            ("a", "ainda_nao_suportado", "pending"),
            ("b", "alternativa_sem_id_resolvido", "enabled"),
            ("c", "reconhecido_exato", "enabled"),
        ],
    )
    demand = tmp_path / "demand.json"
    demand.write_text(json.dumps({"ids": ["c", "b"]}), encoding="utf-8")
    work = plan(before, read_demand(demand, before))
    assert work["denominator_ids"] == 3
    assert work["gap_ids"] == 2
    assert [item["id"] for item in work["targets"]] == ["b", "c", "a"]
    assert work["targets"][1]["demanded_by_review"] is True

    after = _matrix(
        tmp_path / "after.csv",
        [
            ("a", "reconhecido_exato", "enabled"),
            ("b", "alternativa_sem_id_resolvido", "enabled"),
            ("c", "ainda_nao_suportado", "enabled"),
        ],
    )
    delta = compare(before, after)
    assert delta["newly_exact_ids"] == ["a"]
    assert delta["lost_exact_ids"] == ["c"]
    assert delta["net_exact_change"] == 0
    assert delta["before_gap_ids"] == delta["after_gap_ids"] == 2


def test_pending_cannot_be_exact_or_disappear(tmp_path: Path) -> None:
    before = _matrix(tmp_path / "before.csv", [("a", "ainda_nao_suportado", "pending")])
    with pytest.raises(ValueError, match="pending package"):
        _matrix(tmp_path / "invalid.csv", [("a", "reconhecido_exato", "pending")])
    with pytest.raises(ValueError, match="disappeared"):
        compare(before, _matrix(tmp_path / "after.csv", [("b", "informativo", "pending")]))


def test_inventory_growth_is_visible_in_denominator_and_exact_delta(tmp_path: Path) -> None:
    before = _matrix(tmp_path / "before.csv", [("a", "informativo", "pending")])
    after = _matrix(
        tmp_path / "after.csv",
        [("a", "informativo", "pending"), ("b", "reconhecido_exato", "enabled")],
    )
    delta = compare(before, after)
    assert delta["before_denominator_ids"] == 1
    assert delta["after_denominator_ids"] == 2
    assert delta["added_ids"] == delta["newly_exact_ids"] == ["b"]
    assert delta["net_exact_change"] == 1


def test_review_demand_rejects_unknown_inventory_id(tmp_path: Path) -> None:
    rows = _matrix(tmp_path / "matrix.csv", [("a", "ainda_nao_suportado", "pending")])
    demand = tmp_path / "demand.json"
    demand.write_text('{"ids": ["unknown"]}', encoding="utf-8")
    with pytest.raises(ValueError, match="outside E01"):
        read_demand(demand, rows)
