from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from socket import create_server
from threading import Event, Thread

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog, QWidget
from pytestqt.qtbot import QtBot
from uvicorn import Config, Server

from zeny_project_handler_client.bootstrap import (
    CONNECTION_URL_SETTING_KEY,
    DialogFactory,
    create_application,
)
from zeny_project_handler_client.config import ClientSettings
from zeny_project_handler_client.ui.project_gateway import ProjectGatewayError
from zeny_project_handler_contracts.session import SessionCapabilitiesResponse
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.config import ServerSettings

PASSWORD = "senha runtime exclusiva do teste de reconexão"


class _AutomaticConnectionDialog(QDialog):
    def __init__(
        self,
        url: str,
        password: str,
        attempt: Callable[[str, str], SessionCapabilitiesResponse],
        parent: QWidget | None,
    ) -> None:
        super().__init__(parent)
        self._url = url
        self._password = password
        self._attempt = attempt
        self.session: SessionCapabilitiesResponse | None = None
        self.connected_url: str | None = None

    def exec(self) -> int:
        self.session = self._attempt(self._url, self._password)
        self.connected_url = self._url
        self._password = ""
        return int(QDialog.DialogCode.Accepted)


@pytest.mark.integration
def test_client_opens_authenticated_blocks_on_disconnect_and_reconnects(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    server_settings = ServerSettings(
        password=PASSWORD,
        data_directory=tmp_path / "server-data",
    )
    client_settings = ClientSettings(data_directory=tmp_path / "client-data")
    connection_targets: list[str] = []

    def factory(
        _initial_url: str,
        attempt: Callable[[str, str], SessionCapabilitiesResponse],
        parent: QWidget | None,
    ) -> QDialog:
        return _AutomaticConnectionDialog(connection_targets.pop(0), PASSWORD, attempt, parent)

    with _running_server(create_app(server_settings)) as first_url:
        connection_targets.append(first_url)
        application, window = create_application(
            [],
            settings=client_settings,
            dialog_factory=cast_dialog_factory(factory),
        )
        qtbot.addWidget(window)
        window.show()
        assert window.project_panel is not None
        panel = window.project_panel
        gateway = panel._gateway
        assert gateway.session().ready
        assert panel.isEnabled()

    with pytest.raises(ProjectGatewayError):
        gateway.session()
    qtbot.waitUntil(lambda: not panel.isEnabled())
    assert window._reconnect_action.isEnabled()

    with _running_server(create_app(server_settings)) as restarted_url:
        connection_targets.append(restarted_url)
        window._reconnect_action.trigger()
        qtbot.waitUntil(panel.isEnabled)
        assert gateway.session().ready
        assert not window._reconnect_action.isEnabled()

    window.close()
    application.processEvents()
    ui_settings = QSettings(str(client_settings.ui_state_path), QSettings.Format.IniFormat)
    assert ui_settings.value(CONNECTION_URL_SETTING_KEY) == restarted_url
    assert all(
        "password" not in key.casefold() and "senha" not in key.casefold()
        for key in ui_settings.allKeys()
    )
    for path in client_settings.data_directory.rglob("*"):
        if path.is_file():
            assert PASSWORD.encode() not in path.read_bytes()
    assert not tuple(client_settings.data_directory.rglob("*.sqlite3"))
    assert not (client_settings.data_directory / "cache").exists()
    assert not (client_settings.data_directory / "project-files").exists()


def cast_dialog_factory(factory: DialogFactory) -> DialogFactory:
    return factory


@contextmanager
def _running_server(app) -> Iterator[str]:  # type: ignore[no-untyped-def]
    with closing(create_server(("127.0.0.1", 0))) as listener:
        port = int(listener.getsockname()[1])
        server = Server(Config(app, log_level="critical", lifespan="on"))
        thread = Thread(
            target=lambda: server.run(sockets=[listener]),
            name="client-reconnection-server",
            daemon=True,
        )
        thread.start()
        tick = Event()
        for _attempt in range(500):
            if server.started:
                break
            if not thread.is_alive():
                raise RuntimeError("Servidor de reconexão encerrou durante a partida")
            tick.wait(0.01)
        else:
            raise RuntimeError("Servidor de reconexão não iniciou no prazo")
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()
