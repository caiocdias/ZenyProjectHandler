"""Gateway HTTP/DTO do painel Resultados, sem lógica protegida."""

from __future__ import annotations

import http.client
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Never, Protocol, TypeVar
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from pydantic import BaseModel

from zeny_project_handler.ui.pdf_gateway import (
    CLIENT_SERVER_URL_ENVIRONMENT_VARIABLE,
    DEFAULT_CLIENT_SERVER_URL,
    SERVER_PASSWORD_ENVIRONMENT_VARIABLE,
)
from zeny_project_handler_contracts import API_V1_PREFIX
from zeny_project_handler_contracts.errors import ErrorCode, ErrorEnvelope
from zeny_project_handler_contracts.review import (
    AcceptReviewProposalRequest,
    CreateManualElementRequest,
    CreateManualRelationRequest,
    RejectReviewProposalRequest,
    ReviewDecisionResponse,
    ReviewProjectSummaryListResponse,
    ReviewSessionResponse,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(slots=True)
class ReviewGatewayError(RuntimeError):
    code: ErrorCode
    message: str
    status_code: int | None = None
    correlation_id: str | None = None
    details: dict[str, object] | None = None

    def __str__(self) -> str:
        suffix = f" (correlação {self.correlation_id})" if self.correlation_id else ""
        return f"{self.message}{suffix}"


class ReviewGateway(Protocol):
    def list_projects(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ReviewProjectSummaryListResponse: ...

    def get_session(self, project_id: UUID) -> ReviewSessionResponse: ...

    def accept(
        self,
        proposal_id: UUID,
        request: AcceptReviewProposalRequest,
    ) -> ReviewDecisionResponse: ...

    def reject(
        self,
        proposal_id: UUID,
        request: RejectReviewProposalRequest,
    ) -> ReviewDecisionResponse: ...

    def create_manual_element(
        self,
        project_id: UUID,
        request: CreateManualElementRequest,
    ) -> ReviewDecisionResponse: ...

    def create_manual_relation(
        self,
        project_id: UUID,
        request: CreateManualRelationRequest,
    ) -> ReviewDecisionResponse: ...


@dataclass(frozen=True, slots=True)
class UnavailableReviewGateway:
    message: str

    def _fail(self) -> Never:
        raise ReviewGatewayError(ErrorCode.AUTHENTICATION_FAILED, self.message)

    def __getattr__(self, _name: str) -> Never:
        self._fail()


def configured_review_gateway(
    environment: Mapping[str, str] | None = None,
) -> ReviewGateway:
    values = os.environ if environment is None else environment
    if not values.get(SERVER_PASSWORD_ENVIRONMENT_VARIABLE, ""):
        return UnavailableReviewGateway(
            "Configure a conexão autenticada com o servidor para usar o painel Resultados."
        )
    return HttpReviewGateway.from_environment(values)


@dataclass(slots=True)
class HttpReviewGateway:
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
    ) -> HttpReviewGateway:
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
            f"{API_V1_PREFIX}/review/projects?{query}",
            None,
            ReviewProjectSummaryListResponse,
        )

    def get_session(self, project_id: UUID) -> ReviewSessionResponse:
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/projects/{project_id}/review-session",
            None,
            ReviewSessionResponse,
        )

    def accept(
        self,
        proposal_id: UUID,
        request: AcceptReviewProposalRequest,
    ) -> ReviewDecisionResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/review/proposals/{proposal_id}/accept",
            request,
            ReviewDecisionResponse,
        )

    def reject(
        self,
        proposal_id: UUID,
        request: RejectReviewProposalRequest,
    ) -> ReviewDecisionResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/review/proposals/{proposal_id}/reject",
            request,
            ReviewDecisionResponse,
        )

    def create_manual_element(
        self,
        project_id: UUID,
        request: CreateManualElementRequest,
    ) -> ReviewDecisionResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/projects/{project_id}/review/elements",
            request,
            ReviewDecisionResponse,
        )

    def create_manual_relation(
        self,
        project_id: UUID,
        request: CreateManualRelationRequest,
    ) -> ReviewDecisionResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/projects/{project_id}/review/relations",
            request,
            ReviewDecisionResponse,
        )

    def _json_model(
        self,
        method: str,
        path: str,
        request: BaseModel | None,
        model: type[ModelT],
    ) -> ModelT:
        body = request.model_dump_json().encode("utf-8") if request is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        attempts = 2 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                status, response_headers, payload = self._request(
                    method,
                    path,
                    headers=headers,
                    body=body,
                )
                return self._model_response(status, response_headers, payload, model)
            except (OSError, http.client.HTTPException) as error:
                if attempt + 1 < attempts:
                    continue
                raise ReviewGatewayError(
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
        target = f"{self._base_path}{path}"
        try:
            connection.request(method, target, body=body, headers=request_headers)
            response = connection.getresponse()
            payload = response.read()
            return (
                response.status,
                {key.lower(): value for key, value in response.getheaders()},
                payload,
            )
        finally:
            connection.close()

    @staticmethod
    def _model_response(
        status: int,
        headers: Mapping[str, str],
        payload: bytes,
        model: type[ModelT],
    ) -> ModelT:
        if 200 <= status < 300:
            return model.model_validate_json(payload)
        try:
            envelope = ErrorEnvelope.model_validate_json(payload)
        except ValueError as error:
            raise ReviewGatewayError(
                ErrorCode.INTERNAL_ERROR,
                "O servidor devolveu uma resposta inválida.",
                status_code=status,
                correlation_id=headers.get("x-correlation-id"),
            ) from error
        raise ReviewGatewayError(
            envelope.code,
            envelope.message,
            status_code=status,
            correlation_id=str(envelope.correlation_id.root),
            details=dict(envelope.details or {}),
        )
