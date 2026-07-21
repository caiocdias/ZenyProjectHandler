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


def test_domain_does_not_import_frameworks_or_adapters() -> None:
    violations: dict[str, list[str]] = {}

    for source_file in DOMAIN_DIRECTORY.rglob("*.py"):
        forbidden = sorted(imported_root_names(source_file) & FORBIDDEN_IMPORTS)
        if forbidden:
            violations[str(source_file.relative_to(DOMAIN_DIRECTORY))] = forbidden

    assert not violations, f"O domínio possui dependências proibidas: {violations}"
