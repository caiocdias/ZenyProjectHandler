import subprocess
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]


def script_text(file_name: str) -> str:
    return (PROJECT_ROOT / file_name).read_text(encoding="utf-8")


def test_setup_creates_venv_and_installs_locked_dependencies() -> None:
    setup_script = script_text("setup.bat")

    assert "-m venv" in setup_script
    assert "requirements-client.lock" in setup_script
    assert "requirements.lock" not in setup_script
    assert "--no-build-isolation --no-deps -e" in setup_script
    assert '"%CD%\\client"' in setup_script
    assert "ZENY_BOOTSTRAP_PYTHON" in setup_script


def test_setup_recreates_incompatible_existing_venv() -> None:
    setup_script = script_text("setup.bat")
    configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "ensure_supported_python" in setup_script
    assert "sys.version_info[:2] in ((3, 11), (3, 12), (3, 13))" in setup_script
    assert configuration["project"]["requires-python"] == ">=3.11,<3.14"
    assert 'rmdir /s /q "%VENV_DIR%"' in setup_script
    assert "Ambiente virtual existente usa uma versao de Python incompativel" in setup_script


def test_setup_excludes_server_and_ocr_dependencies() -> None:
    setup_script = script_text("setup.bat")

    assert "TesseractOCR" not in setup_script
    assert "ZENY_TESSERACT_PATH" not in setup_script
    assert "tesseract_setup" not in setup_script
    assert "requirements-server.lock" not in setup_script


def test_setup_installs_and_validates_only_the_independent_client() -> None:
    setup_script = script_text("setup.bat")

    application_install = setup_script.index(
        "python -m pip install --disable-pip-version-check "
        '--no-build-isolation --no-deps -e "%CD%\\client"'
    )
    python_validation = setup_script.index("python -m pip check")

    assert application_install < python_validation
    assert "sem dependencias do servidor ou OCR local" in setup_script


def test_portuguese_tessdata_provenance_is_pinned_and_documented() -> None:
    from zeny_project_handler.adapters.analysis.tesseract_runtime import (
        PORTUGUESE_TRAINEDDATA_SHA256,
        TESSDATA_FAST_REVISION,
    )

    readme = script_text("README.md")
    notices = script_text("THIRD_PARTY_NOTICES.md")
    runtime_source = script_text("src/zeny_project_handler/adapters/analysis/tesseract_runtime.py")

    for document in (readme, notices, runtime_source):
        assert TESSDATA_FAST_REVISION in document
        assert PORTUGUESE_TRAINEDDATA_SHA256 in document
    assert "Apache-2.0" in notices
    assert "tesseract-ocr/tessdata_fast" in notices


def test_launcher_activates_venv_and_runs_application() -> None:
    launcher_script = script_text("ZenyProjectHandler.bat")

    assert "activate.bat" in launcher_script
    assert "python -m zeny_project_handler_client" in launcher_script
    assert "%*" in launcher_script


def test_quality_script_enforces_the_relevant_quality_gates() -> None:
    quality_script = script_text("IniciarTestes.bat")
    configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "relatorio-testes.txt" in quality_script
    assert "python -m pytest" in quality_script
    assert "--cov" in quality_script
    assert "private_samples" not in quality_script
    assert "python scripts\\complexity_gate.py src" in quality_script
    assert "python scripts\\client_artifact_gate.py --source-only" in quality_script
    assert "radon mi" not in quality_script
    assert "radon raw" not in quality_script
    assert configuration["tool"]["coverage"]["report"]["fail_under"] > 85
    warning_filters = configuration["tool"]["pytest"]["ini_options"]["filterwarnings"]
    assert "error::ResourceWarning" in warning_filters
    assert "error::pytest.PytestUnraisableExceptionWarning" in warning_filters
    assert not any(
        item.startswith("ignore") and "ResourceWarning" in item for item in warning_filters
    )


def test_quality_gate_has_no_private_corpus_branch() -> None:
    configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    registered_markers = configuration["tool"]["pytest"]["ini_options"]["markers"]

    assert not (PROJECT_ROOT / "IniciarTestesPrivados.bat").exists()
    assert not tuple((PROJECT_ROOT / "tests" / "private_samples").glob("test_*.py"))
    assert not any(marker.startswith("private_samples:") for marker in registered_markers)


def test_examples_are_local_only_and_never_part_of_the_quality_gate() -> None:
    ignore_rules = script_text(".gitignore")
    quality_script = script_text("IniciarTestes.bat")
    tracked = subprocess.run(
        ["git", "ls-files", "--", "examples"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert "examples/**" in ignore_rules
    assert "!examples/README.md" in ignore_rules
    assert tracked == ["examples/README.md"]
    assert "examples" not in quality_script.casefold()
