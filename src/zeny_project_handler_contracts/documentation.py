"""Projeções documentais normalizadas."""

from __future__ import annotations

from pydantic import Field

from zeny_project_handler_contracts.base import (
    ContractModel,
    DecimalString,
    DocumentId,
    NonEmptyString,
    PageId,
    ProjectId,
)
from zeny_project_handler_contracts.common import EvidenceNavigationDto
from zeny_project_handler_contracts.enums import DocumentationFieldStatus


class DocumentFieldDto(ContractModel):
    field_key: NonEmptyString
    label: NonEmptyString
    value: str | None = Field(default=None, max_length=2000)
    status: DocumentationFieldStatus
    confidence: DecimalString | None = None
    evidence: tuple[EvidenceNavigationDto, ...]


class DocumentationSectionDto(ContractModel):
    section_key: NonEmptyString
    label: NonEmptyString
    document_id: DocumentId | None = None
    document_name: str | None = Field(default=None, max_length=500)
    fields: tuple[DocumentFieldDto, ...]


class DocumentationResponse(ContractModel):
    project_id: ProjectId
    semantic_signature: NonEmptyString
    page_order: tuple[PageId, ...] = ()
    sections: tuple[DocumentationSectionDto, ...]
