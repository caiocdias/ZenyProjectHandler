"""Read model público e fechado da projeção GMAX."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from zeny_project_handler_contracts.base import (
    ComplianceExecutionId,
    ContractModel,
    NonEmptyString,
    ProjectId,
    UtcDateTime,
)

ServiceNote = Annotated[str, Field(pattern=r"^[0-9]{10}$")]


class GmaxHeaderState(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"


class GmaxSnapshotState(StrEnum):
    NEVER_EXECUTED = "NEVER_EXECUTED"
    CURRENT = "CURRENT"
    STALE = "STALE"
    BLOCKED_NS_MISMATCH = "BLOCKED_NS_MISMATCH"


class GmaxQueryState(StrEnum):
    NOT_EXECUTED = "NOT_EXECUTED"
    NOT_EXECUTED_NO_TRIGGER = "NOT_EXECUTED_NO_TRIGGER"
    NOT_EXECUTED_NO_SERVICE_CODES = "NOT_EXECUTED_NO_SERVICE_CODES"
    EXECUTED = "EXECUTED"


class GmaxCheckType(StrEnum):
    IMPACTO_AMBIENTAL = "IMPACTO_AMBIENTAL"
    SERVIDAO = "SERVIDAO"


class GmaxMarket(StrEnum):
    RURAL = "RURAL"
    URBANO = "URBANO"


class GmaxCheckDto(ContractModel):
    model_config = ConfigDict(from_attributes=True)

    check_type: GmaxCheckType
    label: NonEmptyString
    detected_in_pdf: bool
    action: NonEmptyString
    query_state: GmaxQueryState
    row_found: bool | None = None


class GmaxExecutedCheckDto(GmaxCheckDto):
    query_state: Literal[GmaxQueryState.EXECUTED]
    row_found: bool


class GmaxNotExecutedCheckDto(GmaxCheckDto):
    query_state: Literal[
        GmaxQueryState.NOT_EXECUTED,
        GmaxQueryState.NOT_EXECUTED_NO_TRIGGER,
        GmaxQueryState.NOT_EXECUTED_NO_SERVICE_CODES,
    ]
    row_found: None = None


class GmaxImpactExecutedCheckDto(GmaxExecutedCheckDto):
    check_type: Literal[GmaxCheckType.IMPACTO_AMBIENTAL]


class GmaxImpactNotExecutedCheckDto(GmaxNotExecutedCheckDto):
    check_type: Literal[GmaxCheckType.IMPACTO_AMBIENTAL]


class GmaxServitudeExecutedCheckDto(GmaxExecutedCheckDto):
    check_type: Literal[GmaxCheckType.SERVIDAO]


class GmaxServitudeNotExecutedCheckDto(GmaxNotExecutedCheckDto):
    check_type: Literal[GmaxCheckType.SERVIDAO]


GmaxImpactCheckDto = Annotated[
    GmaxImpactExecutedCheckDto | GmaxImpactNotExecutedCheckDto,
    Field(discriminator="query_state"),
]
GmaxServitudeCheckDto = Annotated[
    GmaxServitudeExecutedCheckDto | GmaxServitudeNotExecutedCheckDto,
    Field(discriminator="query_state"),
]


class GmaxSummaryResponse(ContractModel):
    project_id: ProjectId
    project_service_note: ServiceNote
    header_service_notes: tuple[ServiceNote, ...]
    header_state: GmaxHeaderState
    blocking_reason: str | None = Field(default=None, min_length=1, max_length=500)
    snapshot_state: GmaxSnapshotState
    last_execution_id: ComplianceExecutionId | None = None
    last_executed_at: UtcDateTime | None = None
    is_stale: bool
    market: GmaxMarket | None = None
    checks: tuple[GmaxImpactCheckDto, GmaxServitudeCheckDto]
