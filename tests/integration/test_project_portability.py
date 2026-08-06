from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Engine
from tests.factories import complete_analysis, complete_project
from tests.pdf_fixtures import create_golden_pdf

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
from zeny_project_handler.application.errors import PortabilidadeProjetoError
from zeny_project_handler.application.project_portability import ServicoPortabilidadeProjeto
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.portability import EstadoIntegridadePacote
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.pdf import ReferenciaFontePdf

pytestmark = pytest.mark.integration


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
) -> ServicoPortabilidadeProjeto:
    return ServicoPortabilidadeProjeto(
        lambda: SqlAlchemyUnitOfWork(engine),
        ZipProjectArchive(),
        SqlitePortableProjectDatabase(),
        SqliteBackupManager(),
        diretorio_dados=data,
        caminho_banco=data / "zeny-project-handler.sqlite3",
        descartar_conexoes=dispose_connections or engine.dispose,
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


def test_export_import_preserves_ids_decisions_and_repairs_missing_photo(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
    app_log_capture: pytest.LogCaptureFixture,
) -> None:
    source_data = tmp_path / "source-data"
    source_engine = create_sqlite_engine(source_data / "zeny-project-handler.sqlite3")
    upgrade_database(source_engine)
    project, pdf_source = _project_with_real_pdf(tmp_path, catalogo_inicial)
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
    real_replace = os.replace
    replace_calls = 0

    def interrupt_staging_publication(source: Path, destination: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("interrupted")
        real_replace(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(
            "zeny_project_handler.application.project_portability.os.replace",
            interrupt_staging_publication,
        )
        with pytest.raises(PortabilidadeProjetoError, match="publicar os arquivos"):
            target_service.importar_projeto(moved_package, substituir_existente=True)

    assert {
        path.relative_to(managed_root): path.read_bytes()
        for path in managed_root.rglob("*")
        if path.is_file()
    } == assets_before_failure
    assert not tuple(target_data.glob(".z-*"))

    assert imported.projeto == expected_project
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
    dispose_calls = 0

    def dispose_connections() -> None:
        nonlocal dispose_calls
        dispose_calls += 1
        engine.dispose()

    service = _service(data, engine, dispose_connections)
    photo_path = _create_png(tmp_path / "backup-photo.png")
    attached = service.anexar_foto(project.id, project.elementos[0].id, photo_path)
    backup = service.criar_backup(tmp_path / "backup.zphbackup")
    assert backup.estado_integridade is EstadoIntegridadePacote.INTEGRO
    assert backup.manifesto.versao_formato == 2

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
        assert restored_source.caminho_canonico == pdf_source.caminho_canonico
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
