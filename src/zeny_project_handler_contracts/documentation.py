"""Projeções documentais normalizadas."""

from __future__ import annotations

from pydantic import Field

from zeny_project_handler_contracts.base import (
    ContractModel,
    DecimalString,
    NonEmptyString,
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
    fields: tuple[DocumentFieldDto, ...]


class DocumentationResponse(ContractModel):
    project_id: ProjectId
    semantic_signature: NonEmptyString
    sections: tuple[DocumentationSectionDto, ...]
