"""Worker Qt cliente de upload, polling e download da portabilidade remota."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Event, Lock
from uuid import UUID

from PySide6.QtCore import QObject, Signal, Slot

from zeny_project_handler_client.logging_config import operation_logger
from zeny_project_handler_client.ui.portability_gateway import (
    PortabilityGateway,
    PortabilityGatewayError,
    PortabilityTransferCancelledError,
)
from zeny_project_handler_contracts.backup import (
    BackupPreflightResponse,
    BackupRestorePreflightResponse,
    ConfirmBackupRestoreRequest,
    CreateBackupJobRequest,
)
from zeny_project_handler_contracts.enums import IntegrityState, JobStatus, PreflightDisposition
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.jobs import JobAcceptedResponse, JobResultResponse
from zeny_project_handler_contracts.portability import (
    ConfirmProjectImportRequest,
    ProjectImportPreflightResponse,
)


class PortabilityOperation(StrEnum):
    EXPORT = "export"
    IMPORT = "import"
    BACKUP = "backup"
    RESTORE = "restore"


@dataclass(frozen=True, slots=True)
class PortabilityCommand:
    operation: PortabilityOperation
    path: Path
    project_id: UUID | None = None
    project_version: int | None = None


@dataclass(frozen=True, slots=True)
class PortabilityResult:
    operation: PortabilityOperation
    payload: dict[str, object]
    destination: Path | None = None


class PortabilityWorker(QObject):
    """Mantenha rede e disco local fora da thread visual."""

    progress = Signal(str, int, int, str)
    confirmation_required = Signal(str, str, object)
    succeeded = Signal(str, object)
    failed = Signal(str, str, bool)
    finished = Signal(str)

    def __init__(
        self,
        gateway: PortabilityGateway,
        command: PortabilityCommand,
        cancellation: Event,
        execution_id: str,
    ) -> None:
        super().__init__()
        self._gateway = gateway
        self._command = command
        self._cancellation = cancellation
        self._execution_id = execution_id
        self._confirmation_ready = Event()
        self._confirmation_lock = Lock()
        self._confirmation_response: bool | None = None
        self._job_id: UUID | None = None

    def request_cancel(self) -> None:
        self._cancellation.set()
        with self._confirmation_lock:
            if self._confirmation_response is None:
                self._confirmation_response = False
        self._confirmation_ready.set()

    def resolve_confirmation(self, accepted: bool) -> None:
        with self._confirmation_lock:
            if self._confirmation_response is not None:
                return
            self._confirmation_response = accepted
        self._confirmation_ready.set()

    @Slot()
    def run(self) -> None:
        observation = operation_logger(
            f"qt.worker.portability_{self._command.operation.value}",
            correlation_id=self._execution_id,
            execution_id=self._execution_id,
            project_id=self._command.project_id,
        )
        with observation.context():
            observation.started()
            try:
                result = self._execute()
            except PortabilityTransferCancelledError as error:
                observation.cancelled(error_code=error.__class__.__name__)
                self.failed.emit(self._execution_id, str(error), True)
            except (PortabilityGatewayError, ValueError, OSError) as error:
                observation.failed(error, expected=True)
                self.failed.emit(
                    self._execution_id,
                    str(error).strip() or error.__class__.__name__,
                    False,
                )
            except Exception as error:
                observation.failed(error, expected=False)
                self.failed.emit(
                    self._execution_id,
                    "A operação remota não pôde ser concluída.",
                    False,
                )
            else:
                observation.succeeded()
                self.succeeded.emit(self._execution_id, result)
            finally:
                self.finished.emit(self._execution_id)

    def _execute(self) -> PortabilityResult:
        operation = self._command.operation
        if operation is PortabilityOperation.EXPORT:
            return self._export_project()
        if operation is PortabilityOperation.IMPORT:
            return self._import_project()
        if operation is PortabilityOperation.BACKUP:
            return self._create_backup()
        if operation is PortabilityOperation.RESTORE:
            return self._restore_backup()
        raise ValueError("Operação de portabilidade não suportada")

    def _export_project(self) -> PortabilityResult:
        project_id = self._command.project_id
        project_version = self._command.project_version
        if project_id is None or project_version is None:
            raise ValueError("Projeto da exportação não foi informado")
        accepted = self._gateway.create_project_export_job(
            project_id,
            expected_project_version=project_version,
            idempotency_key=f"{self._execution_id}:export",
        )
        result = self._wait_for_job(accepted, phase_start=0, phase_end=75)
        if result.download is None:
            raise PortabilityGatewayError(
                code=ErrorCode.INTERNAL_ERROR,
                message="O job de exportação terminou sem artefato para download.",
            )
        self._gateway.download_to(
            result.download.download_id.root,
            self._command.path,
            progress=lambda current, total, message: self._emit_phase_progress(
                75,
                100,
                current,
                total,
                message,
            ),
            cancelled=self._cancellation.is_set,
        )
        return PortabilityResult(
            operation=PortabilityOperation.EXPORT,
            payload=dict(result.result or {}),
            destination=self._command.path,
        )

    def _import_project(self) -> PortabilityResult:
        preflight = self._gateway.preflight_project_import(
            self._command.path,
            idempotency_key=f"{self._execution_id}:import-upload",
            progress=lambda current, total, message: self._emit_phase_progress(
                0,
                25,
                current,
                total,
                message,
            ),
            cancelled=self._cancellation.is_set,
        )
        replace_existing = False
        if preflight.disposition is PreflightDisposition.CONFIRMATION_REQUIRED:
            replace_existing = self._confirm("replace_project", preflight)
            if not replace_existing:
                raise PortabilityTransferCancelledError(
                    "Importação cancelada antes da substituição"
                )
        self._ensure_not_cancelled()
        accepted = self._gateway.create_project_import_job(
            ConfirmProjectImportRequest(
                preflight_id=preflight.preflight_id,
                package_sha256=preflight.package_sha256,
                target_fingerprint=preflight.target_fingerprint,
                replace_existing=replace_existing,
                confirmed=True,
            ),
            idempotency_key=f"{self._execution_id}:import-job",
        )
        result = self._wait_for_job(accepted, phase_start=25, phase_end=100)
        return PortabilityResult(
            operation=PortabilityOperation.IMPORT,
            payload=dict(result.result or {}),
        )

    def _create_backup(self) -> PortabilityResult:
        preflight = self._gateway.preflight_backup()
        accept_degraded = preflight.integrity_state is IntegrityState.INTACT
        if preflight.disposition is PreflightDisposition.CONFIRMATION_REQUIRED:
            accept_degraded = self._confirm("degraded_backup", preflight)
            if not accept_degraded:
                raise PortabilityTransferCancelledError(
                    "Backup cancelado antes da criação do pacote degradado"
                )
        self._ensure_not_cancelled()
        accepted = self._gateway.create_backup_job(
            CreateBackupJobRequest(
                preflight_id=preflight.preflight_id,
                source_fingerprint=preflight.source_fingerprint,
                accept_degraded=accept_degraded,
                confirmed=True,
            ),
            idempotency_key=f"{self._execution_id}:backup-job",
        )
        result = self._wait_for_job(accepted, phase_start=0, phase_end=75)
        if result.download is None:
            raise PortabilityGatewayError(
                code=ErrorCode.INTERNAL_ERROR,
                message="O job de backup terminou sem artefato para download.",
            )
        self._gateway.download_to(
            result.download.download_id.root,
            self._command.path,
            progress=lambda current, total, message: self._emit_phase_progress(
                75,
                100,
                current,
                total,
                message,
            ),
            cancelled=self._cancellation.is_set,
        )
        return PortabilityResult(
            operation=PortabilityOperation.BACKUP,
            payload=dict(result.result or {}),
            destination=self._command.path,
        )

    def _restore_backup(self) -> PortabilityResult:
        preflight = self._gateway.preflight_backup_restore(
            self._command.path,
            idempotency_key=f"{self._execution_id}:restore-upload",
            progress=lambda current, total, message: self._emit_phase_progress(
                0,
                25,
                current,
                total,
                message,
            ),
            cancelled=self._cancellation.is_set,
        )
        if not self._confirm("restore_backup", preflight):
            raise PortabilityTransferCancelledError("Restauração cancelada antes da confirmação")
        self._ensure_not_cancelled()
        accepted = self._gateway.create_backup_restore_job(
            ConfirmBackupRestoreRequest(
                preflight_id=preflight.preflight_id,
                package_sha256=preflight.package_sha256,
                target_fingerprint=preflight.target_fingerprint,
                accept_degraded=(preflight.summary.integrity_state is IntegrityState.DEGRADED),
                confirmed=True,
            ),
            idempotency_key=f"{self._execution_id}:restore-job",
        )
        result = self._wait_for_job(accepted, phase_start=25, phase_end=100)
        return PortabilityResult(
            operation=PortabilityOperation.RESTORE,
            payload=dict(result.result or {}),
        )

    def _wait_for_job(
        self,
        accepted: JobAcceptedResponse,
        *,
        phase_start: int,
        phase_end: int,
    ) -> JobResultResponse:
        self._job_id = accepted.job_id.root
        cancellation_requested = False
        while True:
            if self._cancellation.is_set() and not cancellation_requested:
                self._gateway.cancel_job(self._job_id)
                cancellation_requested = True
            status = self._gateway.get_job(self._job_id)
            if self._cancellation.is_set() and not cancellation_requested:
                cancellation = self._gateway.cancel_job(self._job_id)
                cancellation_requested = True
                if cancellation.cancellation_requested:
                    status = self._gateway.get_job(self._job_id)
            self._emit_phase_progress(
                phase_start,
                phase_end,
                status.progress_percent,
                100,
                status.message or "Executando operação no servidor",
            )
            if status.status is JobStatus.SUCCEEDED:
                return self._gateway.get_job_result(self._job_id)
            if status.status is JobStatus.CANCELLED:
                raise PortabilityTransferCancelledError(
                    status.message or "Operação cancelada em ponto seguro"
                )
            if status.status is JobStatus.FAILED:
                if status.error is not None:
                    raise PortabilityGatewayError(
                        code=status.error.code,
                        message=status.error.message,
                        correlation_id=str(status.error.correlation_id.root),
                        details=dict(status.error.details or {}),
                    )
                raise PortabilityGatewayError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=status.message or "O job remoto falhou.",
                )
            if not self._cancellation.is_set():
                self._cancellation.wait(accepted.poll_after_ms / 1000)

    def _confirm(self, kind: str, payload: object) -> bool:
        if self._cancellation.is_set():
            return False
        with self._confirmation_lock:
            self._confirmation_response = None
        self._confirmation_ready.clear()
        self.confirmation_required.emit(self._execution_id, kind, payload)
        self._confirmation_ready.wait()
        with self._confirmation_lock:
            return self._confirmation_response is True and not self._cancellation.is_set()

    def _ensure_not_cancelled(self) -> None:
        if self._cancellation.is_set():
            raise PortabilityTransferCancelledError("Operação cancelada antes do envio ao servidor")

    def _emit_progress(self, current: int, total: int, message: str) -> None:
        self.progress.emit(self._execution_id, current, total, message)

    def _emit_phase_progress(
        self,
        phase_start: int,
        phase_end: int,
        current: int,
        total: int,
        message: str,
    ) -> None:
        safe_total = max(1, total)
        safe_current = min(max(0, current), safe_total)
        scaled = phase_start + round((phase_end - phase_start) * safe_current / safe_total)
        self._emit_progress(scaled, 100, message)


def project_import_confirmation(preflight: ProjectImportPreflightResponse) -> str:
    summary = preflight.summary
    return (
        "O servidor validou o pacote e detectou dados com o mesmo identificador.\n\n"
        f"Projeto: {summary.service_note}\n"
        f"ID: {str(summary.project_id.root)[:8]}\n"
        f"Conteúdo: {summary.document_count} PDF(s), {summary.page_count} página(s) e "
        f"{summary.photo_count} foto(s)\n"
        f"Fingerprint do destino: {preflight.target_fingerprint[:12]}\n\n"
        "Substituir o projeto remoto? O pacote e o destino serão revalidados pelo job."
    )


def backup_confirmation(preflight: BackupPreflightResponse) -> str:
    details = "\n".join(
        f"• Recurso {(item.resource_id or 'não identificado')[:8]} — {item.summary}"
        for item in preflight.issues
    )
    return (
        "O servidor classificou origens que não poderão ser copiadas:\n\n"
        f"{details}\n\nCriar o backup remoto degradado mesmo assim?"
    )


def restore_confirmation(preflight: BackupRestorePreflightResponse) -> str:
    summary = preflight.summary
    qualifier = (
        "degradado, com omissões declaradas"
        if summary.integrity_state is IntegrityState.DEGRADED
        else "íntegro"
    )
    return (
        f"O servidor validou um backup {qualifier} com {len(summary.project_ids)} projeto(s), "
        f"{summary.document_count} PDF(s) e {summary.photo_count} foto(s).\n\n"
        f"Fingerprint do destino: {preflight.target_fingerprint[:12]}\n\n"
        "Substituir o banco e os arquivos gerenciados do servidor? O estado será revalidado "
        "antes de qualquer troca."
    )
