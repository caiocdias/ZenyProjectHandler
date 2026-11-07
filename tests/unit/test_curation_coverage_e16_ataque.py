"""Ataque ao contrato matriz E16 x comparador da curadoria com pacote pending de outro estagio."""

from __future__ import annotations

import csv
import json
from itertools import product
from pathlib import Path

import pytest
from scripts.coverage_matrix_e16 import STATUS, _package_digest, build
from scripts.curation_coverage_e16 import ROUTES, compare, main, read_matrix

FAMILY = "family-f02-03"
CLASS_BY_OWNER = {
    "E04": "ATERRAMENTO",
    "E05": "TRANSFORMADOR",
    "E06": "ESTAI_MT",
    "E07": "POSTE",
    "E10": "POSTE",
}
BASELINE_FIELDS = [
    "id",
    "family_id",
    "class_code",
    "owner_stage",
    "status",
    "possible_reference_ids",
]


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _min_matrix(path: Path, status: str, package_status: str, owner: str) -> Path:
    return _csv(
        path,
        [
            {
                "id": "x",
                "family_id": FAMILY,
                "class_code": "POSTE",
                "owner_stage": owner,
                "status": status,
                "package_status": package_status,
            }
        ],
        ["id", "family_id", "class_code", "owner_stage", "status", "package_status"],
    )


@pytest.mark.parametrize(
    ("status", "package_status", "owner"),
    list(
        product(
            STATUS, ("pending", "enabled", "nao_aplicavel"), ("E04", "E05", "E06", "E07", "E10")
        )
    ),
)
def test_predicado_so_recusa_e07_pending_exata(
    tmp_path: Path, status: str, package_status: str, owner: str
) -> None:
    path = _min_matrix(tmp_path / "m.csv", status, package_status, owner)
    refused = status == "reconhecido_exato" and package_status == "pending" and owner == "E07"
    if refused:
        with pytest.raises(ValueError, match="pending package counted as exact recognition: x"):
            read_matrix(path)
    else:
        assert read_matrix(path)["x"]["status"] == status


def _inputs(
    tmp_path: Path,
    owners: dict[str, str],
    packaged: dict[str, str],
    decisions: list[dict[str, object]] | None = None,
) -> tuple[Path, Path, Path]:
    inventory = _write_json(
        tmp_path / "inventory.json",
        {
            "inventory_version": "test",
            "families": [{"id": FAMILY}],
            "variants": [
                {
                    "id": identity,
                    "family_id": FAMILY,
                    "class_code": CLASS_BY_OWNER[owner],
                    "source_kind": "vector",
                    "owner_stage": owner,
                    "destination": "equipment_review",
                }
                for identity, owner in owners.items()
            ],
        },
    )
    packages = tmp_path / "packages"
    _write_json(
        packages / f"{FAMILY}.json",
        {
            "variants": [
                {"id": identity, "recognition": {"status": status, "reason": "gap"}}
                for identity, status in packaged.items()
            ]
        },
    )
    e07 = _write_json(
        tmp_path / "e07.json",
        {
            "complete_inference": True,
            "package_sha256": _package_digest(packages),
            "by_family": {},
            "decisions": decisions or [],
        },
    )
    return inventory, packages, e07


def _baseline(tmp_path: Path, statuses: dict[str, tuple[str, str]]) -> Path:
    return _csv(
        tmp_path / "baseline.csv",
        [
            {
                "id": identity,
                "family_id": FAMILY,
                "class_code": CLASS_BY_OWNER[owner],
                "owner_stage": owner,
                "status": status,
                "possible_reference_ids": identity,
            }
            for identity, (owner, status) in statuses.items()
        ],
        BASELINE_FIELDS,
    )


def _dump(path: Path, rows: list[dict[str, str]]) -> Path:
    return _csv(path, rows, list(rows[0]))


@pytest.mark.parametrize("owner", ["E05", "E06"])
@pytest.mark.parametrize("package_status", ["pending", "enabled"])
def test_conjunto_de_pacotes_aceita_estagio_nao_e07_nem_e10(
    tmp_path: Path, owner: str, package_status: str
) -> None:
    inventory, packages, e07 = _inputs(
        tmp_path,
        {"other": owner, "package": "E07"},
        {"other": package_status, "package": "pending"},
    )
    baseline = _baseline(tmp_path, {"other": (owner, "alternativa_sem_id_resolvido")})
    rows, _ = build(inventory, packages, None, None, e07, baseline)
    other = rows[0]
    assert other["package_status"] == package_status
    expected = "id_exato_sintetico" if package_status == "enabled" else "pendente_sem_inferencia"
    assert other["declarative-vector-packages"] == expected


def test_pacote_enabled_de_outro_estagio_nao_muda_o_status_da_evidencia(tmp_path: Path) -> None:
    inventory, packages, e07 = _inputs(
        tmp_path,
        {"transformer": "E05", "guy": "E06", "package": "E07"},
        {"transformer": "enabled", "guy": "enabled", "package": "pending"},
    )
    baseline = _baseline(
        tmp_path,
        {
            "transformer": ("E05", "alternativa_sem_id_resolvido"),
            "guy": ("E06", "ainda_nao_suportado"),
        },
    )
    rows, _ = build(inventory, packages, None, None, e07, baseline)
    by_id = {row["id"]: row for row in rows}
    assert by_id["transformer"]["status"] == "alternativa_sem_id_resolvido"
    assert by_id["transformer"]["declarative-vector-packages"] == "id_exato_sintetico"
    assert by_id["transformer"]["evidence_level"] == "documented"
    assert by_id["guy"]["status"] == "ainda_nao_suportado"
    assert by_id["guy"]["declarative-vector-packages"] == "id_exato_sintetico"


def test_e10_recusa_mesmo_quando_ha_variante_fora_do_inventario(tmp_path: Path) -> None:
    inventory, packages, e07 = _inputs(
        tmp_path,
        {"package": "E07", "legend": "E10"},
        {"package": "pending", "legend": "pending", "stranger": "pending"},
    )
    with pytest.raises(ValueError, match=r"outside E01 inventory|must not be packaged"):
        build(inventory, packages, None, None, e07, None)


def test_e07_pending_nunca_sai_exata_do_build_mesmo_com_decisao_positiva(tmp_path: Path) -> None:
    decisions: list[dict[str, object]] = [
        {"variant_id": "package", "stratum": "positive", "tp": ["package"], "fp": [], "fn": []}
    ]
    inventory, packages, e07 = _inputs(
        tmp_path, {"package": "E07"}, {"package": "pending"}, decisions=decisions
    )
    rows, _ = build(inventory, packages, None, None, e07, None)
    assert rows[0]["status"] == "ainda_nao_suportado"
    assert read_matrix(_dump(tmp_path / "m.csv", rows))["package"]["status"] != "reconhecido_exato"


def _doze_e05(tmp_path: Path) -> tuple[Path, Path, Path, Path, list[str]]:
    ids = [f"transformer-{n:02d}" for n in range(12)]
    owners = dict.fromkeys(ids, "E05") | {"package": "E07"}
    inventory, packages, e07 = _inputs(
        tmp_path, owners, dict.fromkeys(ids, "pending") | {"package": "pending"}
    )
    baseline = _baseline(tmp_path, dict.fromkeys(ids, ("E05", "reconhecido_exato")))
    return inventory, packages, e07, baseline, ids


def test_doze_e05_exatas_com_pacote_pending_ponta_a_ponta_contra_matriz_sem_pacote(
    tmp_path: Path,
) -> None:
    inventory, packages, e07, baseline, ids = _doze_e05(tmp_path)
    after_rows, summary = build(inventory, packages, None, None, e07, baseline)
    assert summary["status_counts"]["reconhecido_exato"] == 12

    # Matriz anterior: as mesmas 12 IDs, mas sem pacote (nao_aplicavel).
    old_inventory, old_packages, old_e07 = _inputs(
        tmp_path / "old", dict.fromkeys(ids, "E05") | {"package": "E07"}, {"package": "pending"}
    )
    before_rows, _ = build(old_inventory, old_packages, None, None, old_e07, baseline)
    assert {r["package_status"] for r in before_rows if r["id"] in ids} == {"nao_aplicavel"}

    before = read_matrix(_dump(tmp_path / "before.csv", before_rows))
    after = read_matrix(_dump(tmp_path / "after.csv", after_rows))
    assert {after[i]["package_status"] for i in ids} == {"pending"}
    delta = compare(before, after)
    assert delta["transitions"] == []
    assert delta["lost_exact_ids"] == []
    assert delta["newly_exact_ids"] == []
    assert delta["added_ids"] == []
    assert delta["net_exact_change"] == 0
    assert delta["before_status_counts"] == delta["after_status_counts"]
    assert delta["before_gap_ids"] == delta["after_gap_ids"]
    reverse = compare(after, before)
    assert reverse["lost_exact_ids"] == []
    assert reverse["transitions"] == []


def test_compare_via_cli_com_matrizes_geradas(tmp_path: Path) -> None:
    inventory, packages, e07, baseline, _ = _doze_e05(tmp_path)
    rows, _ = build(inventory, packages, None, None, e07, baseline)
    matrix = _dump(tmp_path / "m.csv", rows)
    out = tmp_path / "out" / "delta.json"
    argv = ["compare", "--before", str(matrix), "--after", str(matrix), "--output", str(out)]
    assert main(argv) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["lost_exact_ids"] == []
    assert result["net_exact_change"] == 0
    assert main(["plan", "--matrix", str(matrix), "--output", str(tmp_path / "plan.json")]) == 0


def test_perda_real_de_exata_continua_sendo_apontada_com_pacote_pending(tmp_path: Path) -> None:
    before = read_matrix(
        _min_matrix(tmp_path / "b.csv", "reconhecido_exato", "nao_aplicavel", "E05")
    )
    after = read_matrix(_min_matrix(tmp_path / "a.csv", "ainda_nao_suportado", "pending", "E05"))
    delta = compare(before, after)
    assert delta["lost_exact_ids"] == ["x"]
    assert delta["net_exact_change"] == -1


def test_rotas_cobrem_todos_os_estagios_do_predicado() -> None:
    assert {"E04", "E05", "E06", "E07", "E10"} <= set(ROUTES)


def test_matriz_historica_publicada_mantem_a_regra_forte() -> None:
    root = Path(__file__).resolve().parents[2] / "docs" / "data"
    matrix = read_matrix(root / "matriz-simbologia-e16.csv")
    assert all(
        row["status"] != "reconhecido_exato"
        for row in matrix.values()
        if row["package_status"] == "pending"
    )
