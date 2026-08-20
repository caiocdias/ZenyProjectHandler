from __future__ import annotations

import ast
from pathlib import Path

REVIEW_CLIENT_MODULES = (
    Path("src/zeny_project_handler_client/ui/review_gateway.py"),
    Path("src/zeny_project_handler_client/ui/review_panel.py"),
)
FORBIDDEN_MODULES = (
    "zeny_project_handler.application",
    "zeny_project_handler.domain",
    "zeny_project_handler.adapters",
    "zeny_project_handler.ports",
    "zeny_project_handler_server",
)
FORBIDDEN_BUSINESS_NAMES = {
    "ServicoRevisaoHumana",
    "agrupar_regioes_da_analise",
    "detectar_vaos",
    "prover_fatos_regionais",
    "prover_fatos_vaos",
}


def test_review_panel_boundary_has_only_http_dtos_and_presentation_logic() -> None:
    violations: list[str] = []
    for path in REVIEW_CLIENT_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for module in _imported_modules(node):
                if module.startswith(FORBIDDEN_MODULES):
                    violations.append(f"{path}:{getattr(node, 'lineno', '?')}: {module}")
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_BUSINESS_NAMES:
                violations.append(f"{path}:{node.lineno}: {node.id}")

    assert violations == []


def _imported_modules(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(item.name for item in node.names)
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return (node.module,)
    return ()
