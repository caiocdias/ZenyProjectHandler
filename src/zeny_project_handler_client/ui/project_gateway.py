"""Gateway HTTP/DTO cliente do painel Projeto, sem lógica protegida."""

from __future__ import annotations

import http.client
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Never, Protocol, TypeVar
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel

from zeny_project_handler_contracts import API_V1_PREFIX
from zeny_project_handler_contracts.base import PageId
from zeny_project_handler_contracts.documents import (
    CreateUploadResponse,
    DocumentImportResultDto,
    PageOrderResponse,
    RemoveDocumentResponse,
    ReplacePageOrderRequest,
    UnlockPdfRequest,
)
from zeny_project_handler_contracts.errors import ErrorCode, ErrorEnvelope
from zeny_project_handler_contracts.jobs import (
    CancelJobResponse,
    CreateAnalysisJobRequest,
    JobAcceptedResponse,
    JobResultResponse,
    JobStatusResponse,
)
from zeny_project_handler_contracts.projects import (
    CreateProjectRequest,
    DeleteProjectResponse,
    ProjectDetailResponse,
    ProjectSummaryListResponse,
    UpdateProjectRequest,
)
from zeny_project_handler_contracts.session import SessionCapabilitiesResponse

_CHUNK_SIZE = 1024 * 1024
_READ_RETRIES = 1
ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(slots=True)
class ProjectGatewayError(RuntimeError):
    code: ErrorCode
    message: str
    status_code: int | None = None
    correlation_id: str | None = None
    details: dict[str, object] | None = None

    def __str__(self) -> str:
        suffix = f" (correlação {self.correlation_id})" if self.correlation_id else ""
        return f"{self.message}{suffix}"


class ProjectGateway(Protocol):
    def session(self) -> SessionCapabilitiesResponse: ...

    def list_projects(self, *, limit: int = 200, offset: int = 0) -> ProjectSummaryListResponse: ...

    def create_project(
        self,
        service_note: str,
        *,
        idempotency_key: str,
    ) -> ProjectDetailResponse: ...

    def get_project(self, project_id: UUID) -> ProjectDetailResponse: ...

    def update_project(
        self,
        project_id: UUID,
        service_note: str,
        *,
        expected_project_version: int,
    ) -> ProjectDetailResponse: ...

    def delete_project(self, project_id: UUID) -> DeleteProjectResponse: ...

    def upload_document(
        self,
        project_id: UUID,
        path: Path,
        *,
        idempotency_key: str,
    ) -> CreateUploadResponse: ...

    def unlock_upload(self, upload_id: UUID, password: str) -> DocumentImportResultDto: ...

    def replace_page_order(
        self,
        project_id: UUID,
        page_ids: tuple[UUID, ...],
        *,
        expected_project_version: int,
    ) -> PageOrderResponse: ...

    def remove_document(self, project_id: UUID, document_id: UUID) -> RemoveDocumentResponse: ...

    def create_analysis_job(
        self,
        project_id: UUID,
        *,
        expected_project_version: int,
        force_reanalysis: bool,
        idempotency_key: str,
    ) -> JobAcceptedResponse: ...

    def get_job(self, job_id: UUID) -> JobStatusResponse: ...

    def get_job_result(self, job_id: UUID) -> JobResultResponse: ...

    def cancel_job(self, job_id: UUID) -> CancelJobResponse: ...


@dataclass(frozen=True, slots=True)
class UnavailableProjectGateway:
    message: str

    def _fail(self) -> Never:
        raise ProjectGatewayError(ErrorCode.AUTHENTICATION_FAILED, self.message)

    def __getattr__(self, _name: str) -> Never:
        self._fail()


@dataclass(slots=True)
class HttpProjectGateway:
    base_url: str
    password: str = field(repr=False)
    timeout_seconds: float = 30.0
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

    def session(self) -> SessionCapabilitiesResponse:
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/session",
            None,
            SessionCapabilitiesResponse,
        )

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
        )

    def create_project(
        self,
        service_note: str,
        *,
        idempotency_key: str,
    ) -> ProjectDetailResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/projects",
            CreateProjectRequest(service_note=service_note),
            ProjectDetailResponse,
            headers={"Idempotency-Key": idempotency_key},
        )

    def get_project(self, project_id: UUID) -> ProjectDetailResponse:
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/projects/{project_id}",
            None,
            ProjectDetailResponse,
        )

    def update_project(
        self,
        project_id: UUID,
        service_note: str,
        *,
        expected_project_version: int,
    ) -> ProjectDetailResponse:
        return self._json_model(
            "PATCH",
            f"{API_V1_PREFIX}/projects/{project_id}",
            UpdateProjectRequest(
                service_note=service_note,
                expected_project_version=expected_project_version,
            ),
            ProjectDetailResponse,
        )

    def delete_project(self, project_id: UUID) -> DeleteProjectResponse:
        return self._json_model(
            "DELETE",
            f"{API_V1_PREFIX}/projects/{project_id}",
            None,
            DeleteProjectResponse,
        )

    def upload_document(
        self,
        project_id: UUID,
        path: Path,
        *,
        idempotency_key: str,
    ) -> CreateUploadResponse:
        source = _pdf_source(path)
        boundary = f"----zeny-{uuid4().hex}"
        display_name = source.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{display_name}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
        ending = f"\r\n--{boundary}--\r\n".encode()

        def body() -> Iterable[bytes]:
            yield header
            with source.open("rb") as stream:
                while chunk := stream.read(_CHUNK_SIZE):
                    yield chunk
            yield ending

        status, response_headers, payload = self._request(
            "POST",
            f"{API_V1_PREFIX}/projects/{project_id}/document-uploads",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(header) + source.stat().st_size + len(ending)),
                "Idempotency-Key": idempotency_key,
            },
            body=body(),
        )
        return self._model_response(
            status,
            response_headers,
            payload,
            CreateUploadResponse,
        )

    def unlock_upload(self, upload_id: UUID, password: str) -> DocumentImportResultDto:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/uploads/{upload_id}/unlock",
            UnlockPdfRequest(password=password),
            DocumentImportResultDto,
        )

    def replace_page_order(
        self,
        project_id: UUID,
        page_ids: tuple[UUID, ...],
        *,
        expected_project_version: int,
    ) -> PageOrderResponse:
        return self._json_model(
            "PUT",
            f"{API_V1_PREFIX}/projects/{project_id}/page-order",
            ReplacePageOrderRequest(
                page_ids=tuple(PageId(item) for item in page_ids),
                expected_project_version=expected_project_version,
            ),
            PageOrderResponse,
        )

    def remove_document(self, project_id: UUID, document_id: UUID) -> RemoveDocumentResponse:
        return self._json_model(
            "DELETE",
            f"{API_V1_PREFIX}/projects/{project_id}/documents/{document_id}",
            None,
            RemoveDocumentResponse,
        )

    def create_analysis_job(
        self,
        project_id: UUID,
        *,
        expected_project_version: int,
        force_reanalysis: bool,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/projects/{project_id}/analysis-jobs",
            CreateAnalysisJobRequest(
                force_reanalysis=force_reanalysis,
                expected_project_version=expected_project_version,
            ),
            JobAcceptedResponse,
            headers={"Idempotency-Key": idempotency_key},
        )

    def get_job(self, job_id: UUID) -> JobStatusResponse:
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/jobs/{job_id}",
            None,
            JobStatusResponse,
        )

    def get_job_result(self, job_id: UUID) -> JobResultResponse:
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/jobs/{job_id}/result",
            None,
            JobResultResponse,
        )

    def cancel_job(self, job_id: UUID) -> CancelJobResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/jobs/{job_id}/cancel",
            None,
            CancelJobResponse,
        )

    def _json_model(
        self,
        method: str,
        path: str,
        request_model: BaseModel | None,
        response_model: type[ModelT],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> ModelT:
        request_headers = dict(headers or {})
        payload = None
        if request_model is not None:
            payload = request_model.model_dump_json().encode()
            request_headers["Content-Type"] = "application/json"
            request_headers["Content-Length"] = str(len(payload))
        status, response_headers, content = self._request(
            method,
            path,
            headers=request_headers,
            body=payload,
        )
        return self._model_response(status, response_headers, content, response_model)

    def _model_response(
        self,
        status: int,
        headers: Mapping[str, str],
        payload: bytes,
        model: type[ModelT],
    ) -> ModelT:
        self._raise_for_error(status, headers, payload)
        try:
            return model.model_validate_json(payload)
        except ValueError as error:
            raise ProjectGatewayError(
                ErrorCode.INTERNAL_ERROR,
                "A resposta do servidor não corresponde ao contrato do painel Projeto.",
                status_code=status,
                correlation_id=headers.get("x-correlation-id"),
            ) from error

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | Iterable[bytes] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        attempts = _READ_RETRIES + 1 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                return self._request_once(method, path, headers=headers, body=body)
            except (OSError, TimeoutError, http.client.HTTPException) as error:
                if attempt + 1 == attempts:
                    raise ProjectGatewayError(
                        ErrorCode.INTERNAL_ERROR,
                        "O servidor está indisponível ou excedeu o tempo limite.",
                    ) from error
        raise AssertionError("Quantidade de tentativas HTTP inválida")

    def _request_once(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None,
        body: bytes | Iterable[bytes] | None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection_type = (
            http.client.HTTPSConnection if self._scheme == "https" else http.client.HTTPConnection
        )
        connection = connection_type(self._host, self._port, timeout=self.timeout_seconds)
        try:
            connection.putrequest(method, f"{self._base_path}{path}")
            connection.putheader("Authorization", f"Bearer {self.password}")
            connection.putheader("Accept", "application/json")
            for name, value in (headers or {}).items():
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

    @staticmethod
    def _raise_for_error(
        status: int,
        headers: Mapping[str, str],
        payload: bytes,
    ) -> None:
        if 200 <= status < 300:
            return
        try:
            envelope = ErrorEnvelope.model_validate_json(payload)
        except ValueError as error:
            raise ProjectGatewayError(
                ErrorCode.INTERNAL_ERROR,
                "O servidor devolveu uma falha sem envelope seguro.",
                status_code=status,
                correlation_id=headers.get("x-correlation-id"),
            ) from error
        raise ProjectGatewayError(
            envelope.code,
            envelope.message,
            status_code=status,
            correlation_id=str(envelope.correlation_id.root),
            details=dict(envelope.details) if envelope.details is not None else None,
        )


def _pdf_source(path: Path) -> Path:
    source = path.expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.casefold() != ".pdf":
        raise ValueError("Selecione somente arquivos PDF regulares")
    return source
