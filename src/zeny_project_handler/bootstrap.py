"""Composição da aplicação desktop."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import cast

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import create_sqlite_engine, upgrade_database
from zeny_project_handler.config import AppSettings
from zeny_project_handler.logging_config import configure_logging
from zeny_project_handler.ui.main_window import MainWindow


def create_application(
    argv: Sequence[str] | None = None,
    *,
    settings: AppSettings | None = None,
) -> tuple[QApplication, MainWindow]:
    """Monte a aplicação sem iniciar o loop de eventos."""
    app_settings = settings or AppSettings.from_environment()
    configure_logging(app_settings)
    initialize_local_storage(app_settings)

    arguments = list(argv) if argv is not None else list(sys.argv)
    existing_application = QApplication.instance()
    if existing_application is None:
        application = QApplication(arguments)
    else:
        application = cast(QApplication, existing_application)

    application.setApplicationName(app_settings.application_name)
    application.setOrganizationName(app_settings.organization_name)

    window = MainWindow(
        application_name=app_settings.application_name,
        pdf_reader=PyMuPdfReader(),
        pdf_render_dpi=app_settings.pdf_render_dpi,
    )
    return application, window


def initialize_local_storage(settings: AppSettings) -> None:
    """Crie a pasta local e migre o banco antes de expor a interface."""
    engine = create_sqlite_engine(settings.database_path)
    try:
        upgrade_database(engine)
    finally:
        engine.dispose()


def run(
    argv: Sequence[str] | None = None,
    *,
    settings: AppSettings | None = None,
) -> int:
    """Inicie o loop de eventos da aplicação."""
    arguments = list(argv) if argv is not None else list(sys.argv)
    smoke_test = "--smoke-test" in arguments
    qt_arguments = [argument for argument in arguments if argument != "--smoke-test"]

    application, window = create_application(qt_arguments, settings=settings)
    window.show()
    if smoke_test:
        QTimer.singleShot(0, application.quit)
    return application.exec()
