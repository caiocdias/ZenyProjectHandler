"""Falhas HTTP seguras da API executável."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import JsonValue

from zeny_project_handler_contracts.errors import ErrorCode


@dataclass(slots=True)
class ApiError(Exception):
    """Erro esperado que pode atravessar a fronteira sem detalhes internos."""

    status_code: int
    code: ErrorCode
    message: str
    details: dict[str, JsonValue] | None = None

    def __str__(self) -> str:
        return self.message


class UploadTooLargeError(ApiError):
    def __init__(self, maximum_bytes: int) -> None:
        super().__init__(
            status_code=413,
            code=ErrorCode.UPLOAD_TOO_LARGE,
            message="O arquivo excede o limite aceito pelo servidor.",
            details={"maximum_bytes": maximum_bytes},
        )


class IdempotencyConflictError(ApiError):
    def __init__(self) -> None:
        super().__init__(
            status_code=409,
            code=ErrorCode.IDEMPOTENCY_CONFLICT,
            message="A chave de idempotência já foi usada por outra solicitação.",
        )


class StaleStateError(ApiError):
    def __init__(self, current_version: int) -> None:
        super().__init__(
            status_code=409,
            code=ErrorCode.STALE_STATE,
            message="O projeto mudou; recarregue os dados antes de tentar novamente.",
            details={"current_project_version": current_version},
        )


def resource_not_found(message: str) -> ApiError:
    return ApiError(404, ErrorCode.RESOURCE_NOT_FOUND, message)


def validation_error(message: str) -> ApiError:
    return ApiError(422, ErrorCode.VALIDATION_ERROR, message)


def operation_conflict(message: str) -> ApiError:
    return ApiError(409, ErrorCode.OPERATION_CONFLICT, message)


def unsupported_media(message: str) -> ApiError:
    return ApiError(415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, message)
