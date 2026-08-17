"""Contratos públicos e versionados da API do Zeny Project Handler."""

from zeny_project_handler_contracts.base import ContractModel, ContractRootModel
from zeny_project_handler_contracts.versioning import (
    API_COMPATIBILITY_POLICY,
    API_V1_PREFIX,
    API_VERSION,
    MAX_COMPATIBLE_API_VERSION,
    MIN_COMPATIBLE_API_VERSION,
)

__all__ = [
    "API_COMPATIBILITY_POLICY",
    "API_V1_PREFIX",
    "API_VERSION",
    "MAX_COMPATIBLE_API_VERSION",
    "MIN_COMPATIBLE_API_VERSION",
    "ContractModel",
    "ContractRootModel",
]
