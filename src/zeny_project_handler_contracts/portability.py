"""DTOs de preflight, confirmação e exportação de projetos portáteis."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from zeny_project_handler_contracts.base import (
    ContractModel,
    NonEmptyString,
    ProjectId,
    ProjectImportPreflightId,
    Sha256,
    UtcDateTime,
)
from zeny_project_handler_contracts.common import PreflightIssueDto
from zeny_project_handler_contracts.enums import IntegrityState, PreflightDisposition


class ProjectImportSummaryDto(ContractModel):
    project_id: ProjectId
    service_note: NonEmptyString
    document_count: int = Field(ge=0)
    page_count: int = Field(ge=0)
    photo_count: int = Field(ge=0)
    replaces_existing: bool


class ProjectImportPreflightResponse(ContractModel):
    preflight_id: ProjectImportPreflightId
    package_sha256: Sha256
    target_fingerprint: Sha256
    disposition: PreflightDisposition
    integrity_state: IntegrityState
    summary: ProjectImportSummaryDto
    issues: tuple[PreflightIssueDto, ...]
    expires_at: UtcDateTime


class ConfirmProjectImportRequest(ContractModel):
    preflight_id: ProjectImportPreflightId
    package_sha256: Sha256
    target_fingerprint: Sha256
    replace_existing: bool
    confirmed: Literal[True]


class ProjectImportAcceptedResponse(ContractModel):
    preflight_id: ProjectImportPreflightId
    accepted: bool
