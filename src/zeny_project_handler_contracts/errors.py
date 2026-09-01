"""Envelope e códigos de erro públicos."""

from __future__ import annotations

from enum import StrEnum

from pydantic import JsonValue

from zeny_project_handler_contracts.base import ContractModel, CorrelationId, NonEmptyString


class ErrorCode(StrEnum):
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    PDF_PASSWORD_REQUIRED = "PDF_PASSWORD_REQUIRED"
    PDF_PASSWORD_INVALID = "PDF_PASSWORD_INVALID"
    PDF_SOURCE_CHANGED = "PDF_SOURCE_CHANGED"
    VIEWER_SESSION_EXPIRED = "VIEWER_SESSION_EXPIRED"
    OPERATION_CONFLICT = "OPERATION_CONFLICT"
    PROJECT_ALREADY_EXISTS = "PROJECT_ALREADY_EXISTS"
    STALE_STATE = "STALE_STATE"
    UPLOAD_TOO_LARGE = "UPLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorEnvelope(ContractModel):
    code: ErrorCode
    message: NonEmptyString
    correlation_id: CorrelationId
    details: dict[str, JsonValue] | None = None
