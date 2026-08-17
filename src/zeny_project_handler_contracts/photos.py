"""DTOs de fotos gerenciadas."""

from __future__ import annotations

from zeny_project_handler_contracts.base import (
    ContractModel,
    ElementId,
    PhotoId,
    ProjectId,
    UtcDateTime,
)
from zeny_project_handler_contracts.common import FileMetadataDto


class ManagedPhotoDto(ContractModel):
    photo_id: PhotoId
    project_id: ProjectId
    element_id: ElementId
    file: FileMetadataDto
    attached_at: UtcDateTime


class ManagedPhotoListResponse(ContractModel):
    items: tuple[ManagedPhotoDto, ...]


class ManagedPhotoResponse(ContractModel):
    photo: ManagedPhotoDto


class RemoveManagedPhotoResponse(ContractModel):
    photo_id: PhotoId
    removed: bool
