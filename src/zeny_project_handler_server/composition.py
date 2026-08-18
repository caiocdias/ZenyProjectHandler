"""Composição e lifecycle dos recursos pertencentes ao processo servidor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Protocol

from zeny_project_handler.adapters.analysis.tesseract_runtime import (
    RuntimeTesseract,
    inspect_tesseract_runtime,
)
from zeny_project_handler.composition import CoreServices, compose_core_services
from zeny_project_handler_contracts import (
    API_VERSION,
    MAX_COMPATIBLE_API_VERSION,
    MIN_COMPATIBLE_API_VERSION,
)
from zeny_project_handler_contracts.enums import OcrStatus
from zeny_project_handler_contracts.session import (
    OcrDiagnosticDto,
    SessionCapabilitiesResponse,
)
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.project_api import ProjectApiService

SERVER_CAPABILITIES = (
    "authenticated-session",
    "persistent-storage",
    "tesseract-ocr",
    "managed-projects",
    "managed-document-uploads",
    "managed-photos",
)


class JobLifecycle(Protocol):
    """Fronteira preparada para o gerenciador de jobs da Etapa 5."""

    def stop_accepting(self) -> None: ...

    def cancel_and_wait(self) -> None: ...


class _IdleJobLifecycle:
    def stop_accepting(self) -> None:
        pass

    def cancel_and_wait(self) -> None:
        pass


class ServerRuntimeProtocol(Protocol):
    """Superfície usada pela camada HTTP durante startup e shutdown."""

    def session_capabilities(self) -> SessionCapabilitiesResponse: ...

    @property
    def project_api(self) -> ProjectApiService | None: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class ServerRuntime:
    """Recursos vivos do worker único e encerramento ordenado e idempotente."""

    core: CoreServices
    ocr: RuntimeTesseract
    jobs: JobLifecycle
    project_api: ProjectApiService | None = None
    _closed: bool = False

    def session_capabilities(self) -> SessionCapabilitiesResponse:
        """Exponha somente diagnóstico seguro, nunca caminhos ou configuração sensível."""
        if self._closed:
            raise RuntimeError("O runtime do servidor já foi encerrado")
        return SessionCapabilitiesResponse(
            server_version=_server_version(),
            api_version=API_VERSION,
            min_compatible_api_version=MIN_COMPATIBLE_API_VERSION,
            max_compatible_api_version=MAX_COMPATIBLE_API_VERSION,
            ready=True,
            capabilities=SERVER_CAPABILITIES,
            ocr=_ocr_diagnostic(self.ocr),
            global_operation=None,
            server_time=datetime.now(UTC),
        )

    def close(self) -> None:
        """Pare novos jobs, aguarde cancelamento e só então descarte o engine."""
        if self._closed:
            return
        self._closed = True
        try:
            self.jobs.stop_accepting()
            self.jobs.cancel_and_wait()
        finally:
            try:
                if self.project_api is not None:
                    self.project_api.close()
            finally:
                self.core.close()


RuntimeFactory = Callable[[ServerSettings], ServerRuntimeProtocol]


def compose_server_runtime(settings: ServerSettings) -> ServerRuntime:
    """Inicialize fonte persistente, coordenação e OCR sem importar o bootstrap Qt."""
    core = compose_core_services(settings.core_settings())
    try:
        ocr = inspect_tesseract_runtime(settings.data_directory)
    except BaseException:
        core.close()
        raise
    try:
        project_api = ProjectApiService(
            engine=core.engine,
            catalog_id=core.catalog.id,
            data_directory=settings.data_directory,
            database_path=settings.core_settings().database_path,
            coordinator=core.operation_coordinator,
            upload_max_bytes=settings.upload_max_bytes,
        )
    except BaseException:
        core.close()
        raise
    return ServerRuntime(
        core=core,
        ocr=ocr,
        jobs=_IdleJobLifecycle(),
        project_api=project_api,
    )


def _server_version() -> str:
    try:
        return version("zeny-project-handler")
    except PackageNotFoundError:
        return "0.1.0"


def _ocr_diagnostic(runtime: RuntimeTesseract) -> OcrDiagnosticDto:
    if runtime.portugues_pronto:
        return OcrDiagnosticDto(
            status=OcrStatus.AVAILABLE,
            engine="tesseract",
            language="+".join(runtime.idiomas_selecionados),
            message="OCR Tesseract em português disponível.",
        )
    diagnostic = runtime.diagnostico
    status = OcrStatus.UNAVAILABLE if runtime.executavel is None else OcrStatus.DEGRADED
    return OcrDiagnosticDto(
        status=status,
        engine="tesseract" if runtime.executavel is not None else None,
        language=("+".join(runtime.idiomas_selecionados) or None),
        message=(
            diagnostic.mensagem
            if diagnostic is not None
            else "OCR Tesseract em português indisponível."
        ),
    )
