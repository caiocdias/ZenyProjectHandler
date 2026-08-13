"""Composição da aplicação desktop."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import cast
from uuid import UUID

from PySide6.QtWidgets import QApplication
from sqlalchemy import Engine

from zeny_project_handler.adapters.analysis import (
    JsonAnalysisCache,
    PyMuPdfDocumentAnalyzer,
    TesseractCliOcr,
)
from zeny_project_handler.adapters.analysis.tesseract_runtime import (
    RuntimeTesseract,
    inspect_tesseract_runtime,
)
from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    SqliteBackupManager,
    SqlitePortableProjectDatabase,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.adapters.portability import ZipProjectArchive
from zeny_project_handler.application.compliance_analysis import ExecutarAnaliseConformidade
from zeny_project_handler.application.compliance_registry import (
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.document_analysis import ExecutarAnaliseDocumento
from zeny_project_handler.application.errors import ApplicationError
from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler.application.import_recovery import RecuperadorImportacaoProjeto
from zeny_project_handler.application.interpretation_pipeline import ExecutarPipelineInterpretacao
from zeny_project_handler.application.managed_files import GerenciadorArquivosGerenciados
from zeny_project_handler.application.mvp_workflow import ServicoFluxoMvp
from zeny_project_handler.application.operation_coordinator import CoordenadorOperacoes
from zeny_project_handler.application.pdf_credentials import ProvedorCredenciaisPdfMemoria
from zeny_project_handler.application.pdf_import import ImportarPdfsNoProjeto
from zeny_project_handler.application.project_compliance import prover_fatos_regionais
from zeny_project_handler.application.project_portability import ServicoPortabilidadeProjeto
from zeny_project_handler.application.span_compliance import prover_fatos_vaos
from zeny_project_handler.config import AppSettings
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.logging_config import (
    configure_logging,
    install_unhandled_exception_logging,
    operation_logger,
)
from zeny_project_handler.ports.pdf import OrcamentoRenderizacaoPdf
from zeny_project_handler.ports.persistence import ComprovanteCommitImportacao
from zeny_project_handler.ui.main_window import MainWindow


class _EngineLifetime:
    """Descarte idempotente compartilhado pelas saídas normais do Qt."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._disposed = False

    def dispose(self, *_signal_arguments: object) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._engine.dispose()


def create_application(
    argv: Sequence[str] | None = None,
    *,
    settings: AppSettings | None = None,
) -> tuple[QApplication, MainWindow]:
    """Monte a aplicação sem iniciar o loop de eventos."""
    app_settings = settings or AppSettings.from_environment()
    logger = configure_logging(app_settings)
    install_unhandled_exception_logging()
    observation = operation_logger("application.bootstrap", logger=logger)
    with observation.context():
        observation.started()
        try:
            application, window = _compose_application(argv, app_settings)
        except (ApplicationError, ValueError) as error:
            observation.failed(error, expected=True)
            raise
        except Exception as error:
            observation.failed(error, expected=False)
            raise
        observation.succeeded()
        return application, window


def _compose_application(
    argv: Sequence[str] | None,
    app_settings: AppSettings,
) -> tuple[QApplication, MainWindow]:
    engine = initialize_local_storage(app_settings)
    lifetime = _EngineLifetime(engine)
    try:
        return _compose_initialized_application(argv, app_settings, engine, lifetime)
    except BaseException:
        lifetime.dispose()
        raise


def _compose_initialized_application(
    argv: Sequence[str] | None,
    app_settings: AppSettings,
    engine: Engine,
    lifetime: _EngineLifetime,
) -> tuple[QApplication, MainWindow]:

    arguments = list(argv) if argv is not None else list(sys.argv)
    existing_application = QApplication.instance()
    if existing_application is None:
        application = QApplication(arguments)
    else:
        application = cast(QApplication, existing_application)

    application.setApplicationName(app_settings.application_name)
    application.setOrganizationName(app_settings.organization_name)

    catalog = _ensure_initial_catalog(engine)
    reader = PyMuPdfReader()

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    compliance_service = ServicoRegistroRegrasConformidade(
        unit_of_work,
        diretorio_dados=app_settings.data_directory,
    )

    def list_projects() -> tuple[Projeto, ...]:
        with unit_of_work() as work:
            return work.projetos.listar()

    registry = carregar_registro_regras_inicial()
    operation_coordinator = CoordenadorOperacoes()
    review_service = ServicoRevisaoHumana(unit_of_work)
    compliance_analysis_service = ExecutarAnaliseConformidade(
        unit_of_work,
        review_service.carregar_sessao_semantica,
        provedores_fatos=(prover_fatos_regionais, prover_fatos_vaos),
    )
    ocr_runtime = inspect_tesseract_runtime(app_settings.data_directory)
    managed_files = GerenciadorArquivosGerenciados(
        app_settings.data_directory,
        list_projects,
    )
    pdf_credentials = ProvedorCredenciaisPdfMemoria()
    workflow_service = ServicoFluxoMvp(
        unit_of_work,
        catalogo_inicial_id=catalog.id,
        importador=ImportarPdfsNoProjeto(
            reader,
            unit_of_work,
            coordenador=operation_coordinator,
        ),
        extrator=ExecutarAnaliseDocumento(
            PyMuPdfDocumentAnalyzer(
                cache=JsonAnalysisCache(app_settings.analysis_cache_directory),
                motor_ocr=_ocr_engine(ocr_runtime),
            ),
            unit_of_work,
        ),
        interpretador=ExecutarPipelineInterpretacao(
            InterpretadorRegrasExplicitas(registry),
            registry,
            unit_of_work,
        ),
        analisador_conformidade=compliance_analysis_service,
        gerenciador_arquivos=managed_files,
        coordenador=operation_coordinator,
    )
    window = MainWindow(
        application_name=app_settings.application_name,
        pdf_reader=reader,
        pdf_render_dpi=app_settings.pdf_render_dpi,
        pdf_render_budget=OrcamentoRenderizacaoPdf(
            limite_pixels=app_settings.pdf_render_max_pixels,
            limite_bytes=app_settings.pdf_render_max_bytes,
        ),
        pdf_tile_cache_max_bytes=app_settings.pdf_tile_cache_max_bytes,
        provedor_credenciais_pdf=pdf_credentials,
        review_service=review_service,
        workflow_service=workflow_service,
        portability_service=ServicoPortabilidadeProjeto(
            unit_of_work,
            ZipProjectArchive(),
            SqlitePortableProjectDatabase(),
            SqliteBackupManager(),
            diretorio_dados=app_settings.data_directory,
            caminho_banco=app_settings.database_path,
            gerenciador_arquivos=managed_files,
            coordenador=operation_coordinator,
            descartar_conexoes=engine.dispose,
        ),
        operation_coordinator=operation_coordinator,
        compliance_registry_service=compliance_service,
        compliance_analysis_service=compliance_analysis_service,
        ui_state_path=app_settings.data_directory / "ui-state.ini",
        startup_ocr_diagnostic=(
            ocr_runtime.diagnostico.texto_ui if ocr_runtime.diagnostico is not None else None
        ),
    )
    window.set_resource_cleanup(lifetime.dispose)
    application.aboutToQuit.connect(lifetime.dispose)
    window.destroyed.connect(lifetime.dispose)
    return application, window


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


def initialize_local_storage(settings: AppSettings) -> Engine:
    """Migre e reconcilie o estado local antes de expor qualquer operação."""
    engine = create_sqlite_engine(settings.database_path)
    try:
        upgrade_database(engine)
        compliance_service = ServicoRegistroRegrasConformidade(
            lambda: SqlAlchemyUnitOfWork(engine),
            diretorio_dados=settings.data_directory,
        )
        compliance_service.inicializar(carregar_registro_conformidade_inicial())
        recovery = RecuperadorImportacaoProjeto(settings.data_directory)

        def obter_comprovante(operation_id: UUID) -> ComprovanteCommitImportacao | None:
            with SqlAlchemyUnitOfWork(engine) as work:
                return work.comprovantes_importacao.obter(operation_id)

        recovery.reconciliar(obter_comprovante)

        def listar_projetos() -> tuple[Projeto, ...]:
            with SqlAlchemyUnitOfWork(engine) as work:
                return work.projetos.listar()

        GerenciadorArquivosGerenciados(
            settings.data_directory,
            listar_projetos,
        ).reconciliar_pendencias()
    except Exception:
        engine.dispose()
        raise
    return engine


def _ensure_initial_catalog(engine: Engine) -> CatalogoTecnico:
    catalog = carregar_catalogo_inicial()
    with SqlAlchemyUnitOfWork(engine) as work:
        if work.catalogos.obter(catalog.id) is None:
            work.catalogos.salvar(catalog)
            work.commit()
    return catalog


def run(
    argv: Sequence[str] | None = None,
    *,
    settings: AppSettings | None = None,
) -> int:
    """Inicie o loop de eventos da aplicação."""
    arguments = list(argv) if argv is not None else list(sys.argv)
    smoke_test = "--smoke-test" in arguments
    qt_arguments = [argument for argument in arguments if argument != "--smoke-test"]
    application, window = create_application(qt_arguments, settings=settings)
    window.show()
    if smoke_test:
        try:
            application.processEvents()
            return 0
        finally:
            window.close()
    try:
        return application.exec()
    finally:
        window.close()
