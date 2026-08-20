"""Diálogo inicial e de reconexão; nunca oferece persistência de senha."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from zeny_project_handler_contracts.session import SessionCapabilitiesResponse

ConnectionAttempt = Callable[[str, str], SessionCapabilitiesResponse]


class ConnectionDialog(QDialog):
    """Solicite URL e senha e mantenha a senha somente durante a tentativa."""

    def __init__(
        self,
        *,
        initial_url: str,
        attempt: ConnectionAttempt,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._attempt = attempt
        self.connected_url: str | None = None
        self.session: SessionCapabilitiesResponse | None = None
        self.setObjectName("connectionDialog")
        self.setWindowTitle("Conectar ao servidor Zeny")
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        explanation = QLabel(
            "Informe o endereço do servidor e a senha fornecida pelo administrador. "
            "A URL pode ser lembrada; a senha nunca é salva."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        form = QFormLayout()
        self.url_input = QLineEdit(initial_url, self)
        self.url_input.setObjectName("serverUrlInput")
        self.url_input.setPlaceholderText("http://servidor:8000")
        form.addRow("URL do servidor", self.url_input)
        self.password_input = QLineEdit(self)
        self.password_input.setObjectName("serverPasswordInput")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Senha")
        self.password_input.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        form.addRow("Senha", self.password_input)
        layout.addLayout(form)
        self.feedback = QLabel("Cancelar encerra o cliente sem carregar dados.", self)
        self.feedback.setObjectName("connectionFeedback")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Conectar")
        buttons.accepted.connect(self._connect)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def reject(self) -> None:
        self.password_input.clear()
        super().reject()

    def _connect(self) -> None:
        url = self.url_input.text().strip()
        password = self.password_input.text()
        if not url or not password:
            self.feedback.setText("Informe a URL e a senha para conectar.")
            self.password_input.clear()
            self.password_input.setFocus()
            return
        self.setEnabled(False)
        try:
            response = self._attempt(url, password)
        except Exception as error:
            status_code = getattr(error, "status_code", None)
            self.feedback.setText(
                "Senha incorreta ou sessão não autorizada. Tente novamente."
                if status_code == 401
                else str(error).strip() or "Não foi possível alcançar o servidor."
            )
            self.password_input.clear()
            self.password_input.setFocus()
            self.setEnabled(True)
            return
        self.session = response
        self.connected_url = url
        self.password_input.clear()
        self.accept()
