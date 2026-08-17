"""Projeções e comandos de revisão humana."""

from __future__ import annotations

from pydantic import Field, JsonValue

from zeny_project_handler_contracts.base import (
    ContractModel,
    DecimalString,
    ElementId,
    NonEmptyString,
    ProjectId,
    ProposalId,
    RegionId,
    RelationId,
    ReviewSessionId,
    UtcDateTime,
)
from zeny_project_handler_contracts.common import (
    EvidenceNavigationDto,
    NormalizedBoxDto,
    PageMetadataDto,
)
from zeny_project_handler_contracts.enums import (
    ElementCategory,
    ElementSituation,
    ReviewDecision,
    ReviewState,
    SpanLengthSource,
)


class ReviewProjectSummaryDto(ContractModel):
    project_id: ProjectId
    service_note: NonEmptyString
    pending_proposal_count: int = Field(ge=0)
    analyzed_at: UtcDateTime


class ReviewProjectSummaryListResponse(ContractModel):
    items: tuple[ReviewProjectSummaryDto, ...]
    page: PageMetadataDto


class ReviewOverlayDto(ContractModel):
    proposal_id: ProposalId
    geometry: NormalizedBoxDto
    label: NonEmptyString
    category: ElementCategory
    situation: ElementSituation


class ReviewProposalDto(ContractModel):
    proposal_id: ProposalId
    category: ElementCategory
    situation: ElementSituation
    review_state: ReviewState
    label: NonEmptyString
    confidence: DecimalString
    attributes: dict[str, JsonValue]
    evidence: tuple[EvidenceNavigationDto, ...]
    overlay: ReviewOverlayDto | None = None


class ReviewRelationDto(ContractModel):
    relation_id: RelationId
    source_element_id: ElementId
    target_element_id: ElementId
    relation_type: NonEmptyString
    review_state: ReviewState
    evidence: tuple[EvidenceNavigationDto, ...]


class AnalysisRegionDto(ContractModel):
    region_id: RegionId
    label: NonEmptyString
    geometry: NormalizedBoxDto
    proposal_ids: tuple[ProposalId, ...]
    relation_ids: tuple[RelationId, ...]
    coordinate_east: DecimalString | None = None
    coordinate_north: DecimalString | None = None


class DetectedSpanDto(ContractModel):
    span_id: str = Field(min_length=1, max_length=200)
    start_element_id: ElementId | None = None
    end_element_id: ElementId | None = None
    cable_element_id: ElementId | None = None
    length: DecimalString | None = None
    length_source: SpanLengthSource
    situation: ElementSituation | None = None
    evidence: tuple[EvidenceNavigationDto, ...]


class ReviewSessionResponse(ContractModel):
    review_session_id: ReviewSessionId
    project_id: ProjectId
    project_version: int = Field(ge=0)
    semantic_signature: NonEmptyString
    regions: tuple[AnalysisRegionDto, ...]
    proposals: tuple[ReviewProposalDto, ...]
    relations: tuple[ReviewRelationDto, ...]
    spans: tuple[DetectedSpanDto, ...]


class AcceptReviewProposalRequest(ContractModel):
    author: NonEmptyString
    reason: str | None = Field(default=None, max_length=1000)
    adjustments: dict[str, JsonValue] | None = None
    expected_review_session_id: ReviewSessionId


class RejectReviewProposalRequest(ContractModel):
    author: NonEmptyString
    reason: NonEmptyString
    expected_review_session_id: ReviewSessionId


class CreateManualElementRequest(ContractModel):
    author: NonEmptyString
    category: ElementCategory
    situation: ElementSituation
    attributes: dict[str, JsonValue]
    evidence: tuple[EvidenceNavigationDto, ...]
    expected_project_version: int = Field(ge=0)


class CreateManualRelationRequest(ContractModel):
    author: NonEmptyString
    source_element_id: ElementId
    target_element_id: ElementId
    relation_type: NonEmptyString
    evidence: tuple[EvidenceNavigationDto, ...]
    expected_project_version: int = Field(ge=0)


class ReviewDecisionResponse(ContractModel):
    proposal_id: ProposalId | None = None
    element_id: ElementId | None = None
    relation_id: RelationId | None = None
    decision: ReviewDecision
    review_state: ReviewState
    author: NonEmptyString
    decided_at: UtcDateTime
    project_version: int = Field(ge=0)
