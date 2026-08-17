"""DTOs transversais de paginação, geometria, integridade e downloads."""

from __future__ import annotations

from pydantic import Field

from zeny_project_handler_contracts.base import (
    ContractModel,
    DecimalString,
    DocumentId,
    DownloadId,
    EvidenceId,
    FileName,
    JobId,
    NonEmptyString,
    PageId,
    Sha256,
    UtcDateTime,
)
from zeny_project_handler_contracts.enums import IssueSeverity, JobKind, JobStatus


class PageMetadataDto(ContractModel):
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)


class NormalizedPointDto(ContractModel):
    x: DecimalString
    y: DecimalString


class NormalizedBoxDto(ContractModel):
    x: DecimalString
    y: DecimalString
    width: DecimalString
    height: DecimalString


class EvidenceNavigationDto(ContractModel):
    evidence_id: EvidenceId | None = None
    document_id: DocumentId
    page_id: PageId
    geometry: NormalizedBoxDto | None = None
    label: str | None = Field(default=None, max_length=500)


class FileMetadataDto(ContractModel):
    display_name: FileName
    mime_type: NonEmptyString
    size_bytes: int = Field(ge=0)
    sha256: Sha256


class DownloadMetadataDto(ContractModel):
    download_id: DownloadId
    file_name: FileName
    mime_type: NonEmptyString
    size_bytes: int = Field(ge=0)
    sha256: Sha256
    expires_at: UtcDateTime


class PreflightIssueDto(ContractModel):
    code: NonEmptyString
    severity: IssueSeverity
    summary: NonEmptyString
    resource_id: str | None = Field(default=None, max_length=200)


class DeletionCountsDto(ContractModel):
    documents: int = Field(default=0, ge=0)
    pages: int = Field(default=0, ge=0)
    analyses: int = Field(default=0, ge=0)
    reviews: int = Field(default=0, ge=0)
    photos: int = Field(default=0, ge=0)


class GlobalOperationDto(ContractModel):
    job_id: JobId
    kind: JobKind
    status: JobStatus
    progress_percent: int = Field(ge=0, le=100)
    message: str | None = Field(default=None, max_length=500)
    updated_at: UtcDateTime


class EmptyResponse(ContractModel):
    acknowledged: bool = True
