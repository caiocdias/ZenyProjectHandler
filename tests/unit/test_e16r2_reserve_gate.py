"""E16R2 reserve gate controls with a fabricated accessor and no sealed input reads."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import scripts.benchmark_reserve_e16r2 as harness
from scripts.symbol_benchmark_runner import file_sha256, write_json


def test_freeze_is_new_only_and_rejects_code_or_configuration_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_root = tmp_path / "authorial-root"
    manifest = fake_root / "tests" / "fixtures" / "symbols" / "e16r2" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"authorial":true}\n', encoding="utf-8")
    monkeypatch.setattr(harness, "ROOT", fake_root)
    monkeypatch.setattr(harness, "public_manifest", lambda: {"archive": {"sha256": "a" * 64}})
    monkeypatch.setattr(harness, "_code_hash", lambda: "b" * 64)
    monkeypatch.setattr(harness, "_require_optional_runtime_absent", lambda: None)
    checkpoint = tmp_path / "frozen.json"

    frozen = harness.freeze(checkpoint)
    assert frozen["archive_sha256"] == "a" * 64
    assert frozen["code_sha256"] == "b" * 64
    assert harness._verify_checkpoint(checkpoint) == frozen
    with pytest.raises(FileExistsError, match="new file"):
        harness.freeze(checkpoint)

    monkeypatch.setattr(harness, "_code_hash", lambda: "c" * 64)
    with pytest.raises(ValueError, match="changed after freeze"):
        harness._verify_checkpoint(checkpoint)
    monkeypatch.setattr(harness, "_code_hash", lambda: "b" * 64)
    manifest.write_text('{"authorial":false}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="changed after freeze"):
        harness._verify_checkpoint(checkpoint)
    manifest.write_text('{"authorial":true}\n', encoding="utf-8")
    monkeypatch.setattr(harness, "CONFIG", {**harness.CONFIG, "include_raster": False})
    with pytest.raises(ValueError, match="changed after freeze"):
        harness._verify_checkpoint(checkpoint)


def test_checkpoint_refuses_optional_opencv_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: object() if name == "cv2" else None,
    )
    with pytest.raises(RuntimeError, match="excludes optional OpenCV"):
        harness._require_optional_runtime_absent()


def test_run_writes_frozen_predictions_and_composition_before_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = tmp_path / "authorial-checkpoint.json"
    checkpoint.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "run"
    phases: list[str] = []
    manifest: dict[str, Any] = {
        "archive": {"sha256": "a" * 64},
        "documents": [{"id": "author-pdf", "path": "author.pdf"}],
    }
    monkeypatch.setattr(harness, "public_manifest", lambda: deepcopy(manifest))

    def verify(path: Path) -> dict[str, Any]:
        assert path == checkpoint
        if "reference" in phases:
            return {"checkpoint_id": "author-checkpoint"}
        assert "reference" not in phases
        phases.append("verify")
        return {"checkpoint_id": "author-checkpoint"}

    def extract(path: Path, target: Path) -> dict[str, Any]:
        assert path == checkpoint and target == output
        assert phases == ["verify"]
        (target / "corpus").mkdir(parents=True)
        (target / "corpus" / "author.pdf").write_bytes(b"%PDF-1.7 authorial mock")
        write_json(target / "corpus-receipt.json", {"reference_read": False})
        phases.append("extract")
        return {"reference_read": False}

    def infer(sources: list[tuple[Path, str]], target: Path, **flags: Any) -> dict[str, Any]:
        assert sources == [(output / "corpus" / "author.pdf", "author-pdf")]
        assert target == output
        assert flags["include_raster"] and flags["include_legend"]
        assert phases == ["verify", "extract"]
        write_json(
            target / "predictions.json",
            {"methods": [], "documents": [], "predictions": [], "executions": []},
        )
        phases.append("inference")
        return {"completed": True, "documents": [{"id": "author-pdf", "split": "development"}]}

    def compose(raw: dict[str, Any], excluded: tuple[str, ...]) -> dict[str, Any]:
        assert raw["predictions"] == []
        assert excluded == harness.EXCLUDED
        assert phases == ["verify", "extract", "inference"]
        phases.append("composition")
        return {"candidates": []}

    def release(
        path: Path,
        receipt: Path,
        prediction_manifest: Path,
        predictions: Path,
        target: Path,
        *,
        acknowledge: bool,
    ) -> dict[str, Any]:
        assert path == checkpoint and acknowledge
        assert receipt.is_file() and prediction_manifest.is_file() and predictions.is_file()
        assert (output / "composition.json").is_file()
        assert json.loads(receipt.read_text())["reference_read"] is False
        assert json.loads(prediction_manifest.read_text())["documents"][0]["split"] == "reserve"
        assert phases == ["verify", "extract", "inference", "composition", "verify"]
        target.mkdir()
        write_json(target / "pre-reference-receipt.json", {"reference_read": False})
        phases.append("reference")
        write_json(target / "reference.json", {"occurrences": [], "documents": []})
        return {"reference_read": True}

    def evaluate(
        reference: dict[str, Any], raw: dict[str, Any], *, allow_reserve: bool
    ) -> dict[str, Any]:
        assert phases[-1] == "reference"
        assert allow_reserve and reference["occurrences"] == [] and raw["predictions"] == []
        return {
            "denominators": {"documents": 1},
            "compositions": {"raw_union": {"micro": {"tp": 0, "fp": 0, "fn": 0}}},
        }

    monkeypatch.setattr(harness, "_verify_checkpoint", verify)
    monkeypatch.setattr(harness, "extract_corpus", extract)
    monkeypatch.setattr(harness, "_run", infer)
    monkeypatch.setattr(harness, "compose", compose)
    monkeypatch.setattr(harness, "release_reference", release)
    monkeypatch.setattr(harness, "evaluate", evaluate)
    monkeypatch.setattr(
        harness, "_evaluation", lambda *_args, **_kwargs: {"micro": {"tp": 0, "fp": 0, "fn": 0}}
    )

    report = harness.run(checkpoint, output)
    assert report["predictions_sha256"] == file_sha256(output / "predictions.json")
    assert phases == ["verify", "extract", "inference", "composition", "verify", "reference"]
    assert (output / "reference-release" / "pre-reference-receipt.json").is_file()
    assert checkpoint.with_name(checkpoint.name + ".used.json").is_file()
    with pytest.raises(FileExistsError, match="must be new"):
        harness.run(checkpoint, output)
    with pytest.raises(FileExistsError):
        harness.run(checkpoint, tmp_path / "different-output")
    assert phases.count("inference") == 1


def test_incomplete_inference_cannot_release_labels_or_rerun_same_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint, output = tmp_path / "author-checkpoint.json", tmp_path / "failed-run"
    checkpoint.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(harness, "_verify_checkpoint", lambda _path: {})
    monkeypatch.setattr(
        harness,
        "public_manifest",
        lambda: {"documents": [{"id": "author-pdf", "path": "author.pdf"}]},
    )

    def extract(_checkpoint: Path, target: Path) -> None:
        target.mkdir()

    calls = 0

    def incomplete(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"completed": False}

    monkeypatch.setattr(harness, "extract_corpus", extract)
    monkeypatch.setattr(harness, "_run", incomplete)
    monkeypatch.setattr(
        harness,
        "release_reference",
        lambda *_args, **_kwargs: pytest.fail("labels released after incomplete inference"),
    )
    with pytest.raises(RuntimeError, match="inference incomplete"):
        harness.run(checkpoint, output)
    with pytest.raises(FileExistsError, match="must be new"):
        harness.run(checkpoint, output)
    with pytest.raises(FileExistsError):
        harness.run(checkpoint, tmp_path / "different-output")
    assert calls == 1
