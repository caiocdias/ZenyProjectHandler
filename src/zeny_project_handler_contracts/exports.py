"""Contratos dos arquivos finais exportados para o usuário."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from zeny_project_handler_contracts.base import CalloutId, ContractModel
from zeny_project_handler_contracts.common import NormalizedBoxDto


class DeliverableExportKind(StrEnum):
    ANNOTATED_PDF = "ANNOTATED_PDF"
    RESULTS_XLSX = "RESULTS_XLSX"
    DOCUMENTATION_XLSX = "DOCUMENTATION_XLSX"
    COMPLIANCE_XLSX = "COMPLIANCE_XLSX"


class CalloutPositionOverrideDto(ContractModel):
    callout_id: CalloutId
    box: NormalizedBoxDto


class CreateDeliverableExportRequest(ContractModel):
    kind: DeliverableExportKind
    expected_project_version: int = Field(ge=0)
    callout_positions: tuple[CalloutPositionOverrideDto, ...] = ()
