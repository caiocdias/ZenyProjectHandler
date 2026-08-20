"""DTOs de projetos."""

from __future__ import annotations

from pydantic import Field

from zeny_project_handler_contracts.base import (
    ContractModel,
    NonEmptyString,
    ProjectId,
    UtcDateTime,
)
from zeny_project_handler_contracts.common import DeletionCountsDto, PageMetadataDto
from zeny_project_handler_contracts.documents import DocumentSummaryDto, PageSummaryDto
from zeny_project_handler_contracts.enums import AnalysisExecutionState, ProjectState


class ProjectAnalysisSummaryDto(ContractModel):
    last_extraction: AnalysisExecutionState | None = None
    last_interpretation: AnalysisExecutionState | None = None
    pending_proposals: int = Field(ge=0)
    completed_decisions: int = Field(ge=0)


class ProjectSummaryDto(ContractModel):
    project_id: ProjectId
    service_note: NonEmptyString
    state: ProjectState
    project_version: int = Field(ge=0)
    document_count: int = Field(ge=0)
    page_count: int = Field(ge=0)
    analysis: ProjectAnalysisSummaryDto
    created_at: UtcDateTime
    updated_at: UtcDateTime


class ProjectSummaryListResponse(ContractModel):
    items: tuple[ProjectSummaryDto, ...]
    page: PageMetadataDto


class CreateProjectRequest(ContractModel):
    service_note: NonEmptyString


class UpdateProjectRequest(ContractModel):
    service_note: NonEmptyString
    expected_project_version: int = Field(ge=0)


class ProjectDetailDto(ContractModel):
    project_id: ProjectId
    service_note: NonEmptyString
    state: ProjectState
    project_version: int = Field(ge=0)
    documents: tuple[DocumentSummaryDto, ...]
    pages: tuple[PageSummaryDto, ...]
    analysis: ProjectAnalysisSummaryDto
    created_at: UtcDateTime
    updated_at: UtcDateTime


class ProjectDetailResponse(ContractModel):
    project: ProjectDetailDto


class DeleteProjectResponse(ContractModel):
    project_id: ProjectId
    deleted: bool
    counts: DeletionCountsDto
