from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import scripts.audit_symbol_packages as modulo
from scripts.audit_symbol_packages import audit, main

PROFILE = "perfil-sintetico"
OUTRO_PERFIL = "perfil-outro"
SOURCE = "F02"
FAMILIAS = {"E04": "fam-e04", "E05": "fam-e05", "E06": "fam-e06", "E07": "fam-e07"}


def _ref(identity: str, family: str, stage: str) -> dict[str, Any]:
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


def _item(ref: dict[str, Any], status: str = "enabled") -> dict[str, Any]:
    recognition: dict[str, Any] = {"status": status}
    if status == "pending":
        recognition["reason"] = "lacuna"
    else:
        recognition["grammar"] = {"kind": "sintetica"}
    return {
        "id": ref["id"],
        "class_code": ref["class_code"],
        "destination": ref["destination"],
        "source_ref": ref["source_refs"][0],
        "role": "operational",
        "recognition": recognition,
    }


def _montar(
    tmp_path: Path,
    *,
    ausentes: tuple[str, ...] = (),
    pendentes: tuple[str, ...] = (),
    extras_inventario: tuple[dict[str, Any], ...] = (),
    alterar: dict[str, dict[str, Any]] | None = None,
    alterar_inventario: dict[str, dict[str, Any]] | None = None,
    pacote: dict[str, dict[str, Any]] | None = None,
    pacotes_extras: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[Path, Path]:
    """Toda variante nao E10 empacotada (uma por familia), salvo as `ausentes`."""
    refs = [_ref(f"v-{s.lower()}", f, s) for s, f in FAMILIAS.items()]
    refs += list(extras_inventario)
    packaged_items = {
        ref["id"]: _item(ref, "pending" if ref["owner_stage"] in pendentes else "enabled")
        for ref in refs
    }
    for ref in refs:
        ref.update((alterar_inventario or {}).get(ref["id"], {}))
    inventory = {
        "inventory_version": "sintetico",
        "sources": [{"id": SOURCE}],
        "profiles": [{"id": PROFILE}, {"id": OUTRO_PERFIL}],
        "variants": refs,
    }
    inventory_path = tmp_path / "inventario.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    package_dir = tmp_path / "pacotes"
    package_dir.mkdir()
    for stage, family in FAMILIAS.items():
        if stage in ausentes:
            continue
        item = packaged_items[f"v-{stage.lower()}"]
        item.update((alterar or {}).get(item["id"], {}))
        body: dict[str, Any] = {
            "schema_version": 1,
            "family_id": family,
            "profile_id": PROFILE,
            "source_id": SOURCE,
            "variants": [item, *(pacotes_extras or {}).get(family, [])],
        }
        body.update((pacote or {}).get(family, {}))
        (package_dir / f"{family}.json").write_text(json.dumps(body), encoding="utf-8")
    return inventory_path, package_dir


@pytest.mark.parametrize("estagio", ["E04", "E05", "E06"])
@pytest.mark.parametrize(
    ("campo", "valor", "erro"),
    [
        ("class_code", "ERRADA", "class mismatch"),
        ("destination", "outro", "destination mismatch"),
        (
            "source_ref",
            {"source_id": SOURCE, "pdf_page": 9, "locator": "x"},
            "source locator mismatch",
        ),
        ("role", "informative", "role mismatch"),
    ],
    ids=["classe", "destino", "source_ref", "papel"],
)
def test_variante_de_outro_estagio_com_campo_divergente_acusa(
    tmp_path: Path, estagio: str, campo: str, valor: Any, erro: str
) -> None:
    identity = f"v-{estagio.lower()}"
    inventory, packages = _montar(tmp_path, alterar={identity: {campo: valor}})

    result = audit(inventory, packages)

    assert result["errors"] == [f"{identity}: {erro}"]


@pytest.mark.parametrize("estagio", ["E04", "E05", "E06"])
def test_variante_de_outro_estagio_em_perfil_divergente_acusa(tmp_path: Path, estagio: str) -> None:
    familia = FAMILIAS[estagio]
    inventory, packages = _montar(tmp_path, pacote={familia: {"profile_id": OUTRO_PERFIL}})

    result = audit(inventory, packages)

    assert result["errors"] == [f"v-{estagio.lower()}: profile mismatch"]


@pytest.mark.parametrize("estagio", ["E04", "E05", "E06"])
def test_variante_de_outro_estagio_em_familia_divergente_acusa(
    tmp_path: Path, estagio: str
) -> None:
    identity = f"v-{estagio.lower()}"
    inventory, packages = _montar(tmp_path, alterar_inventario={identity: {"family_id": "outra"}})

    result = audit(inventory, packages)

    assert result["errors"] == [f"{identity}: family mismatch"]


def test_variante_de_outro_estagio_enabled_sem_gramatica_acusa(tmp_path: Path) -> None:
    inventory, packages = _montar(
        tmp_path, alterar={"v-e05": {"recognition": {"status": "enabled"}}}
    )

    assert audit(inventory, packages)["errors"] == ["v-e05: enabled without grammar"]


def test_variante_de_outro_estagio_pending_sem_motivo_acusa(tmp_path: Path) -> None:
    inventory, packages = _montar(
        tmp_path, alterar={"v-e05": {"recognition": {"status": "pending"}}}
    )

    assert audit(inventory, packages)["errors"] == ["v-e05: pending without reason"]


def test_variante_fora_do_inventario_acusa_em_pacote_de_outro_estagio(tmp_path: Path) -> None:
    intrusa = _item(_ref("v-fantasma", "fam-e05", "E05"))
    inventory, packages = _montar(tmp_path, pacotes_extras={"fam-e05": [intrusa]})

    result = audit(inventory, packages)

    assert result["errors"] == ["unexpected variant: v-fantasma"]


def test_variante_e10_do_inventario_empacotada_acusa_e_nao_entra_no_relato(
    tmp_path: Path,
) -> None:
    ref_e10 = _ref("v-e10", "fam-e10", "E10")
    inventory, packages = _montar(
        tmp_path,
        extras_inventario=(ref_e10,),
        pacotes_extras={"fam-e05": [_item(ref_e10)]},
    )

    result = audit(inventory, packages)

    assert result["errors"] == ["unexpected variant: v-e10"]
    assert "E10" not in result["by_owner_stage"]
    assert result["complete_recognition"] is False


def test_variante_duplicada_entre_pacotes_de_estagios_diferentes_acusa(tmp_path: Path) -> None:
    copia = _item(_ref("v-e05", "fam-e05", "E05"))
    inventory, packages = _montar(tmp_path, pacotes_extras={"fam-e06": [copia]})

    result = audit(inventory, packages)

    assert "duplicate variant: v-e05" in result["errors"]
    assert result["complete_recognition"] is False


def test_variante_duplicada_no_mesmo_pacote_acusa(tmp_path: Path) -> None:
    copia = _item(_ref("v-e06", "fam-e06", "E06"))
    inventory, packages = _montar(tmp_path, pacotes_extras={"fam-e06": [copia]})

    assert "duplicate variant: v-e06" in audit(inventory, packages)["errors"]


def test_by_owner_stage_fecha_com_o_total_empacotado_e_enabled_mais_pending(
    tmp_path: Path,
) -> None:
    inventory, packages = _montar(tmp_path, pendentes=("E05", "E07"), ausentes=("E06",))

    result = audit(inventory, packages)

    por_estagio = result["by_owner_stage"]
    assert result["errors"] == ["missing variant: v-e06", "missing family: fam-e06"]
    assert sum(item["packaged"] for item in por_estagio.values()) == result["package_variants"]
    assert sum(item["enabled"] for item in por_estagio.values()) == result["enabled"]
    assert sum(item["pending"] for item in por_estagio.values()) == result["pending"]
    for item in por_estagio.values():
        assert item["enabled"] + item["pending"] == item["packaged"]
    assert por_estagio["E06"] == {"expected": 1, "packaged": 0, "enabled": 0, "pending": 0}
    assert por_estagio["E05"] == {"expected": 1, "packaged": 1, "enabled": 0, "pending": 1}
    assert por_estagio["E04"] == {"expected": 1, "packaged": 1, "enabled": 1, "pending": 0}


def test_by_owner_stage_conta_expected_de_todas_as_variantes_do_estagio(tmp_path: Path) -> None:
    segunda = _ref("v-e05-b", "fam-e05", "E05")
    inventory, packages = _montar(tmp_path, extras_inventario=(segunda,))

    result = audit(inventory, packages)

    assert result["by_owner_stage"]["E05"] == {
        "expected": 2,
        "packaged": 1,
        "enabled": 1,
        "pending": 0,
    }
    assert result["errors"] == ["missing variant: v-e05-b"]


def test_complete_recognition_verdadeiro_com_todas_as_nao_e10_habilitadas(
    tmp_path: Path,
) -> None:
    inventory, packages = _montar(tmp_path)

    assert audit(inventory, packages)["complete_recognition"] is True


def test_complete_recognition_falso_com_variante_de_outro_estagio_pendente(
    tmp_path: Path,
) -> None:
    inventory, packages = _montar(tmp_path, pendentes=("E04",))

    result = audit(inventory, packages)

    assert result["errors"] == []
    assert result["complete_recognition"] is False


def test_complete_recognition_falso_com_variante_de_outro_estagio_nao_empacotada(
    tmp_path: Path,
) -> None:
    inventory, packages = _montar(tmp_path, ausentes=("E06",))

    result = audit(inventory, packages)

    assert result["errors"] == ["missing variant: v-e06", "missing family: fam-e06"]
    assert result["complete_recognition"] is False


def test_complete_recognition_falso_com_variante_nao_e10_so_no_inventario(
    tmp_path: Path,
) -> None:
    inventory, packages = _montar(tmp_path, extras_inventario=(_ref("v-e06-b", "fam-e06", "E06"),))

    assert audit(inventory, packages)["complete_recognition"] is False


def test_complete_recognition_ignora_variantes_e10_do_inventario(tmp_path: Path) -> None:
    inventory, packages = _montar(tmp_path, extras_inventario=(_ref("v-e10", "fam-e10", "E10"),))

    assert audit(inventory, packages)["complete_recognition"] is True


def test_complete_recognition_falso_se_ha_erro(tmp_path: Path) -> None:
    inventory, packages = _montar(tmp_path, alterar={"v-e04": {"class_code": "X"}})

    assert audit(inventory, packages)["complete_recognition"] is False


def test_e07_ausente_continua_acusando_variante_e_familia(tmp_path: Path) -> None:
    inventory, packages = _montar(tmp_path, ausentes=("E07",))

    result = audit(inventory, packages)

    assert result["errors"] == ["missing variant: v-e07", "missing family: fam-e07"]
    assert result["expected_variants"] == 4
    assert result["expected_families"] == 4


def test_ausencia_de_e04_a_e06_acusa_variante_e_familia_como_a_e07(tmp_path: Path) -> None:
    inventory, packages = _montar(tmp_path, ausentes=("E04", "E05", "E06"))

    result = audit(inventory, packages)

    assert result["errors"] == [
        "missing variant: v-e04",
        "missing variant: v-e05",
        "missing variant: v-e06",
        "missing family: fam-e04",
        "missing family: fam-e05",
        "missing family: fam-e06",
    ]
    assert result["expected_variants"] == 4


def test_expected_variants_e_families_contam_todas_as_nao_e10(tmp_path: Path) -> None:
    inventory, packages = _montar(tmp_path)

    result = audit(inventory, packages)

    assert result["expected_variants"] == 4
    assert result["expected_families"] == 4
    assert result["package_variants"] == 4
    assert result["package_families"] == 4


def _apontar_cli(monkeypatch: pytest.MonkeyPatch, inventory: Path, packages: Path) -> None:
    original = modulo.audit
    monkeypatch.setattr(modulo, "audit", lambda **kw: original(inventory, packages, **kw))


def test_cli_require_complete_falha_com_variante_de_outro_estagio_pendente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    inventory, packages = _montar(tmp_path, pendentes=("E06",))
    _apontar_cli(monkeypatch, inventory, packages)

    assert main([]) == 0
    assert main(["--require-complete"]) == 1
    saida = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert saida["by_owner_stage"]["E06"]["pending"] == 1
    assert saida["complete_recognition"] is False


def test_cli_require_complete_passa_com_tudo_habilitado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory, packages = _montar(tmp_path)
    _apontar_cli(monkeypatch, inventory, packages)

    assert main(["--require-complete"]) == 0


def test_cli_retorna_erro_para_divergencia_de_outro_estagio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory, packages = _montar(tmp_path, alterar={"v-e05": {"class_code": "X"}})
    _apontar_cli(monkeypatch, inventory, packages)

    assert main([]) == 1
