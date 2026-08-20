"""Uploads e downloads temporários, persistentes e limitados por TTL."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from zeny_project_handler._atomic_files import sibling_temporary_file
from zeny_project_handler_contracts.base import DownloadId
from zeny_project_handler_contracts.common import DownloadMetadataDto
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_server.api_errors import ApiError, UploadTooLargeError, validation_error
from zeny_project_handler_server.upload_storage import ReceivedUpload, sanitize_display_name

_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class StoredPreflight:
    preflight_id: UUID
    kind: str
    path: Path
    request_sha256: str
    key_sha256: str
    response_json: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class TransferDownload:
    path: Path
    metadata: DownloadMetadataDto


class ManagedTransferStorage:
    """Nunca aceite caminhos remotos; derive todos os alvos de UUIDs do servidor."""

    def __init__(self, data_directory: Path, *, maximum_bytes: int, ttl_seconds: int) -> None:
        if maximum_bytes <= 0 or ttl_seconds <= 0:
            raise ValueError("Limites de transferência devem ser positivos")
        self.maximum_bytes = maximum_bytes
        self.ttl = timedelta(seconds=ttl_seconds)
        self.root = data_directory.expanduser().resolve() / "transfers"
        self.incoming_root = self.root / "incoming"
        self.preflight_root = self.root / "preflights"
        self.pending_download_root = self.root / "download-pending"
        self.download_root = self.root / "downloads"
        self._prepare_roots()
        self.cleanup(remove_interrupted=True)

    async def receive(self, upload: UploadFile, *, expected_suffix: str) -> ReceivedUpload:
        display_name = sanitize_display_name(upload.filename)
        if Path(display_name).suffix.casefold() != expected_suffix.casefold():
            raise validation_error(f"O arquivo enviado deve usar a extensão {expected_suffix}.")
        temporary = self.incoming_root / f"{uuid4()}.part"
        digest = sha256()
        size = 0
        try:
            with temporary.open("xb") as output:
                while chunk := await upload.read(_CHUNK_SIZE):
                    size += len(chunk)
                    if size > self.maximum_bytes:
                        raise UploadTooLargeError(self.maximum_bytes)
                    output.write(chunk)
                    digest.update(chunk)
                output.flush()
                os.fsync(output.fileno())
            if size == 0:
                raise validation_error("O pacote enviado está vazio.")
            return ReceivedUpload(
                path=temporary,
                display_name=display_name,
                content_type=upload.content_type,
                size_bytes=size,
                sha256=digest.hexdigest(),
            )
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

    def find_preflight_by_key(self, kind: str, key_sha256: str) -> StoredPreflight | None:
        self.cleanup()
        for metadata_path in self.preflight_root.glob("*.json"):
            record = self._read_preflight(metadata_path)
            if record is not None and record.kind == kind and record.key_sha256 == key_sha256:
                return record
        return None

    def retain_preflight(
        self,
        upload: ReceivedUpload,
        *,
        preflight_id: UUID,
        kind: str,
        key_sha256: str,
        response_json: str,
        expires_at: datetime,
    ) -> StoredPreflight:
        suffix = Path(upload.display_name).suffix.casefold()
        destination = self.preflight_root / f"{preflight_id}{suffix}"
        if destination.exists():
            if _file_identity(destination) != (upload.sha256, upload.size_bytes):
                raise ApiError(
                    409,
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    "O preflight existente diverge do pacote recebido.",
                )
            upload.path.unlink(missing_ok=True)
        else:
            os.replace(upload.path, destination)
        payload = {
            "version": 1,
            "preflight_id": str(preflight_id),
            "kind": kind,
            "artifact": destination.name,
            "request_sha256": upload.sha256,
            "key_sha256": key_sha256,
            "response_json": response_json,
            "expires_at": expires_at.isoformat(),
        }
        self._write_json(self.preflight_root / f"{preflight_id}.json", payload)
        return StoredPreflight(
            preflight_id=preflight_id,
            kind=kind,
            path=destination,
            request_sha256=upload.sha256,
            key_sha256=key_sha256,
            response_json=response_json,
            expires_at=expires_at,
        )

    def get_preflight(self, preflight_id: UUID, *, kind: str) -> StoredPreflight:
        self.cleanup()
        record = self._read_preflight(self.preflight_root / f"{preflight_id}.json")
        if record is None or record.kind != kind:
            raise ApiError(
                410,
                ErrorCode.RESOURCE_NOT_FOUND,
                "O preflight expirou ou não está mais disponível.",
            )
        return record

    def discard_preflight(self, preflight_id: UUID) -> None:
        record = self._read_preflight(
            self.preflight_root / f"{preflight_id}.json",
            allow_expired=True,
        )
        if record is not None:
            record.path.unlink(missing_ok=True)
        (self.preflight_root / f"{preflight_id}.json").unlink(missing_ok=True)

    def discard_upload(self, upload: ReceivedUpload) -> None:
        upload.path.unlink(missing_ok=True)

    def pending_download_path(self, job_id: UUID, suffix: str) -> Path:
        if suffix not in {".zphproj", ".zphbackup"}:
            raise ValueError("Extensão de download não suportada")
        return self.pending_download_root / f"{job_id}{suffix}"

    def publish_download(
        self,
        pending: Path,
        *,
        file_name: str,
        mime_type: str,
    ) -> DownloadMetadataDto:
        safe_name = sanitize_display_name(file_name)
        source = pending.resolve()
        if not source.is_relative_to(self.pending_download_root.resolve()):
            raise validation_error("O artefato saiu da área temporária gerenciada.")
        if source.is_symlink() or not source.is_file():
            raise ApiError(409, ErrorCode.INTEGRITY_ERROR, "O artefato do job não está disponível.")
        digest, size = _file_identity(source)
        download_id = uuid4()
        suffix = Path(safe_name).suffix.casefold()
        destination = self.download_root / f"{download_id}{suffix}"
        os.replace(source, destination)
        expires_at = datetime.now(UTC) + self.ttl
        metadata = DownloadMetadataDto(
            download_id=DownloadId(download_id),
            file_name=safe_name,
            mime_type=mime_type,
            size_bytes=size,
            sha256=digest,
            expires_at=expires_at,
        )
        self._write_json(
            self.download_root / f"{download_id}.json",
            {
                "version": 1,
                "artifact": destination.name,
                "metadata": metadata.model_dump(mode="json"),
            },
        )
        return metadata

    def get_download(self, download_id: UUID) -> TransferDownload:
        self.cleanup()
        metadata_path = self.download_root / f"{download_id}.json"
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata = DownloadMetadataDto.model_validate(raw["metadata"])
            path = self._contained(self.download_root / str(raw["artifact"]), self.download_root)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ApiError(
                404,
                ErrorCode.RESOURCE_NOT_FOUND,
                "O download não existe ou expirou.",
            ) from error
        if metadata.download_id.root != download_id or not path.is_file() or path.is_symlink():
            raise ApiError(409, ErrorCode.INTEGRITY_ERROR, "O registro do download é inválido.")
        if _file_identity(path) != (metadata.sha256, metadata.size_bytes):
            raise ApiError(409, ErrorCode.INTEGRITY_ERROR, "A integridade do download não confere.")
        return TransferDownload(path=path, metadata=metadata)

    def cleanup(self, *, remove_interrupted: bool = False) -> int:
        removed = 0
        now = datetime.now(UTC)
        if remove_interrupted:
            for path in (
                *self.incoming_root.glob("*.part"),
                *self.pending_download_root.glob("*"),
            ):
                if path.is_file() and not path.is_symlink():
                    path.unlink(missing_ok=True)
                    removed += 1
        for metadata_path in self.preflight_root.glob("*.json"):
            record = self._read_preflight(metadata_path, allow_expired=True)
            if record is None or record.expires_at <= now:
                if record is not None:
                    record.path.unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
                removed += 1
        for metadata_path in self.download_root.glob("*.json"):
            try:
                raw = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata = DownloadMetadataDto.model_validate(raw["metadata"])
                artifact = self._contained(
                    self.download_root / str(raw["artifact"]), self.download_root
                )
            except (OSError, ValueError, KeyError, TypeError):
                metadata = None
                artifact = None
            if metadata is None or metadata.expires_at <= now:
                if artifact is not None:
                    artifact.unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
                removed += 1
        referenced = {
            record.path.name
            for path in self.preflight_root.glob("*.json")
            if (record := self._read_preflight(path)) is not None
        }
        referenced.update(
            str(raw["artifact"])
            for path in self.download_root.glob("*.json")
            if isinstance((raw := self._read_json(path)), dict) and "artifact" in raw
        )
        for root in (self.preflight_root, self.download_root):
            for artifact in root.iterdir():
                if (
                    artifact.suffix != ".json"
                    and artifact.name not in referenced
                    and artifact.is_file()
                ):
                    artifact.unlink(missing_ok=True)
                    removed += 1
        return removed

    def _read_preflight(
        self,
        metadata_path: Path,
        *,
        allow_expired: bool = False,
    ) -> StoredPreflight | None:
        raw = self._read_json(metadata_path)
        if not isinstance(raw, dict):
            return None
        try:
            expires_at = datetime.fromisoformat(str(raw["expires_at"]))
            if expires_at.tzinfo is None:
                return None
            record = StoredPreflight(
                preflight_id=UUID(str(raw["preflight_id"])),
                kind=str(raw["kind"]),
                path=self._contained(
                    self.preflight_root / str(raw["artifact"]), self.preflight_root
                ),
                request_sha256=str(raw["request_sha256"]),
                key_sha256=str(raw["key_sha256"]),
                response_json=str(raw["response_json"]),
                expires_at=expires_at,
            )
        except (KeyError, OSError, ValueError, TypeError):
            return None
        if not allow_expired and record.expires_at <= datetime.now(UTC):
            return None
        if not record.path.is_file() or record.path.is_symlink():
            return None
        return record

    @staticmethod
    def _read_json(path: Path) -> object:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_json(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with sibling_temporary_file(path) as temporary:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    payload, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)

    def _prepare_roots(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for path in (
            self.incoming_root,
            self.preflight_root,
            self.pending_download_root,
            self.download_root,
        ):
            if os.path.lexists(path) and (path.is_symlink() or not path.is_dir()):
                raise RuntimeError("A raiz de transferências não é um diretório regular")
            path.mkdir(exist_ok=True)

    @staticmethod
    def _contained(path: Path, root: Path) -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ValueError("Referência de transferência fora da raiz gerenciada")
        return resolved


def idempotency_key_sha256(kind: str, key: str) -> str:
    return sha256(f"{kind}\0{key}".encode()).hexdigest()


def _file_identity(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size
