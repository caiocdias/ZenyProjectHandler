"""Adaptadores do pipeline semântico baseado em regras explícitas."""

from .json_registry import (
    JsonRuleRegistry,
    carregar_registro_regras_inicial,
    carregar_registro_regras_json,
)
from .rule_based import InterpretadorRegrasExplicitas

__all__ = [
    "InterpretadorRegrasExplicitas",
    "JsonRuleRegistry",
    "carregar_registro_regras_inicial",
    "carregar_registro_regras_json",
]
