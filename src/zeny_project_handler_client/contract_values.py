"""Conversões primitivas usadas na construção de DTOs pelo cliente."""

from __future__ import annotations

from decimal import Decimal


def decimal_string(value: Decimal | int | float | str) -> str:
    """Formate um decimal para transporte sem usar notação científica."""
    return format(Decimal(str(value)), "f")
