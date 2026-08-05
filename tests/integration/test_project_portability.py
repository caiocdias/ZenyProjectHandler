from __future__ import annotations

import os
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
from zeny_project_handler.adapters.portability import ZipProjectArchive
from zeny_project_handler.application.errors import PortabilidadeProjetoError
from zeny_project_handler.application.project_portability import ServicoPortabilidadeProjeto
from zeny_project_handler.domain.catalog import CatalogoTecnico
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


def _service(data: Path, engine: Engine) -> ServicoPortabilidadeProjeto:
    return ServicoPortabilidadeProjeto(
        lambda: SqlAlchemyUnitOfWork(engine),
        ZipProjectArchive(),
        SqlitePortableProjectDatabase(),
        SqliteBackupManager(),
        diretorio_dados=data,
        caminho_banco=data / "zeny-project-handler.sqlite3",
        descartar_conexoes=engine.dispose,
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


def test_full_backup_restores_database_and_managed_files(
    tmp_path: Path, catalogo_inicial: CatalogoTecnico
) -> None:
    data = tmp_path / "data"
    engine = create_sqlite_engine(data / "zeny-project-handler.sqlite3")
    upgrade_database(engine)
    project, pdf_source = _project_with_real_pdf(tmp_path, catalogo_inicial)
    _persist_complete_project(engine, catalogo_inicial, project, pdf_source)
    service = _service(data, engine)
    photo_path = _create_png(tmp_path / "backup-photo.png")
    attached = service.anexar_foto(project.id, project.elementos[0].id, photo_path)
    backup = service.criar_backup(tmp_path / "backup.zphbackup")

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

    service.restaurar_backup(backup)

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
    engine.dispose()
    assert not tuple(data.glob(".z-*"))
