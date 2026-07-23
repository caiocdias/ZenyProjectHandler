"""Adaptadores do registro versionado de regras de conformidade."""

from .json_registry import (
    JsonComplianceRuleRegistry,
    carregar_registro_conformidade_inicial,
    carregar_registro_conformidade_json,
)

__all__ = [
    "JsonComplianceRuleRegistry",
    "carregar_registro_conformidade_inicial",
    "carregar_registro_conformidade_json",
]
