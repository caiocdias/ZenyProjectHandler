"""Conversões primitivas usadas na projeção dos DTOs HTTP."""

from __future__ import annotations

from decimal import Decimal

_LABEL_MAX_LENGTH = 500


def decimal_string(value: Decimal | int | float | str) -> str:
    """Formate um decimal para transporte sem usar notação científica."""
    return format(Decimal(str(value)), "f")


def bounded_label(value: str | None) -> str | None:
    """Limite texto de apresentação ao contrato sem alterar o dado de origem."""
    if value is None or len(value) <= _LABEL_MAX_LENGTH:
        return value
    return f"{value[: _LABEL_MAX_LENGTH - 1]}…"
