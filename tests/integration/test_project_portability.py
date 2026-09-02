from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, inspect
from tests.factories import complete_analysis, complete_project
from tests.pdf_fixtures import create_golden_pdf

from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    SqliteBackupManager,
    SqlitePortableProjectDatabase,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.adapters.persistence.errors import PersistenceError
from zeny_project_handler.adapters.portability import ZipProjectArchive
from zeny_project_handler.application.compliance_registry import (
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.errors import (
    OperacaoEmAndamentoError,
    PlanoImportacaoObsoletoError,
    PortabilidadeProjetoError,
)
from zeny_project_handler.application.import_recovery import (
    ArmazenamentoJournalImportacao,
    PontoFalhaImportacao,
    RecuperadorImportacaoProjeto,
)
from zeny_project_handler.application.operation_coordinator import (
    CoordenadorOperacoes,
    TipoOperacao,
)
from zeny_project_handler.application.project_portability import ServicoPortabilidadeProjeto
from zeny_project_handler.composition import initialize_local_storage
from zeny_project_handler.config import AppSettings
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.compliance import (
    RegistroRegrasConformidade,
    RegraConformidade,
)
from zeny_project_handler.domain.portability import EstadoIntegridadePacote
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler.ports.persistence import ComprovanteCommitImportacao

pytestmark = pytest.mark.integration


class _SimulatedProcessCrash(BaseException):
    pass


@dataclass(frozen=True, slots=True)
class _ImportStateSnapshot:
    database: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...]
    filesystem: tuple[tuple[str, str, str], ...]


def _project_with_real_pdf(
    tmp_path: Path, catalog: CatalogoTecnico
) -> tuple[Projeto, ReferenciaFontePdf]:
    path = create_golden_pdf(tmp_path / "source.pdf")
    inspection = PyMuPdfReader().inspecionar(path)
    page_id = inspection.documento.paginas[0].id
    base = complete_project(catalog)
    elements = tuple(
        replace(
            element,
            geometria=(
                replace(element.geometria, pagina_id=page_id)
                if element.geometria is not None
                else None
            ),
            fotos=(),
        )
        for element in base.elementos
    )
    points = tuple(
        replace(
            point,
            geometria=(
                replace(point.geometria, pagina_id=page_id) if point.geometria is not None else None
            ),
        )
        for point in base.pontos_rede
    )
    project = replace(
        base,
        documentos=(inspection.documento,),
        ordem_leitura_paginas=tuple(page.id for page in inspection.documento.paginas),
        elementos=elements,
        pontos_rede=points,
    )
    source = ReferenciaFontePdf(
        documento_id=inspection.documento.id,
        projeto_id=project.id,
        caminho_canonico=path.resolve(),
        sha256=inspection.documento.sha256,
        tamanho_bytes=inspection.tamanho_bytes,
        modificado_em_ns=inspection.modificado_em_ns,
    )
    return project, source


def _service(
    data: Path,
    engine: Engine,
    dispose_connections: Callable[[], None] | None = None,
    coordinator: CoordenadorOperacoes | None = None,
    inject_import_failure: Callable[[PontoFalhaImportacao], None] | None = None,
    compliance_registry: ServicoRegistroRegrasConformidade | None = None,
) -> ServicoPortabilidadeProjeto:
    return ServicoPortabilidadeProjeto(
        lambda: SqlAlchemyUnitOfWork(engine),
        ZipProjectArchive(),
        SqlitePortableProjectDatabase(),
        SqliteBackupManager(),
        diretorio_dados=data,
        caminho_banco=data / "zeny-project-handler.sqlite3",
        coordenador=coordinator,
        descartar_conexoes=dispose_connections or engine.dispose,
        injetar_falha_importacao=inject_import_failure,
        registro_conformidade=compliance_registry,
    )


def _compliance_registry(
    data: Path,
    engine: Engine,
) -> ServicoRegistroRegrasConformidade:
    return ServicoRegistroRegrasConformidade(
        lambda: SqlAlchemyUnitOfWork(engine),
        diretorio_dados=data,
    )


def _registry_after_backup() -> tuple[
    RegistroRegrasConformidade,
    RegistroRegrasConformidade,
    RegraConformidade,
    RegraConformidade,
    RegraConformidade,
]:
    seed = carregar_registro_conformidade_inicial()
    restored_rule = seed.regras[0]
    changed_rule = replace(restored_rule, titulo="Conteúdo posterior ao backup")
    custom_rule = replace(
        restored_rule,
        id="fixture.restauracao.regra-preservada",
        titulo="Regra local preservada",
    )
    current = replace(
        seed,
        versao="estado-posterior-ao-backup",
        regras=(changed_rule, *seed.regras[1:], custom_rule),
    )
    return seed, current, restored_rule, changed_rule, custom_rule


def _legacy_bundled_registry(
    seed: RegistroRegrasConformidade,
) -> RegistroRegrasConformidade:
    span_rule = next(item for item in seed.regras if item.id == "nd31.vao.urbano-compacto-isolado")
    legacy_span = replace(
        span_rule,
        aplicabilidade=tuple(
            condition
            for condition in span_rule.aplicabilidade
            if condition.chave_fato != "vao.aplicabilidade_excecao_45_60_resolvida"
        ),
    )
    return replace(
        seed,
        versao="cemig-normas-distribuicao-2025.3",
        regras=tuple(
            legacy_span if item.id == legacy_span.id else item for item in seed.regras[:8]
        ),
    )


def _create_png(path: Path) -> Path:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"portable-photo")
    return path


def _persist_complete_project(
    engine: Engine,
    catalog: CatalogoTecnico,
    project: Projeto,
    source: ReferenciaFontePdf,
) -> None:
    execution, evidence, proposal, relation, decision = complete_analysis(project)
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalog)
        work.projetos.salvar(project)
        work.fontes_pdf.salvar(source)
        work.execucoes_analise.salvar(execution)
        work.evidencias.salvar(evidence)
        work.propostas.salvar(proposal)
        work.propostas.salvar(relation)
        work.decisoes_revisao.salvar(decision)
        work.commit()


def _snapshot_import_state(data: Path, engine: Engine) -> _ImportStateSnapshot:
    database: list[tuple[str, tuple[tuple[str, ...], ...]]] = []
    inspector = inspect(engine)
    with engine.connect() as connection:
        for table in sorted(inspector.get_table_names()):
            rows = connection.exec_driver_sql(f'SELECT * FROM "{table}"').all()
            normalized = tuple(sorted(tuple(repr(value) for value in row) for row in rows))
            database.append((table, normalized))
    filesystem: list[tuple[str, str, str]] = []
    if data.is_dir():
        for path in sorted(data.rglob("*"), key=lambda item: item.relative_to(data).as_posix()):
            relative = path.relative_to(data).as_posix()
            if relative.split("/", 1)[0].startswith("zeny-project-handler.sqlite3"):
                continue
            if path.is_dir():
                filesystem.append((relative, "directory", ""))
            elif path.is_file():
                content = path.read_bytes()
                filesystem.append((relative, "file", sha256(content).hexdigest()))
            else:
                filesystem.append((relative, "other", ""))
    return _ImportStateSnapshot(database=tuple(database), filesystem=tuple(filesystem))


def _assert_no_import_residue(data: Path) -> None:
    assert not tuple(data.rglob(".z-*"))
    assert not tuple(data.rglob("*.previous"))
    recovery_root = data / "project-files" / ".import-recovery"
    assert not recovery_root.exists() or not tuple(recovery_root.iterdir())


def _create_import_package(
    tmp_path: Path,
    catalog: CatalogoTecnico,
) -> tuple[Path, Projeto, ReferenciaFontePdf]:
    source_data = tmp_path / "package-source"
    source_engine = create_sqlite_engine(source_data / "zeny-project-handler.sqlite3")
    try:
        upgrade_database(source_engine)
        project, pdf_source = _project_with_real_pdf(tmp_path, catalog)
        project = replace(project, nome="Projeto validado do pacote")
        _persist_complete_project(source_engine, catalog, project, pdf_source)
        service = _service(source_data, source_engine)
        attached = service.anexar_foto(
            project.id,
            project.elementos[0].id,
            _create_png(tmp_path / "package-photo.png"),
            legenda="Foto preservada",
        )
        exported = service.exportar_projeto(project.id, tmp_path / "validated.zphproj")
        return exported.caminho, attached.projeto, pdf_source
    finally:
        source_engine.dispose()


def _persist_conflicting_target(
    data: Path,
    engine: Engine,
    catalog: CatalogoTecnico,
    packaged_project: Projeto,
    pdf_source: ReferenciaFontePdf,
) -> Projeto:
    local = replace(packaged_project, nome="Versão local anterior")
    _persist_complete_project(engine, catalog, local, pdf_source)
    root = data / "project-files" / str(local.id)
    root.mkdir(parents=True)
    (root / "local-only.bin").write_bytes(b"estado-local-anterior")
    return local


def test_import_new_project_preflight_is_pure_and_applies_validated_plan(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    package, packaged_project, _pdf_source = _create_import_package(tmp_path, catalogo_inicial)
    data = tmp_path / "new-target"
    engine = create_sqlite_engine(data / "zeny-project-handler.sqlite3")
    try:
        upgrade_database(engine)
        service = _service(data, engine)
        before = _snapshot_import_state(data, engine)

        plan = service.preflight_importacao(package)

        assert _snapshot_import_state(data, engine) == before
        assert plan.resumo.projeto_id == packaged_project.id
        assert plan.resumo.nome == packaged_project.nome
        assert plan.resumo.quantidade_documentos == 1
        assert plan.resumo.quantidade_fotos == 1
        assert len(plan.pacote_sha256) == 64
        assert len(plan.estado_alvo_sha256) == 64
        assert len(plan.fingerprint) == 64
        assert not plan.requer_confirmacao
        _assert_no_import_residue(data)

        result = service.aplicar_plano_importacao(plan)

        after = _snapshot_import_state(data, engine)
        assert after != before
        assert result.projeto == packaged_project
        assert not result.substituiu_existente
        assert service.verificar_integridade(packaged_project.id).integro
        _assert_no_import_residue(data)
    finally:
        engine.dispose()


def test_import_conflict_refused_preserves_database_files_and_has_no_residue(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    package, packaged_project, pdf_source = _create_import_package(tmp_path, catalogo_inicial)
    data = tmp_path / "refused-target"
    engine = create_sqlite_engine(data / "zeny-project-handler.sqlite3")
    try:
        upgrade_database(engine)
        service = _service(data, engine)
        local = _persist_conflicting_target(
            data, engine, catalogo_inicial, packaged_project, pdf_source
        )
        before = _snapshot_import_state(data, engine)

        plan = service.preflight_importacao(package)

        assert plan.projeto_existente
        assert plan.pasta_destino_existente
        assert plan.requer_confirmacao
        assert _snapshot_import_state(data, engine) == before
        with pytest.raises(PortabilidadeProjetoError, match="confirme explicitamente"):
            service.aplicar_plano_importacao(plan)

        assert _snapshot_import_state(data, engine) == before
        with SqlAlchemyUnitOfWork(engine) as work:
            assert work.projetos.obter(local.id) == local
        _assert_no_import_residue(data)
    finally:
        engine.dispose()


def test_import_conflict_accepted_replaces_database_and_files_preserving_ids(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    package, packaged_project, pdf_source = _create_import_package(tmp_path, catalogo_inicial)
    data = tmp_path / "accepted-target"
    engine = create_sqlite_engine(data / "zeny-project-handler.sqlite3")
    try:
        upgrade_database(engine)
        service = _service(data, engine)
        _persist_conflicting_target(data, engine, catalogo_inicial, packaged_project, pdf_source)
        before = _snapshot_import_state(data, engine)

        plan = service.preflight_importacao(package)

        assert _snapshot_import_state(data, engine) == before
        result = service.aplicar_plano_importacao(plan, confirmar_substituicao=True)

        after = _snapshot_import_state(data, engine)
        assert after != before
        assert result.substituiu_existente
        assert result.projeto == packaged_project
        assert {item.id for item in result.projeto.documentos} == {
            item.id for item in packaged_project.documentos
        }
        assert {item.id for item in result.projeto.elementos} == {
            item.id for item in packaged_project.elementos
        }
        root = data / "project-files" / str(packaged_project.id)
        assert not (root / "local-only.bin").exists()
        assert service.verificar_integridade(packaged_project.id).integro
        _assert_no_import_residue(data)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("failure_point", "commit_expected"),
    (
        (PontoFalhaImportacao.ANTES_PREPARAR, False),
        (PontoFalhaImportacao.DEPOIS_PREPARAR, False),
        (PontoFalhaImportacao.ANTES_TROCAR_ARQUIVOS, False),
        (PontoFalhaImportacao.DEPOIS_MOVER_ANTERIOR, False),
        (PontoFalhaImportacao.DEPOIS_TROCAR_ARQUIVOS, False),
        (PontoFalhaImportacao.ANTES_COMMIT_BANCO, False),
        (PontoFalhaImportacao.DEPOIS_COMMIT_BANCO, True),
        (PontoFalhaImportacao.DEPOIS_CONFIRMAR_BANCO, True),
        (PontoFalhaImportacao.ANTES_LIMPEZA, True),
        (PontoFalhaImportacao.DEPOIS_LIMPEZA, True),
    ),
)
def test_bootstrap_reconciles_each_import_crash_boundary_idempotently(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    failure_point: PontoFalhaImportacao,
    commit_expected: bool,
    app_log_capture: pytest.LogCaptureFixture,
) -> None:
    package, packaged_project, pdf_source = _create_import_package(tmp_path, catalogo_inicial)
    data = tmp_path / "crash-target"
    engine = create_sqlite_engine(data / "zeny-project-handler.sqlite3")
    upgrade_database(engine)
    local_project = _persist_conflicting_target(
        data,
        engine,
        catalogo_inicial,
        packaged_project,
        pdf_source,
    )

    def interrupt(selected: PontoFalhaImportacao) -> None:
        if selected is failure_point:
            raise _SimulatedProcessCrash(selected.value)

    service = _service(data, engine, inject_import_failure=interrupt)
    plan = service.preflight_importacao(package)
    with pytest.raises(_SimulatedProcessCrash, match=failure_point.value):
        service.aplicar_plano_importacao(plan, confirmar_substituicao=True)
    engine.dispose()

    recovered_engine = initialize_local_storage(AppSettings(data_directory=data))
    try:
        with SqlAlchemyUnitOfWork(recovered_engine) as work:
            recovered_project = work.projetos.obter(packaged_project.id)
        assert recovered_project is not None
        assert recovered_project.nome == (
            packaged_project.nome if commit_expected else local_project.nome
        )
        project_root = data / "project-files" / str(packaged_project.id)
        assert (project_root / "local-only.bin").exists() is not commit_expected
        assert any(project_root.rglob("*.pdf")) is commit_expected
        _assert_no_import_residue(data)

        before_repeat = _snapshot_import_state(data, recovered_engine)
        recovery = RecuperadorImportacaoProjeto(data)

        def get_receipt(operation_id: UUID) -> ComprovanteCommitImportacao | None:
            with SqlAlchemyUnitOfWork(recovered_engine) as work:
                return work.comprovantes_importacao.obter(operation_id)

        assert recovery.reconciliar(get_receipt) is None
        assert _snapshot_import_state(data, recovered_engine) == before_repeat
    finally:
        recovered_engine.dispose()

    recovery_records = [
        record
        for record in app_log_capture.records
        if getattr(record, "operation", None) == "portability.import.recovery"
    ]
    assert recovery_records
    assert all(getattr(record, "phase", None) for record in recovery_records)
    assert str(data) not in app_log_capture.text


def test_bootstrap_blocks_corrupted_journal_and_releases_database(
    tmp_path: Path,
) -> None:
    data = tmp_path / "blocked-bootstrap"
    store = ArmazenamentoJournalImportacao(data)
    store.recovery_root.mkdir(parents=True)
    store.journal_path.write_text("{corrompido", encoding="utf-8")
    settings = AppSettings(data_directory=data)

    with pytest.raises(PortabilidadeProjetoError, match="corrompido"):
        initialize_local_storage(settings)

    moved_database = data / "closed.sqlite3"
    settings.database_path.replace(moved_database)
    moved_database.unlink()
    assert store.journal_path.exists()


@pytest.mark.parametrize("changed_state", ["target", "package"])
def test_import_rejects_race_between_preflight_and_application_without_mutation(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    changed_state: str,
) -> None:
    package, packaged_project, pdf_source = _create_import_package(tmp_path, catalogo_inicial)
    data = tmp_path / f"stale-{changed_state}-target"
    engine = create_sqlite_engine(data / "zeny-project-handler.sqlite3")
    try:
        upgrade_database(engine)
        service = _service(data, engine)
        local = _persist_conflicting_target(
            data, engine, catalogo_inicial, packaged_project, pdf_source
        )
        plan = service.preflight_importacao(package)
        if changed_state == "target":
            with SqlAlchemyUnitOfWork(engine) as work:
                work.projetos.salvar(replace(local, nome="Alterado durante a corrida"))
                work.commit()
            root = data / "project-files" / str(local.id)
            (root / "race.bin").write_bytes(b"mudanca-concorrente")
        else:
            package.write_bytes(package.read_bytes() + b"pacote-alterado")
        raced = _snapshot_import_state(data, engine)

        with pytest.raises(PlanoImportacaoObsoletoError, match="após o preflight"):
            service.aplicar_plano_importacao(plan, confirmar_substituicao=True)

        assert _snapshot_import_state(data, engine) == raced
        _assert_no_import_residue(data)
    finally:
        engine.dispose()


def test_export_import_preserves_ids_decisions_and_repairs_missing_photo(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    app_log_capture: pytest.LogCaptureFixture,
) -> None:
    source_data = tmp_path / "source-data"
    source_engine = create_sqlite_engine(source_data / "zeny-project-handler.sqlite3")
    upgrade_database(source_engine)
    project, pdf_source = _project_with_real_pdf(tmp_path, catalogo_inicial)
    project = replace(project, codigos_servico=("9012", "0007"))
    _persist_complete_project(source_engine, catalogo_inicial, project, pdf_source)
    source_service = _service(source_data, source_engine)
    photo_path = _create_png(tmp_path / "photo.png")
    element_id = project.elementos[0].id

    attached = source_service.anexar_foto(project.id, element_id, photo_path, legenda="Poste")
    duplicated = source_service.anexar_foto(project.id, element_id, photo_path)
    assert attached.foto is not None
    assert duplicated.deduplicada
    assert source_service.verificar_integridade(project.id).integro
    expected_project = attached.projeto
    exported = source_service.exportar_projeto(project.id, tmp_path / "project.zphproj")
    assert all(
        item.caminho_relativo != "derived/graph.json" for item in exported.manifesto.arquivos
    )
    moved_package = tmp_path / "moved" / exported.caminho.name
    moved_package.parent.mkdir()
    exported.caminho.replace(moved_package)

    target_data = tmp_path / "target-data"
    target_engine = create_sqlite_engine(target_data / "zeny-project-handler.sqlite3")
    upgrade_database(target_engine)
    target_service = _service(target_data, target_engine)
    imported = target_service.importar_projeto(moved_package)

    managed_root = target_data / "project-files" / str(project.id)
    assets_before_failure = {
        path.relative_to(managed_root): path.read_bytes()
        for path in managed_root.rglob("*")
        if path.is_file()
    }

    def interrupt_staging_publication(point: PontoFalhaImportacao) -> None:
        if point is PontoFalhaImportacao.DEPOIS_MOVER_ANTERIOR:
            raise OSError("interrupted")

    interrupted_service = _service(
        target_data,
        target_engine,
        inject_import_failure=interrupt_staging_publication,
    )
    with pytest.raises(PortabilidadeProjetoError, match="publicar os arquivos"):
        interrupted_service.importar_projeto(moved_package, substituir_existente=True)

    assert {
        path.relative_to(managed_root): path.read_bytes()
        for path in managed_root.rglob("*")
        if path.is_file()
    } == assets_before_failure
    assert not tuple(target_data.glob(".z-*"))

    assert imported.projeto == expected_project
    assert imported.projeto.codigos_servico == ("0007", "9012")
    assert imported.projeto.catalogo_versao_id == catalogo_inicial.id
    assert target_service.verificar_integridade(project.id).integro
    with SqlAlchemyUnitOfWork(target_engine) as work:
        executions = work.execucoes_analise.listar_do_projeto(project.id)
        proposals = work.propostas.listar_da_execucao(executions[0].id)
        decisions = tuple(work.decisoes_revisao.obter_da_proposta(item.id) for item in proposals)
        imported_catalog = work.catalogos.obter(catalogo_inicial.id)
    assert imported_catalog == catalogo_inicial
    assert any(item is not None for item in decisions)

    photo = imported.projeto.elementos[0].fotos[0]
    managed_photo = target_data / "project-files" / str(project.id) / photo.caminho_relativo
    managed_photo.unlink()
    report = target_service.verificar_integridade(project.id)
    assert {item.codigo for item in report.problemas} == {"FOTO_AUSENTE"}
    repaired = target_service.localizar_foto(project.id, element_id, photo.id, photo_path)
    assert repaired.foto is not None
    assert target_service.verificar_integridade(project.id).integro
    removed_photo = target_service.remover_foto(project.id, element_id, photo.id)
    assert removed_photo.arquivos_gerenciados_removidos == 1
    assert not removed_photo.limpeza_pendente
    assert not managed_photo.exists()
    assert target_service.verificar_integridade(project.id).integro

    with SqlAlchemyUnitOfWork(target_engine) as work:
        imported_source = work.fontes_pdf.obter(project.documentos[0].id)
    assert imported_source is not None
    imported_source.caminho_canonico.unlink()
    assert {item.codigo for item in target_service.verificar_integridade(project.id).problemas} == {
        "PDF_AUSENTE"
    }
    degraded_export = target_service.exportar_projeto(
        project.id, tmp_path / "project-with-omission.zphproj"
    )
    assert degraded_export.estado_integridade is EstadoIntegridadePacote.DEGRADADO
    assert [item.codigo for item in degraded_export.manifesto.omissoes] == ["PDF_AUSENTE"]
    assert degraded_export.integridade_origem.problemas[0].referencia_id == project.documentos[0].id
    target_service.localizar_pdf(
        project.id,
        project.documentos[0].id,
        pdf_source.caminho_canonico,
    )
    assert target_service.verificar_integridade(project.id).integro

    source_engine.dispose()
    target_engine.dispose()
    assert not tuple(source_data.glob(".z-*"))
    assert not tuple(target_data.glob(".z-*"))
    import_failures = [
        record
        for record in app_log_capture.records
        if getattr(record, "operation", None) == "portability.import"
        and getattr(record, "status", None) == "failed"
    ]
    unexpected = [record for record in import_failures if record.levelno == logging.ERROR]
    assert unexpected
    assert all(record.exc_info is not None for record in unexpected)


def test_full_backup_restores_database_and_managed_files(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    app_log_capture: pytest.LogCaptureFixture,
) -> None:
    data = tmp_path / "data"
    engine = create_sqlite_engine(data / "zeny-project-handler.sqlite3")
    upgrade_database(engine)
    project, pdf_source = _project_with_real_pdf(tmp_path, catalogo_inicial)
    _persist_complete_project(engine, catalogo_inicial, project, pdf_source)
    registry_service = _compliance_registry(data, engine)
    seed, current_registry, restored_rule, changed_rule, custom_rule = _registry_after_backup()
    registry_service.inicializar(seed)
    dispose_calls = 0

    def dispose_connections() -> None:
        nonlocal dispose_calls
        dispose_calls += 1
        engine.dispose()

    service = _service(
        data,
        engine,
        dispose_connections,
        compliance_registry=registry_service,
    )
    photo_path = _create_png(tmp_path / "backup-photo.png")
    attached = service.anexar_foto(project.id, project.elementos[0].id, photo_path)
    backup = service.criar_backup(tmp_path / "backup.zphbackup")
    assert backup.estado_integridade is EstadoIntegridadePacote.INTEGRO
    assert backup.manifesto.versao_formato == 2

    current_revision = registry_service.importar(
        registry_service.preparar_importacao(current_registry)
    )
    ids_before_restore = {item.id for item in current_revision.registro.regras}
    numbers_before_restore = {
        item.regra_id: item.numero for item in registry_service.listar_numeros()
    }
    assert (
        next(item for item in current_revision.registro.regras if item.id == changed_rule.id)
        == changed_rule
    )

    with SqlAlchemyUnitOfWork(engine) as work:
        work.projetos.salvar(replace(attached.projeto, nome="Estado posterior"))
        work.commit()
    managed_photo = (
        data
        / "project-files"
        / str(project.id)
        / attached.projeto.elementos[0].fotos[0].caminho_relativo
    )
    managed_photo.unlink()
    pdf_source.caminho_canonico.unlink()

    restored_backup = service.restaurar_backup(backup.caminho)
    assert restored_backup.estado_integridade is EstadoIntegridadePacote.INTEGRO

    with SqlAlchemyUnitOfWork(engine) as work:
        restored = work.projetos.obter(project.id)
    assert restored == attached.projeto
    assert managed_photo.is_file()
    assert service.verificar_integridade(project.id).integro
    with SqlAlchemyUnitOfWork(engine) as work:
        restored_source = work.fontes_pdf.obter(project.documentos[0].id)
    assert restored_source is not None
    assert restored_source.caminho_canonico.is_file()
    assert restored_source.caminho_canonico.is_relative_to(data / "project-files")
    reconciled = registry_service.obter_revisao_ativa()
    reconciled_by_id = {item.id: item for item in reconciled.registro.regras}
    assert reconciled.id != current_revision.id
    assert ids_before_restore <= set(reconciled_by_id)
    assert reconciled_by_id[restored_rule.id] == restored_rule
    assert reconciled_by_id[custom_rule.id] == custom_rule
    assert set(reconciled_by_id) == {
        *(item.id for item in seed.regras),
        custom_rule.id,
    }
    numbers_after_restore = {
        item.regra_id: item.numero for item in registry_service.listar_numeros()
    }
    assert numbers_after_restore[custom_rule.id] == numbers_before_restore[custom_rule.id]
    catalog = registry_service.caminho_catalogo.read_text(encoding="utf-8")
    assert custom_rule.titulo in catalog
    assert restored_rule.titulo in catalog
    assert changed_rule.titulo not in catalog
    assert dispose_calls == 1
    engine.dispose()
    assert not tuple(data.glob(".z-*"))

    for operation in ("portability.backup", "portability.restore"):
        records = [
            record
            for record in app_log_capture.records
            if getattr(record, "operation", None) == operation
        ]
        assert [getattr(record, "status", None) for record in records] == [
            "started",
            "succeeded",
        ]
        assert all(record.levelno == logging.INFO for record in records)
        assert len({getattr(record, "correlation_id", None) for record in records}) == 1


def test_restore_immediately_migrates_the_unchanged_legacy_bundled_span_rule(
    tmp_path: Path,
) -> None:
    data = tmp_path / "legacy-rule-restore"
    engine = create_sqlite_engine(data / "zeny-project-handler.sqlite3")
    try:
        upgrade_database(engine)
        registry_service = _compliance_registry(data, engine)
        safe_seed = carregar_registro_conformidade_inicial()
        legacy_seed = _legacy_bundled_registry(safe_seed)
        registry_service.inicializar(legacy_seed)
        service = _service(data, engine, compliance_registry=registry_service)
        backup = service.criar_backup(tmp_path / "legacy-rules.zphbackup")

        registry_service.inicializar(safe_seed)
        service.restaurar_backup(backup.caminho)

        restored = registry_service.obter_revisao_ativa().registro
        span_rule = next(
            item for item in restored.regras if item.id == "nd31.vao.urbano-compacto-isolado"
        )
        assert restored.versao == "cemig-normas-distribuicao-2026.1"
        assert restored.regras == safe_seed.regras
        assert any(
            item.chave_fato == "vao.aplicabilidade_excecao_45_60_resolvida"
            for item in span_rule.aplicabilidade
        )
    finally:
        engine.dispose()


def test_backup_preflight_is_side_effect_free_and_classifies_pdf_problems(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = tmp_path / "preflight-data"
    engine = create_sqlite_engine(data / "zeny-project-handler.sqlite3")
    try:
        upgrade_database(engine)
        project, pdf_source = _project_with_real_pdf(tmp_path, catalogo_inicial)
        _persist_complete_project(engine, catalogo_inicial, project, pdf_source)
        service = _service(data, engine)
        original = pdf_source.caminho_canonico.read_bytes()

        def reject_temporary_directory(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("preflight tentou criar diretório temporário")

        with monkeypatch.context() as patch:
            patch.setattr(
                "zeny_project_handler.application.project_portability.TemporaryDirectory",
                reject_temporary_directory,
            )
            assert service.preflight_backup().integro

        pdf_source.caminho_canonico.unlink()
        missing = service.preflight_backup()
        assert [item.codigo for item in missing.problemas] == ["PDF_AUSENTE"]

        pdf_source.caminho_canonico.write_bytes(original + b"alterado")
        changed = service.preflight_backup()
        assert [item.codigo for item in changed.problemas] == ["PDF_ADULTERADO"]

        pdf_source.caminho_canonico.write_bytes(b"conteudo ilegivel")
        unreadable = service.preflight_backup()
        assert [item.codigo for item in unreadable.problemas] == ["PDF_ILEGIVEL"]
        assert all(item.caminho_relativo is None for item in unreadable.problemas)
        assert all(item.referencia_id == project.documentos[0].id for item in unreadable.problemas)
        assert not (tmp_path / "preflight.zphbackup").exists()
        assert not tuple(data.glob(".z-*"))
    finally:
        engine.dispose()


def test_degraded_backup_requires_confirmation_records_omission_and_restores_predictably(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    data = tmp_path / "degraded-data"
    engine = create_sqlite_engine(data / "zeny-project-handler.sqlite3")
    try:
        upgrade_database(engine)
        project, pdf_source = _project_with_real_pdf(tmp_path, catalogo_inicial)
        _persist_complete_project(engine, catalogo_inicial, project, pdf_source)
        service = _service(data, engine)
        pdf_source.caminho_canonico.unlink()
        report = service.preflight_backup()
        destination = tmp_path / "degraded.zphbackup"
        destination.write_bytes(b"ultimo-backup-publicado")

        with pytest.raises(PortabilidadeProjetoError, match="confirmação explícita"):
            service.criar_backup(destination, relatorio_integridade=report)

        assert destination.read_bytes() == b"ultimo-backup-publicado"
        assert not tuple(tmp_path.glob(".z-*"))
        accepted = service.criar_backup(
            destination,
            confirmar_degradado=True,
            relatorio_integridade=report,
        )
        assert accepted.estado_integridade is EstadoIntegridadePacote.DEGRADADO
        assert accepted.manifesto.versao_formato == 2
        assert [item.codigo for item in accepted.manifesto.omissoes] == ["PDF_AUSENTE"]
        omission = accepted.manifesto.omissoes[0]
        assert omission.referencia_id == project.documentos[0].id
        assert omission.projeto_id == project.id
        assert all(
            item.referencia_id != project.documentos[0].id for item in accepted.manifesto.arquivos
        )

        extracted = ZipProjectArchive().extrair_validado(
            accepted.caminho, tmp_path / "degraded-extracted"
        )
        assert extracted.integridade.integro
        assert extracted.manifesto.estado_integridade is EstadoIntegridadePacote.DEGRADADO

        with SqlAlchemyUnitOfWork(engine) as work:
            work.projetos.salvar(replace(project, nome="Estado posterior"))
            work.commit()
        restoration = service.restaurar_backup(accepted.caminho)
        assert restoration.estado_integridade is EstadoIntegridadePacote.DEGRADADO
        with SqlAlchemyUnitOfWork(engine) as work:
            restored_project = work.projetos.obter(project.id)
            restored_source = work.fontes_pdf.obter(project.documentos[0].id)
        assert restored_project == project
        assert restored_source is not None
        assert (
            restored_source.caminho_canonico
            == (
                data
                / "project-files"
                / str(project.id)
                / "pdfs"
                / f"{project.documentos[0].id}.pdf"
            ).resolve()
        )
        assert restored_source.caminho_canonico != pdf_source.caminho_canonico
        assert not restored_source.caminho_canonico.exists()
        assert [item.codigo for item in service.verificar_integridade(project.id).problemas] == [
            "PDF_AUSENTE"
        ]
    finally:
        engine.dispose()


def test_restore_disposes_connections_again_before_rollback(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = tmp_path / "rollback-data"
    database_path = data / "zeny-project-handler.sqlite3"
    engine = create_sqlite_engine(database_path)
    try:
        upgrade_database(engine)
        project, pdf_source = _project_with_real_pdf(tmp_path, catalogo_inicial)
        _persist_complete_project(engine, catalogo_inicial, project, pdf_source)
        dispose_calls = 0

        def dispose_connections() -> None:
            nonlocal dispose_calls
            dispose_calls += 1
            engine.dispose()

        service = _service(data, engine, dispose_connections)
        backup = service.criar_backup(tmp_path / "rollback.zphbackup")
        with SqlAlchemyUnitOfWork(engine) as work:
            work.projetos.salvar(replace(project, nome="Estado posterior"))
            work.commit()

        manager = service._backup
        real_restore = manager.restaurar_snapshot
        restore_calls = 0

        def fail_first_restore(source: Path, destination: Path) -> Path:
            nonlocal restore_calls
            restore_calls += 1
            if restore_calls == 1:
                raise PersistenceError("falha simulada na troca")
            return real_restore(source, destination)

        monkeypatch.setattr(manager, "restaurar_snapshot", fail_first_restore)

        with pytest.raises(PersistenceError, match="falha simulada"):
            service.restaurar_backup(backup.caminho)

        assert dispose_calls == 2
        assert restore_calls == 2
        with SqlAlchemyUnitOfWork(engine) as work:
            current = work.projetos.obter(project.id)
        assert current is not None
        assert current.nome == "Estado posterior"
    finally:
        engine.dispose()

    moved_database = data / "rollback-closed.sqlite3"
    database_path.replace(moved_database)
    moved_database.unlink()
    assert not moved_database.exists()


def test_restore_rolls_back_database_assets_and_catalog_when_rule_reconciliation_fails(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = tmp_path / "rule-reconciliation-rollback-data"
    database_path = data / "zeny-project-handler.sqlite3"
    engine = create_sqlite_engine(database_path)
    try:
        upgrade_database(engine)
        project, pdf_source = _project_with_real_pdf(tmp_path, catalogo_inicial)
        _persist_complete_project(engine, catalogo_inicial, project, pdf_source)
        registry_service = _compliance_registry(data, engine)
        seed, current_registry, _restored_rule, _changed_rule, custom_rule = (
            _registry_after_backup()
        )
        registry_service.inicializar(seed)
        service = _service(data, engine, compliance_registry=registry_service)
        backup = service.criar_backup(tmp_path / "rule-reconciliation-rollback.zphbackup")

        current_revision = registry_service.importar(
            registry_service.preparar_importacao(current_registry)
        )
        post_backup_project = replace(project, nome="Estado posterior ao backup")
        with SqlAlchemyUnitOfWork(engine) as work:
            work.projetos.salvar(post_backup_project)
            work.commit()
        managed_marker = data / "project-files" / "post-backup.txt"
        managed_marker.parent.mkdir(parents=True, exist_ok=True)
        managed_marker.write_text("estado posterior", encoding="utf-8")
        catalog_before = registry_service.caminho_catalogo.read_bytes()
        assert managed_marker.is_file()

        real_reconcile = registry_service.reconciliar_apos_restauracao

        def reconcile_then_fail(registry):  # type: ignore[no-untyped-def]
            real_reconcile(registry)
            raise RuntimeError("falha simulada depois da reconciliação")

        monkeypatch.setattr(
            registry_service,
            "reconciliar_apos_restauracao",
            reconcile_then_fail,
        )

        with pytest.raises(RuntimeError, match="falha simulada depois da reconciliação"):
            service.restaurar_backup(backup.caminho)

        with SqlAlchemyUnitOfWork(engine) as work:
            project_after_failure = work.projetos.obter(project.id)
        assert project_after_failure == post_backup_project
        assert managed_marker.read_text(encoding="utf-8") == "estado posterior"
        assert registry_service.obter_revisao_ativa() == current_revision
        assert any(
            item.id == custom_rule.id
            for item in registry_service.obter_revisao_ativa().registro.regras
        )
        assert registry_service.caminho_catalogo.read_bytes() == catalog_before
        assert not tuple(data.glob(".z-*"))
    finally:
        engine.dispose()


def test_portability_refuses_conflict_before_mutating_and_releases_after_success(
    tmp_path: Path,
) -> None:
    data = tmp_path / "coordinated-data"
    engine = create_sqlite_engine(data / "zeny-project-handler.sqlite3")
    upgrade_database(engine)
    coordinator = CoordenadorOperacoes()
    service = _service(data, engine, coordinator=coordinator)
    destination = tmp_path / "coordinated.zphbackup"
    destination.write_bytes(b"backup anterior")

    try:
        with (
            coordinator.adquirir(TipoOperacao.ANALISE),
            pytest.raises(OperacaoEmAndamentoError, match="análise do projeto"),
        ):
            service.criar_backup(destination)

        assert destination.read_bytes() == b"backup anterior"
        assert not tuple(tmp_path.glob(".z-*"))
        result = service.criar_backup(destination)
        assert result.caminho == destination
        assert coordinator.operacao_em_andamento is None
    finally:
        engine.dispose()


def test_portability_exception_releases_coordinator_for_next_operation(tmp_path: Path) -> None:
    data = tmp_path / "exception-data"
    engine = create_sqlite_engine(data / "zeny-project-handler.sqlite3")
    upgrade_database(engine)
    coordinator = CoordenadorOperacoes()
    service = _service(data, engine, coordinator=coordinator)

    try:
        with pytest.raises(PortabilidadeProjetoError, match="Pacote informado não existe"):
            service.importar_projeto(tmp_path / "pacote-inexistente.zphproj")

        assert coordinator.operacao_em_andamento is None
        with coordinator.adquirir(TipoOperacao.BACKUP):
            assert coordinator.operacao_em_andamento is TipoOperacao.BACKUP
    finally:
        engine.dispose()
