"""Gateways DTO em processo para testes Qt; o painel não recebe serviços protegidos."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from zeny_project_handler.adapters.pdf.errors import PdfProtegidoError
from zeny_project_handler.ui.pdf_gateway import RemoteRaster, ViewerGatewayError
from zeny_project_handler.ui.project_gateway import ProjectGatewayError
from zeny_project_handler.ui.review_gateway import ReviewGatewayError
from zeny_project_handler_contracts.common import NormalizedBoxDto
from zeny_project_handler_contracts.documents import (
    CreateUploadResponse,
    DocumentImportResultDto,
    PageOrderResponse,
    RemoveDocumentResponse,
)
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.jobs import (
    CancelJobResponse,
    JobAcceptedResponse,
    JobResultResponse,
    JobStatusResponse,
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
from zeny_project_handler_server.composition import ServerRuntime
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
