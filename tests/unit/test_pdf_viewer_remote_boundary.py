from __future__ import annotations

import ast
from pathlib import Path

VIEWER_MODULES = (
    Path("src/zeny_project_handler/ui/pdf_gateway.py"),
    Path("src/zeny_project_handler/ui/pdf_rendering.py"),
    Path("src/zeny_project_handler/ui/pdf_viewer.py"),
)
FORBIDDEN_MODULES = (
    "fitz",
    "pymupdf",
    "zeny_project_handler.adapters.pdf",
    "zeny_project_handler.ports.pdf",
)


def test_client_viewer_boundary_has_no_pdf_engine_or_local_reader_imports() -> None:
    violations: list[str] = []
    for path in VIEWER_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported = _imported_modules(node)
            for module in imported:
                if module.startswith(FORBIDDEN_MODULES):
                    violations.append(f"{path}:{getattr(node, 'lineno', '?')}: {module}")

    assert violations == []


def _imported_modules(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(item.name for item in node.names)
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return (node.module,)
    return ()
