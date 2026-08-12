"""Adaptadores do registro versionado de regras de conformidade."""

from .json_registry import (
    JsonComplianceRuleRegistry,
    carregar_registro_conformidade_inicial,
    carregar_registro_conformidade_json,
    carregar_registro_conformidade_json_com_avisos,
    carregar_registro_conformidade_texto,
    registro_conformidade_de_dict,
    registro_conformidade_e_avisos_de_dict,
    registro_conformidade_para_dict,
)

__all__ = [
    "JsonComplianceRuleRegistry",
    "carregar_registro_conformidade_inicial",
    "carregar_registro_conformidade_json",
    "carregar_registro_conformidade_json_com_avisos",
    "carregar_registro_conformidade_texto",
    "registro_conformidade_de_dict",
    "registro_conformidade_e_avisos_de_dict",
    "registro_conformidade_para_dict",
]
