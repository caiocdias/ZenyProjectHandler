from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Engine, select, update
from tests.integration.test_compliance_analysis import _NOW, _gmax_gateway, _prepare_context
from tests.market_fakes import FakeVerificadorAcoesConcluidas

from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_atomic_backup,
    create_sqlite_engine,
    current_database_revision,
)
from zeny_project_handler.adapters.persistence.domain_json import dumps_domain
from zeny_project_handler.adapters.persistence.errors import PersistenceConflictError
from zeny_project_handler.adapters.persistence.schema import projects
from zeny_project_handler.application.compliance_analysis import ExecutarAnaliseConformidade
from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.market import ClassificacaoMercado, Mercado
from zeny_project_handler.ports.market import DependenciaAcoesError, DependenciaMercadoError


def test_initial_failure_retry_legacy_copy_and_restart(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, project_id, service, _, classifier = _prepare_context(tmp_path, catalogo_inicial)
    # Retirar o campo reproduz o payload anterior, sem inferir escolha de snapshots antigos.
    with engine.begin() as connection:
        raw_payload = connection.scalar(select(projects.c.payload))
        assert raw_payload is not None
        payload = json.loads(raw_payload)
        payload["fields"].pop("classificacao_mercado")
        connection.execute(update(projects).values(payload=json.dumps(payload)))
    backup = tmp_path / "legacy-copy.sqlite3"
    create_atomic_backup(tmp_path / "compliance.sqlite3", backup)
    with SqlAlchemyUnitOfWork(engine) as work:
        legacy = work.projetos.obter(project_id)
        assert legacy is not None and legacy.classificacao_mercado is None
    classifier.erro = DependenciaMercadoError("SQL indisponível")
    with pytest.raises(DependenciaMercadoError):
        service.executar(project_id)
    with SqlAlchemyUnitOfWork(engine) as work:
        assert work.projetos.obter(project_id) == legacy
    classifier.erro = None
    first = service.executar(project_id)
    assert not service.resultado_desatualizado(first)
    assert service.resultado_desatualizado(replace(first, versao_metodo="12"))
    assert classifier.consultas == [legacy.nome] * 2
    engine.dispose()

    for path, initialized in ((tmp_path / "compliance.sqlite3", True), (backup, False)):
        reopened = create_sqlite_engine(path)
        try:
            assert current_database_revision(reopened) == "0009_remote_jobs"

            def unit_of_work(database: Engine = reopened) -> SqlAlchemyUnitOfWork:
                return SqlAlchemyUnitOfWork(database)

            review = ServicoRevisaoHumana(unit_of_work)
            new_service = ExecutarAnaliseConformidade(
                unit_of_work,
                review.carregar_sessao_semantica,
                classificador_mercado=classifier,
                relogio=lambda: _NOW,
            )
            calls_before = len(classifier.consultas)
            result = new_service.executar(project_id)
            assert len(classifier.consultas) == calls_before + (0 if initialized else 1)
            if initialized:
                assert result == first
        finally:
            reopened.dispose()


def test_choices_mark_snapshots_stale_and_both_refuses_evaluation(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    verifier = FakeVerificadorAcoesConcluidas(resultado=True)
    engine, project_id, service, registry, classifier = _prepare_context(
        tmp_path,
        catalogo_inicial,
        codigos_servico=("0007",),
        extra_evidence=(("Impacto Ambiental: Sim", "0.70", "0.88"),),
        action_verifier=verifier,
    )
    first = service.executar(project_id)
    first_payload = dumps_domain(first)
    gateway = _gmax_gateway(engine, tmp_path, service, registry)
    for choice in (
        ClassificacaoMercado.RURAL,
        ClassificacaoMercado.URBANO,
        ClassificacaoMercado.AMBOS,
    ):
        with SqlAlchemyUnitOfWork(engine) as work:
            project = work.projetos.obter(project_id)
            assert project is not None and project.classificacao_mercado is not None
            work.projetos.salvar(
                replace(
                    project,
                    classificacao_mercado=project.classificacao_mercado.editar(
                        choice,
                        _NOW,
                    ),
                )
            )
            work.commit()
        assert service.resultado_desatualizado(first)
        assert gateway.get_gmax(project_id).is_stale
        if choice is ClassificacaoMercado.AMBOS:
            history = service.listar_historico(project_id)
            with pytest.raises(DomainValidationError, match=r"Ambos.*E03"):
                service.executar(project_id)
            assert service.listar_historico(project_id) == history
        else:
            result = service.executar(project_id)
            assert result.id != first.id
            assert not service.resultado_desatualizado(result)
            assert not gateway.get_gmax(project_id).is_stale
    assert len(verifier.consultas) == 3
    assert len(classifier.consultas) == 1
    assert dumps_domain(service.listar_historico(project_id)[0]) == first_payload
    engine.dispose()


def test_ns_round_trip_requires_new_initialization_even_for_same_database_value(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, project_id, service, _, classifier = _prepare_context(tmp_path, catalogo_inicial)
    first = service.executar(project_id)
    for ns in ("9999999999", "0012345678"):
        with SqlAlchemyUnitOfWork(engine) as work:
            project = work.projetos.obter(project_id)
            assert project is not None
            renamed = replace(project, nome=ns)
            assert renamed.classificacao_mercado is None
            work.projetos.salvar(renamed)
            work.commit()
        assert service.resultado_desatualizado(first)
        assert service.executar(project_id).id != first.id
    assert classifier.consultas == ["0012345678", "9999999999", "0012345678"]
    engine.dispose()


def test_successful_initialization_survives_action_failure(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    verifier = FakeVerificadorAcoesConcluidas(erro=DependenciaAcoesError("Falha nas ações"))
    engine, project_id, service, _, classifier = _prepare_context(
        tmp_path,
        catalogo_inicial,
        codigos_servico=("0007",),
        extra_evidence=(("Impacto Ambiental: Sim", "0.70", "0.88"),),
        action_verifier=verifier,
    )
    with pytest.raises(DependenciaAcoesError):
        service.executar(project_id)
    assert service.listar_historico(project_id) == ()
    verifier.erro = None
    service.executar(project_id)
    assert len(classifier.consultas) == 1
    assert len(verifier.consultas) == 2
    engine.dispose()


def test_concurrent_consumer_initializes_once(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, project_id, service, _, classifier = _prepare_context(tmp_path, catalogo_inicial)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(service.executar, (project_id, project_id)))
    assert results[0] == results[1]
    assert len(classifier.consultas) == 1
    engine.dispose()


def test_ns_change_during_sql_rejects_old_initialization(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, project_id, service, _, classifier = _prepare_context(tmp_path, catalogo_inicial)

    def change_ns(_numero_ns: str) -> Mercado:
        with SqlAlchemyUnitOfWork(engine) as work:
            project = work.projetos.obter(project_id)
            assert project is not None
            work.projetos.salvar(replace(project, nome="9999999999"))
            work.commit()
        return Mercado.RURAL

    monkeypatch.setattr(classifier, "classificar", change_ns)
    with pytest.raises(PersistenceConflictError):
        service.executar(project_id)
    with SqlAlchemyUnitOfWork(engine) as work:
        current = work.projetos.obter(project_id)
        assert current is not None and current.nome == "9999999999"
        assert current.classificacao_mercado is None
    assert service.listar_historico(project_id) == ()
    engine.dispose()
