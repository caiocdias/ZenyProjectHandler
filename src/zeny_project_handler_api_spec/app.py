"""Catálogo declarativo das operações da API v1, sem implementação de servidor."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, FastAPI, File, Header, Query, Security, UploadFile, status
from fastapi.responses import Response
from fastapi.security import HTTPBearer

from zeny_project_handler_contracts import API_COMPATIBILITY_POLICY, API_V1_PREFIX, API_VERSION
from zeny_project_handler_contracts.backup import (
    BackupPreflightResponse,
    BackupRestorePreflightResponse,
    ConfirmBackupRestoreRequest,
    CreateBackupJobRequest,
)
from zeny_project_handler_contracts.common import DownloadMetadataDto
from zeny_project_handler_contracts.compliance import (
    ComplianceExecutionResponse,
    ComplianceHistoryResponse,
)
from zeny_project_handler_contracts.documentation import DocumentationResponse
from zeny_project_handler_contracts.documents import (
    CreateUploadResponse,
    DocumentImportResultDto,
    PageOrderResponse,
    RemoveDocumentResponse,
    ReplacePageOrderRequest,
    UnlockPdfRequest,
)
from zeny_project_handler_contracts.errors import ErrorEnvelope
from zeny_project_handler_contracts.exports import CreateDeliverableExportRequest
from zeny_project_handler_contracts.jobs import (
    CancelJobResponse,
    CreateAnalysisJobRequest,
    CreateComplianceJobRequest,
    CreateExportJobRequest,
    JobAcceptedResponse,
    JobResultResponse,
    JobStatusResponse,
)
from zeny_project_handler_contracts.photos import (
    ManagedPhotoListResponse,
    ManagedPhotoResponse,
    RemoveManagedPhotoResponse,
)
from zeny_project_handler_contracts.portability import (
    ConfirmProjectImportRequest,
    ProjectImportPreflightResponse,
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
from zeny_project_handler_contracts.rules import (
    ActiveRuleRegistryResponse,
    ConfirmRuleImportRequest,
    RuleImportPreflightResponse,
    RuleImportResponse,
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

Responses = dict[int | str, dict[str, Any]]

ERROR_RESPONSES: Responses = {
    401: {"model": ErrorEnvelope, "description": "Credencial Bearer ausente ou inválida."},
    404: {"model": ErrorEnvelope, "description": "Recurso não encontrado."},
    409: {"model": ErrorEnvelope, "description": "Conflito de operação ou estado obsoleto."},
    410: {"model": ErrorEnvelope, "description": "Sessão temporária do visualizador expirada."},
    413: {"model": ErrorEnvelope, "description": "Upload acima do limite configurado."},
    415: {"model": ErrorEnvelope, "description": "Tipo de mídia não suportado."},
    422: {"model": ErrorEnvelope, "description": "Request inválido para o contrato v1."},
    500: {"model": ErrorEnvelope, "description": "Erro interno seguro e correlacionável."},
}

RASTER_HEADERS: dict[str, dict[str, Any]] = {
    "X-Zeny-Page-Id": {"schema": {"type": "string", "format": "uuid"}},
    "X-Zeny-Pixel-Width": {"schema": {"type": "integer", "minimum": 1}},
    "X-Zeny-Pixel-Height": {"schema": {"type": "integer", "minimum": 1}},
    "X-Zeny-Page-Pixel-Width": {"schema": {"type": "integer", "minimum": 1}},
    "X-Zeny-Page-Pixel-Height": {"schema": {"type": "integer", "minimum": 1}},
    "X-Zeny-Origin-X": {"schema": {"type": "integer", "minimum": 0}},
    "X-Zeny-Origin-Y": {"schema": {"type": "integer", "minimum": 0}},
    "X-Zeny-Requested-Dpi": {"schema": {"type": "integer", "minimum": 1, "maximum": 600}},
    "X-Zeny-Effective-Dpi": {"schema": {"type": "integer", "minimum": 1, "maximum": 600}},
    "X-Zeny-Rotation": {"schema": {"type": "integer", "enum": [0, 90, 180, 270]}},
    "X-Zeny-Clip": {"schema": {"type": "string"}},
    "X-Zeny-Reduced": {"schema": {"type": "boolean"}},
}
RASTER_RESPONSES: Responses = {
    200: {
        "description": "Raster sem perda com metadados canônicos nos headers.",
        "headers": RASTER_HEADERS,
        "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}},
    },
    **ERROR_RESPONSES,
}
DOWNLOAD_RESPONSES: Responses = {
    200: {
        "description": "Download binário autenticado e limitado pelo servidor.",
        "headers": {
            "Content-Disposition": {"schema": {"type": "string"}},
            "Content-Length": {"schema": {"type": "integer", "minimum": 0}},
            "Digest": {"schema": {"type": "string"}},
        },
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    },
    **ERROR_RESPONSES,
}

app = FastAPI(
    title="Zeny Project Handler API",
    version=API_VERSION,
    summary="Contrato HTTP v1 do cliente magro e do servidor Zeny.",
    description=API_COMPATIBILITY_POLICY,
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
    contact={"name": "Zeny Project Handler"},
    license_info={"name": "Proprietary project contract"},
)
_bearer = HTTPBearer(auto_error=False, scheme_name="BearerAuth")
protected = APIRouter(prefix=API_V1_PREFIX, dependencies=[Security(_bearer)])


@app.get(
    "/health/live",
    tags=["health"],
    operation_id="getHealthLive",
    response_model=HealthLiveResponse,
    responses={500: ERROR_RESPONSES[500]},
)
async def get_health_live() -> HealthLiveResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/session",
    tags=["session"],
    operation_id="getSessionCapabilities",
    response_model=SessionCapabilitiesResponse,
    responses=ERROR_RESPONSES,
)
async def get_session_capabilities() -> SessionCapabilitiesResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/projects",
    tags=["projects"],
    operation_id="listProjects",
    response_model=ProjectSummaryListResponse,
    responses=ERROR_RESPONSES,
)
async def list_projects(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectSummaryListResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/projects",
    tags=["projects"],
    operation_id="createProject",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectDetailResponse,
    responses=ERROR_RESPONSES,
)
async def create_project(
    request: CreateProjectRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> ProjectDetailResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/projects/{project_id}",
    tags=["projects"],
    operation_id="getProject",
    response_model=ProjectDetailResponse,
    responses=ERROR_RESPONSES,
)
async def get_project(project_id: UUID) -> ProjectDetailResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.patch(
    "/projects/{project_id}",
    tags=["projects"],
    operation_id="updateProject",
    response_model=ProjectDetailResponse,
    responses=ERROR_RESPONSES,
)
async def update_project(project_id: UUID, request: UpdateProjectRequest) -> ProjectDetailResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.delete(
    "/projects/{project_id}",
    tags=["projects"],
    operation_id="deleteProject",
    response_model=DeleteProjectResponse,
    responses=ERROR_RESPONSES,
)
async def delete_project(project_id: UUID) -> DeleteProjectResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/projects/{project_id}/document-uploads",
    tags=["documents"],
    operation_id="uploadProjectDocument",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateUploadResponse,
    responses=ERROR_RESPONSES,
)
async def upload_project_document(
    project_id: UUID,
    file: Annotated[UploadFile, File(description="Conteúdo PDF transmitido por streaming.")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> CreateUploadResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/uploads/{upload_id}/unlock",
    tags=["documents"],
    operation_id="unlockPdfUpload",
    response_model=DocumentImportResultDto,
    responses=ERROR_RESPONSES,
)
async def unlock_pdf_upload(upload_id: UUID, request: UnlockPdfRequest) -> DocumentImportResultDto:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.put(
    "/projects/{project_id}/page-order",
    tags=["documents"],
    operation_id="replaceProjectPageOrder",
    response_model=PageOrderResponse,
    responses=ERROR_RESPONSES,
)
async def replace_project_page_order(
    project_id: UUID,
    request: ReplacePageOrderRequest,
) -> PageOrderResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.delete(
    "/projects/{project_id}/documents/{document_id}",
    tags=["documents"],
    operation_id="removeProjectDocument",
    response_model=RemoveDocumentResponse,
    responses=ERROR_RESPONSES,
)
async def remove_project_document(project_id: UUID, document_id: UUID) -> RemoveDocumentResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/viewer-sessions",
    tags=["viewer"],
    operation_id="createViewerSession",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateViewerSessionResponse,
    responses=ERROR_RESPONSES,
)
async def create_viewer_session(
    files: Annotated[list[UploadFile], File(description="Um ou mais PDFs temporários.")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> CreateViewerSessionResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.delete(
    "/viewer-sessions/{viewer_session_id}",
    tags=["viewer"],
    operation_id="closeViewerSession",
    response_model=CloseViewerSessionResponse,
    responses=ERROR_RESPONSES,
)
async def close_viewer_session(viewer_session_id: UUID) -> CloseViewerSessionResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/viewer-sessions/{viewer_session_id}/uploads/{upload_id}/unlock",
    tags=["viewer"],
    operation_id="unlockViewerSessionPdf",
    response_model=UnlockViewerPdfResponse,
    responses=ERROR_RESPONSES,
)
async def unlock_viewer_session_pdf(
    viewer_session_id: UUID,
    upload_id: UUID,
    request: UnlockPdfRequest,
) -> UnlockViewerPdfResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/viewer-documents/{document_id}/unlock",
    tags=["viewer"],
    operation_id="unlockViewerProjectDocument",
    response_model=ViewerDocumentDto,
    responses=ERROR_RESPONSES,
)
async def unlock_viewer_project_document(
    document_id: UUID,
    request: UnlockPdfRequest,
) -> ViewerDocumentDto:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/projects/{project_id}/viewer",
    tags=["viewer"],
    operation_id="getProjectViewer",
    response_model=ViewerProjectResponse,
    responses=ERROR_RESPONSES,
)
async def get_project_viewer(project_id: UUID) -> ViewerProjectResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/viewer-pages/{page_id}",
    tags=["viewer"],
    operation_id="getViewerPage",
    response_model=ViewerPageDto,
    responses=ERROR_RESPONSES,
)
async def get_viewer_page(page_id: UUID) -> ViewerPageDto:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/viewer-pages/{page_id}/preview",
    tags=["viewer"],
    operation_id="getViewerPagePreview",
    response_class=Response,
    responses=RASTER_RESPONSES,
)
async def get_viewer_page_preview(
    page_id: UUID,
    dpi: Annotated[int, Query(ge=1, le=600)] = 96,
    rotation: Annotated[int, Query(ge=0, le=270, multiple_of=90)] = 0,
) -> Response:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/viewer-pages/{page_id}/tiles",
    tags=["viewer"],
    operation_id="getViewerPageTile",
    response_class=Response,
    responses=RASTER_RESPONSES,
)
async def get_viewer_page_tile(
    page_id: UUID,
    x: Annotated[str, Query(pattern=r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")],
    y: Annotated[str, Query(pattern=r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")],
    width: Annotated[str, Query(pattern=r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")],
    height: Annotated[str, Query(pattern=r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")],
    dpi: Annotated[int, Query(ge=1, le=600)] = 600,
    rotation: Annotated[int, Query(ge=0, le=270, multiple_of=90)] = 0,
) -> Response:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/projects/{project_id}/analysis-jobs",
    tags=["analysis", "jobs"],
    operation_id="createAnalysisJob",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAcceptedResponse,
    responses=ERROR_RESPONSES,
)
async def create_analysis_job(
    project_id: UUID,
    request: CreateAnalysisJobRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> JobAcceptedResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/jobs/{job_id}",
    tags=["jobs"],
    operation_id="getJob",
    response_model=JobStatusResponse,
    responses=ERROR_RESPONSES,
)
async def get_job(job_id: UUID) -> JobStatusResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/jobs/{job_id}/result",
    tags=["jobs"],
    operation_id="getJobResult",
    response_model=JobResultResponse,
    responses=ERROR_RESPONSES,
)
async def get_job_result(job_id: UUID) -> JobResultResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/jobs/{job_id}/cancel",
    tags=["jobs"],
    operation_id="cancelJob",
    response_model=CancelJobResponse,
    responses=ERROR_RESPONSES,
)
async def cancel_job(job_id: UUID) -> CancelJobResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/review/projects",
    tags=["review"],
    operation_id="listReviewProjects",
    response_model=ReviewProjectSummaryListResponse,
    responses=ERROR_RESPONSES,
)
async def list_review_projects(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewProjectSummaryListResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/documentation/projects",
    tags=["documentation"],
    operation_id="listDocumentationProjects",
    response_model=ReviewProjectSummaryListResponse,
    responses=ERROR_RESPONSES,
)
async def list_documentation_projects(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewProjectSummaryListResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/projects/{project_id}/review-session",
    tags=["review"],
    operation_id="getReviewSession",
    response_model=ReviewSessionResponse,
    responses=ERROR_RESPONSES,
)
async def get_review_session(project_id: UUID) -> ReviewSessionResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/review/proposals/{proposal_id}/accept",
    tags=["review"],
    operation_id="acceptReviewProposal",
    response_model=ReviewDecisionResponse,
    responses=ERROR_RESPONSES,
)
async def accept_review_proposal(
    proposal_id: UUID,
    request: AcceptReviewProposalRequest,
) -> ReviewDecisionResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/review/proposals/{proposal_id}/reject",
    tags=["review"],
    operation_id="rejectReviewProposal",
    response_model=ReviewDecisionResponse,
    responses=ERROR_RESPONSES,
)
async def reject_review_proposal(
    proposal_id: UUID,
    request: RejectReviewProposalRequest,
) -> ReviewDecisionResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/projects/{project_id}/review/elements",
    tags=["review"],
    operation_id="createManualReviewElement",
    status_code=status.HTTP_201_CREATED,
    response_model=ReviewDecisionResponse,
    responses=ERROR_RESPONSES,
)
async def create_manual_review_element(
    project_id: UUID,
    request: CreateManualElementRequest,
) -> ReviewDecisionResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/projects/{project_id}/review/relations",
    tags=["review"],
    operation_id="createManualReviewRelation",
    status_code=status.HTTP_201_CREATED,
    response_model=ReviewDecisionResponse,
    responses=ERROR_RESPONSES,
)
async def create_manual_review_relation(
    project_id: UUID,
    request: CreateManualRelationRequest,
) -> ReviewDecisionResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/projects/{project_id}/documentation",
    tags=["documentation"],
    operation_id="getProjectDocumentation",
    response_model=DocumentationResponse,
    responses=ERROR_RESPONSES,
)
async def get_project_documentation(project_id: UUID) -> DocumentationResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/projects/{project_id}/compliance/latest",
    tags=["compliance"],
    operation_id="getLatestCompliance",
    response_model=ComplianceExecutionResponse,
    responses=ERROR_RESPONSES,
)
async def get_latest_compliance(project_id: UUID) -> ComplianceExecutionResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/projects/{project_id}/compliance/history",
    tags=["compliance"],
    operation_id="listComplianceHistory",
    response_model=ComplianceHistoryResponse,
    responses=ERROR_RESPONSES,
)
async def list_compliance_history(
    project_id: UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ComplianceHistoryResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/projects/{project_id}/compliance-jobs",
    tags=["compliance", "jobs"],
    operation_id="createComplianceJob",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAcceptedResponse,
    responses=ERROR_RESPONSES,
)
async def create_compliance_job(
    project_id: UUID,
    request: CreateComplianceJobRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> JobAcceptedResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/rules/active",
    tags=["rules"],
    operation_id="getActiveRuleRegistry",
    response_model=ActiveRuleRegistryResponse,
    responses=ERROR_RESPONSES,
)
async def get_active_rule_registry() -> ActiveRuleRegistryResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/rules/import-preflights",
    tags=["rules"],
    operation_id="preflightRuleImport",
    status_code=status.HTTP_201_CREATED,
    response_model=RuleImportPreflightResponse,
    responses=ERROR_RESPONSES,
)
async def preflight_rule_import(
    file: Annotated[UploadFile, File(description="Registro JSON transmitido por streaming.")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> RuleImportPreflightResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/rules/imports",
    tags=["rules"],
    operation_id="confirmRuleImport",
    status_code=status.HTTP_201_CREATED,
    response_model=RuleImportResponse,
    responses=ERROR_RESPONSES,
)
async def confirm_rule_import(request: ConfirmRuleImportRequest) -> RuleImportResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/rules/active/download",
    tags=["rules"],
    operation_id="downloadActiveRuleRegistry",
    response_class=Response,
    responses={
        200: {
            "description": "Registro JSON ativo.",
            "content": {"application/json": {"schema": {"type": "string", "format": "binary"}}},
        },
        **ERROR_RESPONSES,
    },
)
async def download_active_rule_registry() -> Response:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/projects/{project_id}/deliverable-exports",
    tags=["exports"],
    operation_id="createDeliverableExport",
    status_code=status.HTTP_201_CREATED,
    response_model=DownloadMetadataDto,
    responses=ERROR_RESPONSES,
)
async def create_deliverable_export(
    project_id: UUID,
    request: CreateDeliverableExportRequest,
) -> DownloadMetadataDto:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/projects/{project_id}/export-jobs",
    tags=["portability", "jobs"],
    operation_id="createProjectExportJob",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAcceptedResponse,
    responses=ERROR_RESPONSES,
)
async def create_project_export_job(
    project_id: UUID,
    request: CreateExportJobRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> JobAcceptedResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/project-import-preflights",
    tags=["portability"],
    operation_id="preflightProjectImport",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectImportPreflightResponse,
    responses=ERROR_RESPONSES,
)
async def preflight_project_import(
    file: Annotated[UploadFile, File(description="Pacote .zphproj transmitido por streaming.")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> ProjectImportPreflightResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/project-import-jobs",
    tags=["portability", "jobs"],
    operation_id="confirmProjectImport",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAcceptedResponse,
    responses=ERROR_RESPONSES,
)
async def confirm_project_import(
    request: ConfirmProjectImportRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> JobAcceptedResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/backup-preflights",
    tags=["backup"],
    operation_id="preflightBackupCreate",
    status_code=status.HTTP_201_CREATED,
    response_model=BackupPreflightResponse,
    responses=ERROR_RESPONSES,
)
async def preflight_backup_create() -> BackupPreflightResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/backup-jobs",
    tags=["backup", "jobs"],
    operation_id="createBackupJob",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAcceptedResponse,
    responses=ERROR_RESPONSES,
)
async def create_backup_job(
    request: CreateBackupJobRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> JobAcceptedResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/backup-restore-preflights",
    tags=["backup"],
    operation_id="preflightBackupRestore",
    status_code=status.HTTP_201_CREATED,
    response_model=BackupRestorePreflightResponse,
    responses=ERROR_RESPONSES,
)
async def preflight_backup_restore(
    file: Annotated[UploadFile, File(description="Pacote .zphbackup transmitido por streaming.")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> BackupRestorePreflightResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/backup-restore-jobs",
    tags=["backup", "jobs"],
    operation_id="confirmBackupRestore",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAcceptedResponse,
    responses=ERROR_RESPONSES,
)
async def confirm_backup_restore(
    request: ConfirmBackupRestoreRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> JobAcceptedResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/downloads/{download_id}",
    tags=["jobs", "portability", "backup"],
    operation_id="downloadJobArtifact",
    response_class=Response,
    responses=DOWNLOAD_RESPONSES,
)
async def download_job_artifact(download_id: UUID) -> Response:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/downloads/{download_id}/metadata",
    tags=["jobs", "portability", "backup"],
    operation_id="getDownloadMetadata",
    response_model=DownloadMetadataDto,
    responses=ERROR_RESPONSES,
)
async def get_download_metadata(download_id: UUID) -> DownloadMetadataDto:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/projects/{project_id}/photos",
    tags=["photos"],
    operation_id="listManagedPhotos",
    response_model=ManagedPhotoListResponse,
    responses=ERROR_RESPONSES,
)
async def list_managed_photos(project_id: UUID) -> ManagedPhotoListResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.post(
    "/projects/{project_id}/elements/{element_id}/photos",
    tags=["photos"],
    operation_id="attachManagedPhoto",
    status_code=status.HTTP_201_CREATED,
    response_model=ManagedPhotoResponse,
    responses=ERROR_RESPONSES,
)
async def attach_managed_photo(
    project_id: UUID,
    element_id: UUID,
    file: Annotated[UploadFile, File(description="Foto transmitida por streaming.")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> ManagedPhotoResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.delete(
    "/projects/{project_id}/elements/{element_id}/photos/{photo_id}",
    tags=["photos"],
    operation_id="removeManagedPhoto",
    response_model=RemoveManagedPhotoResponse,
    responses=ERROR_RESPONSES,
)
async def remove_managed_photo(
    project_id: UUID,
    element_id: UUID,
    photo_id: UUID,
) -> RemoveManagedPhotoResponse:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


@protected.get(
    "/projects/{project_id}/photos/{photo_id}/content",
    tags=["photos"],
    operation_id="downloadManagedPhoto",
    response_class=Response,
    responses=DOWNLOAD_RESPONSES,
)
async def download_managed_photo(project_id: UUID, photo_id: UUID) -> Response:
    raise NotImplementedError("Aplicação exclusiva para geração da OpenAPI.")


app.include_router(protected)


def build_openapi_schema() -> dict[str, Any]:
    """Produza o schema determinístico registrado pela aplicação declarativa."""
    return app.openapi()
