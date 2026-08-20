"""Configuração compartilhada dos testes."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any, Protocol

import pytest

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.logging_config import LOGGER_NAME
from zeny_project_handler_client.logging_config import LOGGER_NAME as CLIENT_LOGGER_NAME

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

    from zeny_project_handler_client.config import ClientSettings
    from zeny_project_handler_client.ui.documentation_gateway import DocumentationGateway
    from zeny_project_handler_client.ui.main_window import MainWindow
    from zeny_project_handler_client.ui.pdf_gateway import PdfViewerGateway
    from zeny_project_handler_client.ui.portability_gateway import PortabilityGateway
from zeny_project_handler_client.ui.project_gateway import ProjectGateway
from zeny_project_handler_client.ui.review_gateway import ReviewGateway

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def catalogo_inicial() -> CatalogoTecnico:
    return carregar_catalogo_inicial()


@pytest.fixture
def app_log_capture(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """Capture os loggers não propagados de cliente e servidor sem trocar handlers reais."""
    loggers = tuple(logging.getLogger(name) for name in (LOGGER_NAME, CLIENT_LOGGER_NAME))
    previous = tuple((logger.level, logger.propagate) for logger in loggers)
    for logger in loggers:
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        for logger, (previous_level, previous_propagate) in zip(
            loggers,
            previous,
            strict=True,
        ):
            logger.removeHandler(caplog.handler)
            logger.setLevel(previous_level)
            logger.propagate = previous_propagate


class ApplicationFactory(Protocol):
    def __call__(
        self,
        argv: Sequence[str] | None = None,
        *,
        settings: ClientSettings | None = None,
        pdf_viewer_gateway: PdfViewerGateway | None = None,
        project_gateway: ProjectGateway | None = None,
        review_gateway: ReviewGateway | None = None,
        documentation_gateway: DocumentationGateway | None = None,
        portability_gateway: PortabilityGateway | None = None,
    ) -> tuple[QApplication, MainWindow]: ...


@pytest.fixture
def application_factory() -> Iterator[ApplicationFactory]:
    """Componha janelas e descarte seus engines antes da coleta do pytest."""
    created: list[tuple[QApplication, MainWindow]] = []
    gateways: list[Any] = []
    server_runtimes: list[Any] = []

    def create(
        argv: Sequence[str] | None = None,
        *,
        settings: ClientSettings | None = None,
        pdf_viewer_gateway: PdfViewerGateway | None = None,
        project_gateway: ProjectGateway | None = None,
        review_gateway: ReviewGateway | None = None,
        documentation_gateway: DocumentationGateway | None = None,
        portability_gateway: PortabilityGateway | None = None,
    ) -> tuple[QApplication, MainWindow]:
        from tests.remote_gateways import (
            DirectDocumentationGateway,
            DirectPdfViewerGateway,
            DirectPortabilityGateway,
            DirectProjectGateway,
            DirectReviewGateway,
        )
        from zeny_project_handler_client.bootstrap import create_application
        from zeny_project_handler_server.composition import compose_server_runtime
        from zeny_project_handler_server.config import ServerSettings

        if settings is None:
            raise ValueError("Os testes de janela devem fornecer AppSettings isolado")
        runtime = None
        if project_gateway is None:
            runtime = compose_server_runtime(
                ServerSettings(
                    password="senha isolada do gateway Qt de testes",
                    data_directory=(
                        settings.data_directory.parent / f"{settings.data_directory.name}-server"
                    ),
                    render_dpi=settings.pdf_render_dpi,
                    render_max_pixels=settings.pdf_render_max_pixels,
                    render_max_bytes=settings.pdf_render_max_bytes,
                )
            )
            server_runtimes.append(runtime)
            project_gateway = DirectProjectGateway(runtime)
        if pdf_viewer_gateway is None:
            if runtime is None:
                raise ValueError("O gateway PDF deve acompanhar o gateway de projeto customizado")
            gateway: Any = DirectPdfViewerGateway(runtime)
        else:
            gateway = pdf_viewer_gateway
        if review_gateway is None:
            if runtime is None:
                raise ValueError("O gateway de revisão deve acompanhar o runtime de teste")
            review_gateway = DirectReviewGateway(runtime)
        if documentation_gateway is None:
            if runtime is None:
                raise ValueError("O gateway de documentação deve acompanhar o runtime de teste")
            documentation_gateway = DirectDocumentationGateway(runtime)
        if portability_gateway is None:
            if runtime is None:
                raise ValueError("O gateway de portabilidade deve acompanhar o runtime de teste")
            portability_gateway = DirectPortabilityGateway(runtime)
        gateways.append(gateway)
        result = create_application(
            argv,
            settings=settings,
            pdf_viewer_gateway=gateway,
            project_gateway=project_gateway,
            review_gateway=review_gateway,
            documentation_gateway=documentation_gateway,
            portability_gateway=portability_gateway,
        )
        created.append(result)
        return result

    try:
        yield create
    finally:
        for application, window in reversed(created):
            window.close()
            window.release_resources()
            application.processEvents()
        for gateway in gateways:
            close = getattr(gateway, "close", None)
            if callable(close):
                close()
        for runtime in reversed(server_runtimes):
            runtime.close()


@pytest.fixture
def pdf_viewer_gateway() -> Iterator[PdfViewerGateway]:
    """Forneça um servidor em memória que mantém o limite UI/DTO dos testes Qt."""
    from tests.viewer_gateway import LocalTestPdfViewerGateway

    gateway = LocalTestPdfViewerGateway()
    try:
        yield gateway
    finally:
        gateway.close()
