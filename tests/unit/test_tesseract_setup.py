from pathlib import Path

import pytest

from zeny_project_handler import tesseract_setup
from zeny_project_handler.adapters.analysis.tesseract_runtime import (
    DiagnosticoRuntimeOcr,
    RuntimeTesseract,
)
from zeny_project_handler.config import AppSettings


def test_setup_cli_provisions_and_reports_selected_languages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = AppSettings(data_directory=tmp_path / "data")
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"stub")
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    ready = RuntimeTesseract(
        executavel=executable,
        diretorio_tessdata=tessdata,
        idiomas_disponiveis=("eng", "por"),
        idiomas_selecionados=("por", "eng"),
    )
    calls: list[Path] = []

    def provision(data_directory: Path) -> RuntimeTesseract:
        calls.append(data_directory)
        return ready

    monkeypatch.setattr(
        "zeny_project_handler.tesseract_setup.AppSettings.from_environment",
        lambda: settings,
    )
    monkeypatch.setattr(
        tesseract_setup,
        "provision_portuguese_language",
        provision,
    )

    exit_code = tesseract_setup.main(["--provision"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == [settings.data_directory]
    assert "tesseract --list-langs" in output
    assert "por+eng" in output


def test_setup_cli_diagnostic_is_actionable_and_returns_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = AppSettings(data_directory=tmp_path / "data")
    unavailable = RuntimeTesseract(
        executavel=None,
        diretorio_tessdata=None,
        diagnostico=DiagnosticoRuntimeOcr(
            codigo="ocr.tesseract_ausente",
            mensagem="O Tesseract não foi encontrado.",
            remediacao="Execute setup.bat novamente.",
        ),
    )
    monkeypatch.setattr(
        "zeny_project_handler.tesseract_setup.AppSettings.from_environment",
        lambda: settings,
    )
    monkeypatch.setattr(
        tesseract_setup,
        "inspect_tesseract_runtime",
        lambda _data_directory: unavailable,
    )

    exit_code = tesseract_setup.main([])
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "ocr.tesseract_ausente" in output
    assert "REMEDIAÇÃO" in output
    assert "setup.bat" in output
