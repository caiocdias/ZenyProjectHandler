from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Never
from uuid import uuid4

import pytest
from sqlalchemy import Engine
from tests.factories import complete_project
from tests.interpretation_factories import text_evidence

from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.errors import (
    InterpretacaoCanceladaError,
    InterpretacaoProjetoError,
)
from zeny_project_handler.application.interpretation_pipeline import ExecutarPipelineInterpretacao
from zeny_project_handler.domain.analysis import ExecucaoAnalise
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoExecucaoAnalise
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.interpretation import ConfiguracaoInterpretacao

pytestmark = pytest.mark.integration


class FailingInterpreter:
    nome = "semantic-failure"
    versao = "1"

    def interpretar(self, _request, *, cancelado=None) -> Never:  # type: ignore[no-untyped-def]
        raise RuntimeError("regra indisponível")


@pytest.fixture
def interpretation_context(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> tuple[Engine, Projeto, ExecucaoAnalise]:
    engine = create_sqlite_engine(tmp_path / "interpretation.sqlite3")
    upgrade_database(engine)
    project = complete_project(catalogo_inicial)
    source_execution = ExecucaoAnalise(
        id=uuid4(),
        projeto_id=project.id,
        metodo="fixture-extraction",
        versao_metodo="1",
        parametros=(),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=datetime(2026, 7, 21, 12, tzinfo=UTC),
        finalizada_em=datetime(2026, 7, 21, 12, 1, tzinfo=UTC),
    )
    page_id = project.documentos[0].paginas[0].id
    evidence = tuple(
        text_evidence(
            execution_id=source_execution.id,
            page_id=page_id,
            key=category.value,
            text=catalogo_inicial.itens_ativos(category)[0].codigo,
            x=str(Decimal("0.10") + Decimal(index) / Decimal(10)),
            y="0.20",
            color="#008000",
        )
        for index, category in enumerate(CategoriaElemento)
    )
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(project)
        work.execucoes_analise.salvar(source_execution)
        for item in evidence:
            work.evidencias.salvar(item)
        work.commit()
    return engine, project, source_execution


def _runner(engine: Engine) -> ExecutarPipelineInterpretacao:
    registry = carregar_registro_regras_inicial()
    return ExecutarPipelineInterpretacao(
        InterpretadorRegrasExplicitas(registry),
        registry,
        lambda: SqlAlchemyUnitOfWork(engine),
        relogio=lambda: datetime(2026, 7, 21, 13, tzinfo=UTC),
    )


def test_pipeline_persists_cross_run_provenance_and_reuses_completed_result(
    interpretation_context: tuple[Engine, Projeto, ExecucaoAnalise],
) -> None:
    engine, project, source_execution = interpretation_context
    runner = _runner(engine)

    first = runner.executar(project.id, source_execution.id)
    second = runner.executar(project.id, source_execution.id)

    assert first.execucao.estado is EstadoExecucaoAnalise.CONCLUIDA
    assert {item.categoria for item in first.elementos} == set(CategoriaElemento)
    assert not first.resultado_reutilizado
    assert second.resultado_reutilizado
    assert second.execucao.id == first.execucao.id
    assert second.elementos == first.elementos
    assert all(source_execution.id != item.execucao_id for item in first.elementos)
    with SqlAlchemyUnitOfWork(engine) as work:
        stored = work.propostas.listar_da_execucao(first.execucao.id)
        assert len(stored) == len(first.elementos) + len(first.relacoes)


def test_cancelled_pipeline_resumes_with_same_identity_without_duplicates(
    interpretation_context: tuple[Engine, Projeto, ExecucaoAnalise],
) -> None:
    engine, project, source_execution = interpretation_context
    runner = _runner(engine)
    config = ConfiguracaoInterpretacao(maximo_propostas=9999)

    with pytest.raises(InterpretacaoCanceladaError, match="retomável"):
        runner.executar(
            project.id, source_execution.id, configuracao=config, cancelado=lambda: True
        )
    with SqlAlchemyUnitOfWork(engine) as work:
        cancelled = next(
            item
            for item in work.execucoes_analise.listar_do_projeto(project.id)
            if item.estado is EstadoExecucaoAnalise.CANCELADA
        )
        assert work.propostas.listar_da_execucao(cancelled.id) == ()

    resumed = runner.executar(project.id, source_execution.id, configuracao=config)
    repeated = runner.executar(project.id, source_execution.id, configuracao=config)

    assert resumed.execucao.id == cancelled.id
    assert resumed.execucao.estado is EstadoExecucaoAnalise.CONCLUIDA
    assert repeated.resultado_reutilizado
    with SqlAlchemyUnitOfWork(engine) as work:
        stored = work.propostas.listar_da_execucao(resumed.execucao.id)
        assert len({item.id for item in stored}) == len(stored)


def test_fatal_semantic_failure_is_auditable(
    interpretation_context: tuple[Engine, Projeto, ExecucaoAnalise],
) -> None:
    engine, project, source_execution = interpretation_context
    registry = carregar_registro_regras_inicial()
    runner = ExecutarPipelineInterpretacao(
        FailingInterpreter(),
        registry,
        lambda: SqlAlchemyUnitOfWork(engine),
        relogio=lambda: datetime(2026, 7, 21, 14, tzinfo=UTC),
    )

    with pytest.raises(InterpretacaoProjetoError, match="registrada"):
        runner.executar(project.id, source_execution.id)

    with SqlAlchemyUnitOfWork(engine) as work:
        failed = next(
            item
            for item in work.execucoes_analise.listar_do_projeto(project.id)
            if item.metodo == FailingInterpreter.nome
        )
    assert failed.estado is EstadoExecucaoAnalise.FALHOU
    assert failed.erro == "regra indisponível"
