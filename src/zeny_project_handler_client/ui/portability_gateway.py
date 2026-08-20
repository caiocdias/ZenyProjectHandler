"""Gateway cliente de portabilidade; contém somente transporte e arquivos locais."""

from __future__ import annotations

import http.client
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Never, Protocol, TypeVar
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel

from zeny_project_handler_client.atomic_files import sibling_temporary_file
from zeny_project_handler_contracts import API_V1_PREFIX
from zeny_project_handler_contracts.backup import (
    BackupPreflightResponse,
    BackupRestorePreflightResponse,
    ConfirmBackupRestoreRequest,
    CreateBackupJobRequest,
)
from zeny_project_handler_contracts.common import DownloadMetadataDto
from zeny_project_handler_contracts.errors import ErrorCode, ErrorEnvelope
from zeny_project_handler_contracts.jobs import (
    CancelJobResponse,
    CreateExportJobRequest,
    JobAcceptedResponse,
    JobResultResponse,
    JobStatusResponse,
)
from zeny_project_handler_contracts.portability import (
    ConfirmProjectImportRequest,
    ProjectImportPreflightResponse,
)
from zeny_project_handler_contracts.projects import ProjectSummaryListResponse

_CHUNK_SIZE = 1024 * 1024
ModelT = TypeVar("ModelT", bound=BaseModel)
ProgressCallback = Callable[[int, int, str], None]
CancelCallback = Callable[[], bool]


@dataclass(slots=True)
class PortabilityGatewayError(RuntimeError):
    code: ErrorCode
    message: str
    status_code: int | None = None
    correlation_id: str | None = None
    details: dict[str, object] | None = None

    def __str__(self) -> str:
        suffix = f" (correlação {self.correlation_id})" if self.correlation_id else ""
        return f"{self.message}{suffix}"


class PortabilityTransferCancelledError(RuntimeError):
    pass


class PortabilityGateway(Protocol):
    def list_projects(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ProjectSummaryListResponse: ...

    def create_project_export_job(
        self,
        project_id: UUID,
        *,
        expected_project_version: int,
        idempotency_key: str,
    ) -> JobAcceptedResponse: ...

    def preflight_project_import(
        self,
        path: Path,
        *,
        idempotency_key: str,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> ProjectImportPreflightResponse: ...

    def create_project_import_job(
        self,
        request: ConfirmProjectImportRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse: ...

    def preflight_backup(self) -> BackupPreflightResponse: ...

    def create_backup_job(
        self,
        request: CreateBackupJobRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse: ...

    def preflight_backup_restore(
        self,
        path: Path,
        *,
        idempotency_key: str,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> BackupRestorePreflightResponse: ...

    def create_backup_restore_job(
        self,
        request: ConfirmBackupRestoreRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse: ...

    def get_job(self, job_id: UUID) -> JobStatusResponse: ...

    def get_job_result(self, job_id: UUID) -> JobResultResponse: ...

    def cancel_job(self, job_id: UUID) -> CancelJobResponse: ...

    def get_download_metadata(self, download_id: UUID) -> DownloadMetadataDto: ...

    def download_to(
        self,
        download_id: UUID,
        destination: Path,
        *,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> DownloadMetadataDto: ...


@dataclass(frozen=True, slots=True)
class UnavailablePortabilityGateway:
    message: str

    def _fail(self) -> Never:
        raise PortabilityGatewayError(ErrorCode.AUTHENTICATION_FAILED, self.message)

    def __getattr__(self, _name: str) -> Never:
        self._fail()


@dataclass(slots=True)
class HttpPortabilityGateway:
    base_url: str
    password: str = field(repr=False)
    timeout_seconds: float = 60.0
    _scheme: str = field(init=False, repr=False)
    _host: str = field(init=False, repr=False)
    _port: int = field(init=False, repr=False)
    _base_path: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("A URL do servidor deve usar http:// ou https:// e conter um host")
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("A URL do servidor não pode conter credenciais, query ou fragmento")
        if not self.password:
            raise ValueError("A senha do servidor é obrigatória")
        if self.timeout_seconds <= 0:
            raise ValueError("O timeout HTTP deve ser positivo")
        self._scheme = parsed.scheme
        self._host = parsed.hostname
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._base_path = parsed.path.rstrip("/")

    def list_projects(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ProjectSummaryListResponse:
        query = urlencode({"limit": limit, "offset": offset})
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/projects?{query}",
            None,
            ProjectSummaryListResponse,
            retry_read=True,
        )

    def create_project_export_job(
        self,
        project_id: UUID,
        *,
        expected_project_version: int,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/projects/{project_id}/export-jobs",
            CreateExportJobRequest(expected_project_version=expected_project_version),
            JobAcceptedResponse,
            headers={"Idempotency-Key": idempotency_key},
        )

    def preflight_project_import(
        self,
        path: Path,
        *,
        idempotency_key: str,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> ProjectImportPreflightResponse:
        return self._upload_preflight(
            path,
            expected_suffix=".zphproj",
            endpoint=f"{API_V1_PREFIX}/project-import-preflights",
            idempotency_key=idempotency_key,
            model=ProjectImportPreflightResponse,
            progress=progress,
            cancelled=cancelled,
        )

    def create_project_import_job(
        self,
        request: ConfirmProjectImportRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/project-import-jobs",
            request,
            JobAcceptedResponse,
            headers={"Idempotency-Key": idempotency_key},
        )

    def preflight_backup(self) -> BackupPreflightResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/backup-preflights",
            None,
            BackupPreflightResponse,
        )

    def create_backup_job(
        self,
        request: CreateBackupJobRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/backup-jobs",
            request,
            JobAcceptedResponse,
            headers={"Idempotency-Key": idempotency_key},
        )

    def preflight_backup_restore(
        self,
        path: Path,
        *,
        idempotency_key: str,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> BackupRestorePreflightResponse:
        return self._upload_preflight(
            path,
            expected_suffix=".zphbackup",
            endpoint=f"{API_V1_PREFIX}/backup-restore-preflights",
            idempotency_key=idempotency_key,
            model=BackupRestorePreflightResponse,
            progress=progress,
            cancelled=cancelled,
        )

    def create_backup_restore_job(
        self,
        request: ConfirmBackupRestoreRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/backup-restore-jobs",
            request,
            JobAcceptedResponse,
            headers={"Idempotency-Key": idempotency_key},
        )

    def get_job(self, job_id: UUID) -> JobStatusResponse:
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/jobs/{job_id}",
            None,
            JobStatusResponse,
            retry_read=True,
        )

    def get_job_result(self, job_id: UUID) -> JobResultResponse:
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/jobs/{job_id}/result",
            None,
            JobResultResponse,
            retry_read=True,
        )

    def cancel_job(self, job_id: UUID) -> CancelJobResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/jobs/{job_id}/cancel",
            None,
            CancelJobResponse,
        )

    def get_download_metadata(self, download_id: UUID) -> DownloadMetadataDto:
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/downloads/{download_id}/metadata",
            None,
            DownloadMetadataDto,
            retry_read=True,
        )

    def download_to(
        self,
        download_id: UUID,
        destination: Path,
        *,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> DownloadMetadataDto:
        metadata = self.get_download_metadata(download_id)
        target = destination.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connection()
        try:
            connection.request(
                "GET",
                f"{self._base_path}{API_V1_PREFIX}/downloads/{download_id}",
                headers={
                    "Accept": "application/octet-stream",
                    "Authorization": f"Bearer {self.password}",
                },
            )
            response = connection.getresponse()
            headers = {key.lower(): value for key, value in response.getheaders()}
            if not 200 <= response.status < 300:
                self._raise_error(response.status, headers, response.read())
            digest = sha256()
            received = 0
            with sibling_temporary_file(target) as temporary:
                try:
                    with temporary.open("wb") as stream:
                        while chunk := response.read(_CHUNK_SIZE):
                            if cancelled():
                                raise PortabilityTransferCancelledError(
                                    "Download cancelado antes da publicação local"
                                )
                            stream.write(chunk)
                            digest.update(chunk)
                            received += len(chunk)
                            progress(received, metadata.size_bytes, "Baixando pacote")
                        stream.flush()
                        os.fsync(stream.fileno())
                    if received != metadata.size_bytes or digest.hexdigest() != metadata.sha256:
                        raise PortabilityGatewayError(
                            ErrorCode.INTEGRITY_ERROR,
                            "O arquivo recebido diverge dos metadados do servidor.",
                        )
                    if cancelled():
                        raise PortabilityTransferCancelledError(
                            "Download cancelado antes da publicação local"
                        )
                    os.replace(temporary, target)
                except BaseException:
                    temporary.unlink(missing_ok=True)
                    raise
        except PortabilityTransferCancelledError:
            raise
        except (OSError, TimeoutError, http.client.HTTPException) as error:
            raise PortabilityGatewayError(
                ErrorCode.INTERNAL_ERROR,
                "A transferência foi interrompida; o destino anterior foi preservado.",
            ) from error
        finally:
            connection.close()
        return metadata

    def _upload_preflight(
        self,
        path: Path,
        *,
        expected_suffix: str,
        endpoint: str,
        idempotency_key: str,
        model: type[ModelT],
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> ModelT:
        source = path.expanduser().resolve(strict=True)
        if (
            source.is_symlink()
            or not source.is_file()
            or source.suffix.casefold() != expected_suffix
        ):
            raise ValueError(f"Selecione um arquivo regular {expected_suffix}")
        boundary = f"----zeny-portability-{uuid4().hex}"
        display_name = source.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{display_name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        ending = f"\r\n--{boundary}--\r\n".encode()
        total = source.stat().st_size
        digest = sha256()
        sent = 0

        def body() -> Iterable[bytes]:
            nonlocal sent
            yield header
            with source.open("rb") as stream:
                while chunk := stream.read(_CHUNK_SIZE):
                    if cancelled():
                        raise PortabilityTransferCancelledError(
                            "Upload cancelado antes da conclusão do preflight"
                        )
                    digest.update(chunk)
                    sent += len(chunk)
                    progress(sent, total, "Enviando pacote")
                    yield chunk
            yield ending

        try:
            status, headers, payload = self._request_once(
                "POST",
                endpoint,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Content-Length": str(len(header) + total + len(ending)),
                    "Idempotency-Key": idempotency_key,
                },
                body=body(),
            )
        except PortabilityTransferCancelledError:
            raise
        except (OSError, TimeoutError, http.client.HTTPException) as error:
            raise PortabilityGatewayError(
                ErrorCode.INTERNAL_ERROR,
                "O upload foi interrompido antes do preflight.",
            ) from error
        response = self._model_response(status, headers, payload, model)
        package_hash = getattr(response, "package_sha256", None)
        if sent != total or digest.hexdigest() != package_hash:
            raise PortabilityGatewayError(
                ErrorCode.INTEGRITY_ERROR,
                "A identidade confirmada pelo servidor diverge do upload local.",
            )
        return response

    def _json_model(
        self,
        method: str,
        path: str,
        request: BaseModel | None,
        model: type[ModelT],
        *,
        headers: Mapping[str, str] | None = None,
        retry_read: bool = False,
    ) -> ModelT:
        payload = request.model_dump_json().encode() if request is not None else None
        request_headers = dict(headers or {})
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
            request_headers["Content-Length"] = str(len(payload))
        attempts = 2 if retry_read else 1
        for attempt in range(attempts):
            try:
                status, response_headers, content = self._request_once(
                    method,
                    path,
                    headers=request_headers,
                    body=payload,
                )
                return self._model_response(status, response_headers, content, model)
            except (OSError, TimeoutError, http.client.HTTPException) as error:
                if attempt + 1 == attempts:
                    raise PortabilityGatewayError(
                        ErrorCode.INTERNAL_ERROR,
                        "Não foi possível comunicar com o servidor.",
                    ) from error
        raise AssertionError("Quantidade de tentativas HTTP inválida")

    def _request_once(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str],
        body: bytes | Iterable[bytes] | None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = self._connection()
        try:
            connection.putrequest(method, f"{self._base_path}{path}")
            connection.putheader("Authorization", f"Bearer {self.password}")
            connection.putheader("Accept", "application/json")
            for name, value in headers.items():
                connection.putheader(name, value)
            connection.endheaders()
            if isinstance(body, bytes):
                connection.send(body)
            elif body is not None:
                for chunk in body:
                    connection.send(chunk)
            response = connection.getresponse()
            response_headers = {name.lower(): value for name, value in response.getheaders()}
            return response.status, response_headers, response.read()
        finally:
            connection.close()

    def _connection(self) -> http.client.HTTPConnection:
        connection_type = (
            http.client.HTTPSConnection if self._scheme == "https" else http.client.HTTPConnection
        )
        return connection_type(self._host, self._port, timeout=self.timeout_seconds)

    @classmethod
    def _model_response(
        cls,
        status: int,
        headers: Mapping[str, str],
        payload: bytes,
        model: type[ModelT],
    ) -> ModelT:
        if 200 <= status < 300:
            try:
                return model.model_validate_json(payload)
            except ValueError as error:
                raise PortabilityGatewayError(
                    ErrorCode.INTERNAL_ERROR,
                    "A resposta do servidor não corresponde ao contrato de portabilidade.",
                    status_code=status,
                    correlation_id=headers.get("x-correlation-id"),
                ) from error
        cls._raise_error(status, headers, payload)

    @staticmethod
    def _raise_error(status: int, headers: Mapping[str, str], payload: bytes) -> Never:
        try:
            envelope = ErrorEnvelope.model_validate_json(payload)
        except ValueError as error:
            raise PortabilityGatewayError(
                ErrorCode.INTERNAL_ERROR,
                "O servidor devolveu uma falha sem envelope seguro.",
                status_code=status,
                correlation_id=headers.get("x-correlation-id"),
            ) from error
        raise PortabilityGatewayError(
            envelope.code,
            envelope.message,
            status_code=status,
            correlation_id=str(envelope.correlation_id.root),
            details=dict(envelope.details or {}),
        )
