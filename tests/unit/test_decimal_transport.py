"""Conversões decimais nas duas fronteiras de transporte."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from zeny_project_handler_client.contract_values import decimal_string as client_decimal_string
from zeny_project_handler_server.dto_values import decimal_string as server_decimal_string


@pytest.mark.parametrize("formatter", (client_decimal_string, server_decimal_string))
@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (Decimal("0E-17"), "0.00000000000000000"),
        ("1E-17", "0.00000000000000001"),
        (1e-17, "0.00000000000000001"),
    ),
)
def test_decimal_string_expands_scientific_notation(
    formatter: Callable[[Decimal | int | float | str], str],
    value: Decimal | float | str,
    expected: str,
) -> None:
    result = formatter(value)

    assert result == expected
    assert "e" not in result.lower()
