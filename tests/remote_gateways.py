"""Gateways DTO em processo para testes Qt; o painel não recebe serviços protegidos."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import Engine

from zeny_project_handler._atomic_files import sibling_temporary_file
from zeny_project_handler.adapters.pdf.errors import PdfProtegidoError
from zeny_project_handler.application.compliance_analysis import ExecutarAnaliseConformidade
from zeny_project_handler.application.compliance_registry import (
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler_client.ui.documentation_gateway import DocumentationGatewayError
from zeny_project_handler_client.ui.pdf_gateway import RemoteRaster, ViewerGatewayError
from zeny_project_handler_client.ui.portability_gateway import (
    CancelCallback,
    PortabilityTransferCancelledError,
    ProgressCallback,
)
from zeny_project_handler_client.ui.project_gateway import ProjectGatewayError
from zeny_project_handler_client.ui.review_gateway import ReviewGatewayError
from zeny_project_handler_contracts.backup import (
    BackupPreflightResponse,
    BackupRestorePreflightResponse,
    ConfirmBackupRestoreRequest,
    CreateBackupJobRequest,
)
from zeny_project_handler_contracts.base import JobId, ProjectId
from zeny_project_handler_contracts.common import DownloadMetadataDto, NormalizedBoxDto
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
)
from zeny_project_handler_contracts.enums import JobKind, JobStatus
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.jobs import (
    CancelJobResponse,
    CreateExportJobRequest,
    JobAcceptedResponse,
    JobResultResponse,
    JobStatusResponse,
)
from zeny_project_handler_contracts.portability import (
    ConfirmProjectImportRequest,
    ProjectImportPreflightResponse,
)
from zeny_project_handler_contracts.projects import (
    DeleteProjectResponse,
    ProjectDetailResponse,
    ProjectSummaryListResponse,
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
from zeny_project_handler_contracts.session import SessionCapabilitiesResponse
from zeny_project_handler_contracts.viewer import (
    CloseViewerSessionResponse,
    CreateViewerSessionResponse,
    UnlockViewerPdfResponse,
    ViewerDocumentDto,
    ViewerPageDto,
    ViewerProjectResponse,
)
from zeny_project_handler_server.api_errors import ApiError
from zeny_project_handler_server.compliance_api import DocumentationComplianceApiService
from zeny_project_handler_server.composition import ServerRuntime
from zeny_project_handler_server.portability_api import PortabilityApiService
from zeny_project_handler_server.project_api import ProjectApiService
from zeny_project_handler_server.review_api import ReviewApiService
from zeny_project_handler_server.viewer_api import ViewerApiService


class DirectProjectGateway:
    def __init__(self, runtime: ServerRuntime) -> None:
        self._runtime = runtime

    @property
    def _projects(self) -> ProjectApiService:
        service = self._runtime.project_api
        if service is None:
            raise RuntimeError("API de projetos indisponível")
        return service

    def session(self) -> SessionCapabilitiesResponse:
        return self._runtime.session_capabilities()

    def list_projects(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ProjectSummaryListResponse:
        return self._projects.list_projects(limit=limit, offset=offset)

    def create_project(
        self,
        service_note: str,
        *,
        idempotency_key: str,
    ) -> ProjectDetailResponse:
        return self._projects.create_project(service_note, idempotency_key)

    def get_project(self, project_id: UUID) -> ProjectDetailResponse:
        return self._projects.get_project(project_id)

    def update_project(
        self,
        project_id: UUID,
        service_note: str,
        *,
        expected_project_version: int,
    ) -> ProjectDetailResponse:
        return self._projects.update_project(
            project_id,
            service_note=service_note,
            expected_version=expected_project_version,
        )

    def delete_project(self, project_id: UUID) -> DeleteProjectResponse:
        return self._projects.delete_project(project_id)

    def upload_document(
        self,
        project_id: UUID,
        path: Path,
        *,
        idempotency_key: str,
    ) -> CreateUploadResponse:
        with path.open("rb") as stream:
            upload = UploadFile(file=stream, filename=path.name)
            received = asyncio.run(self._projects.receive_upload(upload))
        return self._projects.upload_document(project_id, received, idempotency_key)

    def unlock_upload(self, upload_id: UUID, password: str) -> DocumentImportResultDto:
        try:
            return self._projects.unlock_pdf(upload_id, password)
        except ApiError as error:
            raise _project_error(error) from None

    def replace_page_order(
        self,
        project_id: UUID,
        page_ids: tuple[UUID, ...],
        *,
        expected_project_version: int,
    ) -> PageOrderResponse:
        return self._projects.replace_page_order(
            project_id,
            page_ids=page_ids,
            expected_version=expected_project_version,
        )

    def remove_document(self, project_id: UUID, document_id: UUID) -> RemoveDocumentResponse:
        return self._projects.remove_document(project_id, document_id)

    def create_analysis_job(
        self,
        project_id: UUID,
        *,
        expected_project_version: int,
        force_reanalysis: bool,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        return self._runtime.jobs.create_analysis_job(
            project_id,
            expected_project_version=expected_project_version,
            force_reanalysis=force_reanalysis,
            idempotency_key=idempotency_key,
            correlation_id="11111111111111111111111111111111",
        )

    def get_job(self, job_id: UUID) -> JobStatusResponse:
        return self._runtime.jobs.get_job(job_id)

    def get_job_result(self, job_id: UUID) -> JobResultResponse:
        return self._runtime.jobs.get_result(job_id)

    def cancel_job(self, job_id: UUID) -> CancelJobResponse:
        return self._runtime.jobs.cancel(job_id)


class DirectPortabilityGateway:
    def __init__(self, runtime: ServerRuntime) -> None:
        self._runtime = runtime

    @property
    def _portability(self) -> PortabilityApiService:
        service = self._runtime.portability_api
        if service is None:
            raise RuntimeError("API de portabilidade indisponível")
        return service

    def list_projects(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ProjectSummaryListResponse:
        assert self._runtime.project_api is not None
        return self._runtime.project_api.list_projects(limit=limit, offset=offset)

    def create_project_export_job(
        self,
        project_id: UUID,
        *,
        expected_project_version: int,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        return self._runtime.jobs.create_project_export_job(
            project_id,
            CreateExportJobRequest(expected_project_version=expected_project_version),
            idempotency_key=idempotency_key,
            correlation_id=str(uuid4()),
        )

    def preflight_project_import(
        self,
        path: Path,
        *,
        idempotency_key: str,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> ProjectImportPreflightResponse:
        if cancelled():
            raise PortabilityTransferCancelledError("transferência cancelada")
        progress(path.stat().st_size, path.stat().st_size, "Enviando pacote")
        with path.open("rb") as stream:
            upload = UploadFile(file=stream, filename=path.name)
            return asyncio.run(
                self._portability.receive_project_import(
                    upload,
                    idempotency_key=idempotency_key,
                )
            )

    def create_project_import_job(
        self,
        request: ConfirmProjectImportRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        return self._runtime.jobs.create_project_import_job(
            request,
            idempotency_key=idempotency_key,
            correlation_id=str(uuid4()),
        )

    def preflight_backup(self) -> BackupPreflightResponse:
        return self._portability.preflight_backup()

    def create_backup_job(
        self,
        request: CreateBackupJobRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        return self._runtime.jobs.create_backup_job(
            request,
            idempotency_key=idempotency_key,
            correlation_id=str(uuid4()),
        )

    def preflight_backup_restore(
        self,
        path: Path,
        *,
        idempotency_key: str,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> BackupRestorePreflightResponse:
        if cancelled():
            raise PortabilityTransferCancelledError("transferência cancelada")
        progress(path.stat().st_size, path.stat().st_size, "Enviando pacote")
        with path.open("rb") as stream:
            upload = UploadFile(file=stream, filename=path.name)
            return asyncio.run(
                self._portability.receive_backup_restore(
                    upload,
                    idempotency_key=idempotency_key,
                )
            )

    def create_backup_restore_job(
        self,
        request: ConfirmBackupRestoreRequest,
        *,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        return self._runtime.jobs.create_backup_restore_job(
            request,
            idempotency_key=idempotency_key,
            correlation_id=str(uuid4()),
        )

    def get_job(self, job_id: UUID) -> JobStatusResponse:
        return self._runtime.jobs.get_job(job_id)

    def get_job_result(self, job_id: UUID) -> JobResultResponse:
        return self._runtime.jobs.get_result(job_id)

    def cancel_job(self, job_id: UUID) -> CancelJobResponse:
        return self._runtime.jobs.cancel(job_id)

    def get_download_metadata(self, download_id: UUID) -> DownloadMetadataDto:
        return self._portability.get_download(download_id).metadata

    def download_to(
        self,
        download_id: UUID,
        destination: Path,
        *,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> DownloadMetadataDto:
        download = self._portability.get_download(download_id)
        metadata = download.metadata
        digest = sha256()
        received = 0
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sibling_temporary_file(destination) as temporary:
            with download.path.open("rb") as source, temporary.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    if cancelled():
                        raise PortabilityTransferCancelledError("transferência cancelada")
                    target.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    progress(received, metadata.size_bytes, "Baixando pacote")
                target.flush()
                os.fsync(target.fileno())
            assert received == metadata.size_bytes
            assert digest.hexdigest() == metadata.sha256
            os.replace(temporary, destination)
        return metadata


class DirectReviewGateway:
    def __init__(self, runtime: ServerRuntime) -> None:
        self._runtime = runtime

    @property
    def _review(self) -> ReviewApiService:
        service = self._runtime.review_api
        if service is None:
            raise RuntimeError("Revisão remota indisponível")
        return service

    def list_projects(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ReviewProjectSummaryListResponse:
        return self._review.list_projects(limit=limit, offset=offset)

    def get_session(self, project_id: UUID) -> ReviewSessionResponse:
        return self._review.get_session(project_id)

    def accept(
        self,
        proposal_id: UUID,
        request: AcceptReviewProposalRequest,
    ) -> ReviewDecisionResponse:
        try:
            return self._review.accept(proposal_id, request)
        except ApiError as error:
            raise _review_error(error) from None

    def reject(
        self,
        proposal_id: UUID,
        request: RejectReviewProposalRequest,
    ) -> ReviewDecisionResponse:
        try:
            return self._review.reject(proposal_id, request)
        except ApiError as error:
            raise _review_error(error) from None

    def create_manual_element(
        self,
        project_id: UUID,
        request: CreateManualElementRequest,
    ) -> ReviewDecisionResponse:
        try:
            return self._review.create_manual_element(project_id, request)
        except ApiError as error:
            raise _review_error(error) from None

    def create_manual_relation(
        self,
        project_id: UUID,
        request: CreateManualRelationRequest,
    ) -> ReviewDecisionResponse:
        try:
            return self._review.create_manual_relation(project_id, request)
        except ApiError as error:
            raise _review_error(error) from None


class DirectDocumentationGateway:
    def __init__(self, runtime: ServerRuntime) -> None:
        self._runtime = runtime

    @property
    def _compliance(self) -> DocumentationComplianceApiService:
        service = self._runtime.compliance_api
        if service is None:
            raise RuntimeError("Documentação remota indisponível")
        return service

    def list_projects(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ReviewProjectSummaryListResponse:
        return self._compliance.list_projects(limit=limit, offset=offset)

    def get_documentation(self, project_id: UUID) -> DocumentationResponse:
        try:
            return self._compliance.get_documentation(project_id)
        except ApiError as error:
            raise _documentation_error(error) from None

    def get_latest_compliance(
        self,
        project_id: UUID,
    ) -> ComplianceExecutionResponse | None:
        try:
            return self._compliance.get_latest(project_id)
        except ApiError as error:
            if error.code is ErrorCode.RESOURCE_NOT_FOUND:
                return None
            raise _documentation_error(error) from None

    def list_compliance_history(
        self,
        project_id: UUID,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ComplianceHistoryResponse:
        return self._compliance.list_history(project_id, limit=limit, offset=offset)

    def create_compliance_job(
        self,
        project_id: UUID,
        *,
        expected_semantic_signature: str,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        return self._runtime.jobs.create_compliance_job(
            project_id,
            expected_semantic_signature=expected_semantic_signature,
            idempotency_key=idempotency_key,
            correlation_id="11111111111111111111111111111111",
        )

    def get_job(self, job_id: UUID) -> JobStatusResponse:
        return self._runtime.jobs.get_job(job_id)

    def get_job_result(self, job_id: UUID) -> JobResultResponse:
        return self._runtime.jobs.get_result(job_id)

    def get_active_registry(self) -> ActiveRuleRegistryResponse:
        return self._compliance.get_active_registry()

    def preflight_rule_import(
        self,
        path: Path,
        *,
        idempotency_key: str,
    ) -> RuleImportPreflightResponse:
        try:
            return self._compliance.preflight_rule_import(
                path.read_bytes(),
                idempotency_key=idempotency_key,
            )
        except ApiError as error:
            raise _documentation_error(error) from None

    def confirm_rule_import(self, request: ConfirmRuleImportRequest) -> RuleImportResponse:
        try:
            return self._compliance.confirm_rule_import(request)
        except ApiError as error:
            raise _documentation_error(error) from None

    def download_active_registry(self) -> bytes:
        return self._compliance.active_registry_json()


class SynchronousDocumentationGateway:
    """Mesmo limite DTO do HTTP, com jobs síncronos para testes focados na UI."""

    def __init__(
        self,
        *,
        engine: Engine,
        data_directory: Path,
        review_service: ServicoRevisaoHumana,
        analysis_service: ExecutarAnaliseConformidade,
        registry_service: ServicoRegistroRegrasConformidade,
    ) -> None:
        self._review_api = ReviewApiService(engine)
        self._compliance = DocumentationComplianceApiService(
            engine=engine,
            data_directory=data_directory,
            review_api=self._review_api,
            upload_max_bytes=16 * 1024 * 1024,
            review_service=review_service,
            analysis_service=analysis_service,
            registry_service=registry_service,
        )
        self._jobs: dict[UUID, JobStatusResponse] = {}

    @property
    def compliance_api(self) -> DocumentationComplianceApiService:
        return self._compliance

    def list_projects(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ReviewProjectSummaryListResponse:
        return self._compliance.list_projects(limit=limit, offset=offset)

    def get_documentation(self, project_id: UUID) -> DocumentationResponse:
        try:
            return self._compliance.get_documentation(project_id)
        except ApiError as error:
            raise _documentation_error(error) from None

    def get_latest_compliance(
        self,
        project_id: UUID,
    ) -> ComplianceExecutionResponse | None:
        try:
            return self._compliance.get_latest(project_id)
        except ApiError as error:
            if error.code is ErrorCode.RESOURCE_NOT_FOUND:
                return None
            raise _documentation_error(error) from None

    def list_compliance_history(
        self,
        project_id: UUID,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ComplianceHistoryResponse:
        return self._compliance.list_history(project_id, limit=limit, offset=offset)

    def create_compliance_job(
        self,
        project_id: UUID,
        *,
        expected_semantic_signature: str,
        idempotency_key: str,
    ) -> JobAcceptedResponse:
        del idempotency_key
        if self._compliance.semantic_signature(project_id) != expected_semantic_signature:
            raise DocumentationGatewayError(
                ErrorCode.STALE_STATE,
                "A sessão semântica mudou; recarregue a documentação.",
                status_code=409,
            )
        job_id = uuid4()
        self._compliance.execute_compliance(project_id, Event())
        now = datetime.now(UTC)
        self._jobs[job_id] = JobStatusResponse(
            job_id=JobId(job_id),
            project_id=ProjectId(project_id),
            kind=JobKind.COMPLIANCE,
            status=JobStatus.SUCCEEDED,
            progress_percent=100,
            message="Conformidade concluída",
            result_available=True,
            created_at=now,
            updated_at=now,
        )
        return JobAcceptedResponse(
            job_id=JobId(job_id),
            kind=JobKind.COMPLIANCE,
            status=JobStatus.QUEUED,
            poll_after_ms=350,
        )

    def get_job(self, job_id: UUID) -> JobStatusResponse:
        return self._jobs[job_id]

    def get_job_result(self, job_id: UUID) -> JobResultResponse:
        job = self._jobs[job_id]
        return JobResultResponse(job_id=job.job_id, status=job.status, result={})

    def get_active_registry(self) -> ActiveRuleRegistryResponse:
        return self._compliance.get_active_registry()

    def preflight_rule_import(
        self,
        path: Path,
        *,
        idempotency_key: str,
    ) -> RuleImportPreflightResponse:
        return self._compliance.preflight_rule_import(
            path.read_bytes(),
            idempotency_key=idempotency_key,
        )

    def confirm_rule_import(self, request: ConfirmRuleImportRequest) -> RuleImportResponse:
        return self._compliance.confirm_rule_import(request)

    def download_active_registry(self) -> bytes:
        return self._compliance.active_registry_json()


class DirectPdfViewerGateway:
    def __init__(self, runtime: ServerRuntime) -> None:
        self._runtime = runtime

    @property
    def _viewer(self) -> ViewerApiService:
        service = self._runtime.viewer_api
        if service is None:
            raise RuntimeError("Visualizador indisponível")
        return service

    def create_session(
        self,
        paths: tuple[Path, ...],
        *,
        idempotency_key: str,
    ) -> CreateViewerSessionResponse:
        streams = [path.open("rb") for path in paths]
        try:
            uploads = [
                UploadFile(file=stream, filename=path.name)
                for stream, path in zip(streams, paths, strict=True)
            ]
            received = asyncio.run(self._viewer.receive_uploads(uploads))
        finally:
            for stream in streams:
                stream.close()
        return self._viewer.create_session(received, idempotency_key)

    def unlock_session_pdf(
        self,
        session_id: UUID,
        upload_id: UUID,
        password: str,
    ) -> UnlockViewerPdfResponse:
        try:
            return self._viewer.unlock_session_pdf(session_id, upload_id, password)
        except ApiError as error:
            raise _viewer_error(error) from None

    def close_session(self, session_id: UUID) -> CloseViewerSessionResponse:
        return self._viewer.close_session(session_id)

    def get_project(self, project_id: UUID) -> ViewerProjectResponse:
        try:
            return self._viewer.get_project(project_id)
        except ApiError as error:
            raise _viewer_error(error) from None

    def get_page(self, page_id: UUID) -> ViewerPageDto:
        try:
            return self._viewer.get_page(page_id)
        except ApiError as error:
            raise _viewer_error(error) from None

    def unlock_project_document(self, document_id: UUID, password: str) -> ViewerDocumentDto:
        try:
            return self._viewer.unlock_project_document(document_id, password)
        except ApiError as error:
            raise _viewer_error(error) from None
        except PdfProtegidoError as error:
            raise _protected_viewer_error(error) from None

    def render_preview(self, page_id: UUID, *, dpi: int, rotation: int) -> RemoteRaster:
        try:
            raster = self._viewer.render_preview(page_id, dpi=dpi, rotation=rotation)
        except ApiError as error:
            raise _viewer_error(error) from None
        except PdfProtegidoError as error:
            raise _protected_viewer_error(error) from None
        return RemoteRaster(raster.png, raster.metadata)

    def render_tile(
        self,
        page_id: UUID,
        *,
        dpi: int,
        rotation: int,
        clip: NormalizedBoxDto,
    ) -> RemoteRaster:
        try:
            raster = self._viewer.render_tile(
                page_id,
                dpi=dpi,
                rotation=rotation,
                clip=clip,
            )
        except ApiError as error:
            raise _viewer_error(error) from None
        except PdfProtegidoError as error:
            raise _protected_viewer_error(error) from None
        return RemoteRaster(raster.png, raster.metadata)


def _project_error(error: ApiError) -> ProjectGatewayError:
    return ProjectGatewayError(
        error.code,
        error.message,
        status_code=error.status_code,
        correlation_id="11111111-1111-1111-1111-111111111111",
        details=dict(error.details) if error.details is not None else None,
    )


def _viewer_error(error: ApiError) -> ViewerGatewayError:
    return ViewerGatewayError(
        error.code,
        error.message,
        status_code=error.status_code,
        correlation_id="11111111-1111-1111-1111-111111111111",
        details=dict(error.details) if error.details is not None else None,
    )


def _review_error(error: ApiError) -> ReviewGatewayError:
    return ReviewGatewayError(
        error.code,
        error.message,
        status_code=error.status_code,
        correlation_id="11111111-1111-1111-1111-111111111111",
        details=dict(error.details) if error.details is not None else None,
    )


def _documentation_error(error: ApiError) -> DocumentationGatewayError:
    return DocumentationGatewayError(
        error.code,
        error.message,
        status_code=error.status_code,
        correlation_id="11111111-1111-1111-1111-111111111111",
        details=dict(error.details) if error.details is not None else None,
    )


def _protected_viewer_error(error: PdfProtegidoError) -> ViewerGatewayError:
    return ViewerGatewayError(
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
        status_code=409,
        correlation_id="11111111-1111-1111-1111-111111111111",
    )
