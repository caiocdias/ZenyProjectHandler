"""Aplicação FastAPI executável do servidor base."""

from __future__ import annotations

from base64 import b64encode
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Query, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import JsonValue
from starlette.middleware.base import RequestResponseEndpoint

from zeny_project_handler.adapters.pdf.errors import PdfArquivoInvalidoError
from zeny_project_handler.adapters.persistence.errors import PersistenceConflictError
from zeny_project_handler.application.errors import (
    DocumentoDuplicadoError,
    OperacaoEmAndamentoError,
    PortabilidadeProjetoError,
    ProjetoNaoEncontradoError,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.logging_config import (
    configure_logging,
    correlation_scope,
    install_unhandled_exception_logging,
    operation_logger,
)
from zeny_project_handler_contracts import API_V1_PREFIX, API_VERSION
from zeny_project_handler_contracts.base import CorrelationId
from zeny_project_handler_contracts.documents import (
    CreateUploadResponse,
    DocumentImportResultDto,
    PageOrderResponse,
    RemoveDocumentResponse,
    ReplacePageOrderRequest,
    UnlockPdfRequest,
)
from zeny_project_handler_contracts.errors import ErrorCode, ErrorEnvelope
from zeny_project_handler_contracts.photos import (
    ManagedPhotoListResponse,
    ManagedPhotoResponse,
    RemoveManagedPhotoResponse,
)
from zeny_project_handler_contracts.projects import (
    CreateProjectRequest,
    DeleteProjectResponse,
    ProjectDetailResponse,
    ProjectSummaryListResponse,
    UpdateProjectRequest,
)
from zeny_project_handler_contracts.session import HealthLiveResponse, SessionCapabilitiesResponse
from zeny_project_handler_server.api_errors import ApiError
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
from zeny_project_handler_server.project_api import ManagedDownload, ProjectApiService

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

    @application.exception_handler(ApiError)
    async def handle_api_error(request: Request, error: ApiError) -> JSONResponse:
        return _error_response(
            request,
            status_code=error.status_code,
            code=error.code,
            message=error.message,
            details=error.details,
        )

    @application.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="A solicitação não corresponde ao contrato da API.",
        )

    @application.exception_handler(Exception)
    async def handle_safe_failure(request: Request, error: Exception) -> JSONResponse:
        mapped = _mapped_error(error)
        observation = operation_logger(
            "server.http_failure",
            correlation_id=str(request.state.correlation_id),
        )
        observation.failed(error, expected=mapped is not None)
        if mapped is not None:
            return _error_response(
                request,
                status_code=mapped.status_code,
                code=mapped.code,
                message=mapped.message,
                details=mapped.details,
            )
        return _error_response(
            request,
            status_code=500,
            code=ErrorCode.INTERNAL_ERROR,
            message="O servidor não conseguiu concluir a solicitação.",
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

    protected = [Depends(authenticator)]

    @application.get(
        f"{API_V1_PREFIX}/projects",
        response_model=ProjectSummaryListResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def list_projects(
        request: Request,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> ProjectSummaryListResponse:
        return _project_api(request).list_projects(limit=limit, offset=offset)

    @application.post(
        f"{API_V1_PREFIX}/projects",
        status_code=status.HTTP_201_CREATED,
        response_model=ProjectDetailResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def create_project(
        request: Request,
        payload: CreateProjectRequest,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ) -> ProjectDetailResponse:
        return _project_api(request).create_project(payload.service_note, idempotency_key)

    @application.get(
        f"{API_V1_PREFIX}/projects/{{project_id}}",
        response_model=ProjectDetailResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def get_project(request: Request, project_id: UUID) -> ProjectDetailResponse:
        return _project_api(request).get_project(project_id)

    @application.patch(
        f"{API_V1_PREFIX}/projects/{{project_id}}",
        response_model=ProjectDetailResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def update_project(
        request: Request,
        project_id: UUID,
        payload: UpdateProjectRequest,
    ) -> ProjectDetailResponse:
        return _project_api(request).update_project(
            project_id,
            service_note=payload.service_note,
            expected_version=payload.expected_project_version,
        )

    @application.delete(
        f"{API_V1_PREFIX}/projects/{{project_id}}",
        response_model=DeleteProjectResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def delete_project(request: Request, project_id: UUID) -> DeleteProjectResponse:
        return _project_api(request).delete_project(project_id)

    @application.post(
        f"{API_V1_PREFIX}/projects/{{project_id}}/document-uploads",
        status_code=status.HTTP_201_CREATED,
        response_model=CreateUploadResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def upload_project_document(
        request: Request,
        project_id: UUID,
        file: UploadFile,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ) -> CreateUploadResponse:
        service = _project_api(request)
        received = await service.receive_upload(file)
        return service.upload_document(project_id, received, idempotency_key)

    @application.post(
        f"{API_V1_PREFIX}/uploads/{{upload_id}}/unlock",
        response_model=DocumentImportResultDto,
        dependencies=protected,
        include_in_schema=False,
    )
    async def unlock_pdf_upload(
        request: Request,
        upload_id: UUID,
        payload: UnlockPdfRequest,
    ) -> DocumentImportResultDto:
        return _project_api(request).unlock_pdf(upload_id, payload.password)

    @application.put(
        f"{API_V1_PREFIX}/projects/{{project_id}}/page-order",
        response_model=PageOrderResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def replace_project_page_order(
        request: Request,
        project_id: UUID,
        payload: ReplacePageOrderRequest,
    ) -> PageOrderResponse:
        return _project_api(request).replace_page_order(
            project_id,
            page_ids=tuple(item.root for item in payload.page_ids),
            expected_version=payload.expected_project_version,
        )

    @application.delete(
        f"{API_V1_PREFIX}/projects/{{project_id}}/documents/{{document_id}}",
        response_model=RemoveDocumentResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def remove_project_document(
        request: Request,
        project_id: UUID,
        document_id: UUID,
    ) -> RemoveDocumentResponse:
        return _project_api(request).remove_document(project_id, document_id)

    @application.get(
        f"{API_V1_PREFIX}/projects/{{project_id}}/photos",
        response_model=ManagedPhotoListResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def list_managed_photos(
        request: Request,
        project_id: UUID,
    ) -> ManagedPhotoListResponse:
        return _project_api(request).list_photos(project_id)

    @application.post(
        f"{API_V1_PREFIX}/projects/{{project_id}}/elements/{{element_id}}/photos",
        status_code=status.HTTP_201_CREATED,
        response_model=ManagedPhotoResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def attach_managed_photo(
        request: Request,
        project_id: UUID,
        element_id: UUID,
        file: UploadFile,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ) -> ManagedPhotoResponse:
        service = _project_api(request)
        received = await service.receive_upload(file)
        return service.attach_photo(project_id, element_id, received, idempotency_key)

    @application.delete(
        f"{API_V1_PREFIX}/projects/{{project_id}}/elements/{{element_id}}/photos/{{photo_id}}",
        response_model=RemoveManagedPhotoResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def remove_managed_photo(
        request: Request,
        project_id: UUID,
        element_id: UUID,
        photo_id: UUID,
    ) -> RemoveManagedPhotoResponse:
        return _project_api(request).remove_photo(project_id, element_id, photo_id)

    @application.get(
        f"{API_V1_PREFIX}/projects/{{project_id}}/photos/{{photo_id}}/content",
        response_class=Response,
        dependencies=protected,
        include_in_schema=False,
    )
    async def download_managed_photo(
        request: Request,
        project_id: UUID,
        photo_id: UUID,
    ) -> Response:
        return _stream_download(_project_api(request).photo_download(project_id, photo_id))

    return application


def _runtime(request: Request) -> ServerRuntimeProtocol:
    runtime: ServerRuntimeProtocol = request.app.state.runtime
    return runtime


def _project_api(request: Request) -> ProjectApiService:
    service = _runtime(request).project_api
    if service is None:
        raise ApiError(503, ErrorCode.OPERATION_CONFLICT, "A API de projetos não está disponível.")
    return service


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: dict[str, JsonValue] | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        code=code,
        message=message,
        correlation_id=CorrelationId(UUID(str(request.state.correlation_id))),
        details=details,
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


def _mapped_error(error: Exception) -> ApiError | None:
    if isinstance(error, (ProjetoNaoEncontradoError,)):
        return ApiError(
            404,
            ErrorCode.RESOURCE_NOT_FOUND,
            "O recurso solicitado não foi encontrado.",
        )
    if isinstance(
        error,
        (DocumentoDuplicadoError, OperacaoEmAndamentoError, PersistenceConflictError),
    ):
        return ApiError(409, ErrorCode.OPERATION_CONFLICT, str(error))
    if isinstance(error, PdfArquivoInvalidoError):
        return ApiError(
            415,
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            "O arquivo enviado não é um PDF válido.",
        )
    if isinstance(error, (DomainValidationError, PortabilidadeProjetoError, ValueError)):
        return ApiError(422, ErrorCode.VALIDATION_ERROR, str(error))
    return None


def _stream_download(download: ManagedDownload) -> StreamingResponse:
    def sync_chunks() -> Iterator[bytes]:
        with download.path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                yield chunk

    digest = b64encode(bytes.fromhex(download.sha256)).decode("ascii")
    return StreamingResponse(
        sync_chunks(),
        media_type=download.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{download.display_name}"',
            "Content-Length": str(download.size_bytes),
            "Digest": f"sha-256={digest}",
        },
    )
