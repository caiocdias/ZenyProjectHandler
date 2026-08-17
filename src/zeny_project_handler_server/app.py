"""Aplicação FastAPI executável do servidor base."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import RequestResponseEndpoint

from zeny_project_handler.logging_config import (
    configure_logging,
    correlation_scope,
    install_unhandled_exception_logging,
    operation_logger,
)
from zeny_project_handler_contracts import API_V1_PREFIX, API_VERSION
from zeny_project_handler_contracts.session import HealthLiveResponse, SessionCapabilitiesResponse
from zeny_project_handler_server.auth import (
    BEARER_CHALLENGE,
    AuthenticationFailedError,
    BearerAuthenticator,
    authentication_error,
)
from zeny_project_handler_server.composition import (
    RuntimeFactory,
    ServerRuntimeProtocol,
    compose_server_runtime,
)
from zeny_project_handler_server.config import ServerSettings

CORRELATION_HEADER = "X-Correlation-ID"


def create_app(
    settings: ServerSettings | None = None,
    *,
    runtime_factory: RuntimeFactory = compose_server_runtime,
) -> FastAPI:
    """Crie a aplicação; configuração inválida impede até o startup do ASGI."""
    server_settings = settings or ServerSettings.from_environment()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(server_settings.core_settings())
        install_unhandled_exception_logging()
        observation = operation_logger("server.lifecycle")
        with observation.context():
            observation.started()
            try:
                runtime = runtime_factory(server_settings)
            except BaseException as error:
                observation.failed(error, expected=False)
                raise
            application.state.runtime = runtime
            observation.succeeded()
        try:
            yield
        finally:
            shutdown = operation_logger("server.shutdown")
            with shutdown.context():
                shutdown.started()
                try:
                    runtime.close()
                except BaseException as error:
                    shutdown.failed(error, expected=False)
                    raise
                shutdown.succeeded()

    application = FastAPI(
        title="Zeny Project Handler API",
        version=API_VERSION,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    authenticator = BearerAuthenticator(server_settings.password)

    @application.middleware("http")
    async def correlate_request(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        correlation_id = uuid4().hex
        request.state.correlation_id = correlation_id
        observation = operation_logger("server.http_request", correlation_id=correlation_id)
        with correlation_scope(correlation_id):
            observation.started()
            try:
                response = await call_next(request)
            except BaseException as error:
                observation.failed(error, expected=False)
                raise
            response.headers[CORRELATION_HEADER] = correlation_id
            observation.succeeded()
            return response

    @application.exception_handler(AuthenticationFailedError)
    async def handle_authentication_failure(
        request: Request,
        _error: AuthenticationFailedError,
    ) -> JSONResponse:
        correlation_id = str(request.state.correlation_id)
        envelope = authentication_error(correlation_id)
        return JSONResponse(
            status_code=401,
            content=envelope.model_dump(mode="json"),
            headers={"WWW-Authenticate": BEARER_CHALLENGE},
        )

    @application.get(
        "/health/live",
        response_model=HealthLiveResponse,
        include_in_schema=False,
    )
    async def health_live() -> HealthLiveResponse:
        return HealthLiveResponse(live=True)

    @application.get(
        f"{API_V1_PREFIX}/session",
        response_model=SessionCapabilitiesResponse,
        dependencies=[Depends(authenticator)],
        include_in_schema=False,
    )
    async def session(request: Request) -> SessionCapabilitiesResponse:
        runtime = _runtime(request)
        return runtime.session_capabilities()

    return application


def _runtime(request: Request) -> ServerRuntimeProtocol:
    runtime: ServerRuntimeProtocol = request.app.state.runtime
    return runtime
