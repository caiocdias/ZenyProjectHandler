"""Ataque a R-E06.3.2-5 na matriz E16: variante habilitada de tipo só do modelo."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from scripts.coverage_matrix_e16 import _package_digest, build
from scripts.curation_coverage_e16 import compare, read_matrix

from zeny_project_handler.adapters.analysis.declarative_symbols import GRAMATICAS_SO_MODELO

FAMILIA = "family-f02-03"
CLASSE = {
    "E04": "ATERRAMENTO",
    "E05": "TRANSFORMADOR",
    "E06": "ESTAI_MT",
    "E07": "POSTE",
}
CAMPOS_BASE = ["id", "family_id", "class_code", "owner_stage", "status", "possible_reference_ids"]


def _json(caminho: Path, valor: object) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(valor), encoding="utf-8")
    return caminho


def _montar(
    tmp_path: Path, donos: dict[str, str], reconhecimentos: dict[str, dict[str, Any]]
) -> tuple[Path, Path, Path, Path]:
    inventario = _json(
        tmp_path / "inventario.json",
        {
            "inventory_version": "teste",
            "families": [{"id": FAMILIA}],
            "variants": [
                {
                    "id": identidade,
                    "family_id": FAMILIA,
                    "class_code": CLASSE[dono],
                    "source_kind": "vector",
                    "owner_stage": dono,
                    "destination": "equipment_review",
                }
                for identidade, dono in donos.items()
            ],
        },
    )
    pacotes = tmp_path / "pacotes"
    _json(
        pacotes / f"{FAMILIA}.json",
        {
            "variants": [
                {"id": identidade, "recognition": reconhecimento}
                for identidade, reconhecimento in reconhecimentos.items()
            ]
        },
    )
    e07 = _json(
        tmp_path / "e07.json",
        {
            "complete_inference": True,
            "package_sha256": _package_digest(pacotes),
            "by_family": {},
            "decisions": [],
        },
    )
    base = tmp_path / "base.csv"
    with base.open("w", encoding="utf-8", newline="") as fluxo:
        escritor = csv.DictWriter(fluxo, fieldnames=CAMPOS_BASE)
        escritor.writeheader()
        for identidade, dono in donos.items():
            if dono in {"E05", "E06"}:
                escritor.writerow(
                    {
                        "id": identidade,
                        "family_id": FAMILIA,
                        "class_code": CLASSE[dono],
                        "owner_stage": dono,
                        "status": "ainda_nao_suportado",
                        "possible_reference_ids": "",
                    }
                )
    return inventario, pacotes, e07, base


def _haste(status: str = "enabled") -> dict[str, Any]:
    return {"status": status, "grammar": {"kind": "stem_bars"}, "reason": "gap"}


def _moldura() -> dict[str, Any]:
    return {"status": "enabled", "grammar": {"kind": "label_in_frame"}, "reason": "gap"}


def _construir(tmp_path: Path, donos: dict[str, str], rec: dict[str, dict[str, Any]]) -> Any:
    inventario, pacotes, e07, base = _montar(tmp_path, donos, rec)
    linhas, _ = build(inventario, pacotes, None, None, e07, base)
    return {linha["id"]: linha for linha in linhas}


def test_gramatica_so_modelo_inclui_stem_bars() -> None:
    assert "stem_bars" in GRAMATICAS_SO_MODELO


@pytest.mark.parametrize("dono", ["E04", "E05", "E06", "E07"])
def test_stem_bars_habilitada_fica_fora_do_dominio_em_todo_estagio(
    tmp_path: Path, dono: str
) -> None:
    por_id = _construir(
        tmp_path, {"haste": dono, "moldura": "E07"}, {"haste": _haste(), "moldura": _moldura()}
    )
    assert por_id["haste"]["package_status"] == "enabled"
    assert por_id["haste"]["declarative-vector-packages"] == "fora_do_dominio"
    assert por_id["moldura"]["declarative-vector-packages"] == "id_exato_sintetico"


@pytest.mark.parametrize("dono", ["E04", "E05", "E06", "E07"])
def test_stem_bars_pending_continua_pendente_sem_inferencia(tmp_path: Path, dono: str) -> None:
    por_id = _construir(tmp_path, {"haste": dono}, {"haste": _haste("pending")})
    assert por_id["haste"]["declarative-vector-packages"] == "pendente_sem_inferencia"


def test_pacote_pending_sem_gramatica_continua_pendente(tmp_path: Path) -> None:
    por_id = _construir(
        tmp_path, {"p": "E07"}, {"p": {"status": "pending", "reason": "sem gramática ainda"}}
    )
    assert por_id["p"]["declarative-vector-packages"] == "pendente_sem_inferencia"


def test_enabled_sem_gramatica_nao_quebra_e_nao_vira_so_modelo(tmp_path: Path) -> None:
    por_id = _construir(tmp_path, {"p": "E07"}, {"p": {"status": "enabled", "reason": "x"}})
    assert por_id["p"]["declarative-vector-packages"] == "id_exato_sintetico"


def test_so_modelo_nao_muda_o_status_de_evidencia_nem_os_outros_metodos(tmp_path: Path) -> None:
    com = _construir(tmp_path / "com", {"h": "E04"}, {"h": _haste()})
    sem = _construir(tmp_path / "sem", {"h": "E04"}, {"h": _haste("pending")})
    assert com["h"]["status"] == sem["h"]["status"] == "nao_avaliavel"
    diferem = {chave for chave in com["h"] if com["h"][chave] != sem["h"][chave]}
    assert diferem == {"package_status", "declarative-vector-packages"}


def test_matriz_gravada_com_so_modelo_e_lida_pelo_comparador(tmp_path: Path) -> None:
    antes = _construir(
        tmp_path / "a", {"h": "E04", "m": "E07"}, {"h": _haste("pending"), "m": _moldura()}
    )
    depois = _construir(tmp_path / "d", {"h": "E04", "m": "E07"}, {"h": _haste(), "m": _moldura()})
    caminhos = []
    for nome, linhas in (("antes", antes), ("depois", depois)):
        caminho = tmp_path / f"{nome}.csv"
        with caminho.open("w", encoding="utf-8", newline="") as fluxo:
            escritor = csv.DictWriter(fluxo, fieldnames=list(next(iter(linhas.values()))))
            escritor.writeheader()
            escritor.writerows(linhas.values())
        caminhos.append(caminho)
    lida_antes, lida_depois = read_matrix(caminhos[0]), read_matrix(caminhos[1])
    assert lida_depois["h"]["declarative-vector-packages"] == "fora_do_dominio"
    assert lida_antes["h"]["declarative-vector-packages"] == "pendente_sem_inferencia"
    resultado = compare(lida_antes, lida_depois)
    assert resultado["transitions"] == []
    assert resultado["lost_exact_ids"] == []
    assert resultado["net_exact_change"] == 0
