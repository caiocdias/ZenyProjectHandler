"""Inicie o cliente com os valores efêmeros fornecidos pelo lançador de desenvolvimento."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

from PySide6.QtWidgets import QDialog, QWidget

from zeny_project_handler_client.bootstrap import run
from zeny_project_handler_client.connection_dialog import ConnectionDialog
from zeny_project_handler_contracts.session import SessionCapabilitiesResponse


def main() -> int:
    """Preencha a conexão local sem introduzir credenciais padrão no cliente distribuído."""
    server_url = os.environ.get("ZENY_CLIENT_SERVER_URL", "").strip()
    server_password = os.environ.pop("ZENY_SERVER_PASSWORD", "")
    if not server_url or not server_password:
        raise RuntimeError(
            "O cliente de desenvolvimento deve ser iniciado por ZenyProjectHandler.bat"
        )

    def development_dialog(
        _initial_url: str,
        attempt: Callable[[str, str], SessionCapabilitiesResponse],
        parent: QWidget | None,
    ) -> QDialog:
        dialog = ConnectionDialog(initial_url=server_url, attempt=attempt, parent=parent)
        dialog.password_input.setText(server_password)
        return dialog

    return run(sys.argv, dialog_factory=development_dialog)


if __name__ == "__main__":
    raise SystemExit(main())
