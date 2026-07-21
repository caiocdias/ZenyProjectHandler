"""Validações primitivas compartilhadas pelo domínio de avaliação."""

from __future__ import annotations

import re
from decimal import Decimal

from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import decimal_value, required_text

IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def evaluation_identifier(value: str, *, field_name: str) -> str:
    normalized = required_text(value, field_name=field_name).lower()
    if not IDENTIFIER_PATTERN.fullmatch(normalized):
        raise DomainValidationError(f"{field_name} deve ser um identificador minúsculo com hífens")
    return normalized


def optional_evaluation_text(value: str | None) -> str | None:
    normalized = value.strip() if value else None
    return normalized or None


def evaluation_rate(value: Decimal | int | str, *, field_name: str) -> Decimal:
    result = decimal_value(value, field_name=field_name)
    if not Decimal(0) <= result <= Decimal(1):
        raise DomainValidationError(f"{field_name} deve estar entre 0 e 1")
    return result
