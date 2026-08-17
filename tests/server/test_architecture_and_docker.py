from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
SERVER_SOURCE = ROOT / "src" / "zeny_project_handler_server"


def _imported_modules(source_file: Path) -> set[str]:
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_server_package_does_not_import_qt_ui_or_desktop_bootstrap() -> None:
    violations: dict[str, list[str]] = {}
    for source_file in SERVER_SOURCE.rglob("*.py"):
        forbidden = sorted(
            module
            for module in _imported_modules(source_file)
            if module.partition(".")[0] == "PySide6"
            or module == "zeny_project_handler.bootstrap"
            or module.startswith("zeny_project_handler.ui")
        )
        if forbidden:
            violations[source_file.name] = forbidden

    assert not violations


def test_docker_build_is_multistage_non_root_with_ocr_and_no_build_secret() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    normalized = dockerfile.casefold()

    assert len(re.findall(r"^FROM ", dockerfile, flags=re.MULTILINE)) >= 2
    assert "tesseract-ocr" in normalized
    assert "tesseract-ocr-por" in normalized
    assert re.search(r"^USER\s+(?!root\b)\S+", dockerfile, flags=re.MULTILINE)
    assert "healthcheck" in normalized
    assert "arg zeny_server_password" not in normalized
    assert not re.search(r"^ENV\s+.*ZENY_SERVER_PASSWORD", dockerfile, flags=re.MULTILINE)
    assert "copy .env" not in normalized
    assert "--workers" not in normalized


def test_compose_injects_secret_at_runtime_and_mounts_persistent_data() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "${ZENY_SERVER_PASSWORD:" in compose
    assert "ZENY_SERVER_PASSWORD" not in (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "zeny-data:/data" in compose
    assert "target: runtime" in compose
    assert "healthcheck:" in compose
    assert "down -v" not in compose


def test_docker_context_and_server_lock_exclude_local_secret_and_qt() -> None:
    ignored = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    server_lock = (ROOT / "requirements-server.lock").read_text(encoding="utf-8")
    aggregate_lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    development_lock = (ROOT / "requirements-development.lock").read_text(encoding="utf-8")

    assert ".env" in ignored
    assert "pyside" not in server_lock.casefold()
    assert "-r requirements-development.lock" in aggregate_lock
    assert "-r requirements-client.lock" in development_lock
    assert "-r requirements-server.lock" in development_lock
