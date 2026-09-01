"""Restrições de dependência entre as camadas."""

from __future__ import annotations

import ast
from pathlib import Path

DOMAIN_DIRECTORY = Path(__file__).parents[2] / "src" / "zeny_project_handler" / "domain"
FORBIDDEN_IMPORTS = frozenset(
    {
        "PySide6",
        "sqlalchemy",
        "fitz",
        "pymupdf",
        "networkx",
        "cv2",
        "PIL",
    }
)
GMAX_CLIENT_MODULES = (
    Path(__file__).parents[2] / "src" / "zeny_project_handler_client" / "ui" / "gmax_panel.py",
    Path(__file__).parents[2]
    / "src"
    / "zeny_project_handler_client"
    / "ui"
    / "documentation_gateway.py",
)
GMAX_FORBIDDEN_MODULES = (
    "pyodbc",
    "zeny_project_handler.adapters",
    "zeny_project_handler.application",
    "zeny_project_handler.domain",
    "zeny_project_handler.ports",
)


def imported_root_names(source_file: Path) -> set[str]:
    """Colete os módulos raiz importados por um arquivo Python."""
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.partition(".")[0])
    return imported


def imported_module_names(source_file: Path) -> set[str]:
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_domain_does_not_import_frameworks_or_adapters() -> None:
    violations: dict[str, list[str]] = {}

    for source_file in DOMAIN_DIRECTORY.rglob("*.py"):
        forbidden = sorted(imported_root_names(source_file) & FORBIDDEN_IMPORTS)
        if forbidden:
            violations[str(source_file.relative_to(DOMAIN_DIRECTORY))] = forbidden

    assert not violations, f"O domínio possui dependências proibidas: {violations}"


def test_domain_does_not_know_concrete_adapters() -> None:
    violations = {
        str(source_file.relative_to(DOMAIN_DIRECTORY)): sorted(
            module
            for module in imported_module_names(source_file)
            if module.startswith("zeny_project_handler.adapters")
        )
        for source_file in DOMAIN_DIRECTORY.rglob("*.py")
    }

    assert not {key: value for key, value in violations.items() if value}


def test_gmax_client_uses_only_remote_contracts_and_presentation_dependencies() -> None:
    violations = {
        str(source_file.relative_to(Path(__file__).parents[2])): sorted(
            module
            for module in imported_module_names(source_file)
            if module.startswith(GMAX_FORBIDDEN_MODULES)
        )
        for source_file in GMAX_CLIENT_MODULES
    }

    assert not {key: value for key, value in violations.items() if value}
