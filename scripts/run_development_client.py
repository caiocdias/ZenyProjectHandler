"""Espere o servidor Docker efêmero e execute o cliente local pré-configurado."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PySide6.QtWidgets import QDialog, QWidget

from zeny_project_handler_client.bootstrap import run
from zeny_project_handler_client.connection_dialog import ConnectionDialog
from zeny_project_handler_contracts.session import SessionCapabilitiesResponse


def main() -> int:
    """Preencha a conexão local sem introduzir credenciais padrão no cliente distribuído."""
    os.environ.pop("ZENY_MARKET_SQLSERVER_CONNECTION_STRING", None)
    os.environ.pop("ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS", None)
    server_url = os.environ.get("ZENY_CLIENT_SERVER_URL", "").strip()
    server_password = os.environ.pop("ZENY_SERVER_PASSWORD", "")
    session_directory_value = os.environ.get("ZENY_LOCAL_SESSION_DIR", "").strip()
    stop_file_value = os.environ.get("ZENY_LOCAL_STOP_FILE", "").strip()
    result_file_value = os.environ.get("ZENY_LOCAL_RESULT_FILE", "").strip()
    compose_file = os.environ.get("ZENY_LOCAL_COMPOSE_FILE", "").strip()
    compose_project = os.environ.get("ZENY_LOCAL_COMPOSE_PROJECT", "").strip()
    if not all(
        (
            server_url,
            server_password,
            session_directory_value,
            stop_file_value,
            result_file_value,
            compose_file,
            compose_project,
        )
    ):
        raise RuntimeError(
            "O cliente de desenvolvimento deve ser iniciado por ZenyProjectHandler.bat"
        )
    session_directory = Path(session_directory_value)
    stop_file = Path(stop_file_value)
    result_file = Path(result_file_value)

    def development_dialog(
        _initial_url: str,
        attempt: Callable[[str, str], SessionCapabilitiesResponse],
        parent: QWidget | None,
    ) -> QDialog:
        dialog = ConnectionDialog(initial_url=server_url, attempt=attempt, parent=parent)
        dialog.password_input.setText(server_password)
        return dialog

    exit_code = 1
    try:
        _wait_until_ready(server_url, server_password, stop_file)
        if stop_file.exists():
            return exit_code
        exit_code = run(sys.argv, dialog_factory=development_dialog)
        return exit_code
    finally:
        _stop_server(compose_file, compose_project, server_password)
        logging.shutdown()
        result_file.parent.mkdir(parents=True, exist_ok=True)
        result_file.write_text(str(exit_code), encoding="ascii")
        _discard_client_data(session_directory, result_file)


def _wait_until_ready(server_url: str, password: str, stop_file: Path) -> None:
    deadline = time.monotonic() + 120
    request = Request(
        f"{server_url.rstrip('/')}/api/v1/session",
        headers={"Authorization": f"Bearer {password}"},
    )
    while time.monotonic() < deadline and not stop_file.exists():
        try:
            with urlopen(request, timeout=1) as response:
                if response.status == 200:
                    return
        except (HTTPError, URLError, TimeoutError, OSError):
            time.sleep(0.25)
    if stop_file.exists():
        raise RuntimeError("O servidor Docker foi encerrado antes de ficar pronto")
    raise RuntimeError("O servidor Docker local não ficou pronto em até 120 segundos")


def _stop_server(compose_file: str, compose_project: str, server_password: str) -> None:
    subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            compose_project,
            "--file",
            compose_file,
            "stop",
            "--timeout",
            "30",
        ],
        check=False,
        env={
            **os.environ,
            "ZENY_SERVER_PASSWORD": server_password,
            # O Compose exige a variável para resolver o arquivo, mas `stop` não a usa.
            # Um sentinela impede que o segredo SQL Server precise existir no processo cliente.
            "ZENY_MARKET_SQLSERVER_CONNECTION_STRING": "development-stop-not-used",
            "ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS": "15",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _discard_client_data(session_directory: Path, result_file: Path) -> None:
    for path in session_directory.iterdir():
        if path == result_file:
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
