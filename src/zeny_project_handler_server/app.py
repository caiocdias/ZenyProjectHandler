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

from zeny_project_handler.adapters.pdf.errors import (
    PdfArquivoInvalidoError,
    PdfOrigemAlteradaError,
    PdfPaginaInvalidaError,
    PdfProtegidoError,
)
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
from zeny_project_handler_contracts.common import NormalizedBoxDto
from zeny_project_handler_contracts.documents import (
    CreateUploadResponse,
    DocumentImportResultDto,
    PageOrderResponse,
    RemoveDocumentResponse,
    ReplacePageOrderRequest,
    UnlockPdfRequest,
)
from zeny_project_handler_contracts.errors import ErrorCode, ErrorEnvelope
from zeny_project_handler_contracts.jobs import (
    CancelJobResponse,
    CreateAnalysisJobRequest,
    JobAcceptedResponse,
    JobResultResponse,
    JobStatusResponse,
)
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
from zeny_project_handler_contracts.review import (
    AcceptReviewProposalRequest,
    CreateManualElementRequest,
    CreateManualRelationRequest,
    RejectReviewProposalRequest,
    ReviewDecisionResponse,
    ReviewProjectSummaryListResponse,
    ReviewSessionResponse,
)
from zeny_project_handler_contracts.session import HealthLiveResponse, SessionCapabilitiesResponse
from zeny_project_handler_contracts.viewer import (
    CloseViewerSessionResponse,
    CreateViewerSessionResponse,
    UnlockViewerPdfResponse,
    ViewerDocumentDto,
    ViewerPageDto,
    ViewerProjectResponse,
)
from zeny_project_handler_server.api_errors import ApiError
from zeny_project_handler_server.auth import (
    BEARER_CHALLENGE,
    AuthenticationFailedError,
    BearerAuthenticator,
    authentication_error,
)
from zeny_project_handler_server.composition import (
    JobLifecycle,
    RuntimeFactory,
    ServerRuntimeProtocol,
    compose_server_runtime,
)
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.project_api import ManagedDownload, ProjectApiService
from zeny_project_handler_server.review_api import ReviewApiService
from zeny_project_handler_server.viewer_api import ViewerApiService, ViewerRaster

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

    @application.post(
        f"{API_V1_PREFIX}/viewer-sessions",
        status_code=status.HTTP_201_CREATED,
        response_model=CreateViewerSessionResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def create_viewer_session(
        request: Request,
        files: list[UploadFile],
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ) -> CreateViewerSessionResponse:
        service = _viewer_api(request)
        received = await service.receive_uploads(files)
        return service.create_session(received, idempotency_key)

    @application.delete(
        f"{API_V1_PREFIX}/viewer-sessions/{{viewer_session_id}}",
        response_model=CloseViewerSessionResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def close_viewer_session(
        request: Request,
        viewer_session_id: UUID,
    ) -> CloseViewerSessionResponse:
        return _viewer_api(request).close_session(viewer_session_id)

    @application.post(
        f"{API_V1_PREFIX}/viewer-sessions/{{viewer_session_id}}/uploads/{{upload_id}}/unlock",
        response_model=UnlockViewerPdfResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def unlock_viewer_session_pdf(
        request: Request,
        viewer_session_id: UUID,
        upload_id: UUID,
        payload: UnlockPdfRequest,
    ) -> UnlockViewerPdfResponse:
        return _viewer_api(request).unlock_session_pdf(
            viewer_session_id,
            upload_id,
            payload.password,
        )

    @application.post(
        f"{API_V1_PREFIX}/viewer-documents/{{document_id}}/unlock",
        response_model=ViewerDocumentDto,
        dependencies=protected,
        include_in_schema=False,
    )
    async def unlock_viewer_project_document(
        request: Request,
        document_id: UUID,
        payload: UnlockPdfRequest,
    ) -> ViewerDocumentDto:
        return _viewer_api(request).unlock_project_document(document_id, payload.password)

    @application.get(
        f"{API_V1_PREFIX}/projects/{{project_id}}/viewer",
        response_model=ViewerProjectResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def get_project_viewer(request: Request, project_id: UUID) -> ViewerProjectResponse:
        return _viewer_api(request).get_project(project_id)

    @application.get(
        f"{API_V1_PREFIX}/viewer-pages/{{page_id}}",
        response_model=ViewerPageDto,
        dependencies=protected,
        include_in_schema=False,
    )
    async def get_viewer_page(request: Request, page_id: UUID) -> ViewerPageDto:
        return _viewer_api(request).get_page(page_id)

    @application.get(
        f"{API_V1_PREFIX}/viewer-pages/{{page_id}}/preview",
        response_class=Response,
        dependencies=protected,
        include_in_schema=False,
    )
    async def get_viewer_page_preview(
        request: Request,
        page_id: UUID,
        dpi: int = Query(default=96, ge=1, le=600),
        rotation: int = Query(default=0, ge=0, le=270, multiple_of=90),
    ) -> Response:
        return _raster_response(
            _viewer_api(request).render_preview(page_id, dpi=dpi, rotation=rotation)
        )

    @application.get(
        f"{API_V1_PREFIX}/viewer-pages/{{page_id}}/tiles",
        response_class=Response,
        dependencies=protected,
        include_in_schema=False,
    )
    async def get_viewer_page_tile(
        request: Request,
        page_id: UUID,
        x: str = Query(pattern=r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"),
        y: str = Query(pattern=r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"),
        width: str = Query(pattern=r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"),
        height: str = Query(pattern=r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"),
        dpi: int = Query(default=600, ge=1, le=600),
        rotation: int = Query(default=0, ge=0, le=270, multiple_of=90),
    ) -> Response:
        clip = NormalizedBoxDto(x=x, y=y, width=width, height=height)
        return _raster_response(
            _viewer_api(request).render_tile(
                page_id,
                dpi=dpi,
                rotation=rotation,
                clip=clip,
            )
        )

    @application.post(
        f"{API_V1_PREFIX}/projects/{{project_id}}/analysis-jobs",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=JobAcceptedResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def create_analysis_job(
        request: Request,
        project_id: UUID,
        payload: CreateAnalysisJobRequest,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ) -> JobAcceptedResponse:
        return _jobs(request).create_analysis_job(
            project_id,
            expected_project_version=payload.expected_project_version,
            force_reanalysis=payload.force_reanalysis,
            idempotency_key=idempotency_key,
            correlation_id=str(request.state.correlation_id),
        )

    @application.get(
        f"{API_V1_PREFIX}/jobs/{{job_id}}",
        response_model=JobStatusResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def get_job(request: Request, job_id: UUID) -> JobStatusResponse:
        return _jobs(request).get_job(job_id)

    @application.get(
        f"{API_V1_PREFIX}/jobs/{{job_id}}/result",
        response_model=JobResultResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def get_job_result(request: Request, job_id: UUID) -> JobResultResponse:
        return _jobs(request).get_result(job_id)

    @application.post(
        f"{API_V1_PREFIX}/jobs/{{job_id}}/cancel",
        response_model=CancelJobResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def cancel_job(request: Request, job_id: UUID) -> CancelJobResponse:
        return _jobs(request).cancel(job_id)

    @application.get(
        f"{API_V1_PREFIX}/review/projects",
        response_model=ReviewProjectSummaryListResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def list_review_projects(
        request: Request,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> ReviewProjectSummaryListResponse:
        return _review_api(request).list_projects(limit=limit, offset=offset)

    @application.get(
        f"{API_V1_PREFIX}/projects/{{project_id}}/review-session",
        response_model=ReviewSessionResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def get_review_session(
        request: Request,
        project_id: UUID,
    ) -> ReviewSessionResponse:
        return _review_api(request).get_session(project_id)

    @application.post(
        f"{API_V1_PREFIX}/review/proposals/{{proposal_id}}/accept",
        response_model=ReviewDecisionResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def accept_review_proposal(
        request: Request,
        proposal_id: UUID,
        payload: AcceptReviewProposalRequest,
    ) -> ReviewDecisionResponse:
        return _review_api(request).accept(proposal_id, payload)

    @application.post(
        f"{API_V1_PREFIX}/review/proposals/{{proposal_id}}/reject",
        response_model=ReviewDecisionResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def reject_review_proposal(
        request: Request,
        proposal_id: UUID,
        payload: RejectReviewProposalRequest,
    ) -> ReviewDecisionResponse:
        return _review_api(request).reject(proposal_id, payload)

    @application.post(
        f"{API_V1_PREFIX}/projects/{{project_id}}/review/elements",
        status_code=status.HTTP_201_CREATED,
        response_model=ReviewDecisionResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def create_manual_review_element(
        request: Request,
        project_id: UUID,
        payload: CreateManualElementRequest,
    ) -> ReviewDecisionResponse:
        return _review_api(request).create_manual_element(project_id, payload)

    @application.post(
        f"{API_V1_PREFIX}/projects/{{project_id}}/review/relations",
        status_code=status.HTTP_201_CREATED,
        response_model=ReviewDecisionResponse,
        dependencies=protected,
        include_in_schema=False,
    )
    async def create_manual_review_relation(
        request: Request,
        project_id: UUID,
        payload: CreateManualRelationRequest,
    ) -> ReviewDecisionResponse:
        return _review_api(request).create_manual_relation(project_id, payload)

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


def _viewer_api(request: Request) -> ViewerApiService:
    service = _runtime(request).viewer_api
    if service is None:
        raise ApiError(503, ErrorCode.OPERATION_CONFLICT, "O visualizador não está disponível.")
    return service


def _review_api(request: Request) -> ReviewApiService:
    service = _runtime(request).review_api
    if service is None:
        raise ApiError(503, ErrorCode.OPERATION_CONFLICT, "A revisão não está disponível.")
    return service


def _jobs(request: Request) -> JobLifecycle:
    return _runtime(request).jobs


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
    if isinstance(error, PdfProtegidoError):
        return ApiError(
            409,
            (
                ErrorCode.PDF_PASSWORD_INVALID
                if error.senha_fornecida
                else ErrorCode.PDF_PASSWORD_REQUIRED
            ),
            (
                "A senha informada para o PDF está incorreta."
                if error.senha_fornecida
                else "O PDF é protegido e requer uma senha."
            ),
        )
    if isinstance(error, PdfOrigemAlteradaError):
        return ApiError(
            409,
            ErrorCode.PDF_SOURCE_CHANGED,
            "A origem PDF mudou desde a abertura da sessão.",
        )
    if isinstance(error, PdfPaginaInvalidaError):
        return ApiError(422, ErrorCode.VALIDATION_ERROR, str(error))
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


def _raster_response(raster: ViewerRaster) -> Response:
    metadata = raster.metadata
    clip = metadata.clip
    return Response(
        content=raster.png,
        media_type=metadata.content_type,
        headers={
            "X-Zeny-Page-Id": str(metadata.page_id.root),
            "X-Zeny-Pixel-Width": str(metadata.pixel_width),
            "X-Zeny-Pixel-Height": str(metadata.pixel_height),
            "X-Zeny-Page-Pixel-Width": str(metadata.page_pixel_width),
            "X-Zeny-Page-Pixel-Height": str(metadata.page_pixel_height),
            "X-Zeny-Origin-X": str(metadata.origin_x_pixels),
            "X-Zeny-Origin-Y": str(metadata.origin_y_pixels),
            "X-Zeny-Requested-Dpi": str(metadata.requested_dpi),
            "X-Zeny-Effective-Dpi": str(metadata.effective_dpi),
            "X-Zeny-Rotation": str(metadata.rotation_degrees),
            "X-Zeny-Clip": f"{clip.x},{clip.y},{clip.width},{clip.height}",
            "X-Zeny-Reduced": "true" if metadata.reduced else "false",
            "Cache-Control": "private, no-store",
        },
    )
