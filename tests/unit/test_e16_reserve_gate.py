"""E16 reserve opt-in boundaries using authorial in-memory records only."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from scripts.symbol_benchmark_evaluator import evaluate
from scripts.symbol_benchmark_runner import write_json


def _reference(split: str = "reserve") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "annotation_scope": "complete",
        "families": ["family-control"],
        "documents": [
            {
                "id": "control-1",
                "sha256": "a" * 64,
                "path": "control-1.pdf",
                "split": split,
                "ancestor_id": "author-control-1",
                "template_family": "author-control-1",
                "pages": [{"number": 1, "width_pt": 400, "height_pt": 300}],
            }
        ],
        "occurrences": [],
    }


def _outputs() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "methods": [
            {
                "id": "control-method",
                "version": "1",
                "algorithm_family": "author-control",
                "shared_sources": [],
                "supported_classes": ["CONTROL"],
            }
        ],
        "documents": [{"id": "control-1", "sha256": "a" * 64}],
        "predictions": [],
        "executions": [],
    }


def test_e16_reserve_is_refused_without_explicit_opt_in() -> None:
    with pytest.raises(ValueError, match="reserve"):
        evaluate(_reference(), _outputs())


def test_e16_opt_in_accepts_only_reserve_documents() -> None:
    report = evaluate(_reference(), _outputs(), allow_reserve=True)
    assert report["denominators"]["documents"] == 1
    assert report["denominators"]["confirmed_operational"] == 0
    with pytest.raises(ValueError, match="reserve"):
        evaluate(_reference("development"), _outputs(), allow_reserve=True)


def test_e16_opt_in_refuses_mixed_partitions() -> None:
    reference = _reference()
    other = deepcopy(reference["documents"][0])
    other.update(
        id="control-2",
        sha256="b" * 64,
        path="control-2.pdf",
        split="development",
        ancestor_id="author-control-2",
        template_family="author-control-2",
    )
    reference["documents"].append(other)
    outputs = _outputs()
    outputs["documents"].append({"id": "control-2", "sha256": "b" * 64})
    with pytest.raises(ValueError, match="reserve"):
        evaluate(reference, outputs, allow_reserve=True)


def test_e16_harness_persists_predictions_and_composition_before_revealing_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fabricated archive checks the phase boundary without reading the real ZIP."""
    import scripts.benchmark_reserve_e16 as harness

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    inventory = tmp_path / "docs" / "data" / "inventario-simbologia-v1.json"
    inventory.parent.mkdir(parents=True)
    inventory.write_text("{}", encoding="utf-8")
    fake_pdf = b"%PDF-1.7\nAuthorial mock; no PDF decoder is called.\n"
    reference = _reference()
    reference["documents"][0]["sha256"] = sha256(fake_pdf).hexdigest()
    reference_bytes = json.dumps(reference).encode()
    archive_bytes = b"authorial fake ZIP bytes"
    (fixtures / "reserve.sealed.zip").write_bytes(archive_bytes)
    manifest = {
        "reserve": {
            "path": "reserve.sealed.zip",
            "sha256": sha256(archive_bytes).hexdigest(),
            "documents": 1,
        },
        "inventory_sha256": sha256(inventory.read_bytes()).hexdigest(),
        "partitions": [
            {
                "split": "reserve",
                "documents": [
                    {
                        "id": "control-1",
                        "path": "control-1.pdf",
                        "sha256": sha256(fake_pdf).hexdigest(),
                    }
                ],
            }
        ],
    }
    write_json(fixtures / "manifest.json", manifest)
    output = tmp_path / "gate"
    phases: list[str] = []

    class FakeZipFile:
        def __init__(self, path: Path) -> None:
            assert path == fixtures / "reserve.sealed.zip"

        def __enter__(self) -> FakeZipFile:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def infolist(self) -> list[Any]:
            return [
                SimpleNamespace(filename=name, is_dir=lambda: False)
                for name in ("control-1.pdf", "reference.json")
            ]

        def read(self, name: str) -> bytes:
            if name == "control-1.pdf":
                phases.append("pdf")
                return fake_pdf
            assert name == "reference.json"
            assert (output / "predictions.json").is_file()
            assert (output / "manifest.json").is_file()
            assert (output / "pre_reference_receipt.json").is_file()
            assert (output / "composition.json").is_file()
            receipt = json.loads((output / "pre_reference_receipt.json").read_text())
            assert receipt["reference_read"] is False
            runner_manifest = json.loads((output / "manifest.json").read_text())
            assert runner_manifest["documents"][0]["split"] == "reserve"
            phases.append("reference")
            return reference_bytes

    def fake_run(sources: list[tuple[Path, str]], target: Path, **flags: Any) -> dict[str, Any]:
        assert sources == [(output / "corpus" / "control-1.pdf", "control-1")]
        assert target == output
        assert flags["include_structural"] is True
        assert "reference" not in flags
        assert phases == ["pdf"]
        write_json(
            output / "predictions.json", {"methods": [], "predictions": [], "executions": []}
        )
        runner_manifest = {
            "completed": True,
            "documents": [{"id": "control-1", "split": "development"}],
        }
        write_json(output / "manifest.json", runner_manifest)
        phases.append("inference")
        return runner_manifest

    def fake_compose(raw: dict[str, Any], excluded: tuple[str, ...]) -> dict[str, Any]:
        assert raw["predictions"] == []
        assert excluded == harness.EXCLUDED
        assert phases == ["pdf", "inference"]
        phases.append("composition")
        return {"candidates": []}

    def fake_evaluate(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        assert kwargs == {"allow_reserve": True}
        assert phases == ["pdf", "inference", "composition", "reference"]
        return {"denominators": {}, "compositions": {"raw_union": {"micro": {}}}}

    monkeypatch.setattr(harness, "ROOT", tmp_path)
    monkeypatch.setattr(harness, "FIXTURES", fixtures)
    monkeypatch.setattr(harness, "ZipFile", FakeZipFile)
    monkeypatch.setattr(harness, "_run", fake_run)
    monkeypatch.setattr(harness, "compose", fake_compose)
    monkeypatch.setattr(harness, "evaluate", fake_evaluate)
    monkeypatch.setattr(harness, "_evaluation", lambda *_args, **_kwargs: {"micro": {}})

    harness.run(output)
    assert phases == ["pdf", "inference", "composition", "reference"]
    with pytest.raises(FileExistsError, match="new directory"):
        harness.run(output)
