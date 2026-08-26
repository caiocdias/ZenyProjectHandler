"""Bootstrap do cliente: Qt, preferências visuais e sessão HTTP autenticada."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from subprocess import list2cmdline
from typing import cast

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from zeny_project_handler_client.config import ClientRenderBudget, ClientSettings
from zeny_project_handler_client.connection import (
    ClientGateways,
    ConnectionManager,
)
from zeny_project_handler_client.connection_dialog import ConnectionDialog
from zeny_project_handler_client.logging_config import (
    configure_logging,
    install_unhandled_exception_logging,
    operation_logger,
)
from zeny_project_handler_client.ui.application_icon import (
    carregar_icone_aplicacao,
    materializar_icone_aplicacao,
)
from zeny_project_handler_client.ui.documentation_gateway import DocumentationGateway
from zeny_project_handler_client.ui.main_window import MainWindow
from zeny_project_handler_client.ui.pdf_gateway import PdfViewerGateway
from zeny_project_handler_client.ui.portability_gateway import PortabilityGateway
from zeny_project_handler_client.ui.project_gateway import ProjectGateway
from zeny_project_handler_client.ui.review_gateway import ReviewGateway
from zeny_project_handler_client.ui.theme import THEME_SETTING_KEY, Tema, aplicar_tema
from zeny_project_handler_client.windows_app_identity import (
    configurar_identidade_aplicativo_windows,
    configurar_identidade_janela_windows,
)
from zeny_project_handler_contracts.enums import OcrStatus
from zeny_project_handler_contracts.session import SessionCapabilitiesResponse

CONNECTION_URL_SETTING_KEY = "connection/server_url"
DialogFactory = Callable[
    [str, Callable[[str, str], SessionCapabilitiesResponse], QWidget | None],
    QDialog,
]


class ConnectionCancelledError(RuntimeError):
    """O usuário encerrou o diálogo antes de autenticar."""


def create_application(
    argv: Sequence[str] | None = None,
    *,
    settings: ClientSettings | None = None,
    pdf_viewer_gateway: PdfViewerGateway | None = None,
    project_gateway: ProjectGateway | None = None,
    review_gateway: ReviewGateway | None = None,
    documentation_gateway: DocumentationGateway | None = None,
    portability_gateway: PortabilityGateway | None = None,
    dialog_factory: DialogFactory | None = None,
) -> tuple[QApplication, MainWindow]:
    """Valide a sessão e somente então construa painéis que consultam dados."""
    app_settings = settings or ClientSettings.from_environment()
    logger = configure_logging(app_settings)
    install_unhandled_exception_logging()
    observation = operation_logger("client.bootstrap", logger=logger)
    with observation.context():
        observation.started()
        try:
            application = _qt_application(argv, app_settings)
            ui_settings, initial_theme = _local_ui_settings(application, app_settings)
            manager = ConnectionManager()
            session = _establish_initial_session(
                manager,
                ui_settings,
                app_settings,
                pdf_viewer_gateway=pdf_viewer_gateway,
                project_gateway=project_gateway,
                review_gateway=review_gateway,
                documentation_gateway=documentation_gateway,
                portability_gateway=portability_gateway,
                dialog_factory=dialog_factory,
            )
            window = _build_window(
                application,
                app_settings,
                ui_settings,
                initial_theme,
                manager,
                session,
                dialog_factory,
            )
        except ConnectionCancelledError:
            observation.cancelled()
            raise
        except Exception as error:
            observation.failed(error, expected=False)
            raise
        observation.succeeded()
        return application, window


def _qt_application(
    argv: Sequence[str] | None,
    settings: ClientSettings,
) -> QApplication:
    arguments = list(argv) if argv is not None else list(sys.argv)
    existing = QApplication.instance()
    if existing is None:
        configurar_identidade_aplicativo_windows()
        application = QApplication(arguments)
    else:
        application = cast(QApplication, existing)
    application.setApplicationName(settings.application_name)
    application.setOrganizationName(settings.organization_name)
    application.setWindowIcon(carregar_icone_aplicacao())
    return application


def _local_ui_settings(
    application: QApplication,
    settings: ClientSettings,
) -> tuple[QSettings, Tema]:
    ui_settings = QSettings(str(settings.ui_state_path), QSettings.Format.IniFormat)
    saved_theme = ui_settings.value(THEME_SETTING_KEY, Tema.CLARO.value)
    return ui_settings, aplicar_tema(application, str(saved_theme))


def _establish_initial_session(
    manager: ConnectionManager,
    ui_settings: QSettings,
    settings: ClientSettings,
    *,
    pdf_viewer_gateway: PdfViewerGateway | None,
    project_gateway: ProjectGateway | None,
    review_gateway: ReviewGateway | None,
    documentation_gateway: DocumentationGateway | None,
    portability_gateway: PortabilityGateway | None,
    dialog_factory: DialogFactory | None,
) -> SessionCapabilitiesResponse:
    custom = (
        pdf_viewer_gateway,
        project_gateway,
        review_gateway,
        documentation_gateway,
        portability_gateway,
    )
    if any(item is not None for item in custom):
        if not all(item is not None for item in custom):
            raise ValueError("Os testes devem fornecer o conjunto completo de gateways do cliente")
        return manager.install_test_gateways(
            ClientGateways(
                cast(PdfViewerGateway, pdf_viewer_gateway),
                cast(ProjectGateway, project_gateway),
                cast(ReviewGateway, review_gateway),
                cast(DocumentationGateway, documentation_gateway),
                cast(PortabilityGateway, portability_gateway),
            )
        )
    return _show_connection_dialog(
        manager,
        ui_settings,
        settings.development_server_url,
        parent=None,
        dialog_factory=dialog_factory,
    )


def _show_connection_dialog(
    manager: ConnectionManager,
    ui_settings: QSettings,
    fallback_url: str,
    *,
    parent: QWidget | None,
    dialog_factory: DialogFactory | None,
) -> SessionCapabilitiesResponse:
    saved_url = str(ui_settings.value(CONNECTION_URL_SETTING_KEY, manager.url or fallback_url))
    factory = dialog_factory or _default_dialog_factory
    dialog = factory(saved_url, manager.connect, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        raise ConnectionCancelledError("Conexão cancelada; nenhum dado remoto foi carregado.")
    session = getattr(dialog, "session", None)
    connected_url = getattr(dialog, "connected_url", None)
    if not isinstance(session, SessionCapabilitiesResponse) or not isinstance(connected_url, str):
        raise RuntimeError("O diálogo encerrou sem uma sessão autenticada válida")
    ui_settings.setValue(CONNECTION_URL_SETTING_KEY, connected_url)
    ui_settings.sync()
    return session


def _default_dialog_factory(
    initial_url: str,
    attempt: Callable[[str, str], SessionCapabilitiesResponse],
    parent: QWidget | None,
) -> QDialog:
    return ConnectionDialog(initial_url=initial_url, attempt=attempt, parent=parent)


def _build_window(
    application: QApplication,
    settings: ClientSettings,
    ui_settings: QSettings,
    initial_theme: Tema,
    manager: ConnectionManager,
    session: SessionCapabilitiesResponse,
    dialog_factory: DialogFactory | None,
) -> MainWindow:
    gateways = manager.gateways

    def reconnect() -> bool:
        try:
            _show_connection_dialog(
                manager,
                ui_settings,
                settings.development_server_url,
                parent=window,
                dialog_factory=dialog_factory,
            )
        except ConnectionCancelledError:
            return False
        return True

    window = MainWindow(
        application_name=settings.application_name,
        pdf_viewer_gateway=gateways.pdf,
        project_gateway=gateways.project,
        pdf_render_dpi=settings.pdf_render_dpi,
        pdf_render_budget=ClientRenderBudget(
            settings.pdf_render_max_pixels,
            settings.pdf_render_max_bytes,
        ),
        pdf_tile_cache_max_bytes=settings.pdf_tile_cache_max_bytes,
        review_gateway=gateways.review,
        documentation_gateway=gateways.documentation,
        portability_gateway=gateways.portability,
        reconnect_callback=reconnect,
        ui_state_path=settings.ui_state_path,
        initial_theme=initial_theme,
        window_icon=application.windowIcon(),
        startup_ocr_diagnostic=(
            session.ocr.message if session.ocr.status is not OcrStatus.AVAILABLE else None
        ),
    )

    def connection_lost(message: str) -> None:
        manager.mark_unavailable()
        window.set_connection_available(False, message)

    manager.events.lost.connect(connection_lost)

    def cleanup_window_identity() -> None:
        pass

    if application.platformName() == "windows":
        icon_path = materializar_icone_aplicacao(settings.data_directory)
        relaunch_command = list2cmdline([sys.executable, "-m", "zeny_project_handler_client"])
        cleanup_window_identity = configurar_identidade_janela_windows(
            int(window.winId()),
            icon_path=icon_path,
            relaunch_command=relaunch_command,
            application_name=settings.application_name,
        )

    cleaned = False

    def release_resources() -> None:
        nonlocal cleaned
        if cleaned:
            return
        cleaned = True
        try:
            cleanup_window_identity()
        finally:
            manager.clear()

    window.set_resource_cleanup(release_resources)
    application.aboutToQuit.connect(release_resources)
    window.destroyed.connect(release_resources)
    return window


def _artifact_self_test(argv: Sequence[str]) -> int:
    """Comprove que Qt e assets carregam no executável sem tocar no diretório de dados."""
    existing = QApplication.instance()
    application = QApplication(list(argv)) if existing is None else cast(QApplication, existing)
    icon = carregar_icone_aplicacao()
    application.setWindowIcon(icon)
    return 0 if not icon.isNull() else 1


def run(
    argv: Sequence[str] | None = None,
    *,
    settings: ClientSettings | None = None,
    dialog_factory: DialogFactory | None = None,
) -> int:
    arguments = list(argv) if argv is not None else list(sys.argv)
    if "--artifact-self-test" in arguments:
        return _artifact_self_test(
            [argument for argument in arguments if argument != "--artifact-self-test"]
        )
    smoke_test = "--smoke-test" in arguments
    qt_arguments = [argument for argument in arguments if argument != "--smoke-test"]
    try:
        application, window = create_application(
            qt_arguments,
            settings=settings,
            dialog_factory=dialog_factory,
        )
    except ConnectionCancelledError:
        return 0
    window.show()
    if smoke_test:
        try:
            application.processEvents()
            return 0
        finally:
            window.close()
    try:
        return application.exec()
    finally:
        window.close()
