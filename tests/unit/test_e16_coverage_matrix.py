"""The published E16 matrix must account for every frozen E01 ID."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest
from scripts.coverage_matrix_e16 import _package_digest, build

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "docs" / "data"


def test_published_matrix_reconciles_the_frozen_inventory() -> None:
    inventory = json.loads((DATA / "inventario-simbologia-v1.json").read_text(encoding="utf-8"))
    summary = json.loads((DATA / "matriz-simbologia-e16-resumo.json").read_text(encoding="utf-8"))
    with (DATA / "matriz-simbologia-e16.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    expected = {variant["id"] for variant in inventory["variants"]}
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids)) == summary["denominator_ids"] == len(expected)
    assert set(ids) == expected
    assert {row["family_id"] for row in rows} == {family["id"] for family in inventory["families"]}
    assert Counter(row["status"] for row in rows) == summary["status_counts"]
    assert all(row["evidence"] for row in rows)
    assert all(
        row["status"] != "reconhecido_exato" for row in rows if row["package_status"] == "pending"
    )
    assert all(
        row["evidence_level"] == "synthetic_only"
        for row in rows
        if row["status"] == "reconhecido_exato"
    )
    assert {row["raster-template"] for row in rows if row["class_code"] == "PARA_RAIOS_BT"} == {
        "classe_sem_id"
    }
    assert {row["raster-template"] for row in rows if row["class_code"] == "TRANSFORMADOR"} == {
        "classe_sem_id"
    }


def test_matrix_rejects_stale_e07_evidence(tmp_path: Path) -> None:
    def write(path: Path, value: object) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    inventory = write(
        tmp_path / "inventory.json",
        {
            "inventory_version": "test",
            "families": [{"id": "family-f02-03"}],
            "variants": [
                {
                    "id": "variant-a",
                    "family_id": "family-f02-03",
                    "class_code": "POSTE",
                    "source_kind": "vector",
                    "owner_stage": "E07",
                    "destination": "operational",
                }
            ],
        },
    )
    packages = tmp_path / "packages"
    write(
        packages / "family-f02-03.json",
        {"variants": [{"id": "variant-a", "recognition": {"status": "enabled"}}]},
    )
    stage = write(
        tmp_path / "stage.json",
        {
            "methods": {
                "transformer-vector-shapes": {"matches": []},
                "guy-vector-shapes": {"matches": []},
            }
        },
    )
    e07 = write(
        tmp_path / "e07.json",
        {"complete_inference": True, "package_sha256": "stale", "by_family": {}, "decisions": []},
    )
    with pytest.raises(ValueError, match="current package checkpoint"):
        build(inventory, packages, stage, stage, e07)


def test_matrix_carries_unmodified_stage_evidence_without_local_reports(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.json"
    variants = [
        {
            "id": identity,
            "family_id": "family-f02-03",
            "class_code": class_code,
            "source_kind": "vector",
            "owner_stage": owner,
            "destination": "equipment_review",
        }
        for identity, class_code, owner in (
            ("transformer", "TRANSFORMADOR", "E05"),
            ("guy", "ESTAI_MT", "E06"),
            ("package", "POSTE", "E07"),
        )
    ]
    inventory.write_text(
        json.dumps(
            {
                "inventory_version": "test",
                "families": [{"id": "family-f02-03"}],
                "variants": variants,
            }
        ),
        encoding="utf-8",
    )
    packages = tmp_path / "packages"
    packages.mkdir()
    (packages / "family-f02-03.json").write_text(
        json.dumps(
            {"variants": [{"id": "package", "recognition": {"status": "pending", "reason": "gap"}}]}
        ),
        encoding="utf-8",
    )
    e07 = tmp_path / "e07.json"
    e07.write_text(
        json.dumps(
            {
                "complete_inference": True,
                "package_sha256": _package_digest(packages),
                "by_family": {},
                "decisions": [],
            }
        ),
        encoding="utf-8",
    )
    baseline = tmp_path / "before.csv"
    with baseline.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "id",
                "family_id",
                "class_code",
                "owner_stage",
                "status",
                "possible_reference_ids",
            ],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "id": "transformer",
                    "family_id": "family-f02-03",
                    "class_code": "TRANSFORMADOR",
                    "owner_stage": "E05",
                    "status": "reconhecido_exato",
                    "possible_reference_ids": "transformer",
                },
                {
                    "id": "guy",
                    "family_id": "family-f02-03",
                    "class_code": "ESTAI_MT",
                    "owner_stage": "E06",
                    "status": "alternativa_sem_id_resolvido",
                    "possible_reference_ids": "guy;another",
                },
            ]
        )
    rows, summary = build(inventory, packages, None, None, e07, baseline)
    assert [row["status"] for row in rows] == [
        "reconhecido_exato",
        "alternativa_sem_id_resolvido",
        "ainda_nao_suportado",
    ]
    assert summary["inputs_sha256"].keys() == {"inventory", "e07_report", "baseline_matrix"}
