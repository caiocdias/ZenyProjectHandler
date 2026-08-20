"""Registros persistentes sem segredos para idempotência e uploads protegidos."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from uuid import UUID

from sqlalchemy import Engine, delete, insert, select, update

from zeny_project_handler.adapters.persistence.schema import (
    api_idempotency_records,
    api_uploads,
)
from zeny_project_handler_contracts.enums import UploadState
from zeny_project_handler_server.api_errors import IdempotencyConflictError


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    key: str
    operation: str
    request_sha256: str
    resource_id: UUID
    response_json: str | None


@dataclass(frozen=True, slots=True)
class UploadRecord:
    upload_id: UUID
    project_id: UUID
    document_id: UUID | None
    state: UploadState
    display_name: str
    sha256: str
    size_bytes: int
    pending_relative_path: str | None
    password_attempts_remaining: int | None
    created_at: datetime
    updated_at: datetime


class StageThreeStore:
    """Serializa chaves no worker e persiste somente identidades/respostas seguras."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._lock = RLock()

    @contextmanager
    def idempotency_guard(
        self,
        *,
        key: str,
        operation: str,
        request_sha256: str,
        resource_id: UUID,
    ) -> Iterator[IdempotencyRecord]:
        with self._lock:
            yield self._reserve(
                key=key,
                operation=operation,
                request_sha256=request_sha256,
                resource_id=resource_id,
            )

    def complete_idempotency(self, record: IdempotencyRecord, response_json: str) -> None:
        now = _now_text()
        with self._engine.begin() as connection:
            connection.execute(
                update(api_idempotency_records)
                .where(
                    api_idempotency_records.c.idempotency_key == record.key,
                    api_idempotency_records.c.operation == record.operation,
                    api_idempotency_records.c.request_sha256 == record.request_sha256,
                )
                .values(response_json=response_json, updated_at=now)
            )

    def abandon_idempotency(self, record: IdempotencyRecord) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                delete(api_idempotency_records).where(
                    api_idempotency_records.c.idempotency_key == record.key,
                    api_idempotency_records.c.operation == record.operation,
                    api_idempotency_records.c.request_sha256 == record.request_sha256,
                    api_idempotency_records.c.response_json.is_(None),
                )
            )

    def replace_completed_idempotency(
        self,
        *,
        key: str,
        operation: str,
        request_sha256: str,
        resource_id: UUID,
        response_json: str,
    ) -> None:
        """Republique o recibo que um restore de banco pode ter substituído."""
        now = _now_text()
        with self._lock, self._engine.begin() as connection:
            connection.execute(
                delete(api_idempotency_records).where(
                    api_idempotency_records.c.idempotency_key == key
                )
            )
            connection.execute(
                insert(api_idempotency_records).values(
                    idempotency_key=key,
                    operation=operation,
                    request_sha256=request_sha256,
                    resource_id=str(resource_id),
                    response_json=response_json,
                    created_at=now,
                    updated_at=now,
                )
            )

    def get_upload(self, upload_id: UUID) -> UploadRecord | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(select(api_uploads).where(api_uploads.c.id == str(upload_id)))
                .mappings()
                .one_or_none()
            )
        return _upload_record(row) if row is not None else None

    def save_pending_upload(
        self,
        *,
        upload_id: UUID,
        project_id: UUID,
        document_id: UUID,
        display_name: str,
        sha256: str,
        size_bytes: int,
        pending_relative_path: str,
    ) -> UploadRecord:
        now = _now_text()
        values = {
            "project_id": str(project_id),
            "document_id": str(document_id),
            "state": UploadState.PASSWORD_REQUIRED.value,
            "display_name": display_name,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "pending_relative_path": pending_relative_path,
            "password_attempts_remaining": 3,
            "updated_at": now,
        }
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(api_uploads.c.id).where(api_uploads.c.id == str(upload_id))
            ).scalar_one_or_none()
            if existing is None:
                connection.execute(
                    insert(api_uploads).values(id=str(upload_id), created_at=now, **values)
                )
            else:
                connection.execute(
                    update(api_uploads).where(api_uploads.c.id == str(upload_id)).values(**values)
                )
        record = self.get_upload(upload_id)
        if record is None:
            raise RuntimeError("O upload protegido não foi persistido")
        return record

    def mark_upload_imported(self, upload_id: UUID, document_id: UUID) -> UploadRecord:
        return self._update_upload(
            upload_id,
            state=UploadState.IMPORTED.value,
            document_id=str(document_id),
            pending_relative_path=None,
            password_attempts_remaining=None,
        )

    def record_imported_upload(
        self,
        *,
        upload_id: UUID,
        project_id: UUID,
        document_id: UUID,
        display_name: str,
        sha256: str,
        size_bytes: int,
    ) -> UploadRecord:
        now = _now_text()
        values = {
            "project_id": str(project_id),
            "document_id": str(document_id),
            "state": UploadState.IMPORTED.value,
            "display_name": display_name,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "pending_relative_path": None,
            "password_attempts_remaining": None,
            "updated_at": now,
        }
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(api_uploads.c.id).where(api_uploads.c.id == str(upload_id))
            ).scalar_one_or_none()
            if existing is None:
                connection.execute(
                    insert(api_uploads).values(id=str(upload_id), created_at=now, **values)
                )
            else:
                connection.execute(
                    update(api_uploads).where(api_uploads.c.id == str(upload_id)).values(**values)
                )
        record = self.get_upload(upload_id)
        if record is None:
            raise RuntimeError("O recibo do upload importado não foi persistido")
        return record

    def register_invalid_password(self, upload_id: UUID) -> UploadRecord:
        current = self.get_upload(upload_id)
        if current is None or current.password_attempts_remaining is None:
            raise RuntimeError("O upload não está aguardando senha")
        remaining = max(0, current.password_attempts_remaining - 1)
        state = UploadState.REJECTED if remaining == 0 else UploadState.PASSWORD_REQUIRED
        return self._update_upload(
            upload_id,
            state=state.value,
            password_attempts_remaining=remaining,
            pending_relative_path=(None if remaining == 0 else current.pending_relative_path),
        )

    def pending_uploads_before(self, cutoff: datetime) -> tuple[UploadRecord, ...]:
        if cutoff.tzinfo is None:
            raise ValueError("O limite de expiração deve possuir fuso horário")
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(api_uploads).where(
                    api_uploads.c.state == UploadState.PASSWORD_REQUIRED.value,
                    api_uploads.c.updated_at < cutoff.astimezone(UTC).isoformat(),
                )
            ).mappings()
            return tuple(_upload_record(row) for row in rows)

    def mark_upload_expired(self, upload_id: UUID) -> UploadRecord:
        return self._update_upload(
            upload_id,
            state=UploadState.EXPIRED.value,
            pending_relative_path=None,
            password_attempts_remaining=None,
        )

    def _reserve(
        self,
        *,
        key: str,
        operation: str,
        request_sha256: str,
        resource_id: UUID,
    ) -> IdempotencyRecord:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    select(api_idempotency_records).where(
                        api_idempotency_records.c.idempotency_key == key
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                now = _now_text()
                connection.execute(
                    insert(api_idempotency_records).values(
                        idempotency_key=key,
                        operation=operation,
                        request_sha256=request_sha256,
                        resource_id=str(resource_id),
                        response_json=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
                return IdempotencyRecord(key, operation, request_sha256, resource_id, None)
        record = _idempotency_record(row)
        if (
            record.operation != operation
            or record.request_sha256 != request_sha256
            or record.resource_id != resource_id
        ):
            raise IdempotencyConflictError
        return record

    def _update_upload(self, upload_id: UUID, **values: object) -> UploadRecord:
        with self._engine.begin() as connection:
            result = connection.execute(
                update(api_uploads)
                .where(api_uploads.c.id == str(upload_id))
                .values(updated_at=_now_text(), **values)
            )
            if not result.rowcount:
                raise RuntimeError("Upload não encontrado para atualização")
        record = self.get_upload(upload_id)
        if record is None:
            raise RuntimeError("Upload não encontrado depois da atualização")
        return record


def _idempotency_record(row: object) -> IdempotencyRecord:
    values = row
    return IdempotencyRecord(
        key=str(values["idempotency_key"]),  # type: ignore[index]
        operation=str(values["operation"]),  # type: ignore[index]
        request_sha256=str(values["request_sha256"]),  # type: ignore[index]
        resource_id=UUID(str(values["resource_id"])),  # type: ignore[index]
        response_json=(
            str(values["response_json"])  # type: ignore[index]
            if values["response_json"] is not None  # type: ignore[index]
            else None
        ),
    )


def _upload_record(row: object) -> UploadRecord:
    values = row
    document_id = values["document_id"]  # type: ignore[index]
    attempts = values["password_attempts_remaining"]  # type: ignore[index]
    return UploadRecord(
        upload_id=UUID(str(values["id"])),  # type: ignore[index]
        project_id=UUID(str(values["project_id"])),  # type: ignore[index]
        document_id=UUID(str(document_id)) if document_id is not None else None,
        state=UploadState(str(values["state"])),  # type: ignore[index]
        display_name=str(values["display_name"]),  # type: ignore[index]
        sha256=str(values["sha256"]),  # type: ignore[index]
        size_bytes=int(values["size_bytes"]),  # type: ignore[index]
        pending_relative_path=(
            str(values["pending_relative_path"])  # type: ignore[index]
            if values["pending_relative_path"] is not None  # type: ignore[index]
            else None
        ),
        password_attempts_remaining=int(attempts) if attempts is not None else None,
        created_at=_parse_time(str(values["created_at"])),  # type: ignore[index]
        updated_at=_parse_time(str(values["updated_at"])),  # type: ignore[index]
    )


def _now_text() -> str:
    return datetime.now(UTC).isoformat()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
