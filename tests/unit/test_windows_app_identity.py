from __future__ import annotations

import sys

import pytest

from zeny_project_handler import windows_app_identity


def test_windows_identity_is_configured_with_stable_application_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_ids: list[str] = []

    def record_app_id(app_id: str) -> int:
        configured_ids.append(app_id)
        return 0

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        windows_app_identity,
        "_definir_app_user_model_id",
        record_app_id,
    )

    windows_app_identity.configurar_identidade_aplicativo_windows()

    assert configured_ids == [windows_app_identity.WINDOWS_APP_USER_MODEL_ID]


def test_windows_identity_is_skipped_on_other_platforms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_setter(_app_id: str) -> int:
        pytest.fail("A API do Windows não deveria ser chamada em outra plataforma")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        windows_app_identity,
        "_definir_app_user_model_id",
        unexpected_setter,
    )

    windows_app_identity.configurar_identidade_aplicativo_windows()


def test_windows_identity_failure_has_clear_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(windows_app_identity, "_definir_app_user_model_id", lambda _app_id: -1)

    with pytest.raises(OSError, match="Windows recusou o identificador"):
        windows_app_identity.configurar_identidade_aplicativo_windows()
