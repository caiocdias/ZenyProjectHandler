"""Gates de arquitetura do pacote público de contratos."""

from __future__ import annotations

import ast
import importlib
import pkgutil
import sys
from pathlib import Path

from pydantic import BaseModel

import zeny_project_handler_contracts

CONTRACTS_DIRECTORY = Path(__file__).parents[2] / "src" / "zeny_project_handler_contracts"
SPEC_DIRECTORY = Path(__file__).parents[2] / "src" / "zeny_project_handler_api_spec"
ALLOWED_EXTERNAL_ROOTS = frozenset({"pydantic"})
PROTECTED_ROOTS = frozenset(
    {
        "PySide6",
        "SQLAlchemy",
        "alembic",
        "fitz",
        "pymupdf",
        "tesseract",
        "zeny_project_handler",
    }
)
PROTECTED_SEGMENTS = frozenset({"domain", "application", "adapters", "ports"})


def _imported_modules(source_file: Path) -> set[str]:
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def _contract_model_classes() -> set[type[BaseModel]]:
    classes: set[type[BaseModel]] = set()
    package_path = list(zeny_project_handler_contracts.__path__)
    for module_info in pkgutil.iter_modules(package_path):
        module = importlib.import_module(f"zeny_project_handler_contracts.{module_info.name}")
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, BaseModel)
                and value.__module__ == module.__name__
            ):
                classes.add(value)
    return classes


def test_contracts_import_only_stdlib_pydantic_and_themselves() -> None:
    violations: dict[str, list[str]] = {}
    for source_file in CONTRACTS_DIRECTORY.rglob("*.py"):
        forbidden: list[str] = []
        for module in _imported_modules(source_file):
            root = module.partition(".")[0]
            if (
                root in PROTECTED_ROOTS
                or PROTECTED_SEGMENTS & set(module.split("."))
                or (
                    root not in sys.stdlib_module_names
                    and root not in ALLOWED_EXTERNAL_ROOTS
                    and root != "zeny_project_handler_contracts"
                )
            ):
                forbidden.append(module)
        if forbidden:
            violations[source_file.name] = sorted(forbidden)

    assert not violations, f"Contratos possuem imports protegidos: {violations}"


def test_specification_app_imports_no_product_runtime() -> None:
    violations = {
        source_file.name: sorted(
            module
            for module in _imported_modules(source_file)
            if module.partition(".")[0] == "zeny_project_handler"
        )
        for source_file in SPEC_DIRECTORY.rglob("*.py")
    }
    assert not {key: value for key, value in violations.items() if value}


def test_contracts_define_no_functions_or_business_methods() -> None:
    violations: dict[str, list[str]] = {}
    for source_file in CONTRACTS_DIRECTORY.rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        functions = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        ]
        if functions:
            violations[source_file.name] = sorted(functions)

    assert not violations, f"Contratos contêm comportamento executável: {violations}"


def test_contracts_do_not_expose_paths() -> None:
    source_violations: dict[str, list[int]] = {}
    for source_file in CONTRACTS_DIRECTORY.rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        path_names = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id == "Path"
        ]
        if path_names:
            source_violations[source_file.name] = path_names

    field_violations = {
        f"{model.__module__}.{model.__name__}": sorted(
            field_name for field_name in model.model_fields if "path" in field_name.casefold()
        )
        for model in _contract_model_classes()
    }
    assert not source_violations
    assert not {key: value for key, value in field_violations.items() if value}


def test_every_transport_model_forbids_unknown_fields() -> None:
    violations = {
        f"{model.__module__}.{model.__name__}"
        for model in _contract_model_classes()
        if "root" not in model.model_fields and model.model_config.get("extra") != "forbid"
    }
    assert not violations


def test_every_transport_model_produces_json_schema() -> None:
    schemas = {model.__name__: model.model_json_schema() for model in _contract_model_classes()}
    assert len(schemas) >= 75
    assert all(schema for schema in schemas.values())
