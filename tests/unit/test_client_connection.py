from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox
from pytestqt.qtbot import QtBot

from zeny_project_handler_client.config import ClientSettings
from zeny_project_handler_client.connection_dialog import ConnectionDialog
from zeny_project_handler_client.ui.project_gateway import ProjectGatewayError
from zeny_project_handler_contracts.enums import OcrStatus
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.session import OcrDiagnosticDto, SessionCapabilitiesResponse


def _session() -> SessionCapabilitiesResponse:
    return SessionCapabilitiesResponse(
        server_version="0.1.0",
        api_version="1.0.0",
        min_compatible_api_version="1.0.0",
        max_compatible_api_version="1.999.999",
        ready=True,
        capabilities=("thin-client",),
        ocr=OcrDiagnosticDto(
            status=OcrStatus.AVAILABLE,
            engine="Tesseract",
            language="por",
            message="Disponível",
        ),
        server_time=datetime(2026, 8, 20, 12, tzinfo=UTC),
    )


def test_connection_dialog_rejects_wrong_password_then_accepts_retry(qtbot: QtBot) -> None:
    attempts: list[tuple[str, str]] = []

    def attempt(url: str, password: str) -> SessionCapabilitiesResponse:
        attempts.append((url, password))
        if len(attempts) == 1:
            raise ProjectGatewayError(
                ErrorCode.AUTHENTICATION_FAILED,
                "Credenciais inválidas.",
                status_code=401,
            )
        return _session()

    dialog = ConnectionDialog(
        initial_url="http://127.0.0.1:8000",
        attempt=attempt,
    )
    qtbot.addWidget(dialog)
    button_box = dialog.findChild(QDialogButtonBox)
    assert button_box is not None
    connect_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
    dialog.password_input.setText("senha-incorreta")
    qtbot.mouseClick(connect_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]

    assert dialog.result() == 0
    assert dialog.password_input.text() == ""
    assert "Senha incorreta" in dialog.feedback.text()

    dialog.password_input.setText("senha-correta")
    qtbot.mouseClick(connect_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]

    assert dialog.result() == int(ConnectionDialog.DialogCode.Accepted)
    assert dialog.session == _session()
    assert dialog.password_input.text() == ""
    assert attempts == [
        ("http://127.0.0.1:8000", "senha-incorreta"),
        ("http://127.0.0.1:8000", "senha-correta"),
    ]
    assert dialog.findChildren(type(dialog.password_input)) == [
        dialog.url_input,
        dialog.password_input,
    ]


def test_client_environment_uses_url_but_has_no_password_setting(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = ClientSettings.from_environment(
        {
            "ZENY_DATA_DIR": str(tmp_path),
            "ZENY_CLIENT_SERVER_URL": "http://servidor-lan:8123",
            "ZENY_SERVER_PASSWORD": "segredo-que-deve-ser-ignorado",
        }
    )

    assert settings.development_server_url == "http://servidor-lan:8123"
    assert not any("password" in name or "senha" in name for name in settings.__slots__)
