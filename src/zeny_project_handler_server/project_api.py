"""Casos de uso HTTP da Etapa 3 sem expor caminhos ou entidades internas."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import TypeVar
from uuid import UUID, uuid5

from fastapi import UploadFile
from pydantic import BaseModel
from sqlalchemy import Engine, select

from zeny_project_handler.adapters.pdf.errors import PdfProtegidoError
from zeny_project_handler.adapters.pdf.pymupdf_reader import PyMuPdfReader
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    SqliteBackupManager,
    SqlitePortableProjectDatabase,
)
from zeny_project_handler.adapters.persistence.schema import projects
from zeny_project_handler.adapters.portability import ZipProjectArchive
from zeny_project_handler.application.errors import ProjetoNaoEncontradoError
from zeny_project_handler.application.managed_files import (
    GerenciadorArquivosGerenciados,
    fotos_removidas,
)
from zeny_project_handler.application.operation_coordinator import (
    CoordenadorOperacoes,
    TipoOperacao,
)
from zeny_project_handler.application.pdf_credentials import (
    IdentidadeCredencialPdf,
    ProvedorCredenciaisPdfMemoria,
)
from zeny_project_handler.application.pdf_import import ImportarPdfsNoProjeto
from zeny_project_handler.application.project_document_removal import project_without_documents
from zeny_project_handler.application.project_portability import ServicoPortabilidadeProjeto
from zeny_project_handler.domain.documents import DocumentoProjeto
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise, EstadoRevisao
from zeny_project_handler.domain.project import ElementoProjetoType, FotoElemento, Projeto
from zeny_project_handler.domain.project_metadata import (
    normalizar_codigo_servico,
    normalizar_numero_ns,
)
from zeny_project_handler_contracts.base import (
    DocumentId,
    ElementId,
    PageId,
    PhotoId,
    ProjectId,
    UploadId,
)
from zeny_project_handler_contracts.common import (
    DeletionCountsDto,
    FileMetadataDto,
    PageMetadataDto,
)
from zeny_project_handler_contracts.documents import (
    CreateUploadResponse,
    DocumentImportResultDto,
    DocumentSummaryDto,
    DocumentUploadPreflightDto,
    PageOrderResponse,
    PageSummaryDto,
    RemoveDocumentResponse,
)
from zeny_project_handler_contracts.enums import (
    AnalysisExecutionState,
    PreflightDisposition,
    ProjectState,
    UploadState,
)
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.photos import (
    ManagedPhotoDto,
    ManagedPhotoListResponse,
    ManagedPhotoResponse,
    RemoveManagedPhotoResponse,
)
from zeny_project_handler_contracts.projects import (
    DeleteProjectResponse,
    ProjectAnalysisSummaryDto,
    ProjectDetailDto,
    ProjectDetailResponse,
    ProjectServiceCodesResponse,
    ProjectSummaryDto,
    ProjectSummaryListResponse,
)
from zeny_project_handler_server.api_errors import (
    ApiError,
    ProjectAlreadyExistsError,
    StaleStateError,
    operation_conflict,
    resource_not_found,
    unsupported_media,
    validation_error,
)
from zeny_project_handler_server.stage3_store import (
    IdempotencyRecord,
    StageThreeStore,
    UploadRecord,
)
from zeny_project_handler_server.upload_storage import (
    ManagedUploadStorage,
    ReceivedUpload,
)

_RESOURCE_NAMESPACE = UUID("7f9e34ae-e0da-4edc-8bf7-6647553761e4")
_PENDING_UPLOAD_TTL = timedelta(hours=24)
ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class _ProjectSnapshot:
    project: Projeto
    version: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ManagedDownload:
    path: Path
    display_name: str
    mime_type: str
    size_bytes: int
    sha256: str


class ProjectApiService:
    """Superfície transacional consumida exclusivamente pelas rotas protegidas."""

    def __init__(
        self,
        *,
        engine: Engine,
        catalog_id: UUID,
        data_directory: Path,
        database_path: Path,
        coordinator: CoordenadorOperacoes,
        upload_max_bytes: int,
    ) -> None:
        self._engine = engine
        self._catalog_id = catalog_id
        self._data_directory = data_directory.expanduser().resolve()
        self._coordinator = coordinator
        self._store = StageThreeStore(engine)
        self._storage = ManagedUploadStorage(
            self._data_directory,
            maximum_bytes=upload_max_bytes,
        )
        self._reader = PyMuPdfReader()
        self._credentials = ProvedorCredenciaisPdfMemoria()
        self._managed_files = GerenciadorArquivosGerenciados(
            self._data_directory,
            self._all_projects,
        )
        self._importer = ImportarPdfsNoProjeto(
            self._reader,
            self._unit_of_work,
            coordenador=coordinator,
        )
        self._photos = ServicoPortabilidadeProjeto(
            self._unit_of_work,
            ZipProjectArchive(),
            SqlitePortableProjectDatabase(),
            SqliteBackupManager(),
            diretorio_dados=self._data_directory,
            caminho_banco=database_path,
            gerenciador_arquivos=self._managed_files,
            coordenador=coordinator,
            descartar_conexoes=engine.dispose,
        )
        self._storage.cleanup_interrupted()
        self._cleanup_abandoned_uploads()

    @property
    def credential_count(self) -> int:
        return len(self._credentials)

    def close(self) -> None:
        self._credentials.limpar()

    @property
    def portability_service(self) -> ServicoPortabilidadeProjeto:
        """Compartilhe os casos de uso somente com a API servidor de portabilidade."""
        return self._photos

    @property
    def pdf_credentials(self) -> ProvedorCredenciaisPdfMemoria:
        """Compartilhe somente o cofre efêmero com o visualizador do mesmo worker."""
        return self._credentials

    def list_projects(self, *, limit: int, offset: int) -> ProjectSummaryListResponse:
        snapshots = self._all_snapshots()
        items = tuple(self._project_summary(item) for item in snapshots[offset : offset + limit])
        return ProjectSummaryListResponse(
            items=items,
            page=PageMetadataDto(limit=limit, offset=offset, total=len(snapshots)),
        )

    def create_project(self, service_note: str, idempotency_key: str) -> ProjectDetailResponse:
        normalized = normalizar_numero_ns(service_note)
        fingerprint = _fingerprint("create-project", {"service_note": normalized})
        project_id = _resource_id("project", idempotency_key, fingerprint)
        with self._store.idempotency_guard(
            key=idempotency_key,
            operation="create-project",
            request_sha256=fingerprint,
            resource_id=project_id,
        ) as record:
            replay = _replay(record, ProjectDetailResponse)
            if replay is not None:
                return replay
            try:
                with self._coordinator.adquirir(TipoOperacao.ALTERACAO_PROJETO):
                    existing = self._snapshot_or_none(project_id)
                    self._require_available_service_note(normalized, project_id=project_id)
                    if existing is None:
                        self._save_new_project(project_id, normalized)
            except Exception:
                self._store.abandon_idempotency(record)
                raise
            response = self.get_project(project_id)
            self._complete(record, response)
            return response

    def find_project_by_service_note(self, service_note: str) -> ProjectDetailResponse:
        normalized = normalizar_numero_ns(service_note)
        matches = self._snapshots_by_service_note(normalized)
        if not matches:
            raise resource_not_found("Projeto não encontrado para a Nota de Serviço informada.")
        if len(matches) > 1:
            raise self._ambiguous_service_note_error()
        return ProjectDetailResponse(project=self._project_detail(matches[0]))

    def get_project(self, project_id: UUID) -> ProjectDetailResponse:
        return ProjectDetailResponse(project=self._project_detail(self._snapshot(project_id)))

    def get_service_codes(self, project_id: UUID) -> ProjectServiceCodesResponse:
        snapshot = self._snapshot(project_id)
        return ProjectServiceCodesResponse(
            project_id=ProjectId(project_id),
            service_codes=snapshot.project.codigos_servico,
            project_version=snapshot.version,
        )

    def require_project_version(self, project_id: UUID, expected_version: int) -> None:
        """Valide a precondição do job antes de reservar a operação global."""
        self._require_version(self._snapshot(project_id), expected_version)

    def analysis_passwords(self, project_id: UUID) -> dict[UUID, str]:
        """Copie para o job somente credenciais efêmeras do worker atual."""
        project = self._snapshot(project_id).project
        passwords: dict[UUID, str] = {}
        with self._unit_of_work() as work:
            for document in project.documentos:
                source = work.fontes_pdf.obter(document.id)
                if source is None:
                    continue
                password = self._credentials.obter(IdentidadeCredencialPdf.da_fonte(source))
                if password is not None:
                    passwords[document.id] = password
        return passwords

    def update_project(
        self,
        project_id: UUID,
        *,
        service_note: str,
        expected_version: int,
    ) -> ProjectDetailResponse:
        normalized = normalizar_numero_ns(service_note)
        with self._coordinator.adquirir(TipoOperacao.ALTERACAO_PROJETO):
            snapshot = self._snapshot(project_id)
            self._require_version(snapshot, expected_version)
            self._require_available_service_note(normalized, project_id=project_id)
            with self._unit_of_work() as work:
                work.projetos.salvar(replace(snapshot.project, nome=normalized))
                work.commit()
        return self.get_project(project_id)

    def replace_service_codes(
        self,
        project_id: UUID,
        *,
        service_codes: tuple[str, ...],
        expected_version: int,
    ) -> ProjectServiceCodesResponse:
        normalized = tuple(normalizar_codigo_servico(code) for code in service_codes)
        with self._coordinator.adquirir(TipoOperacao.ALTERACAO_PROJETO):
            snapshot = self._snapshot(project_id)
            self._require_version(snapshot, expected_version)
            with self._unit_of_work() as work:
                work.projetos.salvar(replace(snapshot.project, codigos_servico=normalized))
                work.commit()
        return self.get_service_codes(project_id)

    def delete_project(self, project_id: UUID) -> DeleteProjectResponse:
        with self._coordinator.adquirir(TipoOperacao.EXCLUSAO_PROJETO):
            snapshot = self._snapshot(project_id)
            counts = self._deletion_counts(snapshot.project)
            credentials = self._project_credentials(snapshot.project)
            journal = self._managed_files.preparar_exclusao_projeto(project_id)
            try:
                with self._unit_of_work() as work:
                    if not work.projetos.remover(project_id):
                        raise ProjetoNaoEncontradoError("Projeto não encontrado para exclusão")
                    work.commit()
            except Exception:
                self._managed_files.cancelar(journal)
                raise
            self._managed_files.concluir(journal)
            for identity in credentials:
                self._credentials.descartar(identity)
        return DeleteProjectResponse(
            project_id=ProjectId(project_id),
            deleted=True,
            counts=counts,
        )

    async def receive_upload(self, upload: UploadFile) -> ReceivedUpload:
        try:
            return await self._storage.receive(upload)
        finally:
            await upload.close()

    def upload_document(
        self,
        project_id: UUID,
        upload: ReceivedUpload,
        idempotency_key: str,
    ) -> CreateUploadResponse:
        self._require_pdf_name(upload)
        fingerprint = _fingerprint(
            "upload-document",
            {
                "project_id": str(project_id),
                "display_name": upload.display_name,
                "sha256": upload.sha256,
                "size_bytes": upload.size_bytes,
            },
        )
        upload_id = _resource_id("upload", idempotency_key, fingerprint)
        document_id = uuid5(upload_id, "managed-document")
        try:
            with self._store.idempotency_guard(
                key=idempotency_key,
                operation="upload-document",
                request_sha256=fingerprint,
                resource_id=upload_id,
            ) as record:
                response = self._resume_or_import_upload(
                    record,
                    upload_id=upload_id,
                    document_id=document_id,
                    project_id=project_id,
                    upload=upload,
                )
                return response
        finally:
            self._storage.discard(upload)

    def unlock_pdf(self, upload_id: UUID, password: str) -> DocumentImportResultDto:
        record = self._store.get_upload(upload_id)
        if record is None:
            raise resource_not_found("Upload não encontrado.")
        if record.state is UploadState.IMPORTED:
            return self._import_result_from_record(record)
        if record.state is not UploadState.PASSWORD_REQUIRED:
            raise operation_conflict("O upload não aceita novas tentativas de senha.")
        if record.document_id is None or record.pending_relative_path is None:
            raise ApiError(409, ErrorCode.INTEGRITY_ERROR, "O upload protegido está incompleto.")
        pending = self._storage.resolve_pending_relative(record.pending_relative_path)
        if not pending.is_file():
            raise ApiError(409, ErrorCode.INTEGRITY_ERROR, "O upload protegido está indisponível.")
        published = self._storage.publish_pending(
            pending,
            project_id=record.project_id,
            document_id=record.document_id,
        )
        try:
            result = self._importer.executar(
                record.project_id,
                (published.destination,),
                senha=password,
                documentos_ids=(record.document_id,),
                nomes_exibicao=(record.display_name,),
            )
        except PdfProtegidoError:
            published.restore_source()
            updated = self._store.register_invalid_password(upload_id)
            if updated.password_attempts_remaining == 0:
                pending.unlink(missing_ok=True)
            raise ApiError(
                422,
                ErrorCode.PDF_PASSWORD_INVALID,
                "A senha informada para o PDF está incorreta.",
                {"password_attempts_remaining": updated.password_attempts_remaining or 0},
            ) from None
        except Exception:
            published.restore_source()
            raise
        inspection = result.inspecoes[0]
        self._credentials.guardar(IdentidadeCredencialPdf.da_inspecao(inspection), password)
        self._store.mark_upload_imported(upload_id, record.document_id)
        published.complete()
        return self._document_import_result(upload_id, result.projeto, record.document_id)

    def replace_page_order(
        self,
        project_id: UUID,
        *,
        page_ids: tuple[UUID, ...],
        expected_version: int,
    ) -> PageOrderResponse:
        with self._coordinator.adquirir(TipoOperacao.ALTERACAO_PROJETO):
            snapshot = self._snapshot(project_id)
            self._require_version(snapshot, expected_version)
            current_ids = snapshot.project.ordem_leitura_paginas
            if len(set(page_ids)) != len(page_ids):
                raise validation_error("A ordem das páginas repete identificadores.")
            if len(page_ids) != len(current_ids) or set(page_ids) != set(current_ids):
                raise validation_error("A ordem deve conter todas as páginas uma única vez.")
            with self._unit_of_work() as work:
                work.projetos.salvar(replace(snapshot.project, ordem_leitura_paginas=page_ids))
                work.commit()
        updated = self._snapshot(project_id)
        return PageOrderResponse(
            project_id=ProjectId(project_id),
            project_version=updated.version,
            pages=self._page_summaries(updated.project),
        )

    def remove_document(self, project_id: UUID, document_id: UUID) -> RemoveDocumentResponse:
        with self._coordinator.adquirir(TipoOperacao.EXCLUSAO_DOCUMENTOS):
            snapshot = self._snapshot(project_id)
            selected = next(
                (item for item in snapshot.project.documentos if item.id == document_id),
                None,
            )
            if selected is None:
                raise resource_not_found("Documento não encontrado no projeto.")
            page_ids = {page.id for page in selected.paginas}
            updated = project_without_documents(snapshot.project, {document_id}, page_ids)
            candidates = [*fotos_removidas(snapshot.project, updated)]
            managed_source = self._managed_source_candidate(project_id, document_id)
            credential = self._source_credential(document_id)
            if managed_source is not None:
                candidates.append(managed_source)
            journal = self._managed_files.preparar_coleta_fotos(project_id, candidates)
            try:
                with self._unit_of_work() as work:
                    self._remove_affected_analysis(work, project_id, page_ids)
                    work.projetos.salvar(updated)
                    work.commit()
            except Exception:
                self._managed_files.cancelar(journal)
                raise
            self._managed_files.concluir(journal)
            if credential is not None:
                self._credentials.descartar(credential)
        current = self._snapshot(project_id)
        return RemoveDocumentResponse(
            project_id=ProjectId(project_id),
            document_id=DocumentId(document_id),
            removed=True,
            removed_page_count=len(page_ids),
            project_version=current.version,
        )

    def list_photos(self, project_id: UUID) -> ManagedPhotoListResponse:
        snapshot = self._snapshot(project_id)
        return ManagedPhotoListResponse(
            items=tuple(
                self._photo_dto(snapshot, element, photo)
                for element in snapshot.project.elementos
                for photo in element.fotos
            )
        )

    def attach_photo(
        self,
        project_id: UUID,
        element_id: UUID,
        upload: ReceivedUpload,
        idempotency_key: str,
    ) -> ManagedPhotoResponse:
        fingerprint = _fingerprint(
            "attach-photo",
            {
                "project_id": str(project_id),
                "element_id": str(element_id),
                "sha256": upload.sha256,
                "size_bytes": upload.size_bytes,
            },
        )
        resource_id = _resource_id("photo-request", idempotency_key, fingerprint)
        try:
            with self._store.idempotency_guard(
                key=idempotency_key,
                operation="attach-photo",
                request_sha256=fingerprint,
                resource_id=resource_id,
            ) as record:
                replay = _replay(record, ManagedPhotoResponse)
                if replay is not None:
                    return replay
                result = self._photos.anexar_foto(project_id, element_id, upload.path)
                if result.foto is None:
                    raise RuntimeError("O serviço de fotos não retornou a foto anexada")
                snapshot = self._snapshot(project_id)
                element = self._element(snapshot.project, element_id)
                response = ManagedPhotoResponse(
                    photo=self._photo_dto(snapshot, element, result.foto)
                )
                self._complete(record, response)
                return response
        finally:
            self._storage.discard(upload)

    def remove_photo(
        self,
        project_id: UUID,
        element_id: UUID,
        photo_id: UUID,
    ) -> RemoveManagedPhotoResponse:
        self._photos.remover_foto(project_id, element_id, photo_id)
        return RemoveManagedPhotoResponse(photo_id=PhotoId(photo_id), removed=True)

    def photo_download(self, project_id: UUID, photo_id: UUID) -> ManagedDownload:
        project = self._snapshot(project_id).project
        photo = next(
            (
                photo
                for element in project.elementos
                for photo in element.fotos
                if photo.id == photo_id
            ),
            None,
        )
        if photo is None:
            raise resource_not_found("Foto não encontrada no projeto.")
        if photo.sha256 is None or photo.tipo_mime is None or photo.tamanho_bytes is None:
            raise ApiError(409, ErrorCode.INTEGRITY_ERROR, "A foto não possui identidade completa.")
        root = (self._data_directory / "project-files" / str(project_id)).resolve()
        path = (root / photo.caminho_relativo).resolve()
        if not path.is_relative_to(root) or path.is_symlink() or not path.is_file():
            raise ApiError(
                409,
                ErrorCode.INTEGRITY_ERROR,
                "O arquivo gerenciado da foto é inválido.",
            )
        if path.stat().st_size != photo.tamanho_bytes or _file_sha256(path) != photo.sha256:
            raise ApiError(409, ErrorCode.INTEGRITY_ERROR, "A integridade da foto não confere.")
        return ManagedDownload(
            path=path,
            display_name=path.name,
            mime_type=photo.tipo_mime,
            size_bytes=photo.tamanho_bytes,
            sha256=photo.sha256,
        )

    def _resume_or_import_upload(
        self,
        record: IdempotencyRecord,
        *,
        upload_id: UUID,
        document_id: UUID,
        project_id: UUID,
        upload: ReceivedUpload,
    ) -> CreateUploadResponse:
        replay = _replay(record, CreateUploadResponse)
        if replay is not None:
            return replay
        snapshot = self._snapshot(project_id)
        receipt = self._store.get_upload(upload_id)
        if receipt is not None:
            response = self._create_upload_response(receipt, snapshot.project)
            self._complete(record, response)
            return response
        existing = next(
            (item for item in snapshot.project.documentos if item.id == document_id),
            None,
        )
        if existing is not None:
            receipt = self._store.record_imported_upload(
                upload_id=upload_id,
                project_id=project_id,
                document_id=document_id,
                display_name=upload.display_name,
                sha256=upload.sha256,
                size_bytes=upload.size_bytes,
            )
            response = self._create_upload_response(receipt, snapshot.project)
            self._complete(record, response)
            return response
        if any(item.sha256 == upload.sha256 for item in snapshot.project.documentos):
            self._store.abandon_idempotency(record)
            raise operation_conflict("O projeto já contém este conteúdo PDF.")
        return self._import_new_upload(
            record,
            upload_id=upload_id,
            document_id=document_id,
            project_id=project_id,
            upload=upload,
        )

    def _import_new_upload(
        self,
        record: IdempotencyRecord,
        *,
        upload_id: UUID,
        document_id: UUID,
        project_id: UUID,
        upload: ReceivedUpload,
    ) -> CreateUploadResponse:
        published = self._storage.publish_document(
            upload,
            project_id=project_id,
            document_id=document_id,
        )
        try:
            result = self._importer.executar(
                project_id,
                (published.destination,),
                documentos_ids=(document_id,),
                nomes_exibicao=(upload.display_name,),
            )
        except PdfProtegidoError as error:
            if error.senha_fornecida:
                published.restore_source()
                self._store.abandon_idempotency(record)
                raise
            pending = self._storage.pending_path(upload_id)
            published.move_to_pending(pending)
            try:
                receipt = self._store.save_pending_upload(
                    upload_id=upload_id,
                    project_id=project_id,
                    document_id=document_id,
                    display_name=upload.display_name,
                    sha256=upload.sha256,
                    size_bytes=upload.size_bytes,
                    pending_relative_path=self._storage.pending_relative_path(upload_id),
                )
            except Exception:
                pending.unlink(missing_ok=True)
                self._store.abandon_idempotency(record)
                raise
            response = self._create_upload_response(receipt, self._snapshot(project_id).project)
            self._complete(record, response)
            return response
        except Exception:
            published.restore_source()
            self._store.abandon_idempotency(record)
            raise
        published.complete()
        receipt = self._store.record_imported_upload(
            upload_id=upload_id,
            project_id=project_id,
            document_id=document_id,
            display_name=upload.display_name,
            sha256=upload.sha256,
            size_bytes=upload.size_bytes,
        )
        response = self._create_upload_response(receipt, result.projeto)
        self._complete(record, response)
        return response

    def _create_upload_response(
        self,
        receipt: UploadRecord,
        project: Projeto,
    ) -> CreateUploadResponse:
        document = next(
            (item for item in project.documentos if item.id == receipt.document_id),
            None,
        )
        imported = receipt.state is UploadState.IMPORTED and document is not None
        password_required = receipt.state is UploadState.PASSWORD_REQUIRED
        return CreateUploadResponse(
            upload_id=UploadId(receipt.upload_id),
            state=receipt.state,
            display_name=receipt.display_name,
            size_received=receipt.size_bytes,
            sha256=receipt.sha256,
            preflight=DocumentUploadPreflightDto(
                disposition=PreflightDisposition.READY,
                password_required=password_required,
                duplicate_content=False,
                detected_page_count=(
                    len(document.paginas) if imported and document is not None else None
                ),
            ),
        )

    def _import_result_from_record(self, record: UploadRecord) -> DocumentImportResultDto:
        if record.document_id is None:
            raise ApiError(
                409,
                ErrorCode.INTEGRITY_ERROR,
                "O recibo importado não identifica documento.",
            )
        project = self._snapshot(record.project_id).project
        return self._document_import_result(record.upload_id, project, record.document_id)

    def _document_import_result(
        self,
        upload_id: UUID,
        project: Projeto,
        document_id: UUID,
    ) -> DocumentImportResultDto:
        document = next((item for item in project.documentos if item.id == document_id), None)
        if document is None:
            raise resource_not_found("O documento importado não está mais disponível.")
        snapshot = self._snapshot(project.id)
        return DocumentImportResultDto(
            upload_id=UploadId(upload_id),
            state=UploadState.IMPORTED,
            document=self._document_summary(snapshot, document),
            pages=tuple(
                page
                for page in self._page_summaries(project)
                if page.document_id.root == document_id
            ),
        )

    def _save_new_project(self, project_id: UUID, service_note: str) -> None:
        project = Projeto(
            id=project_id,
            nome=service_note,
            catalogo_versao_id=self._catalog_id,
            criado_em=datetime.now(UTC),
        )
        with self._unit_of_work() as work:
            work.projetos.salvar(project)
            work.commit()

    def _cleanup_abandoned_uploads(self) -> None:
        cutoff = datetime.now(UTC) - _PENDING_UPLOAD_TTL
        for record in self._store.pending_uploads_before(cutoff):
            if record.pending_relative_path is not None:
                pending = self._storage.resolve_pending_relative(record.pending_relative_path)
                pending.unlink(missing_ok=True)
            self._store.mark_upload_expired(record.upload_id)

    def _snapshot(self, project_id: UUID) -> _ProjectSnapshot:
        snapshot = self._snapshot_or_none(project_id)
        if snapshot is None:
            raise resource_not_found("Projeto não encontrado.")
        return snapshot

    def _snapshot_or_none(self, project_id: UUID) -> _ProjectSnapshot | None:
        with self._unit_of_work() as work:
            project = work.projetos.obter(project_id)
        if project is None:
            return None
        with self._engine.connect() as connection:
            row = connection.execute(
                select(projects.c.version, projects.c.updated_at).where(
                    projects.c.id == str(project_id)
                )
            ).one()
        return _ProjectSnapshot(project, int(row.version), _parse_time(str(row.updated_at)))

    def _all_snapshots(self) -> tuple[_ProjectSnapshot, ...]:
        with self._unit_of_work() as work:
            all_projects = work.projetos.listar()
        return tuple(self._snapshot(project.id) for project in all_projects)

    def _all_projects(self) -> tuple[Projeto, ...]:
        with self._unit_of_work() as work:
            return work.projetos.listar()

    def _snapshots_by_service_note(self, service_note: str) -> tuple[_ProjectSnapshot, ...]:
        with self._engine.connect() as connection:
            project_ids = tuple(
                UUID(value)
                for value in connection.scalars(
                    select(projects.c.id)
                    .where(projects.c.name == service_note)
                    .order_by(projects.c.created_at, projects.c.id)
                )
            )
        return tuple(self._snapshot(project_id) for project_id in project_ids)

    def _require_available_service_note(self, service_note: str, *, project_id: UUID) -> None:
        matches = self._snapshots_by_service_note(service_note)
        if len(matches) > 1:
            raise self._ambiguous_service_note_error()
        if matches and matches[0].project.id != project_id:
            raise ProjectAlreadyExistsError(matches[0].project.id, service_note)

    @staticmethod
    def _ambiguous_service_note_error() -> ApiError:
        return ApiError(
            409,
            ErrorCode.INTEGRITY_ERROR,
            "Mais de um projeto possui a Nota de Serviço informada.",
        )

    def _unit_of_work(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._engine)

    def _project_summary(self, snapshot: _ProjectSnapshot) -> ProjectSummaryDto:
        project = snapshot.project
        return ProjectSummaryDto(
            project_id=ProjectId(project.id),
            service_note=project.nome,
            state=_project_state(project),
            project_version=snapshot.version,
            document_count=len(project.documentos),
            page_count=sum(len(item.paginas) for item in project.documentos),
            analysis=self._analysis_summary(project),
            created_at=project.criado_em,
            updated_at=snapshot.updated_at,
        )

    def _project_detail(self, snapshot: _ProjectSnapshot) -> ProjectDetailDto:
        project = snapshot.project
        return ProjectDetailDto(
            project_id=ProjectId(project.id),
            service_note=project.nome,
            state=_project_state(project),
            project_version=snapshot.version,
            documents=tuple(self._document_summary(snapshot, item) for item in project.documentos),
            pages=self._page_summaries(project),
            analysis=self._analysis_summary(project),
            created_at=project.criado_em,
            updated_at=snapshot.updated_at,
        )

    def _analysis_summary(self, project: Projeto) -> ProjectAnalysisSummaryDto:
        with self._unit_of_work() as work:
            runs = work.execucoes_analise.listar_do_projeto(project.id)
            extractions = tuple(
                run for run in runs if "execucao_extracao_id" not in dict(run.parametros)
            )
            interpretations = tuple(
                run for run in runs if "execucao_extracao_id" in dict(run.parametros)
            )
            latest_by_source = {}
            for run in interpretations:
                source = str(dict(run.parametros).get("execucao_extracao_id", run.id))
                latest_by_source[source] = run
            proposals = tuple(
                proposal
                for run in latest_by_source.values()
                for proposal in work.propostas.listar_da_execucao(run.id)
            )
            pending = sum(
                proposal.estado_revisao in {EstadoRevisao.PROPOSTA, EstadoRevisao.CONFLITANTE}
                for proposal in proposals
            )
            decided = sum(
                work.decisoes_revisao.obter_da_proposta(proposal.id) is not None
                for proposal in proposals
            )
        return ProjectAnalysisSummaryDto(
            last_extraction=(_analysis_state(extractions[-1].estado) if extractions else None),
            last_interpretation=(
                _analysis_state(interpretations[-1].estado) if interpretations else None
            ),
            pending_proposals=pending,
            completed_decisions=decided + len(project.historico_revisao_manual),
        )

    def _document_summary(
        self,
        snapshot: _ProjectSnapshot,
        document: DocumentoProjeto,
    ) -> DocumentSummaryDto:
        return DocumentSummaryDto(
            document_id=DocumentId(document.id),
            project_id=ProjectId(snapshot.project.id),
            file=FileMetadataDto(
                display_name=document.nome_arquivo,
                mime_type="application/pdf",
                size_bytes=document.tamanho_bytes or 0,
                sha256=document.sha256,
            ),
            page_count=len(document.paginas),
            imported_at=snapshot.updated_at,
        )

    def _page_summaries(self, project: Projeto) -> tuple[PageSummaryDto, ...]:
        by_page = {
            page.id: (document.id, page)
            for document in project.documentos
            for page in document.paginas
        }
        return tuple(
            PageSummaryDto(
                page_id=PageId(page_id),
                document_id=DocumentId(by_page[page_id][0]),
                reading_order=index,
                source_page_number=by_page[page_id][1].numero,
                width_points=format(by_page[page_id][1].largura_pontos, "f"),
                height_points=format(by_page[page_id][1].altura_pontos, "f"),
                intrinsic_rotation_degrees=by_page[page_id][1].rotacao_graus,
            )
            for index, page_id in enumerate(project.ordem_leitura_paginas)
        )

    def _deletion_counts(self, project: Projeto) -> DeletionCountsDto:
        with self._unit_of_work() as work:
            runs = work.execucoes_analise.listar_do_projeto(project.id)
            reviews = sum(
                work.decisoes_revisao.obter_da_proposta(proposal.id) is not None
                for run in runs
                for proposal in work.propostas.listar_da_execucao(run.id)
            )
        return DeletionCountsDto(
            documents=len(project.documentos),
            pages=sum(len(item.paginas) for item in project.documentos),
            analyses=len(runs),
            reviews=reviews + len(project.historico_revisao_manual),
            photos=sum(len(item.fotos) for item in project.elementos),
        )

    def _managed_source_candidate(self, project_id: UUID, document_id: UUID) -> FotoElemento | None:
        with self._unit_of_work() as work:
            source = work.fontes_pdf.obter(document_id)
        if source is None:
            return None
        project_root = (self._data_directory / "project-files" / str(project_id)).resolve()
        source_path = source.caminho_canonico.resolve()
        if not source_path.is_relative_to(project_root):
            return None
        return FotoElemento(
            id=document_id,
            caminho_relativo=source_path.relative_to(project_root).as_posix(),
        )

    def _source_credential(self, document_id: UUID) -> IdentidadeCredencialPdf | None:
        with self._unit_of_work() as work:
            source = work.fontes_pdf.obter(document_id)
        return IdentidadeCredencialPdf.da_fonte(source) if source is not None else None

    def _project_credentials(self, project: Projeto) -> tuple[IdentidadeCredencialPdf, ...]:
        identities: list[IdentidadeCredencialPdf] = []
        with self._unit_of_work() as work:
            for document in project.documentos:
                source = work.fontes_pdf.obter(document.id)
                if source is not None:
                    identities.append(IdentidadeCredencialPdf.da_fonte(source))
        return tuple(identities)

    @staticmethod
    def _remove_affected_analysis(
        work: SqlAlchemyUnitOfWork,
        project_id: UUID,
        page_ids: set[UUID],
    ) -> None:
        runs = work.execucoes_analise.listar_do_projeto(project_id)
        affected = {
            run.id
            for run in runs
            if any(
                evidence.pagina_id in page_ids
                for evidence in work.evidencias.listar_da_execucao(run.id)
            )
        }
        changed = True
        while changed:
            before = len(affected)
            affected.update(
                run.id
                for run in runs
                if str(dict(run.parametros).get("execucao_extracao_id", ""))
                in {str(item) for item in affected}
            )
            changed = len(affected) != before
        for run in reversed(runs):
            if run.id in affected:
                work.execucoes_analise.remover(run.id)

    def _photo_dto(
        self,
        snapshot: _ProjectSnapshot,
        element: ElementoProjetoType,
        photo: FotoElemento,
    ) -> ManagedPhotoDto:
        if photo.sha256 is None or photo.tipo_mime is None or photo.tamanho_bytes is None:
            raise ApiError(409, ErrorCode.INTEGRITY_ERROR, "A foto não possui identidade completa.")
        return ManagedPhotoDto(
            photo_id=PhotoId(photo.id),
            project_id=ProjectId(snapshot.project.id),
            element_id=ElementId(element.id),
            file=FileMetadataDto(
                display_name=Path(photo.caminho_relativo).name,
                mime_type=photo.tipo_mime,
                size_bytes=photo.tamanho_bytes,
                sha256=photo.sha256,
            ),
            attached_at=snapshot.updated_at,
        )

    @staticmethod
    def _element(project: Projeto, element_id: UUID) -> ElementoProjetoType:
        element = next((item for item in project.elementos if item.id == element_id), None)
        if element is None:
            raise resource_not_found("Elemento não encontrado no projeto.")
        return element

    @staticmethod
    def _require_version(snapshot: _ProjectSnapshot, expected_version: int) -> None:
        if snapshot.version != expected_version:
            raise StaleStateError(snapshot.version)

    @staticmethod
    def _require_pdf_name(upload: ReceivedUpload) -> None:
        if Path(upload.display_name).suffix.casefold() != ".pdf":
            raise unsupported_media("O upload de documento aceita somente arquivos PDF.")

    def _complete(self, record: IdempotencyRecord, response: BaseModel) -> None:
        self._store.complete_idempotency(
            record,
            response.model_dump_json(),
        )


def _project_state(project: Projeto) -> ProjectState:
    return ProjectState.READY if project.documentos else ProjectState.CREATED


def _analysis_state(state: EstadoExecucaoAnalise) -> AnalysisExecutionState:
    return {
        EstadoExecucaoAnalise.INICIADA: AnalysisExecutionState.STARTED,
        EstadoExecucaoAnalise.CONCLUIDA: AnalysisExecutionState.SUCCEEDED,
        EstadoExecucaoAnalise.FALHOU: AnalysisExecutionState.FAILED,
        EstadoExecucaoAnalise.CANCELADA: AnalysisExecutionState.CANCELLED,
    }[state]


def _fingerprint(operation: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(
        {"operation": operation, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _resource_id(kind: str, key: str, fingerprint: str) -> UUID:
    return uuid5(_RESOURCE_NAMESPACE, f"{kind}:{key}:{fingerprint}")


def _replay(record: IdempotencyRecord, model: type[ModelT]) -> ModelT | None:
    if record.response_json is None:
        return None
    return model.model_validate_json(record.response_json)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
