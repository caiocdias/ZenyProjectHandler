"""Dublê de servidor para testes Qt; a UI continua consumindo somente DTOs/remoto."""

from __future__ import annotations

import shutil
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import mkdtemp
from threading import RLock
from uuid import UUID, uuid4

from PIL import Image

from zeny_project_handler.adapters.pdf.errors import PdfProtegidoError
from zeny_project_handler.adapters.pdf.pymupdf_reader import PyMuPdfReader
from zeny_project_handler.ports.pdf import (
    OrcamentoRenderizacaoPdf,
    PaginaPdfRenderizada,
    SessaoLeituraPdfPort,
)
from zeny_project_handler.ui.pdf_gateway import RemoteRaster, ViewerGatewayError
from zeny_project_handler_contracts.base import DocumentId, PageId, UploadId, ViewerSessionId
from zeny_project_handler_contracts.common import NormalizedBoxDto
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.viewer import (
    CloseViewerSessionResponse,
    CreateViewerSessionResponse,
    RasterMetadataDto,
    UnlockViewerPdfResponse,
    ViewerDocumentDto,
    ViewerPageDto,
    ViewerPendingUploadDto,
    ViewerProjectResponse,
)


@dataclass(slots=True)
class _File:
    upload_id: UUID
    display_name: str
    path: Path
    position: int
    session: SessaoLeituraPdfPort | None = None
    attempts: int = 0


@dataclass(slots=True)
class _Session:
    identifier: UUID
    root: Path
    files: list[_File]


class LocalTestPdfViewerGateway:
    def __init__(
        self,
        *,
        budget: OrcamentoRenderizacaoPdf | None = None,
        reader: PyMuPdfReader | None = None,
    ) -> None:
        self._root = Path(mkdtemp(prefix="zeny-viewer-test-"))
        self._reader = reader or PyMuPdfReader()
        self._budget = budget or OrcamentoRenderizacaoPdf(8_000_000, 64 * 1024 * 1024)
        self._sessions: dict[UUID, _Session] = {}
        self._lock = RLock()

    def create_session(
        self,
        paths: tuple[Path, ...],
        *,
        idempotency_key: str,
    ) -> CreateViewerSessionResponse:
        del idempotency_key
        self._root.mkdir(parents=True, exist_ok=True)
        identifier = uuid4()
        root = self._root / str(identifier)
        root.mkdir()
        files: list[_File] = []
        for position, source in enumerate(paths):
            upload_id = uuid4()
            destination = root / f"{upload_id}.pdf"
            shutil.copyfile(source, destination)
            item = _File(upload_id, source.name, destination, position)
            files.append(item)
            with suppress(PdfProtegidoError):
                item.session = self._reader.abrir_sessao(destination)
        temporary = _Session(identifier, root, files)
        with self._lock:
            self._sessions[identifier] = temporary
        return self._response(temporary)

    def unlock_session_pdf(
        self,
        session_id: UUID,
        upload_id: UUID,
        password: str,
    ) -> UnlockViewerPdfResponse:
        with self._lock:
            temporary = self._sessions[session_id]
            item = next(value for value in temporary.files if value.upload_id == upload_id)
            try:
                item.session = self._reader.abrir_sessao(item.path, senha=password)
            except PdfProtegidoError as error:
                item.attempts += 1
                raise ViewerGatewayError(
                    ErrorCode.PDF_PASSWORD_INVALID,
                    "A senha informada para o PDF está incorreta.",
                    status_code=409,
                    details={"password_attempts_remaining": max(0, 3 - item.attempts)},
                ) from error
            response = self._response(temporary)
            return UnlockViewerPdfResponse(**response.model_dump())

    def close_session(self, session_id: UUID) -> CloseViewerSessionResponse:
        with self._lock:
            temporary = self._sessions.pop(session_id, None)
            if temporary is None:
                return CloseViewerSessionResponse(
                    viewer_session_id=ViewerSessionId(session_id),
                    closed=False,
                )
            for item in temporary.files:
                if item.session is not None:
                    item.session.fechar()
            shutil.rmtree(temporary.root)
            if not self._sessions:
                shutil.rmtree(self._root, ignore_errors=True)
            return CloseViewerSessionResponse(
                viewer_session_id=ViewerSessionId(session_id),
                closed=True,
            )

    def close(self) -> None:
        for session_id in tuple(self._sessions):
            self.close_session(session_id)
        shutil.rmtree(self._root, ignore_errors=True)

    def get_project(self, project_id: UUID) -> ViewerProjectResponse:
        raise ViewerGatewayError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f"Projeto de teste {project_id} não configurado.",
        )

    def get_page(self, page_id: UUID) -> ViewerPageDto:
        with self._lock:
            for temporary in self._sessions.values():
                for document in self._response(temporary).documents:
                    for page in document.pages:
                        if page.page_id.root == page_id:
                            return page
        raise ViewerGatewayError(ErrorCode.RESOURCE_NOT_FOUND, "Página não encontrada.")

    def unlock_project_document(self, document_id: UUID, password: str) -> ViewerDocumentDto:
        del document_id, password
        raise ViewerGatewayError(ErrorCode.RESOURCE_NOT_FOUND, "Documento não encontrado.")

    def render_preview(self, page_id: UUID, *, dpi: int, rotation: int) -> RemoteRaster:
        return self._render(page_id, dpi=dpi, rotation=rotation, clip=None)

    def render_tile(
        self,
        page_id: UUID,
        *,
        dpi: int,
        rotation: int,
        clip: NormalizedBoxDto,
    ) -> RemoteRaster:
        x = float(clip.x)
        y = float(clip.y)
        normalized = (x, y, x + float(clip.width), y + float(clip.height))
        return self._render(page_id, dpi=dpi, rotation=rotation, clip=normalized)

    def _render(
        self,
        page_id: UUID,
        *,
        dpi: int,
        rotation: int,
        clip: tuple[float, float, float, float] | None,
    ) -> RemoteRaster:
        with self._lock:
            session, page_number = self._source(page_id)
            rendered = session.renderizar_pagina(
                page_number,
                dpi=dpi,
                orcamento=self._budget,
                rotacao_adicional_graus=rotation,
                recorte_normalizado=clip,
            )
            return RemoteRaster(_png(rendered), _metadata(page_id, rendered))

    def _source(self, page_id: UUID) -> tuple[SessaoLeituraPdfPort, int]:
        for temporary in self._sessions.values():
            for item in temporary.files:
                if item.session is None:
                    continue
                for page in item.session.inspecao.documento.paginas:
                    if page.id == page_id:
                        return item.session, page.numero
        raise ViewerGatewayError(ErrorCode.RESOURCE_NOT_FOUND, "Página não encontrada.")

    @staticmethod
    def _response(temporary: _Session) -> CreateViewerSessionResponse:
        documents: list[ViewerDocumentDto] = []
        pending: list[ViewerPendingUploadDto] = []
        reading_order = 0
        for item in temporary.files:
            if item.session is None:
                pending.append(
                    ViewerPendingUploadDto(
                        upload_id=UploadId(item.upload_id),
                        display_name=item.display_name,
                        position=item.position,
                        password_attempts_remaining=max(0, 3 - item.attempts),
                    )
                )
                continue
            inspection = item.session.inspecao
            pages = tuple(
                ViewerPageDto(
                    page_id=PageId(page.id),
                    document_id=DocumentId(inspection.documento.id),
                    reading_order=reading_order + index,
                    source_page_number=page.numero,
                    width_points=format(page.largura_pontos, "f"),
                    height_points=format(page.altura_pontos, "f"),
                    intrinsic_rotation_degrees=page.rotacao_graus,
                )
                for index, page in enumerate(inspection.documento.paginas)
            )
            reading_order += len(pages)
            documents.append(
                ViewerDocumentDto(
                    document_id=DocumentId(inspection.documento.id),
                    display_name=item.display_name,
                    size_bytes=item.path.stat().st_size,
                    sha256=inspection.documento.sha256,
                    page_count=len(pages),
                    pages=pages,
                )
            )
        return CreateViewerSessionResponse(
            viewer_session_id=ViewerSessionId(temporary.identifier),
            documents=tuple(documents),
            pending_uploads=tuple(pending),
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )


def _metadata(page_id: UUID, rendered: PaginaPdfRenderizada) -> RasterMetadataDto:
    plan = rendered.plano
    x0, y0, x1, y1 = plan.recorte_normalizado
    return RasterMetadataDto(
        page_id=PageId(page_id),
        pixel_width=plan.largura_pixels,
        pixel_height=plan.altura_pixels,
        page_pixel_width=plan.largura_pagina_pixels,
        page_pixel_height=plan.altura_pagina_pixels,
        origin_x_pixels=plan.origem_x_pixels,
        origin_y_pixels=plan.origem_y_pixels,
        requested_dpi=plan.dpi_solicitado,
        effective_dpi=plan.dpi_efetivo,
        rotation_degrees=plan.rotacao_adicional_graus,
        clip=NormalizedBoxDto(
            x=format(Decimal(str(x0)), "f"),
            y=format(Decimal(str(y0)), "f"),
            width=format(Decimal(str(x1 - x0)), "f"),
            height=format(Decimal(str(y1 - y0)), "f"),
        ),
        reduced=plan.foi_reduzido,
    )


def _png(rendered: PaginaPdfRenderizada) -> bytes:
    image = Image.frombytes(
        "RGB",
        (rendered.largura_pixels, rendered.altura_pixels),
        bytes(rendered.dados_rgb),
        "raw",
        "RGB",
        rendered.stride,
        1,
    )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
