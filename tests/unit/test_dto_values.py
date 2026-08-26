"""Limites de valores projetados para os contratos HTTP."""

from zeny_project_handler_server.dto_values import bounded_label


def test_bounded_label_preserves_valid_values_and_none() -> None:
    valid = "x" * 500

    assert bounded_label(None) is None
    assert bounded_label(valid) == valid


def test_bounded_label_truncates_with_ellipsis_inside_contract_limit() -> None:
    oversized = "x" * 501

    result = bounded_label(oversized)

    assert result == f"{'x' * 499}…"
    assert len(result) == 500
