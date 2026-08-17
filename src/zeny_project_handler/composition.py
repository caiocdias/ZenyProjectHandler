"""Composição do núcleo da aplicação sem dependências de interface."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.compliance_registry import (
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.import_recovery import RecuperadorImportacaoProjeto
from zeny_project_handler.application.managed_files import GerenciadorArquivosGerenciados
from zeny_project_handler.application.operation_coordinator import CoordenadorOperacoes
from zeny_project_handler.config import AppSettings
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.persistence import ComprovanteCommitImportacao


@dataclass(frozen=True, slots=True)
class CoreServices:
    """Recursos compartilhados pelos processos desktop e servidor."""

    engine: Engine
    catalog: CatalogoTecnico
    operation_coordinator: CoordenadorOperacoes

    def close(self) -> None:
        """Libere as conexões persistentes pertencentes à composição."""
        self.engine.dispose()


def compose_core_services(settings: AppSettings) -> CoreServices:
    """Inicialize a fonte persistente e os serviços de coordenação sem carregar Qt."""
    engine = initialize_local_storage(settings)
    try:
        catalog = ensure_initial_catalog(engine)
    except BaseException:
        engine.dispose()
        raise
    return CoreServices(
        engine=engine,
        catalog=catalog,
        operation_coordinator=CoordenadorOperacoes(),
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


def ensure_initial_catalog(engine: Engine) -> CatalogoTecnico:
    """Garanta que o catálogo técnico distribuído exista na fonte persistente."""
    catalog = carregar_catalogo_inicial()
    with SqlAlchemyUnitOfWork(engine) as work:
        if work.catalogos.obter(catalog.id) is None:
            work.catalogos.salvar(catalog)
            work.commit()
    return catalog
