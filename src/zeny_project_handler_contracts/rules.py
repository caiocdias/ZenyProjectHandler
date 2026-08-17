"""DTOs do registro de regras e da importação confirmada."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue

from zeny_project_handler_contracts.base import (
    ContractModel,
    NonEmptyString,
    RuleImportPreflightId,
    Sha256,
    UtcDateTime,
)
from zeny_project_handler_contracts.common import PreflightIssueDto
from zeny_project_handler_contracts.enums import PreflightDisposition


class RuleSummaryDto(ContractModel):
    rule_id: NonEmptyString
    rule_number: int = Field(ge=1)
    title: NonEmptyString
    enabled: bool
    source_reference: NonEmptyString


class RuleDetailDto(ContractModel):
    summary: RuleSummaryDto
    target_scope: NonEmptyString
    fact_keys: tuple[NonEmptyString, ...]
    definition: dict[str, JsonValue]


class ActiveRuleRegistryResponse(ContractModel):
    revision: NonEmptyString
    sha256: Sha256
    rule_count: int = Field(ge=0)
    active_rule_count: int = Field(ge=0)
    activated_at: UtcDateTime
    rules: tuple[RuleSummaryDto, ...]
    details: tuple[RuleDetailDto, ...]


class RuleImportPreflightResponse(ContractModel):
    preflight_id: RuleImportPreflightId
    fingerprint: Sha256
    disposition: PreflightDisposition
    current_revision: NonEmptyString
    proposed_revision: NonEmptyString
    added_rule_ids: tuple[NonEmptyString, ...]
    changed_rule_ids: tuple[NonEmptyString, ...]
    preserved_rule_ids: tuple[NonEmptyString, ...]
    issues: tuple[PreflightIssueDto, ...]
    expires_at: UtcDateTime


class ConfirmRuleImportRequest(ContractModel):
    preflight_id: RuleImportPreflightId
    fingerprint: Sha256
    expected_active_revision: NonEmptyString
    confirmed: Literal[True]


class RuleImportResponse(ContractModel):
    revision: NonEmptyString
    sha256: Sha256
    imported_at: UtcDateTime
    active_rule_count: int = Field(ge=0)
