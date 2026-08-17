"""DTOs de criação, acompanhamento, resultado e cancelamento de jobs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue

from zeny_project_handler_contracts.base import ContractModel, JobId, ProjectId, UtcDateTime
from zeny_project_handler_contracts.common import DownloadMetadataDto
from zeny_project_handler_contracts.enums import JobKind, JobStatus
from zeny_project_handler_contracts.errors import ErrorEnvelope


class CreateAnalysisJobRequest(ContractModel):
    force_reanalysis: bool = False
    expected_project_version: int = Field(ge=0)


class CreateComplianceJobRequest(ContractModel):
    expected_semantic_signature: str = Field(min_length=1, max_length=200)


class CreateExportJobRequest(ContractModel):
    expected_project_version: int = Field(ge=0)


class JobAcceptedResponse(ContractModel):
    job_id: JobId
    kind: JobKind
    status: Literal[JobStatus.QUEUED]
    poll_after_ms: int = Field(ge=250, le=500)


class JobStatusResponse(ContractModel):
    job_id: JobId
    project_id: ProjectId | None = None
    kind: JobKind
    status: JobStatus
    progress_percent: int = Field(ge=0, le=100)
    message: str | None = Field(default=None, max_length=500)
    result_available: bool
    created_at: UtcDateTime
    updated_at: UtcDateTime
    error: ErrorEnvelope | None = None


class JobResultResponse(ContractModel):
    job_id: JobId
    status: JobStatus
    result: dict[str, JsonValue] | None = None
    download: DownloadMetadataDto | None = None


class CancelJobResponse(ContractModel):
    job_id: JobId
    status: JobStatus
    cancellation_requested: bool
