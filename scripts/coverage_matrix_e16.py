"""Reconcile every frozen E01 ID with E16 evidence, without equating support to recognition.

The stage benchmarks are author-owned development controls. A curation round
may inherit unchanged E05/E06 ID evidence from its prior matrix and must use a
fresh E07 report signed by the current packages. No private PDF, reserve label,
or reviewer annotation is an input to this matrix.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
Record = dict[str, Any]
STATUS = (
    "reconhecido_exato",
    "alternativa_sem_id_resolvido",
    "informativo",
    "ainda_nao_suportado",
    "nao_avaliavel",
)
METHODS = (
    "legacy-vector-symbols",
    "transformer-vector-shapes",
    "guy-vector-shapes",
    "declarative-vector-packages",
    "raster-template",
    "raster-hough-generalizado",
    "structural-raster-graph",
    "structural-vector-graph",
    "document-local-legend",
    "learned-e11",
)


def _load(path: Path) -> Record:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _stage_matches(path: Path, method: str) -> dict[str, tuple[str, list[str]]]:
    matches = _load(path)["methods"][method]["matches"]
    found: dict[str, tuple[str, list[str]]] = {}
    for match in matches:
        reference = match["reference"]
        variant_id = reference.get("variant_id") or next(
            (item for item in reference["strata"] if item.startswith("cemig-eo-r3-")), None
        )
        if not variant_id:
            continue
        possible = json.loads(match["prediction"]["provenance"]["possible_references"])
        if variant_id in possible:
            state = (
                "reconhecido_exato" if possible == [variant_id] else "alternativa_sem_id_resolvido"
            )
        else:
            state = "ainda_nao_suportado"
        found[variant_id] = state, possible
    return found


def _baseline_rows(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        identity = row["id"]
        if not identity or identity in indexed:
            raise ValueError(f"blank or duplicate baseline ID: {identity}")
        indexed[identity] = row
    return indexed


def _packages(directory: Path) -> dict[str, Record]:
    result: dict[str, Record] = {}
    for path in sorted(directory.glob("family-*.json")):
        for variant in _load(path)["variants"]:
            if variant["id"] in result:
                raise ValueError(f"duplicate package ID: {variant['id']}")
            result[variant["id"]] = variant
    return result


def _package_digest(directory: Path) -> str:
    """Use the same canonical package snapshot signed by the E07 benchmark."""
    packages = [_load(path) for path in sorted(directory.glob("*.json"))]
    canonical = json.dumps(packages, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    return sha256((canonical + "\n").encode("utf-8")).hexdigest()


def _method_states(row: Record, package: Record | None) -> dict[str, str]:
    state = dict.fromkeys(METHODS, "fora_do_dominio")
    owner = row["owner_stage"]
    status = row["status"]
    if owner == "E04":
        state["legacy-vector-symbols"] = "classe_sem_id"
        if row["class_code"] in {"ATERRAMENTO", "PARA_RAIOS_MT", "PARA_RAIOS_BT"}:
            state["raster-template"] = "classe_sem_id"
            state["raster-hough-generalizado"] = "indisponivel"
        if row["class_code"] in {"ATERRAMENTO", "PARA_RAIOS_MT"}:
            state["structural-raster-graph"] = "experimental_rejeitado"
            state["structural-vector-graph"] = "experimental_rejeitado"
    elif owner == "E05":
        state["transformer-vector-shapes"] = {
            "reconhecido_exato": "id_exato_sintetico",
            "alternativa_sem_id_resolvido": "alternativa_sintetica",
        }.get(status, "nao_avaliavel")
        if row["class_code"] == "TRANSFORMADOR":
            state["raster-template"] = "classe_sem_id"
            state["raster-hough-generalizado"] = "indisponivel"
    elif owner == "E06":
        state["guy-vector-shapes"] = (
            "alternativa_sintetica" if status == "alternativa_sem_id_resolvido" else "nao_avaliavel"
        )
    elif owner == "E07":
        assert package is not None
        state["declarative-vector-packages"] = (
            "id_exato_sintetico"
            if package["recognition"]["status"] == "enabled"
            else "pendente_sem_inferencia"
        )
    elif owner == "E10":
        state["document-local-legend"] = "contexto_informativo_sem_id"
    if status == "informativo":
        state["document-local-legend"] = "informativo_nao_ativo"
    if row["class_code"] in {
        "ATERRAMENTO",
        "PARA_RAIOS_MT",
        "PARA_RAIOS_BT",
        "TRANSFORMADOR",
        "ESTAI",
        "ESTAI_MT",
    }:
        state["learned-e11"] = "experimental_rejeitado"
    return state


def build(
    inventory_path: Path,
    package_dir: Path,
    e05_report: Path | None,
    e06_report: Path | None,
    e07_report: Path,
    baseline_matrix: Path | None = None,
) -> tuple[list[Record], Record]:
    inventory = _load(inventory_path)
    variants = inventory["variants"]
    if len({item["id"] for item in variants}) != len(variants):
        raise ValueError("E01 inventory has duplicate IDs")
    packages = _packages(package_dir)
    e05 = _stage_matches(e05_report, "transformer-vector-shapes") if e05_report else {}
    e06 = _stage_matches(e06_report, "guy-vector-shapes") if e06_report else {}
    baseline = _baseline_rows(baseline_matrix)
    e07 = _load(e07_report)
    if not e07.get("complete_inference"):
        raise ValueError("E07 report has incomplete inference")
    if e07.get("package_sha256") != _package_digest(package_dir):
        raise ValueError("E07 report does not match the current package checkpoint")
    if any(
        family.get("fp", 0) or family.get("fn", 0) or family.get("duplicates", 0)
        for family in e07["by_family"].values()
    ):
        raise ValueError("E07 authored benchmark has failures; do not promote IDs")
    decisions = e07["decisions"]
    e07_validated = {
        decision["variant_id"]
        for decision in decisions
        if decision["stratum"] == "positive"
        and decision["tp"] == [decision["variant_id"]]
        and not decision["fp"]
        and not decision["fn"]
        and not decision.get("duplicates", 0)
    }
    rows = []
    for variant in variants:
        identity = variant["id"]
        owner = variant["owner_stage"]
        package = packages.get(identity)
        package_status = package["recognition"]["status"] if package else "nao_aplicavel"
        possible: list[str] = []
        if owner == "E04":
            status = "nao_avaliavel"
            evidence = "E04 mede classe visual, sem referência/saída por ID E01"
        elif owner == "E05":
            if e05_report:
                status, possible = e05.get(identity, ("nao_avaliavel", []))
                evidence = "E05 controle autoral pareado; referências possíveis na predição"
            else:
                previous = baseline.get(identity)
                if previous is None or previous["owner_stage"] != owner:
                    raise ValueError(f"E05 ID needs a fresh report or baseline: {identity}")
                if (
                    previous["family_id"] != variant["family_id"]
                    or previous.get("class_code") != variant["class_code"]
                ):
                    raise ValueError(f"E05 baseline identity changed: {identity}")
                status = previous["status"]
                if status not in STATUS:
                    raise ValueError(f"E05 baseline status invalid: {identity}")
                possible = list(filter(None, previous["possible_reference_ids"].split(";")))
                evidence = "E05 synthetic evidence inherited from baseline matrix"
        elif owner == "E06":
            if e06_report:
                status, possible = e06.get(identity, ("nao_avaliavel", []))
                evidence = "E06 controle autoral pareado; MT/AT e situação indeterminadas"
            else:
                previous = baseline.get(identity)
                if previous is None or previous["owner_stage"] != owner:
                    raise ValueError(f"E06 ID needs a fresh report or baseline: {identity}")
                if (
                    previous["family_id"] != variant["family_id"]
                    or previous.get("class_code") != variant["class_code"]
                ):
                    raise ValueError(f"E06 baseline identity changed: {identity}")
                status = previous["status"]
                if status not in STATUS:
                    raise ValueError(f"E06 baseline status invalid: {identity}")
                possible = list(filter(None, previous["possible_reference_ids"].split(";")))
                evidence = "E06 synthetic evidence inherited from baseline matrix"
        elif owner == "E07":
            if package is None:
                raise ValueError(f"E07 ID without package: {identity}")
            if variant["destination"] in {"informative_only", "document_convention"}:
                status = "informativo"
                evidence = "destino sem ativo; pacote pending não significa reconhecimento"
            elif package_status == "enabled" and identity in e07_validated:
                status = "reconhecido_exato"
                evidence = "E07 gramática e positivo autoral com ID exato; sem homologação real"
            elif package_status == "pending":
                status = "ainda_nao_suportado"
                evidence = package["recognition"]["reason"]
            else:
                status = "nao_avaliavel"
                evidence = "gramática habilitada sem positivo autoral validado"
        elif owner == "E10":
            status = "informativo"
            evidence = "convenção documental; E10 não resolve ID E01 a partir da legenda"
        else:
            raise ValueError(f"owner E01 unknown: {owner}")
        if status not in STATUS:
            raise ValueError(f"invalid status: {status}")
        row = {
            "id": identity,
            "family_id": variant["family_id"],
            "class_code": variant["class_code"],
            "source_kind": variant["source_kind"],
            "owner_stage": owner,
            "destination": variant["destination"],
            "status": status,
            "package_status": package_status,
            "possible_reference_ids": ";".join(possible),
            "evidence": evidence,
            "evidence_level": "synthetic_only" if status == "reconhecido_exato" else "documented",
        }
        row.update(_method_states(row, package))
        rows.append(row)
    if set(packages) != {item["id"] for item in variants if item["owner_stage"] == "E07"}:
        raise ValueError("E07 package IDs do not reconcile with E01 inventory")
    totals = Counter(row["status"] for row in rows)
    by_family: dict[str, Counter[str]] = defaultdict(Counter)
    by_owner: dict[str, Counter[str]] = defaultdict(Counter)
    by_destination: dict[str, Counter[str]] = defaultdict(Counter)
    by_source_kind: dict[str, Counter[str]] = defaultdict(Counter)
    by_package_status: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        by_family[row["family_id"]][row["status"]] += 1
        by_owner[row["owner_stage"]][row["status"]] += 1
        by_destination[row["destination"]][row["status"]] += 1
        by_source_kind[row["source_kind"]][row["status"]] += 1
        by_package_status[row["package_status"]][row["status"]] += 1
    inputs_sha256 = {
        "inventory": _digest(inventory_path),
        "e07_report": _digest(e07_report),
    }
    if e05_report:
        inputs_sha256["e05_report"] = _digest(e05_report)
    if e06_report:
        inputs_sha256["e06_report"] = _digest(e06_report)
    if baseline_matrix:
        inputs_sha256["baseline_matrix"] = _digest(baseline_matrix)
    summary = {
        "inventory_version": inventory["inventory_version"],
        "denominator_ids": len(rows),
        "denominator_families": len(inventory["families"]),
        "status_order": list(STATUS),
        "status_counts": {key: totals[key] for key in STATUS},
        "by_family": {
            key: {"denominator": sum(counts.values()), **{s: counts[s] for s in STATUS}}
            for key, counts in sorted(by_family.items())
        },
        "by_owner": {
            key: {"denominator": sum(counts.values()), **{s: counts[s] for s in STATUS}}
            for key, counts in sorted(by_owner.items())
        },
        "by_destination": {
            key: {"denominator": sum(counts.values()), **{s: counts[s] for s in STATUS}}
            for key, counts in sorted(by_destination.items())
        },
        "by_source_kind": {
            key: {"denominator": sum(counts.values()), **{s: counts[s] for s in STATUS}}
            for key, counts in sorted(by_source_kind.items())
        },
        "by_package_status": {
            key: {"denominator": sum(counts.values()), **{s: counts[s] for s in STATUS}}
            for key, counts in sorted(by_package_status.items())
        },
        "inputs_sha256": inputs_sha256,
        "method_columns": list(METHODS),
        "limits": [
            "Exact status has author-owned synthetic support only; no field homology claim.",
            "Informative is a semantic destination; pending packages do not recognize IDs.",
            "Method columns separate ID grammar, class-only support, pending, unavailable, "
            "and rejected methods.",
            "A class-level hit does not resolve a variant ID or an asset quantity.",
        ],
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--e05-report", type=Path)
    parser.add_argument("--e06-report", type=Path)
    parser.add_argument(
        "--baseline-matrix", type=Path, default=ROOT / "docs/data/matriz-simbologia-e16.csv"
    )
    parser.add_argument("--e07-report", type=Path, required=True)
    args = parser.parse_args()
    historical = {
        (ROOT / "docs/data/matriz-simbologia-e16.csv").resolve(),
        (ROOT / "docs/data/matriz-simbologia-e16-resumo.json").resolve(),
    }
    if args.output.resolve() in historical or args.summary.resolve() in historical:
        raise ValueError("historical E16 coverage artifacts are immutable")
    if args.output.resolve() == args.summary.resolve():
        raise ValueError("matrix and summary must use separate files")
    rows, summary = build(
        ROOT / "docs/data/inventario-simbologia-v1.json",
        ROOT / "src/zeny_project_handler/adapters/analysis/symbol_packages",
        args.e05_report,
        args.e06_report,
        args.e07_report,
        args.baseline_matrix,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary["status_counts"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
