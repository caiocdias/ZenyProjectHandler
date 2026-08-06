"""Execução Qt isolada das operações de portabilidade."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Event, Lock
from uuid import UUID

from PySide6.QtCore import QObject, Signal, Slot

from zeny_project_handler.application.errors import (
    ApplicationError,
    PortabilidadeCanceladaError,
)
from zeny_project_handler.application.project_portability import ServicoPortabilidadeProjeto
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.logging_config import operation_logger


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


class PortabilityWorker(QObject):
    """Execute serviços sem acessar widgets e identifique todos os sinais emitidos."""

    progress = Signal(str, int, int, str)
    confirmation_required = Signal(str, str, object)
    succeeded = Signal(str, object)
    failed = Signal(str, str, bool)
    finished = Signal(str)

    def __init__(
        self,
        service: ServicoPortabilidadeProjeto,
        command: PortabilityCommand,
        cancellation: Event,
        execution_id: str,
    ) -> None:
        super().__init__()
        self._service = service
        self._command = command
        self._cancellation = cancellation
        self._execution_id = execution_id
        self._confirmation_ready = Event()
        self._confirmation_lock = Lock()
        self._confirmation_response: bool | None = None

    def request_cancel(self) -> None:
        """Solicite cancelamento e libere uma eventual espera por confirmação da GUI."""
        self._cancellation.set()
        with self._confirmation_lock:
            if self._confirmation_response is None:
                self._confirmation_response = False
        self._confirmation_ready.set()

    def resolve_confirmation(self, accepted: bool) -> None:
        """Receba da thread principal a decisão de um diálogo solicitado por sinal."""
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
            except PortabilidadeCanceladaError as error:
                observation.cancelled(error_code=error.__class__.__name__)
                self.failed.emit(self._execution_id, str(error), True)
            except (ApplicationError, DomainValidationError, ValueError) as error:
                observation.failed(error, expected=True)
                self.failed.emit(
                    self._execution_id,
                    str(error).strip() or error.__class__.__name__,
                    False,
                )
            except Exception as error:  # Fronteira Qt: mensagem segura, traceback apenas no log.
                observation.failed(error, expected=False)
                self.failed.emit(
                    self._execution_id,
                    str(error).strip() or error.__class__.__name__,
                    False,
                )
            else:
                observation.succeeded()
                self.succeeded.emit(self._execution_id, result)
            finally:
                self.finished.emit(self._execution_id)

    def _execute(self) -> object:
        operation = self._command.operation
        if operation is PortabilityOperation.EXPORT:
            if self._command.project_id is None:
                raise ValueError("Projeto da exportação não foi informado")
            return self._service.exportar_projeto(
                self._command.project_id,
                self._command.path,
                progresso=self._emit_progress,
                cancelado=self._cancellation.is_set,
            )
        if operation is PortabilityOperation.IMPORT:
            return self._import_project()
        if operation is PortabilityOperation.BACKUP:
            return self._create_backup()
        if operation is PortabilityOperation.RESTORE:
            return self._service.restaurar_backup(
                self._command.path,
                progresso=self._emit_progress,
                cancelado=self._cancellation.is_set,
            )
        raise ValueError("Operação de portabilidade não suportada")

    def _import_project(self) -> object:
        try:
            return self._service.importar_projeto(
                self._command.path,
                progresso=self._emit_progress,
                cancelado=self._cancellation.is_set,
            )
        except Exception as error:
            if "confirme explicitamente" not in str(error):
                raise
        if not self._confirm("replace_project", None):
            raise PortabilidadeCanceladaError("Importação cancelada antes da substituição")
        return self._service.importar_projeto(
            self._command.path,
            substituir_existente=True,
            progresso=self._emit_progress,
            cancelado=self._cancellation.is_set,
        )

    def _create_backup(self) -> object:
        report = self._service.preflight_backup(cancelado=self._cancellation.is_set)
        confirmed_degraded = report.integro
        if not report.integro:
            confirmed_degraded = self._confirm("degraded_backup", report)
            if not confirmed_degraded:
                raise PortabilidadeCanceladaError(
                    "Backup cancelado antes da criação do pacote degradado"
                )
        return self._service.criar_backup(
            self._command.path,
            confirmar_degradado=confirmed_degraded,
            relatorio_integridade=report,
            progresso=self._emit_progress,
            cancelado=self._cancellation.is_set,
        )

    def _confirm(self, kind: str, payload: object) -> bool:
        if self._cancellation.is_set():
            return False
        self.confirmation_required.emit(self._execution_id, kind, payload)
        self._confirmation_ready.wait()
        with self._confirmation_lock:
            return self._confirmation_response is True and not self._cancellation.is_set()

    def _emit_progress(self, current: int, total: int, message: str) -> None:
        self.progress.emit(self._execution_id, current, total, message)
