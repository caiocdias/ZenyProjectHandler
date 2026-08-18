"""Gateway HTTP/DTO do painel Documentação e conformidade."""

from __future__ import annotations

import http.client
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Never, Protocol, TypeVar
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel

from zeny_project_handler.ui.pdf_gateway import (
    CLIENT_SERVER_URL_ENVIRONMENT_VARIABLE,
    DEFAULT_CLIENT_SERVER_URL,
    SERVER_PASSWORD_ENVIRONMENT_VARIABLE,
)
from zeny_project_handler_contracts import API_V1_PREFIX
from zeny_project_handler_contracts.compliance import (
    ComplianceExecutionResponse,
    ComplianceHistoryResponse,
)
from zeny_project_handler_contracts.documentation import DocumentationResponse
from zeny_project_handler_contracts.errors import ErrorCode, ErrorEnvelope
from zeny_project_handler_contracts.jobs import (
    CreateComplianceJobRequest,
    JobAcceptedResponse,
    JobResultResponse,
    JobStatusResponse,
)
from zeny_project_handler_contracts.review import ReviewProjectSummaryListResponse
from zeny_project_handler_contracts.rules import (
    ActiveRuleRegistryResponse,
    ConfirmRuleImportRequest,
    RuleImportPreflightResponse,
    RuleImportResponse,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(slots=True)
class DocumentationGatewayError(RuntimeError):
    code: ErrorCode
    message: str
    status_code: int | None = None
    correlation_id: str | None = None
    details: dict[str, object] | None = None

    def __str__(self) -> str:
        suffix = f" (correlação {self.correlation_id})" if self.correlation_id else ""
        return f"{self.message}{suffix}"


class DocumentationGateway(Protocol):
    def list_projects(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ReviewProjectSummaryListResponse: ...

    def get_documentation(self, project_id: UUID) -> DocumentationResponse: ...

    def get_latest_compliance(
        self,
        project_id: UUID,
    ) -> ComplianceExecutionResponse | None: ...

    def list_compliance_history(
        self,
        project_id: UUID,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ComplianceHistoryResponse: ...

    def create_compliance_job(
        self,
        project_id: UUID,
        *,
        expected_semantic_signature: str,
        idempotency_key: str,
    ) -> JobAcceptedResponse: ...

    def get_job(self, job_id: UUID) -> JobStatusResponse: ...

    def get_job_result(self, job_id: UUID) -> JobResultResponse: ...

    def get_active_registry(self) -> ActiveRuleRegistryResponse: ...

    def preflight_rule_import(
        self,
        path: Path,
        *,
        idempotency_key: str,
    ) -> RuleImportPreflightResponse: ...

    def confirm_rule_import(self, request: ConfirmRuleImportRequest) -> RuleImportResponse: ...

    def download_active_registry(self) -> bytes: ...


@dataclass(frozen=True, slots=True)
class UnavailableDocumentationGateway:
    message: str

    def _fail(self) -> Never:
        raise DocumentationGatewayError(ErrorCode.AUTHENTICATION_FAILED, self.message)

    def __getattr__(self, _name: str) -> Never:
        self._fail()


def configured_documentation_gateway(
    environment: Mapping[str, str] | None = None,
) -> DocumentationGateway:
    values = os.environ if environment is None else environment
    if not values.get(SERVER_PASSWORD_ENVIRONMENT_VARIABLE, ""):
        return UnavailableDocumentationGateway(
            "Configure a conexão autenticada com o servidor para usar Documentação e conformidade."
        )
    return HttpDocumentationGateway.from_environment(values)


@dataclass(slots=True)
class HttpDocumentationGateway:
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

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> HttpDocumentationGateway:
        values = os.environ if environment is None else environment
        return cls(
            base_url=values.get(
                CLIENT_SERVER_URL_ENVIRONMENT_VARIABLE,
                DEFAULT_CLIENT_SERVER_URL,
            ),
            password=values.get(SERVER_PASSWORD_ENVIRONMENT_VARIABLE, ""),
        )

    def list_projects(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ReviewProjectSummaryListResponse:
        query = urlencode({"limit": limit, "offset": offset})
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/documentation/projects?{query}",
            None,
            ReviewProjectSummaryListResponse,
        )

    def get_documentation(self, project_id: UUID) -> DocumentationResponse:
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/projects/{project_id}/documentation",
            None,
            DocumentationResponse,
        )

    def get_latest_compliance(
        self,
        project_id: UUID,
    ) -> ComplianceExecutionResponse | None:
        try:
            return self._json_model(
                "GET",
                f"{API_V1_PREFIX}/projects/{project_id}/compliance/latest",
                None,
                ComplianceExecutionResponse,
            )
        except DocumentationGatewayError as error:
            if error.code is ErrorCode.RESOURCE_NOT_FOUND:
                return None
            raise

    def list_compliance_history(
        self,
        project_id: UUID,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ComplianceHistoryResponse:
        query = urlencode({"limit": limit, "offset": offset})
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/projects/{project_id}/compliance/history?{query}",
            None,
            ComplianceHistoryResponse,
        )

    def create_compliance_job(
        self,
        project_id: UUID,
        *,
        expected_semantic_signature: str,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/projects/{project_id}/compliance-jobs",
            CreateComplianceJobRequest(
                expected_semantic_signature=expected_semantic_signature,
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

    def get_active_registry(self) -> ActiveRuleRegistryResponse:
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/rules/active",
            None,
            ActiveRuleRegistryResponse,
        )

    def preflight_rule_import(
        self,
        path: Path,
        *,
        idempotency_key: str,
    ) -> RuleImportPreflightResponse:
        boundary = f"----ZenyRules{uuid4().hex}"
        name = path.name.replace('"', "")
        content = path.read_bytes()
        body = (
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
                "Content-Type: application/json\r\n\r\n"
            ).encode()
            + content
            + f"\r\n--{boundary}--\r\n".encode("ascii")
        )
        status, response_headers, payload = self._request_with_retry(
            "POST",
            f"{API_V1_PREFIX}/rules/import-preflights",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
                "Idempotency-Key": idempotency_key,
            },
            body=body,
            retry_read=False,
        )
        return self._model_response(
            status,
            response_headers,
            payload,
            RuleImportPreflightResponse,
        )

    def confirm_rule_import(self, request: ConfirmRuleImportRequest) -> RuleImportResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/rules/imports",
            request,
            RuleImportResponse,
        )

    def download_active_registry(self) -> bytes:
        status, headers, payload = self._request_with_retry(
            "GET",
            f"{API_V1_PREFIX}/rules/active/download",
            headers={"Accept": "application/json"},
            body=None,
            retry_read=True,
        )
        if 200 <= status < 300:
            return payload
        self._raise_error(status, headers, payload)

    def _json_model(
        self,
        method: str,
        path: str,
        request: BaseModel | None,
        model: type[ModelT],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> ModelT:
        body = request.model_dump_json().encode("utf-8") if request is not None else None
        request_headers = dict(headers or {})
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        status, response_headers, payload = self._request_with_retry(
            method,
            path,
            headers=request_headers,
            body=body,
            retry_read=method == "GET",
        )
        return self._model_response(status, response_headers, payload, model)

    def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        retry_read: bool,
    ) -> tuple[int, dict[str, str], bytes]:
        attempts = 2 if retry_read else 1
        for attempt in range(attempts):
            try:
                return self._request(method, path, headers=headers, body=body)
            except (OSError, http.client.HTTPException) as error:
                if attempt + 1 < attempts:
                    continue
                raise DocumentationGatewayError(
                    ErrorCode.INTERNAL_ERROR,
                    "Não foi possível comunicar com o servidor.",
                ) from error
        raise AssertionError("Número de tentativas HTTP inválido")

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection_type = (
            http.client.HTTPSConnection if self._scheme == "https" else http.client.HTTPConnection
        )
        connection = connection_type(self._host, self._port, timeout=self.timeout_seconds)
        request_headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.password}",
            **headers,
        }
        try:
            connection.request(
                method,
                f"{self._base_path}{path}",
                body=body,
                headers=request_headers,
            )
            response = connection.getresponse()
            payload = response.read()
            return (
                response.status,
                {key.lower(): value for key, value in response.getheaders()},
                payload,
            )
        finally:
            connection.close()

    @classmethod
    def _model_response(
        cls,
        status: int,
        headers: Mapping[str, str],
        payload: bytes,
        model: type[ModelT],
    ) -> ModelT:
        if 200 <= status < 300:
            return model.model_validate_json(payload)
        cls._raise_error(status, headers, payload)

    @staticmethod
    def _raise_error(status: int, headers: Mapping[str, str], payload: bytes) -> Never:
        try:
            envelope = ErrorEnvelope.model_validate_json(payload)
        except ValueError as error:
            raise DocumentationGatewayError(
                ErrorCode.INTERNAL_ERROR,
                "O servidor devolveu uma resposta inválida.",
                status_code=status,
                correlation_id=headers.get("x-correlation-id"),
            ) from error
        raise DocumentationGatewayError(
            envelope.code,
            envelope.message,
            status_code=status,
            correlation_id=str(envelope.correlation_id.root),
            details=dict(envelope.details or {}),
        )
