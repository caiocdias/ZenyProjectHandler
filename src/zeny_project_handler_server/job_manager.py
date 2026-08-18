"""Execução remota, idempotente e cooperativamente cancelável de operações longas."""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from threading import Event, RLock
from typing import Protocol
from uuid import UUID, uuid5

from pydantic import JsonValue
from sqlalchemy import Engine

from zeny_project_handler.adapters.pdf.errors import PdfProtegidoError
from zeny_project_handler.application.errors import (
    AnaliseConformidadeCanceladaError,
    ApplicationError,
    FluxoMvpCanceladoError,
    OperacaoEmAndamentoError,
)
from zeny_project_handler.application.mvp_workflow import ResultadoFluxoMvp
from zeny_project_handler.application.operation_coordinator import (
    CoordenadorOperacoes,
    TipoOperacao,
    TokenOperacao,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.logging_config import operation_logger
from zeny_project_handler_contracts.base import CorrelationId, JobId, ProjectId
from zeny_project_handler_contracts.common import GlobalOperationDto
from zeny_project_handler_contracts.enums import JobKind, JobStatus
from zeny_project_handler_contracts.errors import ErrorCode, ErrorEnvelope
from zeny_project_handler_contracts.jobs import (
    CancelJobResponse,
    JobAcceptedResponse,
    JobResultResponse,
    JobStatusResponse,
)
from zeny_project_handler_server.api_errors import (
    ApiError,
    operation_conflict,
    resource_not_found,
)
from zeny_project_handler_server.job_store import JobRecord, JobStore
from zeny_project_handler_server.stage3_store import StageThreeStore

_RESOURCE_NAMESPACE = UUID("1b905224-e7dc-4b10-802f-a53ff7bf2356")
_POLL_AFTER_MS = 350


class AnalysisRunner(Protocol):
    def __call__(
        self,
        project_id: UUID,
        progress: Callable[[int, int, str], None],
        cancelled: Callable[[], bool],
    ) -> ResultadoFluxoMvp: ...


class ProjectVersionReader(Protocol):
    def require_project_version(self, project_id: UUID, expected_version: int) -> None: ...


class ComplianceRunner(Protocol):
    def __call__(self, project_id: UUID, cancellation: Event) -> UUID: ...


class SemanticSignatureReader(Protocol):
    def __call__(self, project_id: UUID) -> str: ...


class JobManager:
    """Mantenha um único executor e uma única reserva global por job ativo."""

    def __init__(
        self,
        *,
        engine: Engine,
        coordinator: CoordenadorOperacoes,
        project_versions: ProjectVersionReader,
        analysis_runner: AnalysisRunner,
        compliance_runner: ComplianceRunner | None = None,
        semantic_signature_reader: SemanticSignatureReader | None = None,
        retention_seconds: int,
        maximum_retained: int,
    ) -> None:
        self._coordinator = coordinator
        self._project_versions = project_versions
        self._analysis_runner = analysis_runner
        self._compliance_runner = compliance_runner
        self._semantic_signature_reader = semantic_signature_reader
        self._store = JobStore(
            engine,
            retention=timedelta(seconds=retention_seconds),
            maximum_retained=maximum_retained,
        )
        self._idempotency = StageThreeStore(engine)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zeny-job")
        self._lock = RLock()
        self._accepting = True
        self._active_job_id: UUID | None = None
        self._cancellations: dict[UUID, Event] = {}
        self._futures: dict[UUID, Future[None]] = {}
        self.interrupted_on_startup = self._store.reconcile_interrupted()
        self._store.prune()

    def create_analysis_job(
        self,
        project_id: UUID,
        *,
        expected_project_version: int,
        force_reanalysis: bool,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse:
        fingerprint = _fingerprint(
            "analysis-job",
            {
                "project_id": str(project_id),
                "expected_project_version": expected_project_version,
                "force_reanalysis": force_reanalysis,
            },
        )
        job_id = uuid5(_RESOURCE_NAMESPACE, f"{idempotency_key}:{fingerprint}")
        with self._idempotency.idempotency_guard(
            key=idempotency_key,
            operation="analysis-job",
            request_sha256=fingerprint,
            resource_id=job_id,
        ) as idempotency:
            if idempotency.response_json is not None:
                return JobAcceptedResponse.model_validate_json(idempotency.response_json)
            self._project_versions.require_project_version(
                project_id,
                expected_project_version,
            )
            response = JobAcceptedResponse(
                job_id=JobId(job_id),
                kind=JobKind.ANALYSIS,
                status=JobStatus.QUEUED,
                poll_after_ms=_POLL_AFTER_MS,
            )
            with self._lock:
                if not self._accepting:
                    self._idempotency.abandon_idempotency(idempotency)
                    raise operation_conflict("O servidor está encerrando e não aceita novos jobs.")
                try:
                    token = self._coordinator.adquirir(TipoOperacao.ANALISE)
                except OperacaoEmAndamentoError as error:
                    self._idempotency.abandon_idempotency(idempotency)
                    raise operation_conflict(str(error)) from error
                cancellation = Event()
                try:
                    self._store.create(job_id, project_id, JobKind.ANALYSIS)
                    self._idempotency.complete_idempotency(
                        idempotency,
                        response.model_dump_json(),
                    )
                    self._active_job_id = job_id
                    self._cancellations[job_id] = cancellation
                    future = self._executor.submit(
                        self._run_analysis,
                        job_id,
                        project_id,
                        cancellation,
                        token,
                        correlation_id,
                    )
                    self._futures[job_id] = future
                except BaseException:
                    self._active_job_id = None
                    self._cancellations.pop(job_id, None)
                    token.liberar()
                    self._idempotency.abandon_idempotency(idempotency)
                    raise
        return response

    def create_compliance_job(
        self,
        project_id: UUID,
        *,
        expected_semantic_signature: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse:
        runner = self._compliance_runner
        signature_reader = self._semantic_signature_reader
        if runner is None or signature_reader is None:
            raise operation_conflict("A análise de conformidade não está disponível.")
        current_signature = signature_reader(project_id)
        if current_signature != expected_semantic_signature:
            raise ApiError(
                409,
                ErrorCode.STALE_STATE,
                "A sessão semântica mudou; recarregue o projeto antes de analisar.",
            )
        fingerprint = _fingerprint(
            "compliance-job",
            {
                "project_id": str(project_id),
                "expected_semantic_signature": expected_semantic_signature,
            },
        )
        job_id = uuid5(_RESOURCE_NAMESPACE, f"{idempotency_key}:{fingerprint}")
        with self._idempotency.idempotency_guard(
            key=idempotency_key,
            operation="compliance-job",
            request_sha256=fingerprint,
            resource_id=job_id,
        ) as idempotency:
            if idempotency.response_json is not None:
                return JobAcceptedResponse.model_validate_json(idempotency.response_json)
            response = JobAcceptedResponse(
                job_id=JobId(job_id),
                kind=JobKind.COMPLIANCE,
                status=JobStatus.QUEUED,
                poll_after_ms=_POLL_AFTER_MS,
            )
            with self._lock:
                if not self._accepting:
                    self._idempotency.abandon_idempotency(idempotency)
                    raise operation_conflict("O servidor está encerrando e não aceita novos jobs.")
                try:
                    token = self._coordinator.adquirir(TipoOperacao.CONFORMIDADE)
                except OperacaoEmAndamentoError as error:
                    self._idempotency.abandon_idempotency(idempotency)
                    raise operation_conflict(str(error)) from error
                cancellation = Event()
                try:
                    self._store.create(job_id, project_id, JobKind.COMPLIANCE)
                    self._idempotency.complete_idempotency(
                        idempotency,
                        response.model_dump_json(),
                    )
                    self._active_job_id = job_id
                    self._cancellations[job_id] = cancellation
                    future = self._executor.submit(
                        self._run_compliance,
                        job_id,
                        project_id,
                        cancellation,
                        token,
                        correlation_id,
                    )
                    self._futures[job_id] = future
                except BaseException:
                    self._active_job_id = None
                    self._cancellations.pop(job_id, None)
                    token.liberar()
                    self._idempotency.abandon_idempotency(idempotency)
                    raise
        return response

    def get_job(self, job_id: UUID) -> JobStatusResponse:
        return _status_response(self._required(job_id))

    def get_result(self, job_id: UUID) -> JobResultResponse:
        record = self._required(job_id)
        result: dict[str, JsonValue] | None = None
        if record.result_json is not None:
            decoded = json.loads(record.result_json)
            if not isinstance(decoded, dict):
                raise ApiError(
                    409,
                    ErrorCode.INTEGRITY_ERROR,
                    "O resultado persistido do job é inválido.",
                )
            result = decoded
        return JobResultResponse(
            job_id=JobId(job_id),
            status=record.status,
            result=result,
        )

    def cancel(self, job_id: UUID) -> CancelJobResponse:
        record = self._required(job_id)
        if record.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
            return CancelJobResponse(
                job_id=JobId(job_id),
                status=record.status,
                cancellation_requested=False,
            )
        with self._lock:
            cancellation = self._cancellations.get(job_id)
            if cancellation is None:
                raise operation_conflict(
                    "O job não pertence ao processo atual e não pode mais ser cancelado."
                )
            cancellation.set()
            updated = self._store.update_progress(
                job_id,
                status=JobStatus.CANCELLING,
                progress_percent=record.progress_percent,
                message="Cancelamento solicitado; aguardando um ponto seguro.",
            )
        return CancelJobResponse(
            job_id=JobId(job_id),
            status=updated.status,
            cancellation_requested=True,
        )

    def global_operation(self) -> GlobalOperationDto | None:
        with self._lock:
            job_id = self._active_job_id
        if job_id is None:
            return None
        record = self._store.get(job_id)
        if record is None:
            return None
        return GlobalOperationDto(
            job_id=JobId(record.job_id),
            kind=record.kind,
            status=record.status,
            progress_percent=record.progress_percent,
            message=record.message,
            updated_at=record.updated_at,
        )

    def stop_accepting(self) -> None:
        with self._lock:
            self._accepting = False

    def cancel_and_wait(self) -> None:
        with self._lock:
            active = tuple(self._cancellations.items())
        for job_id, cancellation in active:
            cancellation.set()
            record = self._store.get(job_id)
            if record is not None:
                self._store.update_progress(
                    job_id,
                    status=JobStatus.CANCELLING,
                    progress_percent=record.progress_percent,
                    message="Servidor encerrando; cancelamento solicitado.",
                )
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _run_analysis(
        self,
        job_id: UUID,
        project_id: UUID,
        cancellation: Event,
        token: TokenOperacao,
        correlation_id: str,
    ) -> None:
        observation = operation_logger(
            "server.job.analysis",
            correlation_id=correlation_id,
            project_id=project_id,
            job_id=job_id,
        )
        with observation.context():
            observation.started()
            try:
                self._store.update_progress(
                    job_id,
                    status=JobStatus.RUNNING,
                    progress_percent=0,
                    message="Preparando a análise do projeto.",
                )
                result = self._analysis_runner(
                    project_id,
                    lambda current, total, message: self._report_progress(
                        job_id,
                        cancellation,
                        current,
                        total,
                        message,
                    ),
                    cancellation.is_set,
                )
                if cancellation.is_set():
                    raise FluxoMvpCanceladoError(
                        "Análise cancelada em um ponto seguro; use Retomar análise para continuar"
                    )
            except FluxoMvpCanceladoError as error:
                self._store.finish(
                    job_id,
                    status=JobStatus.CANCELLED,
                    message=str(error),
                )
                observation.cancelled(error_code=type(error).__name__)
            except Exception as error:
                envelope, expected = _safe_job_error(error, correlation_id)
                self._store.finish(
                    job_id,
                    status=JobStatus.FAILED,
                    message=envelope.message,
                    error_json=envelope.model_dump_json(),
                )
                observation.failed(error, expected=expected)
            else:
                self._store.finish(
                    job_id,
                    status=JobStatus.SUCCEEDED,
                    message="Análise concluída.",
                    result_json=json.dumps(_result_payload(result), separators=(",", ":")),
                )
                observation.succeeded()
            finally:
                token.liberar()
                with self._lock:
                    self._cancellations.pop(job_id, None)
                    self._futures.pop(job_id, None)
                    if self._active_job_id == job_id:
                        self._active_job_id = None
                self._store.prune()

    def _run_compliance(
        self,
        job_id: UUID,
        project_id: UUID,
        cancellation: Event,
        token: TokenOperacao,
        correlation_id: str,
    ) -> None:
        runner = self._compliance_runner
        if runner is None:
            token.liberar()
            return
        observation = operation_logger(
            "server.job.compliance",
            correlation_id=correlation_id,
            project_id=project_id,
            job_id=job_id,
        )
        with observation.context():
            observation.started()
            try:
                self._store.update_progress(
                    job_id,
                    status=JobStatus.RUNNING,
                    progress_percent=10,
                    message="Reaplicando as regras à sessão semântica persistida.",
                )
                execution_id = runner(project_id, cancellation)
                if cancellation.is_set():
                    raise AnaliseConformidadeCanceladaError(
                        "Análise de conformidade cancelada sem publicar resultado parcial"
                    )
            except AnaliseConformidadeCanceladaError as error:
                self._store.finish(
                    job_id,
                    status=JobStatus.CANCELLED,
                    message=str(error),
                )
                observation.cancelled(error_code=type(error).__name__)
            except Exception as error:
                envelope, expected = _safe_job_error(error, correlation_id)
                self._store.finish(
                    job_id,
                    status=JobStatus.FAILED,
                    message=envelope.message,
                    error_json=envelope.model_dump_json(),
                )
                observation.failed(error, expected=expected)
            else:
                self._store.finish(
                    job_id,
                    status=JobStatus.SUCCEEDED,
                    message="Análise de conformidade concluída.",
                    result_json=json.dumps(
                        {
                            "project_id": str(project_id),
                            "compliance_execution_id": str(execution_id),
                        },
                        separators=(",", ":"),
                    ),
                )
                observation.succeeded()
            finally:
                token.liberar()
                with self._lock:
                    self._cancellations.pop(job_id, None)
                    self._futures.pop(job_id, None)
                    if self._active_job_id == job_id:
                        self._active_job_id = None
                self._store.prune()

    def _report_progress(
        self,
        job_id: UUID,
        cancellation: Event,
        current: int,
        total: int,
        message: str,
    ) -> None:
        percent = 0 if total <= 0 else round(current * 100 / total)
        status = JobStatus.CANCELLING if cancellation.is_set() else JobStatus.RUNNING
        self._store.update_progress(
            job_id,
            status=status,
            progress_percent=percent,
            message=message,
        )

    def _required(self, job_id: UUID) -> JobRecord:
        record = self._store.get(job_id)
        if record is None:
            raise resource_not_found("Job não encontrado.")
        return record


def _status_response(record: JobRecord) -> JobStatusResponse:
    error = (
        ErrorEnvelope.model_validate_json(record.error_json)
        if record.error_json is not None
        else None
    )
    return JobStatusResponse(
        job_id=JobId(record.job_id),
        project_id=ProjectId(record.project_id) if record.project_id is not None else None,
        kind=record.kind,
        status=record.status,
        progress_percent=record.progress_percent,
        message=record.message,
        result_available=record.result_json is not None,
        created_at=record.created_at,
        updated_at=record.updated_at,
        error=error,
    )


def _safe_job_error(error: Exception, correlation_id: str) -> tuple[ErrorEnvelope, bool]:
    expected = isinstance(
        error,
        (ApplicationError, DomainValidationError, PdfProtegidoError, ValueError),
    )
    if isinstance(error, PdfProtegidoError):
        code = ErrorCode.PDF_PASSWORD_REQUIRED
        message = "Um PDF protegido precisa ser desbloqueado antes da análise."
    elif expected:
        code = ErrorCode.VALIDATION_ERROR
        message = str(error).strip() or "A análise não pôde ser concluída."
    else:
        code = ErrorCode.INTERNAL_ERROR
        message = "O servidor não conseguiu concluir a análise."
    return (
        ErrorEnvelope(
            code=code,
            message=message,
            correlation_id=CorrelationId(UUID(correlation_id)),
        ),
        expected,
    )


def _result_payload(result: ResultadoFluxoMvp) -> dict[str, JsonValue]:
    return {
        "project_id": str(result.projeto_id),
        "interpretation_execution_ids": [str(item) for item in result.execucoes_interpretacao],
        "compliance_execution_id": str(result.execucao_conformidade_id),
        "proposals_generated": result.propostas_geradas,
        "documents_processed": result.documentos_processados,
    }


def _fingerprint(operation: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(
        {"operation": operation, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
