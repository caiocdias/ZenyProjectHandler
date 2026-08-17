"""DTOs de execuções, achados e callouts de conformidade."""

from __future__ import annotations

from pydantic import Field

from zeny_project_handler_contracts.base import (
    CalloutId,
    ComplianceExecutionId,
    ContractModel,
    FindingId,
    NonEmptyString,
    ProjectId,
    UtcDateTime,
)
from zeny_project_handler_contracts.common import (
    EvidenceNavigationDto,
    NormalizedBoxDto,
    NormalizedPointDto,
    PageMetadataDto,
)
from zeny_project_handler_contracts.enums import ComplianceStatus, ComplianceTargetScope


class ComplianceCalloutDto(ContractModel):
    callout_id: CalloutId
    finding_id: FindingId
    text: NonEmptyString
    anchor: NormalizedPointDto
    box: NormalizedBoxDto
    navigation: EvidenceNavigationDto


class ComplianceFindingDto(ContractModel):
    finding_id: FindingId
    rule_id: NonEmptyString
    rule_number: int = Field(ge=1)
    status: ComplianceStatus
    target_scope: ComplianceTargetScope
    target_id: str | None = Field(default=None, max_length=200)
    summary: NonEmptyString
    observed_value: str | None = Field(default=None, max_length=2000)
    expected_value: str | None = Field(default=None, max_length=2000)
    source_reference: NonEmptyString
    evidence: tuple[EvidenceNavigationDto, ...]
    callout: ComplianceCalloutDto | None = None


class ComplianceExecutionSummaryDto(ContractModel):
    execution_id: ComplianceExecutionId
    project_id: ProjectId
    rule_registry_revision: NonEmptyString
    semantic_signature: NonEmptyString
    method_version: NonEmptyString
    is_stale: bool
    compliant_count: int = Field(ge=0)
    divergence_count: int = Field(ge=0)
    not_evaluable_count: int = Field(ge=0)
    completed_at: UtcDateTime


class ComplianceExecutionResponse(ContractModel):
    execution: ComplianceExecutionSummaryDto
    findings: tuple[ComplianceFindingDto, ...]


class ComplianceHistoryResponse(ContractModel):
    items: tuple[ComplianceExecutionSummaryDto, ...]
    page: PageMetadataDto
