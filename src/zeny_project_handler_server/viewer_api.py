"""Sessões temporárias e rasterização remota pertencentes ao servidor."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from threading import Event, RLock, Thread
from time import monotonic
from uuid import UUID, uuid4

from fastapi import UploadFile
from PIL import Image
from sqlalchemy import Engine, select

from zeny_project_handler.adapters.pdf.errors import PdfProtegidoError
from zeny_project_handler.adapters.pdf.pymupdf_reader import PyMuPdfReader
from zeny_project_handler.adapters.persistence.schema import projects
from zeny_project_handler.adapters.persistence.unit_of_work import SqlAlchemyUnitOfWork
from zeny_project_handler.application.pdf_credentials import (
    IdentidadeCredencialPdf,
    ProvedorCredenciaisPdfMemoria,
)
from zeny_project_handler.domain.documents import DocumentoProjeto
from zeny_project_handler.ports.pdf import (
    OrcamentoRenderizacaoPdf,
    PaginaPdfRenderizada,
    PlanoRenderizacaoPdf,
    ReferenciaFontePdf,
    SessaoLeituraPdfPort,
)
from zeny_project_handler_contracts.base import (
    DocumentId,
    PageId,
    ProjectId,
    UploadId,
    ViewerSessionId,
)
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
from zeny_project_handler_server.api_errors import (
    ApiError,
    IdempotencyConflictError,
    resource_not_found,
    unsupported_media,
    validation_error,
    viewer_session_expired,
)
from zeny_project_handler_server.upload_storage import ManagedUploadStorage, ReceivedUpload

_PNG_CONTENT_TYPE = "image/png"
_PDF_CONTENT_TYPE = "application/pdf"
_MAX_PASSWORD_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class ViewerRaster:
    png: bytes
    metadata: RasterMetadataDto


@dataclass(slots=True)
class _TemporaryFile:
    upload_id: UUID
    display_name: str
    path: Path
    size_bytes: int
    sha256: str
    position: int
    password_attempts: int = 0
    reading_session: SessaoLeituraPdfPort | None = None


@dataclass(slots=True)
class _TemporarySession:
    session_id: UUID
    directory: Path
    files: list[_TemporaryFile]
    expires_monotonic: float
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class _ProjectDocument:
    project_id: UUID
    project_version: int
    document: DocumentoProjeto
    source: ReferenciaFontePdf
    reading_order: dict[UUID, int]


@dataclass(slots=True)
class _ProjectReadingSession:
    identity: tuple[str, int, int]
    session: SessaoLeituraPdfPort


@dataclass(slots=True)
class ViewerApiService:
    engine: Engine
    data_directory: Path
    upload_max_bytes: int
    render_dpi: int
    render_max_pixels: int
    render_max_bytes: int
    session_ttl_seconds: int
    maximum_files: int
    credentials: ProvedorCredenciaisPdfMemoria
    _reader: PyMuPdfReader = field(init=False, repr=False)
    _storage: ManagedUploadStorage = field(init=False, repr=False)
    _sessions: dict[UUID, _TemporarySession] = field(init=False, repr=False)
    _idempotency: dict[str, tuple[str, UUID]] = field(init=False, repr=False)
    _expired_pages: set[UUID] = field(init=False, repr=False)
    _project_sessions: dict[UUID, _ProjectReadingSession] = field(init=False, repr=False)
    _lock: RLock = field(init=False, repr=False)
    _stop: Event = field(init=False, repr=False)
    _cleanup_thread: Thread = field(init=False, repr=False)
    _closed: bool = field(init=False, default=False, repr=False)
    _monotonic: Callable[[], float] = field(default=monotonic, repr=False)
    _now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC), repr=False)

    def __post_init__(self) -> None:
        self.data_directory = self.data_directory.expanduser().resolve()
        self._reader = PyMuPdfReader()
        self._storage = ManagedUploadStorage(
            self.data_directory,
            maximum_bytes=self.upload_max_bytes,
        )
        self._sessions = {}
        self._idempotency = {}
        self._expired_pages = set()
        self._project_sessions = {}
        self._lock = RLock()
        self._stop = Event()
        self._viewer_root.mkdir(parents=True, exist_ok=True)
        self._cleanup_stale_directories()
        interval = max(1.0, min(30.0, self.session_ttl_seconds / 2))
        self._cleanup_thread = Thread(
            target=self._cleanup_loop,
            args=(interval,),
            name="viewer-session-cleanup",
            daemon=True,
        )
        self._cleanup_thread.start()

    @property
    def _viewer_root(self) -> Path:
        return self.data_directory / "viewer-sessions"

    async def receive_uploads(self, files: list[UploadFile]) -> tuple[ReceivedUpload, ...]:
        if not files or len(files) > self.maximum_files:
            raise validation_error(
                f"Envie entre 1 e {self.maximum_files} PDFs por sessão do visualizador."
            )
        received: list[ReceivedUpload] = []
        try:
            for upload in files:
                item = await self._storage.receive(upload)
                received.append(item)
                self._require_pdf_upload(item)
        except BaseException:
            for item in received:
                self._storage.discard(item)
            raise
        return tuple(received)

    def create_session(
        self,
        uploads: tuple[ReceivedUpload, ...],
        idempotency_key: str,
    ) -> CreateViewerSessionResponse:
        fingerprint = _uploads_fingerprint(uploads)
        with self._lock:
            self.cleanup_expired()
            replay = self._idempotency.get(idempotency_key)
            if replay is not None:
                self._discard_uploads(uploads)
                if replay[0] != fingerprint:
                    raise IdempotencyConflictError()
                session = self._sessions.get(replay[1])
                if session is None:
                    raise viewer_session_expired()
                self._touch(session)
                return self._session_response(session)
            if len({item.sha256 for item in uploads}) != len(uploads):
                self._discard_uploads(uploads)
                raise validation_error("A seleção contém PDFs com conteúdo duplicado.")
            session = self._publish_session(uploads)
            self._sessions[session.session_id] = session
            self._idempotency[idempotency_key] = (fingerprint, session.session_id)
            return self._session_response(session)

    def unlock_session_pdf(
        self,
        session_id: UUID,
        upload_id: UUID,
        password: str,
    ) -> UnlockViewerPdfResponse:
        with self._lock:
            temporary = self._temporary_session(session_id)
            item = next((value for value in temporary.files if value.upload_id == upload_id), None)
            if item is None:
                raise resource_not_found("Upload temporário do visualizador não encontrado.")
            if item.reading_session is not None:
                return self._unlock_response(temporary)
            if item.password_attempts >= _MAX_PASSWORD_ATTEMPTS:
                raise _invalid_password(0)
            try:
                item.reading_session = self._reader.abrir_sessao(
                    item.path,
                    senha=password,
                    sha256_esperado=item.sha256,
                )
            except PdfProtegidoError as error:
                item.password_attempts += 1
                raise _invalid_password(_MAX_PASSWORD_ATTEMPTS - item.password_attempts) from error
            self._touch(temporary)
            return self._unlock_response(temporary)

    def close_session(self, session_id: UUID) -> CloseViewerSessionResponse:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is None:
                return CloseViewerSessionResponse(
                    viewer_session_id=ViewerSessionId(session_id),
                    closed=False,
                )
            self._remove_session(session, expired=False)
            return CloseViewerSessionResponse(
                viewer_session_id=ViewerSessionId(session_id),
                closed=True,
            )

    def get_project(self, project_id: UUID) -> ViewerProjectResponse:
        documents = self._project_documents(project_id)
        return ViewerProjectResponse(
            project_id=ProjectId(project_id),
            project_version=(
                documents[0].project_version if documents else self._project_version(project_id)
            ),
            documents=tuple(self._project_document_dto(item) for item in documents),
            pages=tuple(
                sorted(
                    (page for item in documents for page in self._project_document_dto(item).pages),
                    key=lambda page: page.reading_order,
                )
            ),
        )

    def get_page(self, page_id: UUID) -> ViewerPageDto:
        with self._lock:
            temporary = self._temporary_page(page_id)
            if temporary is not None:
                return temporary
            if page_id in self._expired_pages:
                raise viewer_session_expired()
        project = self._find_project_document(page_id)
        return self._project_page_dto(project, page_id)

    def unlock_project_document(self, document_id: UUID, password: str) -> ViewerDocumentDto:
        project = self._find_project_document_by_document_id(document_id)
        with self._lock:
            previous = self._project_sessions.pop(document_id, None)
            if previous is not None:
                previous.session.fechar()
            session = self._reader.abrir_sessao(
                project.source.caminho_canonico,
                senha=password,
                documento_id=document_id,
                sha256_esperado=project.document.sha256,
            )
            identity = IdentidadeCredencialPdf.da_fonte(project.source)
            self.credentials.guardar(identity, password)
            self._project_sessions[document_id] = _ProjectReadingSession(
                _source_identity(project.source),
                session,
            )
        return self._project_document_dto(project)

    def render_preview(
        self,
        page_id: UUID,
        *,
        dpi: int,
        rotation: int,
    ) -> ViewerRaster:
        return self._render(page_id, dpi=dpi, rotation=rotation, clip=None)

    def render_tile(
        self,
        page_id: UUID,
        *,
        dpi: int,
        rotation: int,
        clip: NormalizedBoxDto,
    ) -> ViewerRaster:
        return self._render(page_id, dpi=dpi, rotation=rotation, clip=clip)

    def cleanup_expired(self) -> int:
        with self._lock:
            now = self._monotonic()
            expired = [item for item in self._sessions.values() if item.expires_monotonic <= now]
            for session in expired:
                self._sessions.pop(session.session_id, None)
                self._remove_session(session, expired=True)
            return len(expired)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
        self._cleanup_thread.join(timeout=5)
        with self._lock:
            for session in tuple(self._sessions.values()):
                self._remove_session(session, expired=False)
            self._sessions.clear()
            for cached in self._project_sessions.values():
                cached.session.fechar()
            self._project_sessions.clear()

    def _publish_session(self, uploads: tuple[ReceivedUpload, ...]) -> _TemporarySession:
        session_id = uuid4()
        directory = (self._viewer_root / str(session_id)).resolve()
        if not directory.is_relative_to(self._viewer_root.resolve()):
            self._discard_uploads(uploads)
            raise RuntimeError("A sessão temporária saiu da raiz gerenciada")
        directory.mkdir(parents=True)
        files: list[_TemporaryFile] = []
        try:
            for position, upload in enumerate(uploads):
                upload_id = uuid4()
                destination = directory / f"{upload_id}.pdf"
                os.replace(upload.path, destination)
                item = _TemporaryFile(
                    upload_id=upload_id,
                    display_name=upload.display_name,
                    path=destination,
                    size_bytes=upload.size_bytes,
                    sha256=upload.sha256,
                    position=position,
                )
                files.append(item)
                with suppress(PdfProtegidoError):
                    item.reading_session = self._reader.abrir_sessao(
                        destination,
                        sha256_esperado=upload.sha256,
                    )
            expires_at = self._now() + timedelta(seconds=self.session_ttl_seconds)
            return _TemporarySession(
                session_id=session_id,
                directory=directory,
                files=files,
                expires_monotonic=self._monotonic() + self.session_ttl_seconds,
                expires_at=expires_at,
            )
        except BaseException:
            for item in files:
                if item.reading_session is not None:
                    item.reading_session.fechar()
            shutil.rmtree(directory, ignore_errors=True)
            self._discard_uploads(uploads)
            raise

    def _render(
        self,
        page_id: UUID,
        *,
        dpi: int,
        rotation: int,
        clip: NormalizedBoxDto | None,
    ) -> ViewerRaster:
        if dpi > self.render_dpi:
            raise validation_error(
                f"O servidor aceita no máximo {self.render_dpi} DPI para o visualizador."
            )
        normalized_clip = _clip_tuple(clip) if clip is not None else None
        with self._lock:
            source = self._temporary_render_source(page_id)
            if source is None:
                if page_id in self._expired_pages:
                    raise viewer_session_expired()
                project = self._find_project_document(page_id)
                source = (
                    self._project_reading_session(project),
                    project.document.paginas.index(
                        next(page for page in project.document.paginas if page.id == page_id)
                    )
                    + 1,
                )
            reading_session, page_number = source
            rendered = reading_session.renderizar_pagina(
                page_number,
                dpi=dpi,
                orcamento=OrcamentoRenderizacaoPdf(
                    limite_pixels=self.render_max_pixels,
                    limite_bytes=self.render_max_bytes,
                ),
                rotacao_adicional_graus=rotation,
                recorte_normalizado=normalized_clip,
            )
            metadata = _raster_metadata(page_id, rendered.plano)
            png = _encode_png(rendered)
        return ViewerRaster(png=png, metadata=metadata)

    def _temporary_render_source(
        self,
        page_id: UUID,
    ) -> tuple[SessaoLeituraPdfPort, int] | None:
        for temporary in self._sessions.values():
            for item in temporary.files:
                if item.reading_session is None:
                    continue
                for page in item.reading_session.inspecao.documento.paginas:
                    if page.id == page_id:
                        self._touch(temporary)
                        return item.reading_session, page.numero
        return None

    def _temporary_page(self, page_id: UUID) -> ViewerPageDto | None:
        for temporary in self._sessions.values():
            response = self._session_response(temporary)
            for page in (page for document in response.documents for page in document.pages):
                if page.page_id.root == page_id:
                    self._touch(temporary)
                    return page
        return None

    def _temporary_session(self, session_id: UUID) -> _TemporarySession:
        self.cleanup_expired()
        session = self._sessions.get(session_id)
        if session is None:
            raise viewer_session_expired()
        self._touch(session)
        return session

    def _touch(self, session: _TemporarySession) -> None:
        session.expires_monotonic = self._monotonic() + self.session_ttl_seconds
        session.expires_at = self._now() + timedelta(seconds=self.session_ttl_seconds)

    def _session_response(self, session: _TemporarySession) -> CreateViewerSessionResponse:
        documents, pending = self._temporary_dtos(session)
        return CreateViewerSessionResponse(
            viewer_session_id=ViewerSessionId(session.session_id),
            documents=documents,
            pending_uploads=pending,
            expires_at=session.expires_at,
        )

    def _unlock_response(self, session: _TemporarySession) -> UnlockViewerPdfResponse:
        documents, pending = self._temporary_dtos(session)
        return UnlockViewerPdfResponse(
            viewer_session_id=ViewerSessionId(session.session_id),
            documents=documents,
            pending_uploads=pending,
            expires_at=session.expires_at,
        )

    def _temporary_dtos(
        self,
        session: _TemporarySession,
    ) -> tuple[tuple[ViewerDocumentDto, ...], tuple[ViewerPendingUploadDto, ...]]:
        reading_order = 0
        documents: list[ViewerDocumentDto] = []
        pending: list[ViewerPendingUploadDto] = []
        for item in sorted(session.files, key=lambda value: value.position):
            if item.reading_session is None:
                pending.append(
                    ViewerPendingUploadDto(
                        upload_id=UploadId(item.upload_id),
                        display_name=item.display_name,
                        position=item.position,
                        password_attempts_remaining=max(
                            0,
                            _MAX_PASSWORD_ATTEMPTS - item.password_attempts,
                        ),
                    )
                )
                continue
            inspection = item.reading_session.inspecao
            pages = tuple(
                _page_dto(
                    page.id,
                    inspection.documento.id,
                    reading_order + index,
                    page.numero,
                    page.largura_pontos,
                    page.altura_pontos,
                    page.rotacao_graus,
                )
                for index, page in enumerate(inspection.documento.paginas)
            )
            reading_order += len(pages)
            documents.append(
                ViewerDocumentDto(
                    document_id=DocumentId(inspection.documento.id),
                    display_name=item.display_name,
                    size_bytes=item.size_bytes,
                    sha256=item.sha256,
                    page_count=len(pages),
                    pages=pages,
                )
            )
        return tuple(documents), tuple(pending)

    def _project_documents(self, project_id: UUID) -> tuple[_ProjectDocument, ...]:
        with SqlAlchemyUnitOfWork(self.engine) as work:
            project = work.projetos.obter(project_id)
            if project is None:
                raise resource_not_found("Projeto não encontrado.")
            version = self._project_version(project_id)
            reading_order = {
                page_id: index for index, page_id in enumerate(project.ordem_leitura_paginas)
            }
            result: list[_ProjectDocument] = []
            for document in project.documentos:
                source = work.fontes_pdf.obter(document.id)
                if source is None:
                    raise resource_not_found("A origem gerenciada do PDF não foi encontrada.")
                result.append(
                    _ProjectDocument(project_id, version, document, source, reading_order)
                )
            return tuple(result)

    def _project_version(self, project_id: UUID) -> int:
        with self.engine.connect() as connection:
            value = connection.scalar(
                select(projects.c.version).where(projects.c.id == str(project_id))
            )
        if value is None:
            raise resource_not_found("Projeto não encontrado.")
        return int(value)

    def _find_project_document(self, page_id: UUID) -> _ProjectDocument:
        with SqlAlchemyUnitOfWork(self.engine) as work:
            all_projects = work.projetos.listar()
        for project in all_projects:
            for document in project.documentos:
                if any(page.id == page_id for page in document.paginas):
                    return next(
                        item
                        for item in self._project_documents(project.id)
                        if item.document.id == document.id
                    )
        raise resource_not_found("Página do visualizador não encontrada.")

    def _find_project_document_by_document_id(self, document_id: UUID) -> _ProjectDocument:
        with SqlAlchemyUnitOfWork(self.engine) as work:
            all_projects = work.projetos.listar()
        for project in all_projects:
            if any(document.id == document_id for document in project.documentos):
                return next(
                    item
                    for item in self._project_documents(project.id)
                    if item.document.id == document_id
                )
        raise resource_not_found("Documento do visualizador não encontrado.")

    def _project_document_dto(self, item: _ProjectDocument) -> ViewerDocumentDto:
        return ViewerDocumentDto(
            document_id=DocumentId(item.document.id),
            display_name=item.document.nome_arquivo,
            size_bytes=item.document.tamanho_bytes or item.source.tamanho_bytes,
            sha256=item.document.sha256,
            page_count=len(item.document.paginas),
            pages=tuple(self._project_page_dto(item, page.id) for page in item.document.paginas),
        )

    @staticmethod
    def _project_page_dto(item: _ProjectDocument, page_id: UUID) -> ViewerPageDto:
        page = next(page for page in item.document.paginas if page.id == page_id)
        return _page_dto(
            page.id,
            item.document.id,
            item.reading_order[page.id],
            page.numero,
            page.largura_pontos,
            page.altura_pontos,
            page.rotacao_graus,
        )

    def _project_reading_session(self, item: _ProjectDocument) -> SessaoLeituraPdfPort:
        identity = _source_identity(item.source)
        cached = self._project_sessions.get(item.document.id)
        if cached is not None and cached.identity == identity:
            return cached.session
        if cached is not None:
            cached.session.fechar()
        credential_identity = IdentidadeCredencialPdf.da_fonte(item.source)
        session = self._reader.abrir_sessao(
            item.source.caminho_canonico,
            senha=self.credentials.obter(credential_identity),
            documento_id=item.document.id,
            sha256_esperado=item.document.sha256,
        )
        self._project_sessions[item.document.id] = _ProjectReadingSession(identity, session)
        return session

    def _remove_session(self, session: _TemporarySession, *, expired: bool) -> None:
        for item in session.files:
            if item.reading_session is not None:
                if expired:
                    self._expired_pages.update(
                        page.id for page in item.reading_session.inspecao.documento.paginas
                    )
                item.reading_session.fechar()
        shutil.rmtree(session.directory, ignore_errors=True)
        for key, (_fingerprint, value) in tuple(self._idempotency.items()):
            if value == session.session_id:
                del self._idempotency[key]

    def _cleanup_loop(self, interval: float) -> None:
        while not self._stop.wait(interval):
            self.cleanup_expired()

    def _cleanup_stale_directories(self) -> None:
        for path in self._viewer_root.iterdir():
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)

    @staticmethod
    def _require_pdf_upload(upload: ReceivedUpload) -> None:
        if not upload.display_name.lower().endswith(".pdf"):
            raise unsupported_media("A sessão do visualizador aceita somente arquivos PDF.")
        if upload.content_type not in {None, "", _PDF_CONTENT_TYPE, "application/octet-stream"}:
            raise unsupported_media("A sessão do visualizador aceita somente arquivos PDF.")

    @staticmethod
    def _discard_uploads(uploads: tuple[ReceivedUpload, ...]) -> None:
        for upload in uploads:
            upload.path.unlink(missing_ok=True)


def _page_dto(
    page_id: UUID,
    document_id: UUID,
    reading_order: int,
    source_page_number: int,
    width: Decimal,
    height: Decimal,
    intrinsic_rotation: int,
) -> ViewerPageDto:
    return ViewerPageDto(
        page_id=PageId(page_id),
        document_id=DocumentId(document_id),
        reading_order=reading_order,
        source_page_number=source_page_number,
        width_points=format(width, "f"),
        height_points=format(height, "f"),
        intrinsic_rotation_degrees=intrinsic_rotation,
    )


def _clip_tuple(clip: NormalizedBoxDto) -> tuple[float, float, float, float]:
    x = Decimal(clip.x)
    y = Decimal(clip.y)
    width = Decimal(clip.width)
    height = Decimal(clip.height)
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
        raise validation_error("O recorte normalizado deve estar contido na página.")
    return float(x), float(y), float(x + width), float(y + height)


def _raster_metadata(page_id: UUID, plan: PlanoRenderizacaoPdf) -> RasterMetadataDto:
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
        content_type=_PNG_CONTENT_TYPE,
    )


def _encode_png(rendered: PaginaPdfRenderizada) -> bytes:
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
    image.save(output, format="PNG", optimize=False, compress_level=6)
    return output.getvalue()


def _source_identity(source: ReferenciaFontePdf) -> tuple[str, int, int]:
    return source.sha256, source.tamanho_bytes, source.modificado_em_ns


def _uploads_fingerprint(uploads: tuple[ReceivedUpload, ...]) -> str:
    from hashlib import sha256

    payload = "\n".join(
        f"{item.display_name}\0{item.size_bytes}\0{item.sha256}" for item in uploads
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _invalid_password(attempts_remaining: int) -> ApiError:
    return ApiError(
        409,
        ErrorCode.PDF_PASSWORD_INVALID,
        "A senha informada para o PDF está incorreta.",
        details={"password_attempts_remaining": attempts_remaining},
    )
