from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

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


def test_window_identity_sets_taskbar_relaunch_icon_and_clears_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, dict[str, str | None]]] = []

    def record_properties(handle: int, properties: Mapping[str, str | None]) -> None:
        calls.append((handle, dict(properties)))

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        windows_app_identity,
        "_definir_propriedades_janela",
        record_properties,
    )

    cleanup = windows_app_identity.configurar_identidade_janela_windows(
        1234,
        icon_path=Path("C:/Zeny/icone.ico"),
        relaunch_command='"C:\\Zeny\\pythonw.exe" -m zeny_project_handler',
        application_name="Zeny Project Handler",
    )
    cleanup()
    cleanup()

    assert calls[0] == (
        1234,
        {
            "app_user_model_id": windows_app_identity.WINDOWS_APP_USER_MODEL_ID,
            "relaunch_command": '"C:\\Zeny\\pythonw.exe" -m zeny_project_handler',
            "relaunch_display_name": "Zeny Project Handler",
            "relaunch_icon": "C:\\Zeny\\icone.ico,0",
        },
    )
    assert calls[1] == (1234, dict.fromkeys(calls[0][1]))
    assert len(calls) == 2


def test_window_identity_is_skipped_on_other_platforms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_setter(_handle: int, _properties: Mapping[str, str | None]) -> None:
        pytest.fail("As propriedades da janela não deveriam ser alteradas")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        windows_app_identity,
        "_definir_propriedades_janela",
        unexpected_setter,
    )

    cleanup = windows_app_identity.configurar_identidade_janela_windows(
        1234,
        icon_path=Path("/tmp/icone.ico"),
        relaunch_command="zeny-project-handler",
        application_name="Zeny Project Handler",
    )
    cleanup()
