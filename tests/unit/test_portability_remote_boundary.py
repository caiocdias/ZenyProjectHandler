from __future__ import annotations

import ast
from pathlib import Path

CLIENT_MODULES = (
    Path("src/zeny_project_handler/ui/portability_gateway.py"),
    Path("src/zeny_project_handler/ui/portability_panel.py"),
    Path("src/zeny_project_handler/ui/portability_worker.py"),
)
FORBIDDEN_MODULES = (
    "sqlite3",
    "zipfile",
    "zeny_project_handler.application",
    "zeny_project_handler.domain",
    "zeny_project_handler.adapters",
    "zeny_project_handler.ports",
)
FORBIDDEN_NAMES = (
    "ServicoPortabilidadeProjeto",
    "SqliteBackupManager",
    "SqlitePortableProjectDatabase",
    "ZipProjectArchive",
)


def test_portability_client_boundary_has_only_transport_dtos_and_presentation() -> None:
    violations: list[str] = []
    source = ""
    for path in CLIENT_MODULES:
        contents = path.read_text(encoding="utf-8")
        source += contents
        tree = ast.parse(contents, filename=str(path))
        for node in ast.walk(tree):
            for module in _imported_modules(node):
                if module.startswith(FORBIDDEN_MODULES):
                    violations.append(f"{path}:{getattr(node, 'lineno', '?')}: {module}")

    assert violations == []
    assert all(name not in source for name in FORBIDDEN_NAMES)


def _imported_modules(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(item.name for item in node.names)
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return (node.module,)
    return ()
