"""Journal persistente e monotônico dos jobs pertencentes ao worker servidor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import UUID, uuid4

from sqlalchemy import Engine, delete, insert, select, update

from zeny_project_handler.adapters.persistence.schema import (
    api_idempotency_records,
    api_jobs,
)
from zeny_project_handler_contracts.base import CorrelationId
from zeny_project_handler_contracts.enums import JobKind, JobStatus
from zeny_project_handler_contracts.errors import ErrorCode, ErrorEnvelope

_ACTIVE_STATUSES = frozenset(
    {
        JobStatus.QUEUED,
        JobStatus.RUNNING,
        JobStatus.WAITING_CONFIRMATION,
        JobStatus.CANCELLING,
    }
)
_TERMINAL_STATUSES = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED})


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: UUID
    project_id: UUID | None
    kind: JobKind
    status: JobStatus
    progress_percent: int
    message: str | None
    result_json: str | None
    error_json: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class JobStore:
    """Serialize alterações e nunca permita regressão de progresso ou estado terminal."""

    def __init__(self, engine: Engine, *, retention: timedelta, maximum_retained: int) -> None:
        if retention.total_seconds() <= 0:
            raise ValueError("A retenção dos jobs deve ser positiva")
        if maximum_retained < 1:
            raise ValueError("A quantidade de jobs retidos deve ser positiva")
        self._engine = engine
        self._retention = retention
        self._maximum_retained = maximum_retained
        self._lock = RLock()

    def create(self, job_id: UUID, project_id: UUID, kind: JobKind) -> JobRecord:
        now = datetime.now(UTC)
        with self._lock, self._engine.begin() as connection:
            connection.execute(
                insert(api_jobs).values(
                    id=str(job_id),
                    project_id=str(project_id),
                    kind=kind.value,
                    status=JobStatus.QUEUED.value,
                    progress_percent=0,
                    message="Job aguardando o worker do servidor.",
                    result_json=None,
                    error_json=None,
                    created_at=now.isoformat(),
                    updated_at=now.isoformat(),
                    expires_at=(now + self._retention).isoformat(),
                )
            )
        record = self.get(job_id)
        if record is None:
            raise RuntimeError("O job criado não pôde ser relido")
        return record

    def get(self, job_id: UUID) -> JobRecord | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(select(api_jobs).where(api_jobs.c.id == str(job_id)))
                .mappings()
                .one_or_none()
            )
        return _record(row) if row is not None else None

    def update_progress(
        self,
        job_id: UUID,
        *,
        status: JobStatus,
        progress_percent: int,
        message: str | None,
    ) -> JobRecord:
        if status not in _ACTIVE_STATUSES:
            raise ValueError("Atualização de progresso exige um estado ativo")
        bounded = min(100, max(0, progress_percent))
        with self._lock:
            current = self._required(job_id)
            if current.status in _TERMINAL_STATUSES:
                return current
            progress = max(current.progress_percent, bounded)
            self._update(
                job_id,
                status=status.value,
                progress_percent=progress,
                message=_bounded_message(message),
            )
            return self._required(job_id)

    def finish(
        self,
        job_id: UUID,
        *,
        status: JobStatus,
        message: str,
        result_json: str | None = None,
        error_json: str | None = None,
    ) -> JobRecord:
        if status not in _TERMINAL_STATUSES:
            raise ValueError("Finalização exige um estado terminal")
        with self._lock:
            current = self._required(job_id)
            if current.status in _TERMINAL_STATUSES:
                return current
            progress = 100 if status is JobStatus.SUCCEEDED else current.progress_percent
            self._update(
                job_id,
                status=status.value,
                progress_percent=progress,
                message=_bounded_message(message),
                result_json=result_json,
                error_json=error_json,
            )
            return self._required(job_id)

    def reconcile_interrupted(self) -> int:
        """Converta jobs ativos do processo anterior em falha recuperável auditável."""
        with self._lock, self._engine.begin() as connection:
            rows = tuple(
                connection.execute(
                    select(api_jobs.c.id).where(
                        api_jobs.c.status.in_(tuple(item.value for item in _ACTIVE_STATUSES))
                    )
                )
            )
            now = datetime.now(UTC).isoformat()
            for row in rows:
                envelope = ErrorEnvelope(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=(
                        "A execução foi interrompida pela reinicialização do servidor; "
                        "inicie uma nova tentativa."
                    ),
                    correlation_id=CorrelationId(uuid4()),
                    details={"recoverable": True, "restart_interrupted": True},
                )
                connection.execute(
                    update(api_jobs)
                    .where(api_jobs.c.id == str(row.id))
                    .values(
                        status=JobStatus.FAILED.value,
                        message=envelope.message,
                        error_json=envelope.model_dump_json(),
                        updated_at=now,
                    )
                )
        return len(rows)

    def prune(self) -> int:
        """Remova terminais vencidos e limite a quantidade total de históricos."""
        now = datetime.now(UTC).isoformat()
        terminal_values = tuple(item.value for item in _TERMINAL_STATUSES)
        with self._lock, self._engine.begin() as connection:
            terminal_rows = tuple(
                connection.execute(
                    select(api_jobs.c.id, api_jobs.c.expires_at, api_jobs.c.updated_at)
                    .where(api_jobs.c.status.in_(terminal_values))
                    .order_by(api_jobs.c.updated_at.desc())
                )
            )
            removed_ids = {
                str(row.id)
                for index, row in enumerate(terminal_rows)
                if str(row.expires_at) <= now or index >= self._maximum_retained
            }
            if not removed_ids:
                return 0
            connection.execute(
                delete(api_idempotency_records).where(
                    api_idempotency_records.c.resource_id.in_(removed_ids)
                )
            )
            connection.execute(delete(api_jobs).where(api_jobs.c.id.in_(removed_ids)))
        return len(removed_ids)

    def _required(self, job_id: UUID) -> JobRecord:
        record = self.get(job_id)
        if record is None:
            raise KeyError(job_id)
        return record

    def _update(self, job_id: UUID, **values: object) -> None:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            result = connection.execute(
                update(api_jobs)
                .where(api_jobs.c.id == str(job_id))
                .values(
                    updated_at=now.isoformat(),
                    expires_at=(now + self._retention).isoformat(),
                    **values,
                )
            )
        if not result.rowcount:
            raise KeyError(job_id)


def _record(row: object) -> JobRecord:
    values = row
    project_id = values["project_id"]  # type: ignore[index]
    return JobRecord(
        job_id=UUID(str(values["id"])),  # type: ignore[index]
        project_id=UUID(str(project_id)) if project_id is not None else None,
        kind=JobKind(str(values["kind"])),  # type: ignore[index]
        status=JobStatus(str(values["status"])),  # type: ignore[index]
        progress_percent=int(values["progress_percent"]),  # type: ignore[index]
        message=(
            str(values["message"])  # type: ignore[index]
            if values["message"] is not None  # type: ignore[index]
            else None
        ),
        result_json=(
            str(values["result_json"])  # type: ignore[index]
            if values["result_json"] is not None  # type: ignore[index]
            else None
        ),
        error_json=(
            str(values["error_json"])  # type: ignore[index]
            if values["error_json"] is not None  # type: ignore[index]
            else None
        ),
        created_at=_parse_time(str(values["created_at"])),  # type: ignore[index]
        updated_at=_parse_time(str(values["updated_at"])),  # type: ignore[index]
        expires_at=_parse_time(str(values["expires_at"])),  # type: ignore[index]
    )


def _bounded_message(message: str | None) -> str | None:
    if message is None:
        return None
    clean = message.strip()
    return clean[:500] if clean else None


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
