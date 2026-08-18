from __future__ import annotations

import ast
from pathlib import Path

PANEL_MODULES = (
    Path("src/zeny_project_handler/ui/project_gateway.py"),
    Path("src/zeny_project_handler/ui/project_panel.py"),
)
FORBIDDEN_MODULES = (
    "fitz",
    "pymupdf",
    "zeny_project_handler.application",
    "zeny_project_handler.domain",
    "zeny_project_handler.adapters",
    "zeny_project_handler.ports",
)


def test_project_panel_boundary_has_only_http_dtos_and_presentation_imports() -> None:
    violations: list[str] = []
    for path in PANEL_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for module in _imported_modules(node):
                if module.startswith(FORBIDDEN_MODULES):
                    violations.append(f"{path}:{getattr(node, 'lineno', '?')}: {module}")

    assert violations == []


def _imported_modules(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(item.name for item in node.names)
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return (node.module,)
    return ()
