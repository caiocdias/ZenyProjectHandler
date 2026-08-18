"""Projeções e comandos de revisão humana, sem comportamento de negócio."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import Field, JsonValue

from zeny_project_handler_contracts.base import (
    CatalogItemId,
    ContractModel,
    DecimalString,
    ElementId,
    NonEmptyString,
    PageId,
    ProjectId,
    ProposalId,
    RegionId,
    RelationId,
    ReviewSessionId,
    UtcDateTime,
)
from zeny_project_handler_contracts.common import (
    EvidenceNavigationDto,
    NormalizedPointDto,
    PageMetadataDto,
)
from zeny_project_handler_contracts.enums import (
    ElementCategory,
    ElementSituation,
    ReviewDecision,
    ReviewGeometryKind,
    ReviewProposalKind,
    ReviewReferenceKind,
    ReviewState,
    SpanLengthSource,
)


class ReviewGeometryDto(ContractModel):
    page_id: PageId
    kind: ReviewGeometryKind
    points: Annotated[tuple[NormalizedPointDto, ...], Field(min_length=1)]


class ReviewProjectSummaryDto(ContractModel):
    project_id: ProjectId
    service_note: NonEmptyString
    pending_proposal_count: int = Field(ge=0)
    analyzed_at: UtcDateTime


class ReviewProjectSummaryListResponse(ContractModel):
    items: tuple[ReviewProjectSummaryDto, ...]
    page: PageMetadataDto


class ReviewCatalogItemDto(ContractModel):
    catalog_item_id: CatalogItemId
    category: ElementCategory
    code: NonEmptyString
    description: NonEmptyString
    label: NonEmptyString


class ReviewReferenceDto(ContractModel):
    reference_id: UUID
    kind: ReviewReferenceKind
    label: NonEmptyString
    category: ElementCategory | None = None


class ReviewAuditDto(ContractModel):
    audit_id: UUID
    action: ReviewDecision
    author: NonEmptyString
    occurred_at: UtcDateTime
    reason: str | None = Field(default=None, max_length=1000)
    proposal_id: ProposalId | None = None
    created_reference_id: UUID | None = None
    previous_values: dict[str, JsonValue] | None = None
    confirmed_values: dict[str, JsonValue] | None = None


class ReviewOverlayDto(ContractModel):
    proposal_id: ProposalId
    geometry: ReviewGeometryDto
    link_geometry: ReviewGeometryDto
    label: NonEmptyString
    category: ElementCategory
    situation: ElementSituation
    review_state: ReviewState
    confidence: DecimalString | None = None


class ReviewProposalDto(ContractModel):
    proposal_id: ProposalId
    kind: ReviewProposalKind = ReviewProposalKind.ELEMENT
    category: ElementCategory
    situation: ElementSituation
    review_state: ReviewState
    state_label: NonEmptyString
    situation_label: NonEmptyString
    label: NonEmptyString
    catalog_item_id: CatalogItemId | None = None
    catalog_label: NonEmptyString
    detection_summary: NonEmptyString
    observed_code: str | None = Field(default=None, max_length=500)
    confidence: DecimalString | None = None
    attributes: dict[str, JsonValue]
    evidence: tuple[EvidenceNavigationDto, ...]
    relationship_labels: tuple[str, ...] = ()
    requires_review: bool
    overlay: ReviewOverlayDto


class ReviewRelationDto(ContractModel):
    proposal_id: ProposalId
    relation_type: NonEmptyString
    label: NonEmptyString
    source_reference_id: UUID
    target_reference_id: UUID
    review_state: ReviewState
    state_label: NonEmptyString
    confidence: DecimalString | None = None
    evidence: tuple[EvidenceNavigationDto, ...]
    requires_review: bool
    confirmed_relation_id: RelationId | None = None


class ConfirmedElementDto(ContractModel):
    element_id: ElementId
    category: ElementCategory
    situation: ElementSituation
    label: NonEmptyString
    catalog_label: NonEmptyString
    geometry: ReviewGeometryDto | None = None


class ConfirmedRelationDto(ContractModel):
    relation_id: RelationId
    relation_type: NonEmptyString
    source_reference_id: UUID
    target_reference_id: UUID
    label: NonEmptyString


class AnalysisRegionDto(ContractModel):
    region_id: RegionId
    page_id: PageId
    label: NonEmptyString
    location_label: NonEmptyString
    coordinate_label: NonEmptyString
    action_summary: NonEmptyString
    detail_summary: NonEmptyString
    geometry: ReviewGeometryDto
    proposal_ids: tuple[ProposalId, ...]
    relation_proposal_ids: tuple[ProposalId, ...]
    coordinate_east: DecimalString | None = None
    coordinate_north: DecimalString | None = None


class DetectedSpanDto(ContractModel):
    span_id: UUID
    proposal_id: ProposalId | None = None
    start_element_id: ElementId | None = None
    end_element_id: ElementId | None = None
    cable_element_id: ElementId
    label: NonEmptyString
    situation: ElementSituation
    situation_label: NonEmptyString
    start_label: NonEmptyString
    end_label: NonEmptyString
    cable_label: NonEmptyString
    length: DecimalString | None = None
    length_label: NonEmptyString
    length_source: SpanLengthSource
    length_source_label: NonEmptyString
    page_label: NonEmptyString
    geometry: ReviewGeometryDto | None = None
    evidence: tuple[EvidenceNavigationDto, ...]


class ReviewSessionResponse(ContractModel):
    review_session_id: ReviewSessionId
    project_id: ProjectId
    service_note: NonEmptyString
    project_version: int = Field(ge=0)
    semantic_signature: NonEmptyString
    page_order: tuple[PageId, ...]
    catalog_items: tuple[ReviewCatalogItemDto, ...]
    references: tuple[ReviewReferenceDto, ...]
    confirmed_elements: tuple[ConfirmedElementDto, ...]
    confirmed_relations: tuple[ConfirmedRelationDto, ...]
    regions: tuple[AnalysisRegionDto, ...]
    proposals: tuple[ReviewProposalDto, ...]
    relations: tuple[ReviewRelationDto, ...]
    spans: tuple[DetectedSpanDto, ...]
    audit: tuple[ReviewAuditDto, ...]


class ReviewElementInputDto(ContractModel):
    category: ElementCategory
    catalog_item_id: CatalogItemId
    situation: ElementSituation
    geometry: ReviewGeometryDto
    observed_code: str | None = Field(default=None, max_length=500)
    pole_id: ElementId | None = None
    origin_point_id: UUID | None = None
    target_point_id: UUID | None = None


class AcceptReviewProposalRequest(ContractModel):
    author: NonEmptyString
    reason: str | None = Field(default=None, max_length=1000)
    adjustments: ReviewElementInputDto | None = None
    expected_review_session_id: ReviewSessionId


class RejectReviewProposalRequest(ContractModel):
    author: NonEmptyString
    reason: NonEmptyString
    expected_review_session_id: ReviewSessionId


class CreateManualElementRequest(ContractModel):
    author: NonEmptyString
    reason: str | None = Field(default=None, max_length=1000)
    element: ReviewElementInputDto
    evidence: tuple[EvidenceNavigationDto, ...] = ()
    expected_project_version: int = Field(ge=0)


class CreateManualRelationRequest(ContractModel):
    author: NonEmptyString
    reason: str | None = Field(default=None, max_length=1000)
    source_reference_id: UUID
    target_reference_id: UUID
    relation_type: NonEmptyString
    evidence: tuple[EvidenceNavigationDto, ...] = ()
    expected_project_version: int = Field(ge=0)


class ReviewDecisionResponse(ContractModel):
    proposal_id: ProposalId | None = None
    element_id: ElementId | None = None
    relation_id: RelationId | None = None
    decision: ReviewDecision
    review_state: ReviewState
    author: NonEmptyString
    decided_at: UtcDateTime
    reason: str | None = Field(default=None, max_length=1000)
    project_version: int = Field(ge=0)
