"""Composição e lifecycle dos recursos pertencentes ao processo servidor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Protocol
from uuid import UUID

from zeny_project_handler.adapters.analysis import (
    JsonAnalysisCache,
    PyMuPdfDocumentAnalyzer,
    TesseractCliOcr,
)
from zeny_project_handler.adapters.analysis.tesseract_runtime import (
    RuntimeTesseract,
    inspect_tesseract_runtime,
)
from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.market.sql_server import (
    ClassificadorMercadoSqlServer,
    VerificadorAcoesConcluidasSqlServer,
)
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import SqlAlchemyUnitOfWork
from zeny_project_handler.application.compliance_analysis import ExecutarAnaliseConformidade
from zeny_project_handler.application.document_analysis import ExecutarAnaliseDocumento
from zeny_project_handler.application.document_compliance import prover_fatos_documentais
from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler.application.interpretation_pipeline import ExecutarPipelineInterpretacao
from zeny_project_handler.application.managed_files import GerenciadorArquivosGerenciados
from zeny_project_handler.application.mvp_workflow import ResultadoFluxoMvp, ServicoFluxoMvp
from zeny_project_handler.application.pdf_import import ImportarPdfsNoProjeto
from zeny_project_handler.application.project_compliance import prover_fatos_regionais
from zeny_project_handler.application.span_compliance import prover_fatos_vaos
from zeny_project_handler.application.topology_compliance import prover_fatos_topologicos
from zeny_project_handler.composition import CoreServices, compose_core_services
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.market import (
    ClassificadorMercadoPort,
    VerificadorAcoesConcluidasPort,
)
from zeny_project_handler_contracts import (
    API_VERSION,
    MAX_COMPATIBLE_API_VERSION,
    MIN_COMPATIBLE_API_VERSION,
)
from zeny_project_handler_contracts.backup import (
    ConfirmBackupRestoreRequest,
    CreateBackupJobRequest,
)
from zeny_project_handler_contracts.common import GlobalOperationDto
from zeny_project_handler_contracts.enums import OcrStatus
from zeny_project_handler_contracts.jobs import (
    CancelJobResponse,
    CreateExportJobRequest,
    JobAcceptedResponse,
    JobResultResponse,
    JobStatusResponse,
)
from zeny_project_handler_contracts.portability import ConfirmProjectImportRequest
from zeny_project_handler_contracts.session import (
    OcrDiagnosticDto,
    SessionCapabilitiesResponse,
)
from zeny_project_handler_server.compliance_api import DocumentationComplianceApiService
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.deliverable_exports import DeliverableExportService
from zeny_project_handler_server.job_manager import JobManager
from zeny_project_handler_server.portability_api import PortabilityApiService
from zeny_project_handler_server.project_api import ProjectApiService
from zeny_project_handler_server.review_api import ReviewApiService
from zeny_project_handler_server.transfer_storage import ManagedTransferStorage
from zeny_project_handler_server.viewer_api import ViewerApiService
from zeny_project_handler_server.volume_lifecycle import prepare_server_volume

SERVER_CAPABILITIES = (
    "authenticated-session",
    "persistent-storage",
    "tesseract-ocr",
    "managed-projects",
    "managed-document-uploads",
    "managed-photos",
    "remote-pdf-viewer",
    "temporary-viewer-sessions",
    "remote-analysis-jobs",
    "global-operation-observability",
    "remote-human-review",
    "review-audit-projections",
    "remote-documentation-compliance",
    "remote-rule-registry",
    "server-compiled-compliance-callouts",
    "remote-project-portability",
    "remote-backup-restore",
    "managed-transfer-downloads",
    "server-generated-deliverable-exports",
    "managed-volume-v1",
)


class JobLifecycle(Protocol):
    """Fronteira do gerenciador de jobs pertencente ao worker único."""

    def stop_accepting(self) -> None: ...

    def cancel_and_wait(self) -> None: ...

    def create_analysis_job(
        self,
        project_id: UUID,
        *,
        expected_project_version: int,
        force_reanalysis: bool,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse: ...

    def create_compliance_job(
        self,
        project_id: UUID,
        *,
        expected_semantic_signature: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse: ...

    def create_project_export_job(
        self,
        project_id: UUID,
        request: CreateExportJobRequest,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse: ...

    def create_project_import_job(
        self,
        request: ConfirmProjectImportRequest,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse: ...

    def create_backup_job(
        self,
        request: CreateBackupJobRequest,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse: ...

    def create_backup_restore_job(
        self,
        request: ConfirmBackupRestoreRequest,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse: ...

    def get_job(self, job_id: UUID) -> JobStatusResponse: ...

    def get_result(self, job_id: UUID) -> JobResultResponse: ...

    def cancel(self, job_id: UUID) -> CancelJobResponse: ...

    def global_operation(self) -> GlobalOperationDto | None: ...


class _IdleJobLifecycle:
    def stop_accepting(self) -> None:
        pass

    def cancel_and_wait(self) -> None:
        pass

    def create_analysis_job(self, *_args: object, **_kwargs: object) -> JobAcceptedResponse:
        raise RuntimeError("O gerenciador de jobs não está disponível")

    def create_compliance_job(self, *_args: object, **_kwargs: object) -> JobAcceptedResponse:
        raise RuntimeError("O gerenciador de jobs não está disponível")

    def create_project_export_job(self, *_args: object, **_kwargs: object) -> JobAcceptedResponse:
        raise RuntimeError("O gerenciador de jobs não está disponível")

    def create_project_import_job(self, *_args: object, **_kwargs: object) -> JobAcceptedResponse:
        raise RuntimeError("O gerenciador de jobs não está disponível")

    def create_backup_job(self, *_args: object, **_kwargs: object) -> JobAcceptedResponse:
        raise RuntimeError("O gerenciador de jobs não está disponível")

    def create_backup_restore_job(self, *_args: object, **_kwargs: object) -> JobAcceptedResponse:
        raise RuntimeError("O gerenciador de jobs não está disponível")

    def get_job(self, _job_id: UUID) -> JobStatusResponse:
        raise RuntimeError("O gerenciador de jobs não está disponível")

    def get_result(self, _job_id: UUID) -> JobResultResponse:
        raise RuntimeError("O gerenciador de jobs não está disponível")

    def cancel(self, _job_id: UUID) -> CancelJobResponse:
        raise RuntimeError("O gerenciador de jobs não está disponível")

    def global_operation(self) -> GlobalOperationDto | None:
        return None


class ServerRuntimeProtocol(Protocol):
    """Superfície usada pela camada HTTP durante startup e shutdown."""

    def session_capabilities(self) -> SessionCapabilitiesResponse: ...

    @property
    def project_api(self) -> ProjectApiService | None: ...

    @property
    def viewer_api(self) -> ViewerApiService | None: ...

    @property
    def review_api(self) -> ReviewApiService | None: ...

    @property
    def compliance_api(self) -> DocumentationComplianceApiService | None: ...

    @property
    def portability_api(self) -> PortabilityApiService | None: ...

    @property
    def jobs(self) -> JobLifecycle: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class ServerRuntime:
    """Recursos vivos do worker único e encerramento ordenado e idempotente."""

    core: CoreServices
    ocr: RuntimeTesseract
    jobs: JobLifecycle
    project_api: ProjectApiService | None = None
    viewer_api: ViewerApiService | None = None
    review_api: ReviewApiService | None = None
    compliance_api: DocumentationComplianceApiService | None = None
    portability_api: PortabilityApiService | None = None
    _closed: bool = False

    def session_capabilities(self) -> SessionCapabilitiesResponse:
        """Exponha somente diagnóstico seguro, nunca caminhos ou configuração sensível."""
        if self._closed:
            raise RuntimeError("O runtime do servidor já foi encerrado")
        return SessionCapabilitiesResponse(
            server_version=_server_version(),
            api_version=API_VERSION,
            min_compatible_api_version=MIN_COMPATIBLE_API_VERSION,
            max_compatible_api_version=MAX_COMPATIBLE_API_VERSION,
            ready=True,
            capabilities=SERVER_CAPABILITIES,
            ocr=_ocr_diagnostic(self.ocr),
            global_operation=self.jobs.global_operation(),
            server_time=datetime.now(UTC),
        )

    def close(self) -> None:
        """Pare novos jobs, aguarde cancelamento e só então descarte o engine."""
        if self._closed:
            return
        self._closed = True
        try:
            self.jobs.stop_accepting()
            self.jobs.cancel_and_wait()
        finally:
            try:
                try:
                    if self.viewer_api is not None:
                        self.viewer_api.close()
                finally:
                    if self.project_api is not None:
                        self.project_api.close()
            finally:
                self.core.close()


RuntimeFactory = Callable[[ServerSettings], ServerRuntimeProtocol]


def compose_server_runtime(
    settings: ServerSettings,
    *,
    market_classifier: ClassificadorMercadoPort | None = None,
    action_verifier: VerificadorAcoesConcluidasPort | None = None,
) -> ServerRuntime:
    """Inicialize fonte persistente, coordenação e OCR sem importar o bootstrap Qt."""
    core_settings = settings.core_settings()
    prepare_server_volume(settings.data_directory, core_settings.database_path)
    core = compose_core_services(core_settings, database_prepared=True)
    try:
        ocr = inspect_tesseract_runtime(settings.data_directory)
    except BaseException:
        core.close()
        raise
    try:
        project_api = ProjectApiService(
            engine=core.engine,
            catalog_id=core.catalog.id,
            data_directory=settings.data_directory,
            database_path=settings.core_settings().database_path,
            coordinator=core.operation_coordinator,
            upload_max_bytes=settings.upload_max_bytes,
        )
    except BaseException:
        core.close()
        raise
    try:
        viewer_api = ViewerApiService(
            engine=core.engine,
            data_directory=settings.data_directory,
            upload_max_bytes=settings.upload_max_bytes,
            render_dpi=settings.render_dpi,
            render_max_pixels=settings.render_max_pixels,
            render_max_bytes=settings.render_max_bytes,
            session_ttl_seconds=settings.viewer_session_ttl_seconds,
            maximum_files=settings.viewer_max_files,
            credentials=project_api.pdf_credentials,
        )
    except BaseException:
        project_api.close()
        core.close()
        raise
    try:

        def unit_of_work() -> SqlAlchemyUnitOfWork:
            return SqlAlchemyUnitOfWork(core.engine)

        selected_market_classifier = (
            market_classifier
            if market_classifier is not None
            else ClassificadorMercadoSqlServer(
                settings.market_sqlserver_connection_string,
                timeout_seconds=settings.market_sqlserver_timeout_seconds,
            )
        )
        selected_action_verifier = (
            action_verifier
            if action_verifier is not None
            else VerificadorAcoesConcluidasSqlServer(
                settings.market_sqlserver_connection_string,
                timeout_seconds=settings.market_sqlserver_timeout_seconds,
            )
        )
        review = ServicoRevisaoHumana(unit_of_work)
        compliance = ExecutarAnaliseConformidade(
            unit_of_work,
            review.carregar_sessao_semantica,
            classificador_mercado=selected_market_classifier,
            verificador_acoes=selected_action_verifier,
            provedores_fatos=(
                prover_fatos_documentais,
                prover_fatos_regionais,
                prover_fatos_vaos,
                prover_fatos_topologicos,
            ),
        )
        workflow = _compose_analysis_workflow(
            core,
            settings,
            ocr,
            compliance,
        )
        review_api = ReviewApiService(core.engine)
        compliance_api = DocumentationComplianceApiService(
            engine=core.engine,
            data_directory=settings.data_directory,
            review_api=review_api,
            upload_max_bytes=settings.upload_max_bytes,
            review_service=review,
            analysis_service=compliance,
        )
        transfer_storage = ManagedTransferStorage(
            settings.data_directory,
            maximum_bytes=settings.upload_max_bytes,
            ttl_seconds=settings.transfer_ttl_seconds,
        )
        deliverable_exports = DeliverableExportService(
            engine=core.engine,
            projects=project_api,
            review=review_api,
            compliance=compliance_api,
            storage=transfer_storage,
        )
        portability_api = PortabilityApiService(
            project_api=project_api,
            transfer_storage=transfer_storage,
            deliverable_exports=deliverable_exports,
        )

        def run_analysis(
            project_id: UUID,
            progress: Callable[[int, int, str], None],
            cancelled: Callable[[], bool],
        ) -> ResultadoFluxoMvp:
            passwords = project_api.analysis_passwords(project_id)
            try:
                return workflow.executar_pipeline_ja_coordenado(
                    project_id,
                    progresso=progress,
                    cancelado=cancelled,
                    senhas_documentos=passwords,
                )
            finally:
                passwords.clear()

        jobs = JobManager(
            engine=core.engine,
            coordinator=core.operation_coordinator,
            project_versions=project_api,
            analysis_runner=run_analysis,
            compliance_runner=compliance_api.execute_compliance,
            semantic_signature_reader=compliance_api.semantic_signature,
            portability=portability_api,
            retention_seconds=settings.job_retention_seconds,
            maximum_retained=settings.job_max_retained,
        )
    except BaseException:
        viewer_api.close()
        project_api.close()
        core.close()
        raise
    return ServerRuntime(
        core=core,
        ocr=ocr,
        jobs=jobs,
        project_api=project_api,
        viewer_api=viewer_api,
        review_api=review_api,
        compliance_api=compliance_api,
        portability_api=portability_api,
    )


def _compose_analysis_workflow(
    core: CoreServices,
    settings: ServerSettings,
    ocr: RuntimeTesseract,
    compliance: ExecutarAnaliseConformidade,
) -> ServicoFluxoMvp:
    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(core.engine)

    def list_projects() -> tuple[Projeto, ...]:
        with unit_of_work() as work:
            return work.projetos.listar()

    reader = PyMuPdfReader()
    managed_files = GerenciadorArquivosGerenciados(settings.data_directory, list_projects)
    registry = carregar_registro_regras_inicial()
    return ServicoFluxoMvp(
        unit_of_work,
        catalogo_inicial_id=core.catalog.id,
        importador=ImportarPdfsNoProjeto(
            reader,
            unit_of_work,
            coordenador=core.operation_coordinator,
        ),
        extrator=ExecutarAnaliseDocumento(
            PyMuPdfDocumentAnalyzer(
                cache=JsonAnalysisCache(settings.core_settings().analysis_cache_directory),
                motor_ocr=_ocr_engine(ocr),
            ),
            unit_of_work,
        ),
        interpretador=ExecutarPipelineInterpretacao(
            InterpretadorRegrasExplicitas(registry),
            registry,
            unit_of_work,
        ),
        analisador_conformidade=compliance,
        gerenciador_arquivos=managed_files,
        coordenador=core.operation_coordinator,
    )


def _ocr_engine(runtime: RuntimeTesseract) -> TesseractCliOcr | None:
    if not runtime.portugues_pronto:
        return None
    executable = runtime.executavel
    tessdata_directory = runtime.diretorio_tessdata
    if executable is None or tessdata_directory is None:
        return None
    return TesseractCliOcr(
        executable,
        language="+".join(runtime.idiomas_selecionados),
        tessdata_directory=tessdata_directory,
    )


def _server_version() -> str:
    try:
        return version("zeny-project-handler-server")
    except PackageNotFoundError:
        return "0.3.0"


def _ocr_diagnostic(runtime: RuntimeTesseract) -> OcrDiagnosticDto:
    if runtime.portugues_pronto:
        return OcrDiagnosticDto(
            status=OcrStatus.AVAILABLE,
            engine="tesseract",
            language="+".join(runtime.idiomas_selecionados),
            message="OCR Tesseract em português disponível.",
        )
    diagnostic = runtime.diagnostico
    status = OcrStatus.UNAVAILABLE if runtime.executavel is None else OcrStatus.DEGRADED
    return OcrDiagnosticDto(
        status=status,
        engine="tesseract" if runtime.executavel is not None else None,
        language=("+".join(runtime.idiomas_selecionados) or None),
        message=(
            diagnostic.mensagem
            if diagnostic is not None
            else "OCR Tesseract em português indisponível."
        ),
    )
