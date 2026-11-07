from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.audit_symbol_packages import audit

PROFILE = "perfil-sintetico"
SOURCE = "F02"


def _variante_inventario(identity: str, family: str, stage: str) -> dict[str, Any]:
    return {
        "id": identity,
        "family_id": family,
        "profile_id": PROFILE,
        "class_code": f"CLASSE_{stage}",
        "function": "asset",
        "owner_stage": stage,
        "destination": "asset",
        "source_refs": [{"source_id": SOURCE, "pdf_page": 1, "locator": identity}],
    }


def _variante_pacote(reference: dict[str, Any], *, status: str = "pending") -> dict[str, Any]:
    recognition: dict[str, Any] = {"status": status}
    if status == "pending":
        recognition["reason"] = "lacuna tecnica"
    else:
        recognition["grammar"] = {"kind": "sintetica"}
    return {
        "id": reference["id"],
        "class_code": reference["class_code"],
        "destination": reference["destination"],
        "source_ref": reference["source_refs"][0],
        "role": "operational",
        "recognition": recognition,
    }


ESTAGIOS = {"E07": "family-a", "E05": "family-b", "E06": "family-c", "E10": "family-d"}


def _montar(
    tmp_path: Path,
    *,
    empacotar: tuple[str, ...] = ("E07", "E05", "E06"),
    habilitadas: tuple[str, ...] = (),
    alterar: dict[str, dict[str, Any]] | None = None,
) -> tuple[Path, Path]:
    variantes = [
        _variante_inventario(f"v-{stage.lower()}", family, stage)
        for stage, family in ESTAGIOS.items()
    ]
    inventory = {
        "inventory_version": "sintetico",
        "sources": [{"id": SOURCE}],
        "profiles": [{"id": PROFILE}],
        "variants": variantes,
    }
    inventory_path = tmp_path / "inventario.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    package_dir = tmp_path / "pacotes"
    package_dir.mkdir()
    for reference in variantes:
        stage = reference["owner_stage"]
        if stage not in empacotar:
            continue
        item = _variante_pacote(reference, status="enabled" if stage in habilitadas else "pending")
        item.update((alterar or {}).get(reference["id"], {}))
        family = reference["family_id"]
        package = {
            "schema_version": 1,
            "family_id": family,
            "profile_id": PROFILE,
            "source_id": SOURCE,
            "variants": [item],
        }
        (package_dir / f"{family}.json").write_text(json.dumps(package), encoding="utf-8")
    return inventory_path, package_dir


def test_variante_de_outro_estagio_empacotada_e_aceita(tmp_path: Path) -> None:
    inventory, packages = _montar(tmp_path)

    result = audit(inventory, packages)

    assert result["errors"] == []
    assert result["package_variants"] == 3


def test_variante_de_outro_estagio_divergente_acusa(tmp_path: Path) -> None:
    inventory, packages = _montar(tmp_path, alterar={"v-e06": {"class_code": "ERRADA"}})

    result = audit(inventory, packages)

    assert result["errors"] == ["v-e06: class mismatch"]


def test_familia_e10_nao_e_aceita(tmp_path: Path) -> None:
    inventory, packages = _montar(tmp_path, empacotar=("E07", "E05", "E06", "E10"))

    result = audit(inventory, packages)

    assert result["errors"] == ["unexpected variant: v-e10"]


def test_variantes_e07_e_e06_ausentes_acusam_e_a_empacotada_nao(tmp_path: Path) -> None:
    inventory, packages = _montar(tmp_path, empacotar=("E05",))

    result = audit(inventory, packages)

    assert "missing variant: v-e07" in result["errors"]
    assert "missing variant: v-e06" in result["errors"]
    assert "missing variant: v-e05" not in result["errors"]


def test_relato_por_estagio(tmp_path: Path) -> None:
    inventory, packages = _montar(tmp_path, habilitadas=("E05",))

    result = audit(inventory, packages)

    assert result["by_owner_stage"] == {
        "E05": {"expected": 1, "packaged": 1, "enabled": 1, "pending": 0},
        "E06": {"expected": 1, "packaged": 1, "enabled": 0, "pending": 1},
        "E07": {"expected": 1, "packaged": 1, "enabled": 0, "pending": 1},
    }
