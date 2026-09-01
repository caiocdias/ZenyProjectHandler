"""Read model público e fechado da projeção GMAX."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, model_validator

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
    check_type: GmaxCheckType
    label: NonEmptyString
    detected_in_pdf: bool
    action: NonEmptyString
    query_state: GmaxQueryState
    row_found: bool | None = None

    @model_validator(mode="after")
    def validate_query_result(self) -> Self:
        if self.query_state is GmaxQueryState.EXECUTED:
            if self.row_found is None:
                raise ValueError("Check executado exige resultado booleano")
        elif self.row_found is not None:
            raise ValueError("Check não executado não admite resultado de linha")
        return self


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
    checks: tuple[GmaxCheckDto, GmaxCheckDto]

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        if len(set(self.header_service_notes)) != len(self.header_service_notes):
            raise ValueError("NS de cabeçalho não podem se repetir")
        mismatches = tuple(
            item for item in self.header_service_notes if item != self.project_service_note
        )
        expected_header_state = (
            GmaxHeaderState.NOT_FOUND
            if not self.header_service_notes
            else GmaxHeaderState.MISMATCH
            if mismatches
            else GmaxHeaderState.MATCH
        )
        if self.header_state is not expected_header_state:
            raise ValueError("Estado do cabeçalho não corresponde às NS informadas")

        if (self.last_execution_id is None) is not (self.last_executed_at is None):
            raise ValueError("Identidade e data da última execução devem coexistir")
        has_execution = self.last_execution_id is not None
        if self.snapshot_state is GmaxSnapshotState.NEVER_EXECUTED and has_execution:
            raise ValueError("Estado sem execução não admite última execução")
        if self.snapshot_state in {GmaxSnapshotState.CURRENT, GmaxSnapshotState.STALE}:
            if not has_execution or self.market is None:
                raise ValueError("Snapshot projetado exige execução e mercado")
        elif self.market is not None:
            raise ValueError("Estado sem snapshot vigente não admite mercado")

        blocked = self.snapshot_state is GmaxSnapshotState.BLOCKED_NS_MISMATCH
        if blocked:
            if self.header_state is not GmaxHeaderState.MISMATCH or self.blocking_reason is None:
                raise ValueError("Bloqueio por NS exige divergência e motivo")
        elif self.blocking_reason is not None:
            raise ValueError("Motivo de bloqueio só é permitido no estado bloqueado")

        expected_stale = self.snapshot_state in {
            GmaxSnapshotState.STALE,
            GmaxSnapshotState.BLOCKED_NS_MISMATCH,
        }
        if self.is_stale is not expected_stale:
            raise ValueError("Indicador stale não corresponde ao estado do snapshot")

        check_types = tuple(item.check_type for item in self.checks)
        if check_types != tuple(GmaxCheckType):
            raise ValueError("Checks GMAX devem seguir a ordem canônica completa")
        return self
