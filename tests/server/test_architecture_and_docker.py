from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
SERVER_SOURCE = ROOT / "src" / "zeny_project_handler_server"
DOCUMENTATION_CLIENT_SOURCES = (
    ROOT / "src" / "zeny_project_handler_client" / "ui" / "documentation_panel.py",
    ROOT / "src" / "zeny_project_handler_client" / "ui" / "documentation_gateway.py",
)


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
            or module.startswith("zeny_project_handler_client.ui")
        )
        if forbidden:
            violations[source_file.name] = forbidden

    assert not violations


def test_legacy_monolithic_entrypoints_and_ui_adapters_are_absent() -> None:
    core = ROOT / "src" / "zeny_project_handler"
    forbidden = (
        core / "__main__.py",
        core / "bootstrap.py",
        core / "windows_app_identity.py",
        core / "ui" / "pdf_credentials.py",
        core / "ui" / "compliance_presentation.py",
        core / "application" / "compliance_presentation.py",
    )

    assert not tuple(path for path in forbidden if path.exists())


def test_documentation_client_depends_only_on_dtos_gateway_and_qt() -> None:
    protected_prefixes = (
        "zeny_project_handler.adapters",
        "zeny_project_handler.application",
        "zeny_project_handler.domain",
        "zeny_project_handler.ports",
    )
    violations = {
        source_file.name: sorted(
            module
            for module in _imported_modules(source_file)
            if module.startswith(protected_prefixes)
        )
        for source_file in DOCUMENTATION_CLIENT_SOURCES
    }
    assert not {name: modules for name, modules in violations.items() if modules}

    client_source = "\n".join(
        source_file.read_text(encoding="utf-8") for source_file in DOCUMENTATION_CLIENT_SOURCES
    )
    forbidden_payload_names = (
        "regras-conformidade-iniciais.json",
        "catalogo-regras-conformidade.md",
        "projetar_callouts_conformidade",
        "analisar_conformidade_projeto",
    )
    assert all(name not in client_source for name in forbidden_payload_names)


def test_docker_build_is_multistage_non_root_with_ocr_and_no_build_secret() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    normalized = dockerfile.casefold()

    pinned_from_lines = re.findall(
        r"^FROM\s+\S+@sha256:[0-9a-f]{64}(?:\s+AS\s+\S+)?$",
        dockerfile,
        flags=re.MULTILINE,
    )
    assert len(pinned_from_lines) == 2
    assert re.search(
        r"^# syntax=docker/dockerfile:1@sha256:[0-9a-f]{64}$",
        dockerfile,
        flags=re.MULTILINE,
    )
    assert "tesseract-ocr" in normalized
    assert "tesseract-ocr-por" in normalized
    assert "msodbcsql18=18.6.2.1-1" in normalized
    assert "unixodbc=2.3.11-2+deb12u1" in normalized
    assert "8434dcb8c346dc95fbd63dbece056c343704590b58b6a5c323d39acf52bf0b48" in normalized
    assert "accept_eula=y" in normalized
    assert re.search(r"^USER\s+(?!root\b)\S+", dockerfile, flags=re.MULTILINE)
    assert "healthcheck" in normalized
    assert "arg zeny_server_password" not in normalized
    assert not re.search(r"^ENV\s+.*ZENY_SERVER_PASSWORD", dockerfile, flags=re.MULTILINE)
    assert "copy .env" not in normalized
    assert "--workers" not in normalized
    assert "copy src ./src" not in normalized
    assert "src/zeny_project_handler_client" not in normalized
    assert "server/pyproject.toml" in normalized
    assert "user 10001:10001" in normalized
    assert "rm -rf /wheels requirements-server.lock" in normalized


def test_server_distribution_manifest_excludes_client_package() -> None:
    manifest = (ROOT / "server" / "pyproject.toml").read_text(encoding="utf-8").casefold()

    assert 'name = "zeny-project-handler-server"' in manifest
    assert 'exclude = ["zeny_project_handler_client*"]' in manifest
    assert "pyside6" not in manifest


def test_compose_injects_secret_at_runtime_and_mounts_persistent_data() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "${ZENY_SERVER_PASSWORD:" in compose
    assert "ZENY_SERVER_PASSWORD" not in (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "zeny-data:/data" in compose
    assert "target: runtime" in compose
    assert "healthcheck:" in compose
    assert "down -v" not in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose and "- ALL" in compose
    assert "pids_limit:" in compose
    assert "mem_limit:" in compose
    assert "${ZENY_SERVER_BIND_ADDRESS:-127.0.0.1}" in compose


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
    assert "pyodbc==5.3.0" in server_lock
    assert "-r requirements-development.lock" in aggregate_lock
    assert "-r requirements-client.lock" in development_lock
    assert "-r requirements-server.lock" in development_lock
