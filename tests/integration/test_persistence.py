from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, inspect, text, update
from sqlalchemy.exc import IntegrityError
from tests.factories import complete_analysis, complete_project
from tests.path_fixtures import near_windows_path_limit

from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_atomic_backup,
    create_sqlite_engine,
    current_database_revision,
    managed_sqlite_engine,
    restore_atomic_backup,
    upgrade_database,
)
from zeny_project_handler.adapters.persistence.errors import (
    PersistenceConflictError,
    PersistenceError,
    PersistenceNotFoundError,
)
from zeny_project_handler.adapters.persistence.schema import catalog_versions
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import StatusCatalogo, TipoGeometria
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

pytestmark = pytest.mark.integration


@pytest.fixture
def database(tmp_path: Path) -> Iterator[tuple[Path, Engine]]:
    path = tmp_path / "dados" / "zeny.sqlite3"
    engine = create_sqlite_engine(path)
    upgrade_database(engine)
    try:
        yield path, engine
    finally:
        engine.dispose()


def test_migrations_upgrade_empty_database_and_previous_revision(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "migration.sqlite3")

    upgrade_database(engine, "0001_initial")
    assert current_database_revision(engine) == "0001_initial"
    assert "updated_at" not in {
        column["name"] for column in inspect(engine).get_columns("projects")
    }

    upgrade_database(engine)
    upgrade_database(engine)

    assert current_database_revision(engine) == "0004_human_review"
    assert "updated_at" in {column["name"] for column in inspect(engine).get_columns("projects")}
    assert "ix_elements_project" in {
        index["name"] for index in inspect(engine).get_indexes("elements")
    }
    assert "ix_document_sources_project" in {
        index["name"] for index in inspect(engine).get_indexes("document_sources")
    }
    assert "ix_confirmed_relations_project" in {
        index["name"] for index in inspect(engine).get_indexes("confirmed_relations")
    }
    with engine.connect() as connection:
        trigger_count = connection.scalar(
            text("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'")
        )
    assert trigger_count == 5
    engine.dispose()


def test_complete_round_trip_survives_reopen_and_atomic_backup(
    database: tuple[Path, Engine], catalogo_inicial: CatalogoTecnico, tmp_path: Path
) -> None:
    database_path, engine = database
    project = complete_project(catalogo_inicial)
    execution, item, element_proposal, relation_proposal, decision = complete_analysis(project)

    with SqlAlchemyUnitOfWork(engine) as unit:
        unit.catalogos.salvar(catalogo_inicial)
        unit.projetos.salvar(project)
        unit.execucoes_analise.salvar(execution)
        unit.evidencias.salvar(item)
        unit.propostas.salvar(element_proposal)
        unit.propostas.salvar(relation_proposal)
        unit.decisoes_revisao.salvar(decision)
        unit.commit()

    engine.dispose()
    reopened = create_sqlite_engine(database_path)
    upgrade_database(reopened)
    with SqlAlchemyUnitOfWork(reopened) as unit:
        assert unit.catalogos.obter(catalogo_inicial.id) == catalogo_inicial
        assert unit.projetos.obter(project.id) == project
        assert unit.documentos.listar_do_projeto(project.id) == project.documentos
        assert unit.elementos.listar_do_projeto(project.id) == project.elementos
        assert unit.execucoes_analise.obter(execution.id) == execution
        assert unit.execucoes_analise.listar_do_projeto(project.id) == (execution,)
        assert unit.evidencias.obter(item.id) == item
        assert unit.evidencias.listar_da_execucao(execution.id) == (item,)
        assert unit.propostas.obter(element_proposal.id) == element_proposal
        assert unit.propostas.obter(relation_proposal.id) == relation_proposal
        assert unit.decisoes_revisao.obter_da_proposta(element_proposal.id) == decision
        assert unit.decisoes_revisao.obter(decision.id) == decision

    backup_path = create_atomic_backup(database_path, tmp_path / "backups" / "snapshot.sqlite3")
    backup_engine = create_sqlite_engine(backup_path)
    with SqlAlchemyUnitOfWork(backup_engine) as unit:
        assert unit.projetos.obter(project.id) == project
        assert unit.propostas.listar_da_execucao(execution.id) == (
            element_proposal,
            relation_proposal,
        )
    backup_engine.dispose()
    reopened.dispose()


def test_explicit_commit_update_rollback_and_delete(
    database: tuple[Path, Engine], catalogo_inicial: CatalogoTecnico
) -> None:
    _, engine = database
    project = complete_project(catalogo_inicial)

    with SqlAlchemyUnitOfWork(engine) as unit:
        unit.catalogos.salvar(catalogo_inicial)
        unit.projetos.salvar(project)

    with SqlAlchemyUnitOfWork(engine) as unit:
        assert unit.catalogos.obter(catalogo_inicial.id) is None
        assert unit.projetos.obter(project.id) is None
        unit.catalogos.salvar(catalogo_inicial)
        unit.projetos.salvar(project)
        unit.commit()

    updated = replace(project, nome="Projeto atualizado")
    with SqlAlchemyUnitOfWork(engine) as unit:
        unit.projetos.salvar(updated)
        unit.commit()
    with SqlAlchemyUnitOfWork(engine) as unit:
        assert unit.projetos.listar() == (updated,)
        assert unit.documentos.obter(project.documentos[0].id) == project.documentos[0]
        assert unit.elementos.obter(project.elementos[0].id) == project.elementos[0]
        assert unit.projetos.remover(project.id)
        unit.rollback()
        assert unit.projetos.obter(project.id) == updated

    with SqlAlchemyUnitOfWork(engine) as unit:
        assert unit.projetos.remover(project.id)
        unit.commit()
    with SqlAlchemyUnitOfWork(engine) as unit:
        assert unit.projetos.obter(project.id) is None
        assert unit.documentos.obter(project.documentos[0].id) is None


def test_catalog_versioning_soft_deactivation_and_database_trigger(
    database: tuple[Path, Engine], catalogo_inicial: CatalogoTecnico
) -> None:
    _, engine = database
    created_at = datetime(2026, 7, 21, 12, tzinfo=UTC)
    draft = catalogo_inicial.criar_rascunho(novo_id=uuid4(), criado_em=created_at)
    disabled_item = replace(draft.itens[0], ativo=False)
    edited_draft = draft.com_itens((disabled_item, *draft.itens[1:]))

    with SqlAlchemyUnitOfWork(engine) as unit:
        unit.catalogos.salvar(catalogo_inicial)
        unit.catalogos.salvar(draft)
        unit.catalogos.salvar(edited_draft)
        with pytest.raises(PersistenceConflictError, match="publicado"):
            unit.projetos.salvar(complete_project(edited_draft))
        unit.commit()
    with SqlAlchemyUnitOfWork(engine) as unit:
        loaded_draft = unit.catalogos.obter(draft.id)
        assert loaded_draft is not None
        assert not loaded_draft.itens[0].ativo
        assert unit.catalogos.listar() == (catalogo_inicial, edited_draft)
        assert unit.catalogos.remover_rascunho(draft.id)
        assert not unit.catalogos.remover_rascunho(uuid4())
        unit.commit()

    published_revision = replace(
        edited_draft,
        status=StatusCatalogo.PUBLICADO,
        publicado_em=datetime(2026, 7, 21, 12, 5, tzinfo=UTC),
    )
    historical_project = complete_project(catalogo_inicial)
    with SqlAlchemyUnitOfWork(engine) as unit:
        unit.catalogos.salvar(published_revision)
        unit.projetos.salvar(historical_project)
        unit.commit()
    with SqlAlchemyUnitOfWork(engine) as unit:
        assert unit.catalogos.obter(published_revision.id) == published_revision
        loaded_project = unit.projetos.obter(historical_project.id)
        assert loaded_project is not None
        assert loaded_project.catalogo_versao_id == catalogo_inicial.id

    modified_published = replace(catalogo_inicial, versao=catalogo_inicial.versao + 100)
    with (
        SqlAlchemyUnitOfWork(engine) as unit,
        pytest.raises(PersistenceConflictError, match="imutável"),
    ):
        unit.catalogos.salvar(modified_published)

    with engine.begin() as connection, pytest.raises(IntegrityError, match="imutavel"):
        connection.execute(
            update(catalog_versions)
            .where(catalog_versions.c.id == str(catalogo_inicial.id))
            .values(version=999)
        )


def test_repositories_reject_cross_aggregate_references(
    database: tuple[Path, Engine], catalogo_inicial: CatalogoTecnico
) -> None:
    _, engine = database
    project = complete_project(catalogo_inicial)
    execution, evidence, proposal, _, decision = complete_analysis(project)

    with SqlAlchemyUnitOfWork(engine) as unit:
        with pytest.raises(PersistenceNotFoundError, match="Catálogo"):
            unit.projetos.salvar(project)
        unit.rollback()
        unit.catalogos.salvar(catalogo_inicial)
        unit.projetos.salvar(project)
        unit.execucoes_analise.salvar(execution)
        with pytest.raises(PersistenceConflictError, match="evidências"):
            unit.propostas.salvar(proposal)

        foreign_page = uuid4()
        invalid_evidence = replace(
            evidence,
            pagina_id=foreign_page,
            geometria=GeometriaDocumento(
                pagina_id=foreign_page,
                tipo=TipoGeometria.PONTO,
                pontos=(PontoNormalizado(Decimal("0.1"), Decimal("0.1")),),
            ),
        )
        with pytest.raises(PersistenceConflictError, match="mesmo projeto"):
            unit.evidencias.salvar(invalid_evidence)
        with pytest.raises(PersistenceNotFoundError, match="Proposta"):
            unit.decisoes_revisao.salvar(decision)

        unit.evidencias.salvar(evidence)
        unit.propostas.salvar(proposal)
        updated_proposal = replace(proposal, confianca=Decimal("0.91"))
        unit.propostas.salvar(updated_proposal)
        unit.decisoes_revisao.salvar(decision)
        unit.decisoes_revisao.salvar(decision)
        with pytest.raises(PersistenceConflictError, match="imutável"):
            unit.decisoes_revisao.salvar(replace(decision, revisor="outro revisor"))
        unit.commit()


def test_project_projections_reject_identifier_reuse_between_projects(
    database: tuple[Path, Engine], catalogo_inicial: CatalogoTecnico
) -> None:
    _, engine = database
    first = complete_project(catalogo_inicial)
    second = complete_project(catalogo_inicial)
    duplicated_document = replace(second.documentos[0], id=first.documentos[0].id)
    second = replace(second, documentos=(duplicated_document,))

    with SqlAlchemyUnitOfWork(engine) as unit:
        unit.catalogos.salvar(catalogo_inicial)
        unit.projetos.salvar(first)
        unit.commit()
    with (
        SqlAlchemyUnitOfWork(engine) as unit,
        pytest.raises(PersistenceConflictError, match="outro projeto"),
    ):
        unit.projetos.salvar(second)
    with SqlAlchemyUnitOfWork(engine) as unit:
        assert unit.projetos.obter(second.id) is None


def test_backup_rejects_missing_or_same_source(
    database: tuple[Path, Engine], tmp_path: Path
) -> None:
    database_path, engine = database
    with pytest.raises(PersistenceError, match="origem"):
        create_atomic_backup(tmp_path / "ausente.sqlite3", tmp_path / "backup.sqlite3")
    with pytest.raises(PersistenceError, match="diferente"):
        create_atomic_backup(database_path, database_path)
    engine.dispose()


def test_backup_and_restore_use_short_sibling_temps_near_windows_path_limit(
    database: tuple[Path, Engine], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path, engine = database
    backup_destination = near_windows_path_limit(tmp_path / "backup-output", "snapshot.sqlite3")
    restore_destination = near_windows_path_limit(
        tmp_path / "restore-output", "zeny-project-handler.sqlite3"
    )
    observed: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def observe_replace(source_path: Path, target_path: Path) -> None:
        observed.append((Path(source_path), Path(target_path)))
        real_replace(source_path, target_path)

    monkeypatch.setattr(
        "zeny_project_handler.adapters.persistence.backup.os.replace",
        observe_replace,
    )

    backup = create_atomic_backup(database_path, backup_destination)
    restored = restore_atomic_backup(backup, restore_destination)

    assert backup == backup_destination
    assert restored == restore_destination
    assert len(observed) == 2
    for temporary, target in observed:
        assert temporary.parent == target.parent
        assert len(temporary.name) <= 15
        assert len(str(temporary)) < len(str(target))
        assert set(target.parent.iterdir()) == {target}
    engine.dispose()


@pytest.mark.parametrize("operation", ["backup", "restore"])
def test_atomic_sqlite_failure_preserves_destination_without_residue(
    operation: str,
    database: tuple[Path, Engine],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, engine = database
    snapshot = create_atomic_backup(database_path, tmp_path / "source-snapshot.sqlite3")
    destination = near_windows_path_limit(tmp_path / operation, "zeny-project-handler.sqlite3")
    destination.write_bytes(b"stable-version")

    def interrupt_replace(_source: Path, _target: Path) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(
        "zeny_project_handler.adapters.persistence.backup.os.replace",
        interrupt_replace,
    )

    with pytest.raises(PersistenceError, match="destino informado"):
        if operation == "backup":
            create_atomic_backup(database_path, destination)
        else:
            restore_atomic_backup(snapshot, destination)

    assert destination.read_bytes() == b"stable-version"
    assert set(destination.parent.iterdir()) == {destination}
    engine.dispose()


def test_unit_of_work_requires_open_context(database: tuple[Path, Engine]) -> None:
    _, engine = database
    unit = SqlAlchemyUnitOfWork(engine)
    with pytest.raises(RuntimeError, match="não está aberta"):
        unit.commit()
    with unit, pytest.raises(RuntimeError, match="já está aberta"):
        unit.__enter__()
    engine.dispose()


@pytest.mark.parametrize("fail_inside_scope", [False, True])
def test_managed_engine_closes_sessions_connections_and_unlocks_sqlite(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    fail_inside_scope: bool,
) -> None:
    database_path = tmp_path / f"managed-{fail_inside_scope}.sqlite3"

    def use_database() -> None:
        with managed_sqlite_engine(database_path) as engine:
            upgrade_database(engine)
            with SqlAlchemyUnitOfWork(engine) as unit:
                unit.catalogos.salvar(catalogo_inicial)
                if fail_inside_scope:
                    raise RuntimeError("falha controlada")
                unit.commit()
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT COUNT(*) FROM catalog_versions")) == 1

    if fail_inside_scope:
        with pytest.raises(RuntimeError, match="controlada"):
            use_database()
    else:
        use_database()

    moved_path = database_path.with_name("moved.sqlite3")
    database_path.replace(moved_path)
    moved_path.unlink()
    assert not moved_path.exists()
