"""DTOs de saúde, sessão, prontidão e capacidades."""

from __future__ import annotations

from pydantic import Field

from zeny_project_handler_contracts.base import ContractModel, NonEmptyString, UtcDateTime
from zeny_project_handler_contracts.common import GlobalOperationDto
from zeny_project_handler_contracts.enums import OcrStatus


class HealthLiveResponse(ContractModel):
    live: bool


class OcrDiagnosticDto(ContractModel):
    status: OcrStatus
    engine: str | None = Field(default=None, max_length=100)
    language: str | None = Field(default=None, max_length=50)
    message: NonEmptyString


class SessionCapabilitiesResponse(ContractModel):
    server_version: NonEmptyString
    api_version: NonEmptyString
    min_compatible_api_version: NonEmptyString
    max_compatible_api_version: NonEmptyString
    ready: bool
    capabilities: tuple[NonEmptyString, ...]
    ocr: OcrDiagnosticDto
    global_operation: GlobalOperationDto | None = None
    server_time: UtcDateTime
