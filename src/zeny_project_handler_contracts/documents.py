"""DTOs de upload, preflight, desbloqueio e ordenação de documentos."""

from __future__ import annotations

from pydantic import Field

from zeny_project_handler_contracts.base import (
    ContractModel,
    DecimalString,
    DocumentId,
    FileName,
    NonEmptyString,
    PageId,
    ProjectId,
    Sha256,
    UploadId,
    UtcDateTime,
)
from zeny_project_handler_contracts.common import FileMetadataDto, PreflightIssueDto
from zeny_project_handler_contracts.enums import PreflightDisposition, UploadState


class PageSummaryDto(ContractModel):
    page_id: PageId
    document_id: DocumentId
    reading_order: int = Field(ge=0)
    source_page_number: int = Field(ge=1)
    width_points: DecimalString
    height_points: DecimalString
    intrinsic_rotation_degrees: int = Field(ge=0, le=270, multiple_of=90)


class DocumentSummaryDto(ContractModel):
    document_id: DocumentId
    project_id: ProjectId
    file: FileMetadataDto
    page_count: int = Field(ge=0)
    imported_at: UtcDateTime


class DocumentUploadPreflightDto(ContractModel):
    disposition: PreflightDisposition
    password_required: bool
    duplicate_content: bool
    detected_page_count: int | None = Field(default=None, ge=0)
    issues: tuple[PreflightIssueDto, ...] = ()


class CreateUploadResponse(ContractModel):
    upload_id: UploadId
    state: UploadState
    display_name: FileName
    size_received: int = Field(ge=0)
    sha256: Sha256
    preflight: DocumentUploadPreflightDto


class UnlockPdfRequest(ContractModel):
    password: str = Field(min_length=1, max_length=512, repr=False)


class DocumentImportResultDto(ContractModel):
    upload_id: UploadId
    state: UploadState
    document: DocumentSummaryDto | None = None
    pages: tuple[PageSummaryDto, ...] = ()
    password_attempts_remaining: int | None = Field(default=None, ge=0, le=3)
    warnings: tuple[NonEmptyString, ...] = ()


class ReplacePageOrderRequest(ContractModel):
    page_ids: tuple[PageId, ...] = Field(min_length=1)
    expected_project_version: int = Field(ge=0)


class PageOrderResponse(ContractModel):
    project_id: ProjectId
    project_version: int = Field(ge=0)
    pages: tuple[PageSummaryDto, ...]


class RemoveDocumentResponse(ContractModel):
    project_id: ProjectId
    document_id: DocumentId
    removed: bool
    removed_page_count: int = Field(ge=0)
    project_version: int = Field(ge=0)
