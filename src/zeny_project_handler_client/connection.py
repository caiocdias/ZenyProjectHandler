"""Sessão autenticada e gateways substituíveis para reconexão sem reiniciar."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Generic, Protocol, TypeVar, cast

from PySide6.QtCore import QObject, Signal

from zeny_project_handler_client import __version__ as client_version
from zeny_project_handler_client.ui.documentation_gateway import (
    DocumentationGateway,
    HttpDocumentationGateway,
)
from zeny_project_handler_client.ui.pdf_gateway import HttpPdfViewerGateway, PdfViewerGateway
from zeny_project_handler_client.ui.portability_gateway import (
    HttpPortabilityGateway,
    PortabilityGateway,
)
from zeny_project_handler_client.ui.project_gateway import HttpProjectGateway, ProjectGateway
from zeny_project_handler_client.ui.review_gateway import HttpReviewGateway, ReviewGateway
from zeny_project_handler_contracts import (
    API_VERSION,
    MAX_COMPATIBLE_API_VERSION,
    MIN_COMPATIBLE_API_VERSION,
)
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.session import SessionCapabilitiesResponse

GatewayT = TypeVar("GatewayT")


class _GatewayTarget(Protocol):
    def __getattr__(self, name: str) -> Any: ...


class ConnectionEvents(QObject):
    """Transporte seguro de falhas detectadas em workers até a thread Qt."""

    lost = Signal(str)


@dataclass(slots=True)
class ReconnectableGateway(Generic[GatewayT]):
    """Proxy estável cujo alvo autenticado pode ser trocado depois de um restart."""

    _events: ConnectionEvents
    _target: GatewayT | None = field(default=None, repr=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def replace(self, target: GatewayT | None) -> None:
        with self._lock:
            self._target = target

    def __getattr__(self, name: str) -> Any:
        with self._lock:
            target = self._target
        if target is None:
            raise RuntimeError("O cliente não possui uma sessão autenticada ativa")
        member = getattr(target, name)
        if not callable(member):
            return member

        def guarded(*args: object, **kwargs: object) -> Any:
            try:
                return member(*args, **kwargs)
            except Exception as error:
                if _is_connection_failure(error):
                    self._events.lost.emit(_safe_connection_message(error))
                raise

        return guarded


@dataclass(frozen=True, slots=True)
class ClientGateways:
    pdf: PdfViewerGateway
    project: ProjectGateway
    review: ReviewGateway
    documentation: DocumentationGateway
    portability: PortabilityGateway


@dataclass(frozen=True, slots=True)
class _ConcreteGateways:
    pdf: PdfViewerGateway
    project: ProjectGateway
    review: ReviewGateway
    documentation: DocumentationGateway
    portability: PortabilityGateway


class ConnectionManager:
    """Valide credenciais antes de publicar gateways aos painéis."""

    def __init__(self, events: ConnectionEvents | None = None) -> None:
        self.events = events or ConnectionEvents()
        self._pdf = ReconnectableGateway[PdfViewerGateway](self.events)
        self._project = ReconnectableGateway[ProjectGateway](self.events)
        self._review = ReconnectableGateway[ReviewGateway](self.events)
        self._documentation = ReconnectableGateway[DocumentationGateway](self.events)
        self._portability = ReconnectableGateway[PortabilityGateway](self.events)
        self._available = False
        self._lock = RLock()
        self._url: str | None = None
        self._test_gateways: ClientGateways | None = None

    @property
    def gateways(self) -> ClientGateways:
        if self._test_gateways is not None:
            return self._test_gateways
        return ClientGateways(
            pdf=cast(PdfViewerGateway, self._pdf),
            project=cast(ProjectGateway, self._project),
            review=cast(ReviewGateway, self._review),
            documentation=cast(DocumentationGateway, self._documentation),
            portability=cast(PortabilityGateway, self._portability),
        )

    @property
    def url(self) -> str | None:
        with self._lock:
            return self._url

    @property
    def available(self) -> bool:
        with self._lock:
            return self._available

    def connect(self, url: str, password: str) -> SessionCapabilitiesResponse:
        """Teste sessão/compatibilidade antes de trocar qualquer gateway em uso."""
        concrete = _http_gateways(url.strip(), password)
        response = concrete.project.session()
        _validate_session(response)
        self._replace(concrete, url.strip())
        return response

    def install_test_gateways(
        self,
        gateways: ClientGateways,
    ) -> SessionCapabilitiesResponse:
        """Instale doubles completos preservando a mesma validação de sessão."""
        response = gateways.project.session()
        _validate_session(response)
        self._replace(
            _ConcreteGateways(
                gateways.pdf,
                gateways.project,
                gateways.review,
                gateways.documentation,
                gateways.portability,
            ),
            "test://authenticated-session",
        )
        self._test_gateways = gateways
        return response

    def mark_unavailable(self) -> None:
        with self._lock:
            self._available = False

    def clear(self) -> None:
        """Elimine todas as referências que retêm a senha da sessão."""
        self._pdf.replace(None)
        self._project.replace(None)
        self._review.replace(None)
        self._documentation.replace(None)
        self._portability.replace(None)
        self._test_gateways = None
        with self._lock:
            self._available = False
            self._url = None

    def _replace(self, concrete: _ConcreteGateways, url: str) -> None:
        self._test_gateways = None
        self._pdf.replace(concrete.pdf)
        self._project.replace(concrete.project)
        self._review.replace(concrete.review)
        self._documentation.replace(concrete.documentation)
        self._portability.replace(concrete.portability)
        with self._lock:
            self._url = url
            self._available = True


def _http_gateways(url: str, password: str) -> _ConcreteGateways:
    return _ConcreteGateways(
        pdf=HttpPdfViewerGateway(url, password),
        project=HttpProjectGateway(url, password),
        review=HttpReviewGateway(url, password),
        documentation=HttpDocumentationGateway(url, password),
        portability=HttpPortabilityGateway(url, password),
    )


def _validate_session(response: SessionCapabilitiesResponse) -> None:
    if not response.ready:
        raise ConnectionError("O servidor respondeu, mas ainda não está pronto para uso.")
    client_api = _version_tuple(API_VERSION)
    server_api = _version_tuple(response.api_version)
    if not (
        _version_tuple(response.min_compatible_api_version)
        <= client_api
        <= _version_tuple(response.max_compatible_api_version)
        and _version_tuple(MIN_COMPATIBLE_API_VERSION)
        <= server_api
        <= _version_tuple(MAX_COMPATIBLE_API_VERSION)
    ):
        raise ConnectionError(
            "Cliente e servidor usam versões incompatíveis da API. "
            f"Cliente {client_version} (API {API_VERSION}); "
            f"servidor {response.server_version} (API {response.api_version})."
        )


def _version_tuple(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3:
        raise ConnectionError("O servidor informou uma versão de API inválida.")
    try:
        return tuple(int(item) for item in parts)  # type: ignore[return-value]
    except ValueError as error:
        raise ConnectionError("O servidor informou uma versão de API inválida.") from error


def _is_connection_failure(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    code = getattr(error, "code", None)
    return status_code == 401 or (
        status_code is None and code in {ErrorCode.AUTHENTICATION_FAILED, ErrorCode.INTERNAL_ERROR}
    )


def _safe_connection_message(error: Exception) -> str:
    if getattr(error, "status_code", None) == 401:
        return "A sessão foi recusada pelo servidor. Reconecte e informe a senha novamente."
    return "A conexão com o servidor foi perdida. Reconecte para liberar as operações."
