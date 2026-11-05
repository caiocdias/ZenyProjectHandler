import re
import subprocess
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]


def script_text(file_name: str) -> str:
    return (PROJECT_ROOT / file_name).read_text(encoding="utf-8")


def test_setup_creates_venv_and_installs_locked_development_environment() -> None:
    setup_script = script_text("setup.bat")

    assert "where docker" in setup_script
    assert "docker compose version" in setup_script
    assert "-m venv" in setup_script
    assert "requirements-development.lock" in setup_script
    assert "requirements.lock" not in setup_script
    assert "--no-build-isolation --no-deps -e" in setup_script
    assert '"%CD%"' in setup_script
    assert "ZENY_BOOTSTRAP_PYTHON" in setup_script


def test_setup_recreates_incompatible_existing_venv() -> None:
    setup_script = script_text("setup.bat")
    configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "ensure_supported_python" in setup_script
    assert "sys.version_info[:2] in ((3, 11), (3, 12), (3, 13))" in setup_script
    assert configuration["project"]["requires-python"] == ">=3.11,<3.14"
    assert 'rmdir /s /q "%VENV_DIR%"' in setup_script
    assert "Ambiente virtual existente usa uma versao de Python incompativel" in setup_script


def test_setup_uses_the_aggregate_development_lock_without_managing_ocr() -> None:
    setup_script = script_text("setup.bat")

    assert "TesseractOCR" not in setup_script
    assert "ZENY_TESSERACT_PATH" not in setup_script
    assert "tesseract_setup" not in setup_script
    assert "requirements-client.lock" not in setup_script
    assert "requirements-server.lock" not in setup_script


def test_setup_installs_and_validates_the_editable_root_project() -> None:
    setup_script = script_text("setup.bat")

    application_install = setup_script.index(
        'python -m pip install --disable-pip-version-check --no-build-isolation --no-deps -e "%CD%"'
    )
    python_validation = setup_script.index("python -m pip check")

    assert application_install < python_validation
    assert "cliente, servidor, Docker e ferramentas de qualidade" in setup_script


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


def test_sql_server_driver_provenance_is_pinned_and_documented() -> None:
    dockerfile = script_text("Dockerfile")
    notices = script_text("THIRD_PARTY_NOTICES.md")
    release_builder = script_text("scripts/build_release.py")
    release_gate = script_text("scripts/release_artifact_gate.py")
    client_gate = script_text("scripts/client_artifact_gate.py")
    server_lock = script_text("requirements-server.lock")
    locked_components = {
        line.partition("==")[0]
        for line in server_lock.splitlines()
        if line and not line.startswith("#")
    }

    assert "pyodbc==5.3.0" in server_lock
    assert "pyodbc" in locked_components
    assert "pyodbc" in release_gate
    assert '"--pyinstaller-python"' in release_builder
    assert '"--pyinstaller-python"' in release_gate
    assert '"--pyinstaller-python"' in client_gate
    assert '_locked_components(ROOT / "requirements-server.lock")' in release_builder
    assert "msodbcsql18=18.6.2.1-1" in dockerfile
    assert "unixodbc=2.3.11-2+deb12u1" in dockerfile
    for component in ("pyodbc", "msodbcsql18", "unixODBC"):
        assert component in notices
        assert component.casefold() in release_gate.casefold()
    for native_component in ("msodbcsql18", "unixodbc"):
        assert native_component in release_builder
    for license_name in (
        "MIT-0",
        "End User License Agreement",
        "LGPL-2.1-or-later",
        "GPL-2.0-or-later",
    ):
        assert license_name in notices


def test_launcher_runs_ephemeral_docker_server_and_stops_it_after_the_client() -> None:
    launcher_script = script_text("ZenyProjectHandler.bat")
    local_compose = script_text("compose.local.yaml")
    development_client = script_text("scripts/run_development_client.py")
    docker_ignore = script_text(".dockerignore")

    assert "docker info" in launcher_script
    assert "compose.local.yaml" in launcher_script
    assert "docker compose" in launcher_script
    assert '"%ZENY_LOCAL_COMPOSE_FILE%" build' in launcher_script
    assert " up --no-build --force-recreate --remove-orphans" in launcher_script
    assert " up --no-build --force-recreate --remove-orphans -d" not in launcher_script
    assert "scripts\\run_development_client.py" in launcher_script
    assert "%*" in launcher_script
    assert "ZENY_CLIENT_SERVER_URL=http://127.0.0.1:8000" in launcher_script
    assert "[Guid]::NewGuid()" in launcher_script
    assert 'set "ZENY_SERVER_PASSWORD=%%S"' in launcher_script
    assert "ZENY_LOCAL_SESSION_DIR=%TEMP%" in launcher_script
    assert "ZENY_DATA_DIR=%ZENY_LOCAL_SESSION_DIR%\\client" in launcher_script
    assert "down --volumes --remove-orphans" in launcher_script
    assert "/data:rw" in local_compose
    assert "tmpfs:" in local_compose
    assert 'restart: "no"' in local_compose
    assert "zeny-data" not in local_compose
    assert "*.bat" in docker_ignore
    assert 'os.environ.pop("ZENY_SERVER_PASSWORD", "")' in development_client
    assert 'os.environ.pop("ZENY_MARKET_SQLSERVER_CONNECTION_STRING", None)' in (development_client)
    assert 'os.environ.pop("ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS", None)' in (development_client)
    assert "dialog.password_input.setText(server_password)" in development_client
    assert "_wait_until_ready" in development_client
    assert "_discard_client_data" in development_client
    assert launcher_script.index('"%ZENY_LOCAL_COMPOSE_FILE%" build') < launcher_script.index(
        "scripts\\run_development_client.py"
    )


def test_only_batch_launcher_exists_for_local_execution() -> None:
    assert (PROJECT_ROOT / "ZenyProjectHandler.bat").is_file()
    assert not (PROJECT_ROOT / "ZenyProjectHandler.vbs").exists()


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


def test_quality_script_runs_pytest_in_parallel_with_combined_coverage() -> None:
    quality_script = script_text("IniciarTestes.bat")
    configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert re.search(r"python -m pytest -n (auto|\d+)\b", quality_script)
    assert "--cov-fail-under=85.01" in quality_script
    assert "--durations=15" in quality_script
    addopts = configuration["tool"]["pytest"]["ini_options"]["addopts"].split()
    assert not any(
        item == "-n" or item.startswith(("-n", "--numprocesses", "--dist")) for item in addopts
    )


def test_quality_script_pytest_invocation_itself_is_parallel_with_the_required_flags() -> None:
    # O eco "Comando:" do relatorio nao executa nada: o que vale e a linha real.
    lines = script_text("IniciarTestes.bat").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("python -m pytest")]
    assert len(starts) == 1
    invocation = lines[starts[0]]
    position = starts[0]
    while invocation.rstrip().endswith("^"):
        position += 1
        invocation = invocation.rstrip()[:-1] + " " + lines[position].strip()
    tokens = invocation.split()

    assert "-n" in tokens
    workers = tokens[tokens.index("-n") + 1]
    assert workers == "auto" or int(workers) >= 2
    assert "--cov" in tokens
    assert "--cov-fail-under=85.01" in tokens
    assert "--durations=15" in tokens
    echoed = [line for line in lines if "echo Comando: python -m pytest" in line]
    assert len(echoed) == 1
    assert f"-n {workers}" in echoed[0]


def test_xdist_is_a_dev_dependency_pinned_in_the_development_lock() -> None:
    configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    development_extra = configuration["project"]["optional-dependencies"]["dev"]
    development_lock = script_text("requirements-development.lock")

    assert "pytest-xdist>=3.8,<4" in development_extra
    assert "pytest-xdist==3.8.0" in development_lock
    assert "execnet==" in development_lock
    for runtime_lock in ("requirements-client.lock", "requirements-server.lock"):
        runtime_text = script_text(runtime_lock)
        assert "pytest-xdist" not in runtime_text
        assert "execnet" not in runtime_text


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
