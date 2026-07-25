import json
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]


def script_text(file_name: str) -> str:
    return (PROJECT_ROOT / file_name).read_text(encoding="utf-8")


def test_setup_creates_venv_and_installs_locked_dependencies() -> None:
    setup_script = script_text("setup.bat")

    assert "-m venv" in setup_script
    assert "requirements.lock" in setup_script
    assert "--no-build-isolation --no-deps -e" in setup_script
    assert "ZENY_BOOTSTRAP_PYTHON" in setup_script


def test_setup_recreates_incompatible_existing_venv() -> None:
    setup_script = script_text("setup.bat")
    configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "ensure_supported_python" in setup_script
    assert "sys.version_info[:2] in ((3, 11), (3, 12), (3, 13))" in setup_script
    assert configuration["project"]["requires-python"] == ">=3.11,<3.14"
    assert 'rmdir /s /q "%VENV_DIR%"' in setup_script
    assert "Ambiente virtual existente usa uma versao de Python incompativel" in setup_script


def test_setup_installs_and_validates_tesseract_ocr() -> None:
    setup_script = script_text("setup.bat")

    assert "ensure_tesseract" in setup_script
    assert "UB-Mannheim.TesseractOCR" in setup_script
    assert "--accept-package-agreements --accept-source-agreements" in setup_script
    assert "ZENY_TESSERACT_PATH" in setup_script
    assert "ocr_dependency_error" in setup_script


def test_launcher_activates_venv_and_runs_application() -> None:
    launcher_script = script_text("ZenyProjectHandler.bat")

    assert "activate.bat" in launcher_script
    assert "python -m zeny_project_handler" in launcher_script
    assert "%*" in launcher_script


def test_quality_script_enforces_coverage_and_records_metrics() -> None:
    quality_script = script_text("IniciarTestes.bat")
    configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "relatorio-testes.txt" in quality_script
    assert "pytest --cov" in quality_script
    assert "radon cc" in quality_script
    assert "radon mi" in quality_script
    assert "radon raw" in quality_script
    assert configuration["tool"]["coverage"]["report"]["fail_under"] > 85


def test_real_pdf_samples_are_ignored_and_have_an_anonymous_manifest() -> None:
    ignore_rules = script_text(".gitignore")
    manifest_path = PROJECT_ROOT / "evaluation" / "manifesto-amostras.json"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    samples = manifest["samples"]

    assert "examples/**/*.pdf" in ignore_rules
    assert "evaluation/annotations/" in ignore_rules
    assert manifest["sensitive_source_files"] is True
    assert manifest["pdf_count"] == len(samples) == 9
    assert {sample["split"] for sample in samples} == {"DESENVOLVIMENTO", "TESTE"}
    assert len({sample["id"] for sample in samples}) == len(samples)
    assert all(len(sample["sha256"]) == 64 for sample in samples)
    assert "file_name" not in manifest_text
