"""Autenticação Bearer simples, uniforme e comparada em tempo constante."""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from typing import Annotated
from uuid import UUID

from fastapi import Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from zeny_project_handler_contracts.base import CorrelationId
from zeny_project_handler_contracts.errors import ErrorCode, ErrorEnvelope

AUTHENTICATION_MESSAGE = "Não foi possível autenticar a solicitação."
BEARER_CHALLENGE = "Bearer"
_bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")


class AuthenticationFailedError(Exception):
    """Sinal interno sem incluir a credencial recebida."""


@dataclass(frozen=True, slots=True)
class BearerAuthenticator:
    """Dependência FastAPI que nunca persiste nem registra o token recebido."""

    expected_password: str = field(repr=False)

    async def __call__(
        self,
        request: Request,
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Security(_bearer_scheme),
        ],
    ) -> None:
        del request
        if credentials is None or credentials.scheme.casefold() != "bearer":
            raise AuthenticationFailedError
        supplied = credentials.credentials.encode("utf-8")
        expected = self.expected_password.encode("utf-8")
        if not hmac.compare_digest(supplied, expected):
            raise AuthenticationFailedError


def authentication_error(correlation_id: str) -> ErrorEnvelope:
    """Produza a resposta genérica comum a credencial ausente ou incorreta."""
    return ErrorEnvelope(
        code=ErrorCode.AUTHENTICATION_FAILED,
        message=AUTHENTICATION_MESSAGE,
        correlation_id=CorrelationId(UUID(correlation_id)),
    )
