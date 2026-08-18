"""DTOs de sessões temporárias, páginas e raster remoto."""

from __future__ import annotations

from pydantic import Field

from zeny_project_handler_contracts.base import (
    ContractModel,
    DecimalString,
    DocumentId,
    FileName,
    PageId,
    ProjectId,
    Sha256,
    UploadId,
    UtcDateTime,
    ViewerSessionId,
)
from zeny_project_handler_contracts.common import NormalizedBoxDto


class ViewerPageDto(ContractModel):
    page_id: PageId
    document_id: DocumentId
    reading_order: int = Field(ge=0)
    source_page_number: int = Field(ge=1)
    width_points: DecimalString
    height_points: DecimalString
    intrinsic_rotation_degrees: int = Field(ge=0, le=270, multiple_of=90)


class ViewerDocumentDto(ContractModel):
    document_id: DocumentId
    display_name: FileName
    size_bytes: int = Field(ge=1)
    sha256: Sha256
    page_count: int = Field(ge=0)
    pages: tuple[ViewerPageDto, ...]


class ViewerPendingUploadDto(ContractModel):
    upload_id: UploadId
    display_name: FileName
    position: int = Field(ge=0)
    password_attempts_remaining: int = Field(ge=0, le=3)


class CreateViewerSessionResponse(ContractModel):
    viewer_session_id: ViewerSessionId
    documents: tuple[ViewerDocumentDto, ...]
    pending_uploads: tuple[ViewerPendingUploadDto, ...] = ()
    expires_at: UtcDateTime


class UnlockViewerPdfResponse(ContractModel):
    viewer_session_id: ViewerSessionId
    documents: tuple[ViewerDocumentDto, ...]
    pending_uploads: tuple[ViewerPendingUploadDto, ...]
    expires_at: UtcDateTime


class ViewerProjectResponse(ContractModel):
    project_id: ProjectId
    project_version: int = Field(ge=0)
    documents: tuple[ViewerDocumentDto, ...]
    pages: tuple[ViewerPageDto, ...]


class RasterRequestParams(ContractModel):
    dpi: int = Field(ge=1, le=600)
    rotation_degrees: int = Field(default=0, ge=0, le=270, multiple_of=90)
    clip: NormalizedBoxDto | None = None


class RasterMetadataDto(ContractModel):
    page_id: PageId
    pixel_width: int = Field(ge=1)
    pixel_height: int = Field(ge=1)
    page_pixel_width: int = Field(ge=1)
    page_pixel_height: int = Field(ge=1)
    origin_x_pixels: int = Field(ge=0)
    origin_y_pixels: int = Field(ge=0)
    requested_dpi: int = Field(ge=1, le=600)
    effective_dpi: int = Field(ge=1, le=600)
    rotation_degrees: int = Field(ge=0, le=270, multiple_of=90)
    clip: NormalizedBoxDto
    reduced: bool = False
    content_type: str = "image/png"


class CloseViewerSessionResponse(ContractModel):
    viewer_session_id: ViewerSessionId
    closed: bool
