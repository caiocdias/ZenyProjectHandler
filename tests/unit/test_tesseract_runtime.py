from __future__ import annotations

import os
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from subprocess import CompletedProcess
from typing import cast
from urllib.error import URLError

import pytest

from zeny_project_handler.adapters.analysis import tesseract_runtime as runtime_module
from zeny_project_handler.adapters.analysis.tesseract_ocr import TesseractCliOcr
from zeny_project_handler.adapters.analysis.tesseract_runtime import (
    PORTUGUESE_TRAINEDDATA_SHA256,
    PORTUGUESE_TRAINEDDATA_URL,
    TESSDATA_DIRECTORY_ENVIRONMENT_VARIABLE,
    TESSDATA_FAST_REVISION,
    TESSDATA_PREFIX_ENVIRONMENT_VARIABLE,
    TESSERACT_PATH_ENVIRONMENT_VARIABLE,
    inspect_tesseract_runtime,
    provision_portuguese_language,
)


def _fake_installation(root: Path, languages: Mapping[str, bytes]) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    executable = root / "tesseract.exe"
    executable.write_bytes(b"stub executable")
    tessdata = root / "tessdata"
    tessdata.mkdir()
    for language, content in languages.items():
        (tessdata / f"{language}.traineddata").write_bytes(content)
    return executable, tessdata


def _environment(executable: Path, managed: Path) -> dict[str, str]:
    return {
        "PATH": "",
        TESSERACT_PATH_ENVIRONMENT_VARIABLE: str(executable),
        TESSDATA_DIRECTORY_ENVIRONMENT_VARIABLE: str(managed),
    }


def _install_fake_runner(
    monkeypatch: pytest.MonkeyPatch,
    default_tessdata: Path,
) -> list[tuple[tuple[str, ...], dict[str, str]]]:
    calls: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def fake_run(arguments: tuple[str, ...], **kwargs: object) -> CompletedProcess[str]:
        normalized = tuple(arguments)
        child_environment = cast(dict[str, str], kwargs["env"])
        calls.append((normalized, child_environment))
        if "--version" in normalized:
            return CompletedProcess(normalized, 0, stdout="tesseract 5.4.1\n")
        assert "--list-langs" in normalized
        selected = Path(
            child_environment.get(TESSDATA_PREFIX_ENVIRONMENT_VARIABLE, str(default_tessdata))
        )
        languages = sorted(path.stem for path in selected.glob("*.traineddata"))
        output = (
            f'List of available languages in "{selected}" ({len(languages)}):\n'
            + "\n".join(languages)
            + "\n"
        )
        return CompletedProcess(normalized, 0, stdout=output)

    monkeypatch.setattr(
        "zeny_project_handler.adapters.analysis.tesseract_runtime.subprocess.run",
        fake_run,
    )
    return calls


def test_runtime_requires_portuguese_and_selects_portuguese_plus_english(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable, system_tessdata = _fake_installation(
        tmp_path / "system",
        {"eng": b"english", "por": b"system portuguese"},
    )
    managed = tmp_path / "managed"
    calls = _install_fake_runner(monkeypatch, system_tessdata)

    result = inspect_tesseract_runtime(
        tmp_path / "data",
        _environment(executable, managed),
    )

    assert result.portugues_pronto
    assert result.idiomas_selecionados == ("por", "eng")
    assert result.diretorio_tessdata == system_tessdata.resolve()
    assert calls[0][0] == (str(executable.resolve()), "--list-langs")


def test_runtime_rejects_executable_when_list_langs_has_no_portuguese(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable, system_tessdata = _fake_installation(
        tmp_path / "system",
        {"eng": b"english"},
    )
    _install_fake_runner(monkeypatch, system_tessdata)

    result = inspect_tesseract_runtime(
        tmp_path / "data",
        _environment(executable, tmp_path / "managed"),
    )

    assert not result.portugues_pronto
    assert result.idiomas_disponiveis == ("eng",)
    assert result.diagnostico is not None
    assert result.diagnostico.codigo == "ocr.portugues_ausente"
    assert "setup.bat" in result.diagnostico.remediacao


def test_provision_without_admin_writes_only_to_managed_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    official_portuguese = b"pinned official portuguese"
    executable, system_tessdata = _fake_installation(
        tmp_path / "read-only-system",
        {"eng": b"installed english"},
    )
    managed = tmp_path / "user-data" / "ocr"
    environment = _environment(executable, managed)
    system_snapshot = {
        path.name: path.read_bytes() for path in system_tessdata.iterdir() if path.is_file()
    }
    calls = _install_fake_runner(monkeypatch, system_tessdata)
    monkeypatch.setattr(
        runtime_module,
        "PORTUGUESE_TRAINEDDATA_SHA256",
        sha256(official_portuguese).hexdigest(),
    )

    def fake_download(url: str, destination: Path) -> None:
        assert url == PORTUGUESE_TRAINEDDATA_URL
        destination.write_bytes(official_portuguese)

    monkeypatch.setattr(runtime_module, "_download_to", fake_download)
    parent_prefix = os.environ.get(TESSDATA_PREFIX_ENVIRONMENT_VARIABLE)

    result = provision_portuguese_language(tmp_path / "data", environment)

    assert result.portugues_pronto
    assert result.idiomas_selecionados == ("por", "eng")
    assert result.diretorio_tessdata == managed.resolve()
    assert (managed / "por.traineddata").read_bytes() == official_portuguese
    assert (managed / "eng.traineddata").read_bytes() == b"installed english"
    assert {
        path.name: path.read_bytes() for path in system_tessdata.iterdir() if path.is_file()
    } == system_snapshot
    assert os.environ.get(TESSDATA_PREFIX_ENVIRONMENT_VARIABLE) == parent_prefix
    assert any(
        child.get(TESSDATA_PREFIX_ENVIRONMENT_VARIABLE) == str(managed.resolve())
        for _arguments, child in calls
    )


def test_offline_provision_preserves_existing_venv_and_reports_remediation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable, system_tessdata = _fake_installation(
        tmp_path / "system",
        {"eng": b"english"},
    )
    _install_fake_runner(monkeypatch, system_tessdata)
    managed = tmp_path / "data" / "ocr"
    venv_marker = tmp_path / ".venv" / "pyvenv.cfg"
    venv_marker.parent.mkdir()
    venv_marker.write_text("preserve=true", encoding="utf-8")

    def offline_download(_url: str, _destination: Path) -> None:
        raise URLError("offline")

    monkeypatch.setattr(runtime_module, "_download_to", offline_download)

    result = provision_portuguese_language(
        tmp_path / "data",
        _environment(executable, managed),
    )

    assert not result.portugues_pronto
    assert result.diagnostico is not None
    assert result.diagnostico.codigo == "ocr.download_portugues_falhou"
    assert "Conecte-se" in result.diagnostico.remediacao
    assert venv_marker.read_text(encoding="utf-8") == "preserve=true"
    assert not (managed / "por.traineddata").exists()


def test_invalid_download_checksum_is_rejected_before_use(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable, system_tessdata = _fake_installation(
        tmp_path / "system",
        {"eng": b"english"},
    )
    _install_fake_runner(monkeypatch, system_tessdata)
    managed = tmp_path / "managed"

    def tampered_download(_url: str, destination: Path) -> None:
        destination.write_bytes(b"tampered")

    monkeypatch.setattr(runtime_module, "_download_to", tampered_download)

    result = provision_portuguese_language(
        tmp_path / "data",
        _environment(executable, managed),
    )

    assert not result.portugues_pronto
    assert result.diagnostico is not None
    assert result.diagnostico.codigo == "ocr.checksum_portugues_invalido"
    assert not (managed / "por.traineddata").exists()
    assert not tuple(managed.glob("*.download"))


def test_provisioned_runtime_integrates_with_stage_14_capability_signature(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    official_portuguese = b"official portuguese for signature"
    executable, system_tessdata = _fake_installation(
        tmp_path / "system",
        {"eng": b"english"},
    )
    managed = tmp_path / "managed"
    environment = _environment(executable, managed)
    calls = _install_fake_runner(monkeypatch, system_tessdata)
    pinned_digest = sha256(official_portuguese).hexdigest()
    monkeypatch.setattr(runtime_module, "PORTUGUESE_TRAINEDDATA_SHA256", pinned_digest)
    monkeypatch.setattr(
        runtime_module,
        "_download_to",
        lambda _url, destination: destination.write_bytes(official_portuguese),
    )
    runtime = provision_portuguese_language(tmp_path / "data", environment)
    assert runtime.executavel is not None
    assert runtime.diretorio_tessdata is not None

    engine = TesseractCliOcr(
        runtime.executavel,
        language="+".join(runtime.idiomas_selecionados),
        tessdata_directory=runtime.diretorio_tessdata,
    )
    first = engine.consultar_capacidade().capacidade

    assert first is not None
    assert first.idiomas == ("por", "eng")
    assert first.dados_treinados[0].sha256 == pinned_digest
    assert all("--tessdata-dir" not in arguments for arguments, _child in calls)
    assert any(
        child.get(TESSDATA_PREFIX_ENVIRONMENT_VARIABLE) == str(managed.resolve())
        for _arguments, child in calls
    )

    (managed / "por.traineddata").write_bytes(b"different portuguese")
    changed_engine = TesseractCliOcr(
        runtime.executavel,
        language="por+eng",
        tessdata_directory=managed,
    )
    changed = changed_engine.consultar_capacidade().capacidade

    assert changed is not None
    assert first.assinatura() != changed.assinatura()


def test_pinned_artifact_metadata_is_complete() -> None:
    assert len(TESSDATA_FAST_REVISION) == 40
    assert PORTUGUESE_TRAINEDDATA_URL.endswith(f"/{TESSDATA_FAST_REVISION}/por.traineddata")
    assert len(PORTUGUESE_TRAINEDDATA_SHA256) == 64
