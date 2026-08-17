"""DTOs de preflight, criação e restauração de backup."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from zeny_project_handler_contracts.base import (
    BackupPreflightId,
    BackupRestorePreflightId,
    ContractModel,
    ProjectId,
    Sha256,
    UtcDateTime,
)
from zeny_project_handler_contracts.common import PreflightIssueDto
from zeny_project_handler_contracts.enums import IntegrityState, PreflightDisposition


class BackupPreflightResponse(ContractModel):
    preflight_id: BackupPreflightId
    source_fingerprint: Sha256
    disposition: PreflightDisposition
    integrity_state: IntegrityState
    project_count: int = Field(ge=0)
    document_count: int = Field(ge=0)
    issues: tuple[PreflightIssueDto, ...]
    expires_at: UtcDateTime


class CreateBackupJobRequest(ContractModel):
    preflight_id: BackupPreflightId
    source_fingerprint: Sha256
    accept_degraded: bool
    confirmed: Literal[True]


class BackupRestoreSummaryDto(ContractModel):
    project_ids: tuple[ProjectId, ...]
    document_count: int = Field(ge=0)
    photo_count: int = Field(ge=0)
    integrity_state: IntegrityState


class BackupRestorePreflightResponse(ContractModel):
    preflight_id: BackupRestorePreflightId
    package_sha256: Sha256
    target_fingerprint: Sha256
    disposition: PreflightDisposition
    summary: BackupRestoreSummaryDto
    issues: tuple[PreflightIssueDto, ...]
    expires_at: UtcDateTime


class ConfirmBackupRestoreRequest(ContractModel):
    preflight_id: BackupRestorePreflightId
    package_sha256: Sha256
    target_fingerprint: Sha256
    accept_degraded: bool
    confirmed: Literal[True]


class BackupRestoreAcceptedResponse(ContractModel):
    preflight_id: BackupRestorePreflightId
    accepted: bool
