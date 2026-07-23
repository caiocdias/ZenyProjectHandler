"""Composição da aplicação desktop."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import cast

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from sqlalchemy import Engine

from zeny_project_handler.adapters.analysis import (
    JsonAnalysisCache,
    PyMuPdfDocumentAnalyzer,
    TesseractCliOcr,
)
from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
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
from zeny_project_handler.application.document_analysis import ExecutarAnaliseDocumento
from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler.application.interpretation_pipeline import ExecutarPipelineInterpretacao
from zeny_project_handler.application.mvp_workflow import ServicoFluxoMvp
from zeny_project_handler.application.pdf_import import ImportarPdfsNoProjeto
from zeny_project_handler.application.project_portability import ServicoPortabilidadeProjeto
from zeny_project_handler.config import AppSettings
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.logging_config import configure_logging
from zeny_project_handler.ui.main_window import MainWindow


def create_application(
    argv: Sequence[str] | None = None,
    *,
    settings: AppSettings | None = None,
) -> tuple[QApplication, MainWindow]:
    """Monte a aplicação sem iniciar o loop de eventos."""
    app_settings = settings or AppSettings.from_environment()
    configure_logging(app_settings)
    engine = initialize_local_storage(app_settings)

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

    registry = carregar_registro_regras_inicial()
    workflow_service = ServicoFluxoMvp(
        unit_of_work,
        catalogo_inicial_id=catalog.id,
        importador=ImportarPdfsNoProjeto(reader, unit_of_work),
        extrator=ExecutarAnaliseDocumento(
            PyMuPdfDocumentAnalyzer(
                cache=JsonAnalysisCache(app_settings.analysis_cache_directory),
                motor_ocr=TesseractCliOcr.descobrir(),
            ),
            unit_of_work,
        ),
        interpretador=ExecutarPipelineInterpretacao(
            InterpretadorRegrasExplicitas(registry),
            registry,
            unit_of_work,
        ),
    )
    window = MainWindow(
        application_name=app_settings.application_name,
        pdf_reader=reader,
        pdf_render_dpi=app_settings.pdf_render_dpi,
        review_service=ServicoRevisaoHumana(unit_of_work),
        workflow_service=workflow_service,
        portability_service=ServicoPortabilidadeProjeto(
            unit_of_work,
            ZipProjectArchive(),
            SqlitePortableProjectDatabase(),
            SqliteBackupManager(),
            diretorio_dados=app_settings.data_directory,
            caminho_banco=app_settings.database_path,
            descartar_conexoes=engine.dispose,
        ),
        ui_state_path=app_settings.data_directory / "ui-state.ini",
    )
    application.aboutToQuit.connect(engine.dispose)
    window.destroyed.connect(engine.dispose)
    return application, window


def initialize_local_storage(settings: AppSettings) -> Engine:
    """Crie a pasta local e migre o banco antes de expor a interface."""
    engine = create_sqlite_engine(settings.database_path)
    try:
        upgrade_database(engine)
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
        QTimer.singleShot(0, application.quit)
    return application.exec()
