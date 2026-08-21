"""Projeção HTTP de portabilidade e backup, executada somente no servidor."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from threading import RLock
from uuid import UUID, uuid5

from fastapi import UploadFile
from pydantic import JsonValue

from zeny_project_handler.application.errors import (
    PlanoImportacaoObsoletoError,
    PortabilidadeProjetoError,
)
from zeny_project_handler.application.project_portability import (
    PlanoImportacaoProjeto,
    PlanoRestauracaoBackup,
    ServicoPortabilidadeProjeto,
)
from zeny_project_handler.domain.portability import (
    EstadoIntegridadePacote,
    OmissaoPacoteProjeto,
    RelatorioIntegridadeProjeto,
)
from zeny_project_handler_contracts.backup import (
    BackupPreflightResponse,
    BackupRestorePreflightResponse,
    BackupRestoreSummaryDto,
    ConfirmBackupRestoreRequest,
    CreateBackupJobRequest,
)
from zeny_project_handler_contracts.base import (
    BackupPreflightId,
    BackupRestorePreflightId,
    ProjectId,
    ProjectImportPreflightId,
)
from zeny_project_handler_contracts.common import (
    DownloadMetadataDto,
    PreflightIssueDto,
)
from zeny_project_handler_contracts.enums import (
    IntegrityState,
    IssueSeverity,
    PreflightDisposition,
)
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.exports import CreateDeliverableExportRequest
from zeny_project_handler_contracts.portability import (
    ConfirmProjectImportRequest,
    ProjectImportPreflightResponse,
    ProjectImportSummaryDto,
)
from zeny_project_handler_server.api_errors import (
    ApiError,
    IdempotencyConflictError,
)
from zeny_project_handler_server.deliverable_exports import DeliverableExportService
from zeny_project_handler_server.project_api import ProjectApiService
from zeny_project_handler_server.transfer_storage import (
    ManagedTransferStorage,
    TransferDownload,
    idempotency_key_sha256,
)

_PREFLIGHT_NAMESPACE = UUID("78c7080b-d3f0-4fd6-b27b-ccf9a224fd2a")
_PROJECT_IMPORT_KIND = "project-import"
_BACKUP_RESTORE_KIND = "backup-restore"
_PROJECT_MIME = "application/vnd.zeny.project+zip"
_BACKUP_MIME = "application/vnd.zeny.backup+zip"


@dataclass(frozen=True, slots=True)
class JobExecutionResult:
    result: dict[str, JsonValue]
    download: DownloadMetadataDto | None = None


@dataclass(frozen=True, slots=True)
class _BackupPreflight:
    response: BackupPreflightResponse
    report: RelatorioIntegridadeProjeto


class PortabilityApiService:
    """Retenha planos e artefatos sem expor qualquer caminho físico ao cliente."""

    def __init__(
        self,
        *,
        project_api: ProjectApiService,
        transfer_storage: ManagedTransferStorage,
        deliverable_exports: DeliverableExportService | None = None,
    ) -> None:
        self._projects = project_api
        self._service: ServicoPortabilidadeProjeto = project_api.portability_service
        self._storage = transfer_storage
        self._deliverable_exports = deliverable_exports
        self._backup_preflights: dict[UUID, _BackupPreflight] = {}
        self._lock = RLock()

    def create_deliverable_export(
        self,
        project_id: UUID,
        request: CreateDeliverableExportRequest,
    ) -> DownloadMetadataDto:
        exporter = self._deliverable_exports
        if exporter is None:
            raise RuntimeError("A exportação de arquivos finais não está disponível")
        return exporter.create(project_id, request)

    async def receive_project_import(
        self,
        upload: UploadFile,
        *,
        idempotency_key: str,
    ) -> ProjectImportPreflightResponse:
        received = await self._storage.receive(upload, expected_suffix=".zphproj")
        key_hash = idempotency_key_sha256(_PROJECT_IMPORT_KIND, idempotency_key)
        previous = self._storage.find_preflight_by_key(_PROJECT_IMPORT_KIND, key_hash)
        if previous is not None:
            self._storage.discard_upload(received)
            if previous.request_sha256 != received.sha256:
                raise IdempotencyConflictError()
            return ProjectImportPreflightResponse.model_validate_json(previous.response_json)
        try:
            plan = self._service.preflight_importacao(received.path)
            preflight_id = uuid5(
                _PREFLIGHT_NAMESPACE,
                f"{_PROJECT_IMPORT_KIND}:{idempotency_key}:{received.sha256}",
            )
            expires_at = datetime.now(UTC) + self._storage.ttl
            response = _project_preflight_response(preflight_id, plan, expires_at)
            self._storage.retain_preflight(
                received,
                preflight_id=preflight_id,
                kind=_PROJECT_IMPORT_KIND,
                key_sha256=key_hash,
                response_json=response.model_dump_json(),
                expires_at=expires_at,
            )
            return response
        except PortabilidadeProjetoError as error:
            self._storage.discard_upload(received)
            raise _package_integrity_error(str(error)) from error
        except BaseException:
            self._storage.discard_upload(received)
            raise

    def preflight_backup(self) -> BackupPreflightResponse:
        report = self._service.preflight_backup()
        project_count, document_count = self._project_counts()
        fingerprint = _backup_source_fingerprint(
            report,
            project_count,
            document_count,
            self._service.fingerprint_estado_backup(),
        )
        preflight_id = uuid5(_PREFLIGHT_NAMESPACE, f"backup-create:{fingerprint}")
        response = BackupPreflightResponse(
            preflight_id=BackupPreflightId(preflight_id),
            source_fingerprint=fingerprint,
            disposition=(
                PreflightDisposition.READY
                if report.integro
                else PreflightDisposition.CONFIRMATION_REQUIRED
            ),
            integrity_state=_integrity_state(report.estado),
            project_count=project_count,
            document_count=document_count,
            issues=_issues(report),
            expires_at=datetime.now(UTC) + self._storage.ttl,
        )
        with self._lock:
            self._prune_backup_preflights()
            self._backup_preflights[preflight_id] = _BackupPreflight(response, report)
        return response

    async def receive_backup_restore(
        self,
        upload: UploadFile,
        *,
        idempotency_key: str,
    ) -> BackupRestorePreflightResponse:
        received = await self._storage.receive(upload, expected_suffix=".zphbackup")
        key_hash = idempotency_key_sha256(_BACKUP_RESTORE_KIND, idempotency_key)
        previous = self._storage.find_preflight_by_key(_BACKUP_RESTORE_KIND, key_hash)
        if previous is not None:
            self._storage.discard_upload(received)
            if previous.request_sha256 != received.sha256:
                raise IdempotencyConflictError()
            return BackupRestorePreflightResponse.model_validate_json(previous.response_json)
        try:
            plan = self._service.preflight_restauracao_backup(received.path)
            preflight_id = uuid5(
                _PREFLIGHT_NAMESPACE,
                f"{_BACKUP_RESTORE_KIND}:{idempotency_key}:{received.sha256}",
            )
            expires_at = datetime.now(UTC) + self._storage.ttl
            response = _restore_preflight_response(preflight_id, plan, expires_at)
            self._storage.retain_preflight(
                received,
                preflight_id=preflight_id,
                kind=_BACKUP_RESTORE_KIND,
                key_sha256=key_hash,
                response_json=response.model_dump_json(),
                expires_at=expires_at,
            )
            return response
        except PortabilidadeProjetoError as error:
            self._storage.discard_upload(received)
            raise _package_integrity_error(str(error)) from error
        except BaseException:
            self._storage.discard_upload(received)
            raise

    def require_project_import(self, request: ConfirmProjectImportRequest) -> None:
        stored = self._storage.get_preflight(
            request.preflight_id.root,
            kind=_PROJECT_IMPORT_KIND,
        )
        response = ProjectImportPreflightResponse.model_validate_json(stored.response_json)
        if (
            response.package_sha256 != request.package_sha256
            or response.target_fingerprint != request.target_fingerprint
        ):
            raise _stale_preflight()
        current = self._service.preflight_importacao(stored.path)
        if (
            current.pacote_sha256 != request.package_sha256
            or current.estado_alvo_sha256 != request.target_fingerprint
        ):
            raise _stale_preflight()
        if response.summary.replaces_existing and not request.replace_existing:
            raise ApiError(
                409,
                ErrorCode.OPERATION_CONFLICT,
                "A importação exige confirmação explícita da substituição.",
            )

    def require_backup_create(self, request: CreateBackupJobRequest) -> None:
        with self._lock:
            self._prune_backup_preflights()
            stored = self._backup_preflights.get(request.preflight_id.root)
        if stored is None or stored.response.source_fingerprint != request.source_fingerprint:
            raise _stale_preflight()
        current = self._service.preflight_backup()
        project_count, document_count = self._project_counts()
        if (
            _backup_source_fingerprint(
                current,
                project_count,
                document_count,
                self._service.fingerprint_estado_backup(),
            )
            != request.source_fingerprint
        ):
            raise _stale_preflight()
        if not stored.report.integro and not request.accept_degraded:
            raise ApiError(
                409,
                ErrorCode.OPERATION_CONFLICT,
                "O backup degradado exige confirmação explícita.",
            )

    def require_backup_restore(self, request: ConfirmBackupRestoreRequest) -> None:
        stored = self._storage.get_preflight(
            request.preflight_id.root,
            kind=_BACKUP_RESTORE_KIND,
        )
        response = BackupRestorePreflightResponse.model_validate_json(stored.response_json)
        if (
            response.package_sha256 != request.package_sha256
            or response.target_fingerprint != request.target_fingerprint
        ):
            raise _stale_preflight()
        current = self._service.preflight_restauracao_backup(stored.path)
        if (
            current.pacote_sha256 != request.package_sha256
            or current.estado_alvo_sha256 != request.target_fingerprint
        ):
            raise _stale_preflight()
        if (
            response.summary.integrity_state is IntegrityState.DEGRADED
            and not request.accept_degraded
        ):
            raise ApiError(
                409,
                ErrorCode.OPERATION_CONFLICT,
                "A restauração degradada exige confirmação explícita.",
            )

    def export_project(
        self,
        job_id: UUID,
        project_id: UUID,
        progress: Callable[[int, int, str], None],
        cancelled: Callable[[], bool],
    ) -> JobExecutionResult:
        pending = self._storage.pending_download_path(job_id, ".zphproj")
        pending.unlink(missing_ok=True)
        try:
            exported = self._service.exportar_projeto(
                project_id,
                pending,
                progresso=progress,
                cancelado=cancelled,
            )
            metadata = self._storage.publish_download(
                exported.caminho,
                file_name=f"projeto-{str(project_id)[:8]}.zphproj",
                mime_type=_PROJECT_MIME,
            )
        except BaseException:
            pending.unlink(missing_ok=True)
            raise
        return JobExecutionResult(
            result={
                "project_id": str(project_id),
                "integrity_state": _integrity_state(exported.estado_integridade).value,
                "omission_count": len(exported.manifesto.omissoes),
            },
            download=metadata,
        )

    def import_project(
        self,
        request: ConfirmProjectImportRequest,
        progress: Callable[[int, int, str], None],
        cancelled: Callable[[], bool],
    ) -> JobExecutionResult:
        self.require_project_import(request)
        stored = self._storage.get_preflight(
            request.preflight_id.root,
            kind=_PROJECT_IMPORT_KIND,
        )
        plan = self._service.preflight_importacao(stored.path, cancelado=cancelled)
        if (
            plan.pacote_sha256 != request.package_sha256
            or plan.estado_alvo_sha256 != request.target_fingerprint
        ):
            raise _stale_preflight()
        try:
            imported = self._service.aplicar_plano_importacao(
                plan,
                confirmar_substituicao=request.replace_existing,
                progresso=progress,
                cancelado=cancelled,
            )
        except PlanoImportacaoObsoletoError as error:
            raise _stale_preflight() from error
        self._storage.discard_preflight(request.preflight_id.root)
        return JobExecutionResult(
            result={
                "project_id": str(imported.projeto.id),
                "replaced_existing": imported.substituiu_existente,
                "integrity_state": _integrity_state(imported.integridade_pacote.estado).value,
                "omission_count": len(imported.omissoes_origem),
            }
        )

    def create_backup(
        self,
        job_id: UUID,
        request: CreateBackupJobRequest,
        progress: Callable[[int, int, str], None],
        cancelled: Callable[[], bool],
    ) -> JobExecutionResult:
        self.require_backup_create(request)
        with self._lock:
            stored = self._backup_preflights[request.preflight_id.root]
        current = self._service.preflight_backup(cancelado=cancelled)
        project_count, document_count = self._project_counts()
        current_fingerprint = _backup_source_fingerprint(
            current,
            project_count,
            document_count,
            self._service.fingerprint_estado_backup(),
        )
        if current_fingerprint != request.source_fingerprint:
            raise _stale_preflight()
        pending = self._storage.pending_download_path(job_id, ".zphbackup")
        pending.unlink(missing_ok=True)
        try:
            backup = self._service.criar_backup(
                pending,
                confirmar_degradado=request.accept_degraded,
                relatorio_integridade=stored.report,
                progresso=progress,
                cancelado=cancelled,
            )
            metadata = self._storage.publish_download(
                backup.caminho,
                file_name=f"zeny-backup-{datetime.now(UTC):%Y%m%d-%H%M%S}.zphbackup",
                mime_type=_BACKUP_MIME,
            )
        except BaseException:
            pending.unlink(missing_ok=True)
            raise
        with self._lock:
            self._backup_preflights.pop(request.preflight_id.root, None)
        return JobExecutionResult(
            result={
                "integrity_state": _integrity_state(backup.estado_integridade).value,
                "omission_count": len(backup.manifesto.omissoes),
            },
            download=metadata,
        )

    def restore_backup(
        self,
        request: ConfirmBackupRestoreRequest,
        progress: Callable[[int, int, str], None],
        cancelled: Callable[[], bool],
    ) -> JobExecutionResult:
        self.require_backup_restore(request)
        stored = self._storage.get_preflight(
            request.preflight_id.root,
            kind=_BACKUP_RESTORE_KIND,
        )
        plan = self._service.preflight_restauracao_backup(stored.path, cancelado=cancelled)
        if (
            plan.pacote_sha256 != request.package_sha256
            or plan.estado_alvo_sha256 != request.target_fingerprint
        ):
            raise _stale_preflight()
        try:
            restored = self._service.aplicar_plano_restauracao_backup(
                plan,
                progresso=progress,
                cancelado=cancelled,
            )
        except PlanoImportacaoObsoletoError as error:
            raise _stale_preflight() from error
        self._projects.pdf_credentials.limpar()
        self._storage.discard_preflight(request.preflight_id.root)
        return JobExecutionResult(
            result={
                "integrity_state": _integrity_state(restored.estado_integridade).value,
                "omission_count": len(restored.manifesto.omissoes),
                "project_ids": [str(item) for item in plan.resumo.projetos_ids],
            }
        )

    def get_download(self, download_id: UUID) -> TransferDownload:
        return self._storage.get_download(download_id)

    def _project_counts(self) -> tuple[int, int]:
        offset = 0
        count = 0
        documents = 0
        while True:
            page = self._projects.list_projects(limit=200, offset=offset)
            count += len(page.items)
            documents += sum(item.document_count for item in page.items)
            offset += len(page.items)
            if offset >= page.page.total or not page.items:
                return count, documents

    def _prune_backup_preflights(self) -> None:
        now = datetime.now(UTC)
        expired = [
            preflight_id
            for preflight_id, item in self._backup_preflights.items()
            if item.response.expires_at <= now
        ]
        for preflight_id in expired:
            self._backup_preflights.pop(preflight_id, None)


def _project_preflight_response(
    preflight_id: UUID,
    plan: PlanoImportacaoProjeto,
    expires_at: datetime,
) -> ProjectImportPreflightResponse:
    summary = plan.resumo
    return ProjectImportPreflightResponse(
        preflight_id=ProjectImportPreflightId(preflight_id),
        package_sha256=plan.pacote_sha256,
        target_fingerprint=plan.estado_alvo_sha256,
        disposition=(
            PreflightDisposition.CONFIRMATION_REQUIRED
            if plan.requer_confirmacao
            else PreflightDisposition.READY
        ),
        integrity_state=_integrity_state(plan.integridade_pacote.estado),
        summary=ProjectImportSummaryDto(
            project_id=ProjectId(summary.projeto_id),
            service_note=summary.nome,
            document_count=summary.quantidade_documentos,
            page_count=summary.quantidade_paginas,
            photo_count=summary.quantidade_fotos,
            replaces_existing=plan.requer_confirmacao,
        ),
        issues=_issues(plan.integridade_pacote),
        expires_at=expires_at,
    )


def _restore_preflight_response(
    preflight_id: UUID,
    plan: PlanoRestauracaoBackup,
    expires_at: datetime,
) -> BackupRestorePreflightResponse:
    state = (
        IntegrityState.DEGRADED
        if plan.omissoes_origem
        else _integrity_state(plan.integridade_pacote.estado)
    )
    return BackupRestorePreflightResponse(
        preflight_id=BackupRestorePreflightId(preflight_id),
        package_sha256=plan.pacote_sha256,
        target_fingerprint=plan.estado_alvo_sha256,
        disposition=PreflightDisposition.CONFIRMATION_REQUIRED,
        summary=BackupRestoreSummaryDto(
            project_ids=tuple(ProjectId(item) for item in plan.resumo.projetos_ids),
            document_count=plan.resumo.quantidade_documentos,
            photo_count=plan.resumo.quantidade_fotos,
            integrity_state=state,
        ),
        issues=(*_issues(plan.integridade_pacote), *_omission_issues(plan.omissoes_origem)),
        expires_at=expires_at,
    )


def _issues(report: RelatorioIntegridadeProjeto) -> tuple[PreflightIssueDto, ...]:
    return tuple(
        PreflightIssueDto(
            code=item.codigo,
            severity=IssueSeverity.ERROR if item.critico else IssueSeverity.WARNING,
            summary=item.mensagem,
            resource_id=str(item.referencia_id) if item.referencia_id is not None else None,
        )
        for item in report.problemas
    )


def _omission_issues(omissions: tuple[OmissaoPacoteProjeto, ...]) -> tuple[PreflightIssueDto, ...]:
    return tuple(
        PreflightIssueDto(
            code=item.codigo,
            severity=IssueSeverity.WARNING,
            summary=(
                "O backup declara uma origem omitida; os dados auditáveis serão restaurados, "
                "mas o arquivo precisará ser enviado novamente."
            ),
            resource_id=str(item.referencia_id),
        )
        for item in omissions
    )


def _integrity_state(state: EstadoIntegridadePacote) -> IntegrityState:
    return (
        IntegrityState.INTACT
        if state is EstadoIntegridadePacote.INTEGRO
        else IntegrityState.DEGRADED
    )


def _backup_source_fingerprint(
    report: RelatorioIntegridadeProjeto,
    project_count: int,
    document_count: int,
    state_fingerprint: str,
) -> str:
    payload = {
        "version": 1,
        "project_count": project_count,
        "document_count": document_count,
        "state_fingerprint": state_fingerprint,
        "issues": [
            {
                "code": item.codigo,
                "critical": item.critico,
                "type": item.tipo,
                "resource_id": str(item.referencia_id) if item.referencia_id else None,
                "project_id": str(item.projeto_id) if item.projeto_id else None,
                "treatment": item.tratamento.value if item.tratamento else None,
            }
            for item in report.problemas
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def _stale_preflight() -> ApiError:
    return ApiError(
        409,
        ErrorCode.STALE_STATE,
        "O pacote ou o estado do servidor mudou; execute um novo preflight.",
    )


def _package_integrity_error(message: str) -> ApiError:
    return ApiError(422, ErrorCode.INTEGRITY_ERROR, message)
