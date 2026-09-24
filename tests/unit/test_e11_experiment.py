"""E11 experiment boundaries: split integrity, reproducibility and E02 output contract."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from scripts.experiments.e11_adapter import result_from_predictions
from scripts.experiments.e11_calibration_ids import rebind
from scripts.experiments.e11_detector import METHOD_ID, compare
from scripts.symbol_benchmark_evaluator import evaluate

from zeny_project_handler.adapters.persistence.domain_json import dumps_domain, loads_domain
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import ResultadoMetodoSimbolos

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tests" / "fixtures" / "symbols" / "manifest.json"


def _run(*args: str, expected_success: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.experiments.e11_detector", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if expected_success:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0, result.stdout + result.stderr
    return result


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def public_data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("e11-data")
    _run("prepare", "--output", str(root))
    return root


def test_prepare_preserves_frozen_e02_splits_and_sources(public_data: Path) -> None:
    manifest = _json(MANIFEST)
    partitions = {part["split"]: part for part in manifest["partitions"]}
    public_keys: dict[str, set[str]] = {}
    for split in ("development", "calibration"):
        reference = _json(public_data / split / "reference.json")
        expected = partitions[split]
        assert len(reference["documents"]) == len(expected["documents"])
        assert {doc["id"] for doc in reference["documents"]} == {
            doc["id"] for doc in expected["documents"]
        }
        for doc in reference["documents"]:
            recorded = next(item for item in expected["documents"] if item["id"] == doc["id"])
            assert doc["sha256"] == recorded["sha256"]
            assert _sha(public_data / split / recorded["path"]) == recorded["sha256"]
        public_keys[split] = {
            doc[key]
            for doc in reference["documents"]
            for key in ("sha256", "ancestor_id", "template_family")
        }
    assert public_keys["development"].isdisjoint(public_keys["calibration"])
    assert not (public_data / "reserve").exists()


def test_train_rejects_calibration_and_modified_source(public_data: Path, tmp_path: Path) -> None:
    calibration = public_data / "calibration"
    rejected_calibration = tmp_path / "calibration-model"
    _run(
        "train",
        "--reference",
        str(calibration / "reference.json"),
        "--root",
        str(calibration),
        "--output",
        str(rejected_calibration),
        "--seed",
        "20260924",
        expected_success=False,
    )
    assert not (rejected_calibration / "model.json").exists()

    changed_reference = _json(public_data / "development" / "reference.json")
    changed_reference["occurrences"][0]["class_id"] = "UNVERIFIED_CLASS"
    changed_reference_path = tmp_path / "changed-reference.json"
    changed_reference_path.write_text(json.dumps(changed_reference), encoding="utf-8")
    rejected_labels = tmp_path / "changed-label-model"
    _run(
        "train",
        "--reference",
        str(changed_reference_path),
        "--root",
        str(public_data / "development"),
        "--output",
        str(rejected_labels),
        "--seed",
        "20260924",
        expected_success=False,
    )
    assert not (rejected_labels / "model.json").exists()

    copied = tmp_path / "development"
    shutil.copytree(public_data / "development", copied)
    source = copied / "dev-symbols.pdf"
    source.write_bytes(source.read_bytes() + b"\n% E11 changed source\n")
    rejected_modified = tmp_path / "changed-source-model"
    _run(
        "train",
        "--reference",
        str(copied / "reference.json"),
        "--root",
        str(copied),
        "--output",
        str(rejected_modified),
        "--seed",
        "20260924",
        expected_success=False,
    )
    assert not (rejected_modified / "model.json").exists()


def test_train_and_infer_repeat_deterministically_with_e02_contract(
    public_data: Path, tmp_path: Path
) -> None:
    development = public_data / "development"
    models = [tmp_path / "model-1", tmp_path / "model-2"]
    for output in models:
        _run(
            "train",
            "--reference",
            str(development / "reference.json"),
            "--root",
            str(development),
            "--output",
            str(output),
            "--seed",
            "20260924",
        )
    assert _sha(models[0] / "model.json") == _sha(models[1] / "model.json")
    for output in models:
        train_manifest = _json(output / "train-manifest.json")
        assert train_manifest
        assert "reserve" not in json.dumps(train_manifest).lower()
        assert "calibration" not in json.dumps(train_manifest).lower()

    predictions = [tmp_path / "infer-1", tmp_path / "infer-2"]
    for output in predictions:
        _run(
            "infer",
            "--model",
            str(models[0] / "model.json"),
            "--root",
            str(development),
            "--output",
            str(output),
        )
    assert _sha(predictions[0] / "predictions.json") == _sha(predictions[1] / "predictions.json")
    outputs = _json(predictions[0] / "predictions.json")
    reference = _json(development / "reference.json")
    assert outputs["schema_version"] == 1
    assert len(outputs["documents"]) == 4
    assert {doc["id"]: doc["sha256"] for doc in outputs["documents"]} == {
        doc["id"]: doc["sha256"] for doc in reference["documents"]
    }
    assert len(outputs["executions"]) == 12
    assert (
        sum(
            execution["status"] == "executed" and execution["layer"] == "base"
            for execution in outputs["executions"]
        )
        == 6
    )
    assert (
        sum(
            execution["status"] == "not_applicable" and execution["layer"] == "annotation"
            for execution in outputs["executions"]
        )
        == 6
    )
    assert "occurrences" not in outputs
    report = evaluate(reference, outputs)
    assert report["schema_version"] == 1
    assert "raw_union" in report["compositions"]

    empty = tmp_path / "empty"
    empty.mkdir()
    empty_output = tmp_path / "empty-infer"
    _run(
        "infer",
        "--model",
        str(models[0] / "model.json"),
        "--root",
        str(empty),
        "--output",
        str(empty_output),
        expected_success=False,
    )
    assert _json(empty_output / "manifest.json")["status"] == "no_examples"

    corrupt = tmp_path / "corrupt"
    corrupt.mkdir()
    (corrupt / "bad.pdf").write_bytes(b"this is not a PDF")
    corrupt_output = tmp_path / "corrupt-infer"
    _run(
        "infer",
        "--model",
        str(models[0] / "model.json"),
        "--root",
        str(corrupt),
        "--output",
        str(corrupt_output),
        expected_success=False,
    )
    assert _json(corrupt_output / "manifest.json")["documents"][0]["status"] == "failed"


def _output(method_id: str, source_sha: str, *, prediction: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "documents": [{"id": "one", "sha256": source_sha}],
        "methods": [
            {
                "id": method_id,
                "version": "test",
                "algorithm_family": method_id,
                "shared_sources": [],
                "supported_classes": ["ATERRAMENTO"],
                "model_sha256": "c" * 64,
            }
        ],
        "executions": [
            {
                "document_id": "one",
                "page": 1,
                "layer": "base",
                "method_id": method_id,
                "status": "executed",
                "reason": None,
            }
        ],
        "predictions": (
            [
                {
                    "id": f"{method_id}-unique",
                    "method_id": method_id,
                    "document_id": "one",
                    "page": 1,
                    "layer": "base",
                    "family": "family-f02-19",
                    "class_id": "ATERRAMENTO",
                    "bbox": [0.1, 0.1, 0.2, 0.2],
                    "score": 0.2,
                    "situation": None,
                    "quantity": None,
                    "association": None,
                }
            ]
            if prediction
            else []
        ),
    }


def test_compare_keeps_exclusive_candidate_and_rejects_source_mismatch(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    learned_path = tmp_path / "learned.json"
    baseline_path.write_text(json.dumps(_output("legacy", "a" * 64, prediction=False)))
    learned_path.write_text(json.dumps(_output("learned", "a" * 64, prediction=True)))
    result = compare(baseline_path, learned_path, tmp_path / "union")
    merged = _json(tmp_path / "union" / "predictions.json")
    assert result["predictions"] == 1
    assert [item["id"] for item in merged["predictions"]] == ["learned-unique"]
    assert {item["id"] for item in merged["methods"]} == {"legacy", "learned"}
    assert result["policy"].startswith("raw candidate union")

    learned_path.write_text(json.dumps(_output("learned", "b" * 64, prediction=True)))
    with pytest.raises(ValueError, match="source PDFs differ"):
        compare(baseline_path, learned_path, tmp_path / "mismatch")
    assert not (tmp_path / "mismatch" / "predictions.json").exists()


def test_e03_adapter_roundtrip_preserves_evidence_and_out_of_domain() -> None:
    predictions = _output(METHOD_ID, "a" * 64, prediction=True)
    result = result_from_predictions(
        predictions, document_id="one", page=1, layer="base", width_pt=400, height_pt=300
    )
    restored = loads_domain(dumps_domain(result), ResultadoMetodoSimbolos)
    assert restored == result
    assert restored.perfil.assinatura() == result.perfil.assinatura()
    assert restored.observacoes[0].fonte.documento_sha256 == "a" * 64
    assert restored.observacoes[0].score_bruto == Decimal("0.2")
    assert restored.observacoes[0].geometria.pontos_originais[0] == (
        Decimal("40.0"),
        Decimal("30.0"),
    )

    predictions["predictions"] = []
    predictions["executions"][0]["layer"] = "annotation"
    predictions["executions"][0]["status"] = "not_applicable"
    abstained = result_from_predictions(
        predictions, document_id="one", page=1, layer="annotation", width_pt=400, height_pt=300
    )
    restored_abstained = loads_domain(dumps_domain(abstained), ResultadoMetodoSimbolos)
    assert restored_abstained.coberturas[0].estado is EstadoMetodoSimbolos.FORA_DOMINIO
    assert restored_abstained.observacoes == ()
    assert not restored_abstained.coberturas[0].estado.comprova_ausencia

    predictions["executions"][0]["layer"] = "base"
    predictions["executions"][0]["status"] = "executed"
    predictions["predictions"] = _output(METHOD_ID, "a" * 64, prediction=True)["predictions"]
    predictions["predictions"][0]["bbox"] = [0.2, 0.1, 0.1, 0.2]
    with pytest.raises(ValueError, match="Invalid normalized"):
        result_from_predictions(
            predictions, document_id="one", page=1, layer="base", width_pt=400, height_pt=300
        )


def test_e03_adapter_distinguishes_partial_failure_from_no_detection() -> None:
    partial = _output(METHOD_ID, "a" * 64, prediction=True)
    partial["executions"][0]["status"] = "failed"
    failed = result_from_predictions(
        partial, document_id="one", page=1, layer="base", width_pt=400, height_pt=300
    )
    restored_failed = loads_domain(dumps_domain(failed), ResultadoMetodoSimbolos)
    assert restored_failed.coberturas[0].estado is EstadoMetodoSimbolos.FALHA
    assert restored_failed.observacoes == failed.observacoes
    assert len(restored_failed.observacoes) == 1
    assert not restored_failed.completo

    silent = _output(METHOD_ID, "a" * 64, prediction=False)
    no_detection = result_from_predictions(
        silent, document_id="one", page=1, layer="base", width_pt=400, height_pt=300
    )
    restored_silent = loads_domain(dumps_domain(no_detection), ResultadoMetodoSimbolos)
    assert restored_silent.coberturas[0].estado is EstadoMetodoSimbolos.NAO_DETECCAO
    assert restored_silent.observacoes == ()
    assert restored_silent.completo
    assert not restored_silent.coberturas[0].estado.comprova_ausencia


def test_calibration_rebind_preserves_candidates_and_rejects_changed_source(tmp_path: Path) -> None:
    manifest = _json(MANIFEST)
    calibration = next(part for part in manifest["partitions"] if part["split"] == "calibration")
    documents = [
        {"id": f"example:{doc['id']}.pdf", "sha256": doc["sha256"]}
        for doc in calibration["documents"]
    ]
    candidate = {
        "id": "exclusive-p1",
        "document_id": documents[0]["id"],
        "page": 1,
        "layer": "base",
        "method_id": "legacy",
        "class_id": "ATERRAMENTO",
        "bbox": [0.1, 0.2, 0.3, 0.4],
        "score": 0.88,
    }
    raw: dict[str, Any] = {
        "schema_version": 1,
        "documents": documents,
        "methods": [{"id": "legacy", "algorithm_family": "vector"}],
        "predictions": [candidate],
        "executions": [
            {
                "document_id": doc["id"],
                "page": 1,
                "layer": "base",
                "method_id": "legacy",
                "status": "executed",
            }
            for doc in documents
        ],
    }
    raw_path = tmp_path / "raw.json"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    rebound_path = tmp_path / "rebound.json"
    summary = rebind(raw_path, rebound_path)
    rebound = _json(rebound_path)
    expected_ids = {doc["id"] for doc in calibration["documents"]}
    assert summary["documents"] == len(expected_ids) == 2
    assert summary["predictions"] == 1
    assert {doc["id"] for doc in rebound["documents"]} == expected_ids
    assert {doc["sha256"] for doc in rebound["documents"]} == {doc["sha256"] for doc in documents}
    assert rebound["methods"] == raw["methods"]
    assert rebound["predictions"] == [
        {**candidate, "document_id": calibration["documents"][0]["id"]}
    ]
    assert {execution["document_id"] for execution in rebound["executions"]} == expected_ids
    assert _json(raw_path) == raw

    raw["documents"][0]["sha256"] = "0" * 64
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    rejected_path = tmp_path / "rejected.json"
    with pytest.raises(ValueError, match="source hash differs"):
        rebind(raw_path, rejected_path)
    assert not rejected_path.exists()
