from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from socket import create_server
from threading import Event, Thread
from time import monotonic
from uuid import UUID, uuid4

import pytest
from tests.integration.test_project_portability import (
    _compliance_registry,
    _persist_complete_project,
    _project_with_real_pdf,
    _service,
)
from uvicorn import Config, Server

from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.compliance import ExecucaoConformidade
from zeny_project_handler.domain.portability import EstadoIntegridadePacote
from zeny_project_handler_client.ui.portability_gateway import (
    HttpPortabilityGateway,
    PortabilityGatewayError,
)
from zeny_project_handler_client.ui.project_gateway import HttpProjectGateway
from zeny_project_handler_contracts.backup import ConfirmBackupRestoreRequest
from zeny_project_handler_contracts.enums import (
    IntegrityState,
    JobStatus,
    PreflightDisposition,
)
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.config import ServerSettings

pytestmark = pytest.mark.integration

PASSWORD = "senha exclusiva do ensaio de cutover"


def test_representative_backup_cutover_to_fresh_volume_preserves_auditable_state(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    legacy_root = tmp_path / "legacy-local-source"
    client_root = tmp_path / "cutover-client"
    client_root.mkdir()
    legacy_engine = create_sqlite_engine(legacy_root / "zeny-project-handler.sqlite3")
    upgrade_database(legacy_engine)
    project, pdf_source = _project_with_real_pdf(legacy_root, catalogo_inicial)
    _persist_complete_project(legacy_engine, catalogo_inicial, project, pdf_source)
    registry = _compliance_registry(legacy_root, legacy_engine)
    registry.inicializar(carregar_registro_conformidade_inicial())
    with SqlAlchemyUnitOfWork(legacy_engine) as work:
        semantic = work.execucoes_analise.listar_do_projeto(project.id)[0]
        active_rules = work.registros_conformidade.obter_ativa()
        assert active_rules is not None
        compliance = ExecucaoConformidade(
            id=uuid4(),
            projeto_id=project.id,
            execucoes_semanticas_ids=(semantic.id,),
            revisao_regras_id=active_rules.id,
            registro_regras_id=active_rules.registro.id,
            versao_regras=active_rules.registro.versao,
            assinatura_regras=active_rules.assinatura,
            assinatura_sessao="b" * 64,
            versao_metodo="stage10-cutover-fixture",
            executada_em=datetime(2026, 8, 20, 21, 30, tzinfo=UTC),
            alvos=(),
            fatos=(),
            achados=(),
            itens_documentais=(),
        )
        work.execucoes_conformidade.salvar(compliance)
        work.commit()
    source_state = _database_state(legacy_root / "zeny-project-handler.sqlite3")
    source_catalog_hash = sha256(registry.caminho_catalogo.read_bytes()).hexdigest()
    backup_service = _service(
        legacy_root,
        legacy_engine,
        compliance_registry=registry,
    )
    preflight = backup_service.preflight_backup()
    assert preflight.integro
    backup = backup_service.criar_backup(
        client_root / "cutover.zphbackup",
        relatorio_integridade=preflight,
    )
    assert backup.estado_integridade is EstadoIntegridadePacote.INTEGRO
    backup_hash = sha256(backup.caminho.read_bytes()).hexdigest()
    legacy_engine.dispose()

    shutil.rmtree(legacy_root)
    assert not legacy_root.exists()
    target_root = tmp_path / "new-server-volume"
    settings = ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=target_root,
    )
    with _running_server(settings) as base_url:
        transfers = HttpPortabilityGateway(base_url, PASSWORD)
        first_client = HttpProjectGateway(base_url, PASSWORD)
        second_client = HttpProjectGateway(base_url, PASSWORD)
        restore_preflight = transfers.preflight_backup_restore(
            backup.caminho,
            idempotency_key="stage10-cutover-preflight",
            progress=lambda *_args: None,
            cancelled=lambda: False,
        )
        assert restore_preflight.package_sha256 == backup_hash
        assert restore_preflight.disposition is PreflightDisposition.CONFIRMATION_REQUIRED
        accepted = transfers.create_backup_restore_job(
            ConfirmBackupRestoreRequest(
                preflight_id=restore_preflight.preflight_id,
                package_sha256=restore_preflight.package_sha256,
                target_fingerprint=restore_preflight.target_fingerprint,
                accept_degraded=False,
                confirmed=True,
            ),
            idempotency_key="stage10-cutover-confirm",
        )
        _wait_result(transfers, accepted.job_id.root)
        assert first_client.get_project(project.id).project.project_id.root == project.id
        assert second_client.get_project(project.id).project.project_id.root == project.id

    assert _database_state(target_root / "zeny-project-handler.sqlite3") == source_state
    target_engine = create_sqlite_engine(target_root / "zeny-project-handler.sqlite3")
    try:
        with SqlAlchemyUnitOfWork(target_engine) as work:
            assert work.projetos.obter(project.id) == project
            assert work.execucoes_conformidade.obter(compliance.id) == compliance
            restored_source = work.fontes_pdf.obter(project.documentos[0].id)
            restored_rules = work.registros_conformidade.obter_ativa()
        assert restored_source is not None
        assert restored_source.sha256 == pdf_source.sha256
        assert restored_source.caminho_canonico.is_relative_to(target_root)
        assert (
            sha256(restored_source.caminho_canonico.read_bytes()).hexdigest() == pdf_source.sha256
        )
        assert restored_rules is not None
        assert restored_rules.id == active_rules.id
        assert restored_rules.assinatura == active_rules.assinatura
    finally:
        target_engine.dispose()
    assert sha256((target_root / "catalogo-regras-conformidade.md").read_bytes()).hexdigest() == (
        source_catalog_hash
    )


def test_degraded_cutover_requires_confirmation_and_drops_legacy_windows_path(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    legacy_root = tmp_path / "degraded-legacy"
    client_root = tmp_path / "degraded-client"
    client_root.mkdir()
    engine = create_sqlite_engine(legacy_root / "zeny-project-handler.sqlite3")
    upgrade_database(engine)
    project, pdf_source = _project_with_real_pdf(legacy_root, catalogo_inicial)
    _persist_complete_project(engine, catalogo_inicial, project, pdf_source)
    registry = _compliance_registry(legacy_root, engine)
    registry.inicializar(carregar_registro_conformidade_inicial())
    service = _service(legacy_root, engine, compliance_registry=registry)
    legacy_path = pdf_source.caminho_canonico
    legacy_path.unlink()
    report = service.preflight_backup()
    assert not report.integro
    backup = service.criar_backup(
        client_root / "degraded-cutover.zphbackup",
        confirmar_degradado=True,
        relatorio_integridade=report,
    )
    engine.dispose()

    target_root = tmp_path / "degraded-target"
    with _running_server(
        ServerSettings(
            password=PASSWORD,
            market_sqlserver_connection_string="fixture-market-connection",
            data_directory=target_root,
        )
    ) as base_url:
        transfers = HttpPortabilityGateway(base_url, PASSWORD)
        prepared = transfers.preflight_backup_restore(
            backup.caminho,
            idempotency_key="stage10-degraded-preflight",
            progress=lambda *_args: None,
            cancelled=lambda: False,
        )
        assert prepared.summary.integrity_state is IntegrityState.DEGRADED
        rejected_request = ConfirmBackupRestoreRequest(
            preflight_id=prepared.preflight_id,
            package_sha256=prepared.package_sha256,
            target_fingerprint=prepared.target_fingerprint,
            accept_degraded=False,
            confirmed=True,
        )
        with pytest.raises(PortabilityGatewayError) as rejected:
            transfers.create_backup_restore_job(
                rejected_request,
                idempotency_key="stage10-degraded-rejected",
            )
        assert rejected.value.code is ErrorCode.OPERATION_CONFLICT
        accepted = transfers.create_backup_restore_job(
            rejected_request.model_copy(update={"accept_degraded": True}),
            idempotency_key="stage10-degraded-accepted",
        )
        _wait_result(transfers, accepted.job_id.root)

    target_engine = create_sqlite_engine(target_root / "zeny-project-handler.sqlite3")
    try:
        with SqlAlchemyUnitOfWork(target_engine) as work:
            restored_source = work.fontes_pdf.obter(project.documentos[0].id)
        assert restored_source is not None
        assert restored_source.caminho_canonico.is_relative_to(target_root / "project-files")
        assert restored_source.caminho_canonico != legacy_path
        assert not restored_source.caminho_canonico.exists()
    finally:
        target_engine.dispose()


def _database_state(database: Path) -> tuple[tuple[str, tuple[tuple[str, ...], ...]], ...]:
    excluded = {"api_idempotency_records", "api_jobs", "api_uploads", "sqlite_sequence"}
    state: list[tuple[str, tuple[tuple[str, ...], ...]]] = []
    with closing(sqlite3.connect(database)) as connection:
        tables = tuple(
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            if str(row[0]) not in excluded
        )
        for table in tables:
            columns = tuple(
                str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')
            )
            rows = []
            for row in connection.execute(f'SELECT * FROM "{table}"'):
                normalized = tuple(
                    "<managed-pdf-path>"
                    if table == "document_sources" and columns[index] == "canonical_path"
                    else repr(value)
                    for index, value in enumerate(row)
                )
                rows.append(normalized)
            state.append((table, tuple(sorted(rows))))
    return tuple(state)


def _wait_result(gateway: HttpPortabilityGateway, job_id: UUID):  # type: ignore[no-untyped-def]
    deadline = monotonic() + 30
    tick = Event()
    while monotonic() < deadline:
        status = gateway.get_job(job_id)
        if status.status is JobStatus.SUCCEEDED:
            return gateway.get_job_result(job_id)
        if status.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
            raise AssertionError(f"Job terminou em {status.status.value}: {status.error}")
        tick.wait(0.03)
    raise AssertionError("Job remoto não terminou no prazo")


@contextmanager
def _running_server(settings: ServerSettings) -> Iterator[str]:
    with closing(create_server(("127.0.0.1", 0))) as listener:
        port = int(listener.getsockname()[1])
        server = Server(Config(create_app(settings), log_level="critical", lifespan="on"))

        def serve() -> None:
            server.run(sockets=[listener])

        thread = Thread(target=serve, name=f"stage10-cutover-{uuid4().hex[:8]}", daemon=True)
        thread.start()
        tick = Event()
        deadline = monotonic() + 10
        while monotonic() < deadline and not server.started:
            if not thread.is_alive():
                break
            tick.wait(0.01)
        if not server.started:
            raise RuntimeError("Servidor do ensaio de cutover não iniciou")
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            assert not thread.is_alive()
