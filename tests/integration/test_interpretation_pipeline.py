from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
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
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    TipoEvidencia,
)
from zeny_project_handler.domain.project import Poste, Projeto
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
) -> Iterator[tuple[Engine, Projeto, ExecucaoAnalise]]:
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
    coordinate_east = text_evidence(
        execution_id=source_execution.id,
        page_id=page_id,
        key="coordinate-east",
        text="0465702",
        x="0.11",
        y="0.21",
    )
    coordinate_north = replace(
        text_evidence(
            execution_id=source_execution.id,
            page_id=page_id,
            key="coordinate-north",
            text="7772468",
            x="0.12",
            y="0.21",
        ),
        tipo=TipoEvidencia.OCR,
    )
    point_label = text_evidence(
        execution_id=source_execution.id,
        page_id=page_id,
        key="point-label",
        text="P1",
        x="0.20",
        y="0.18",
    )
    equipment_point_label = text_evidence(
        execution_id=source_execution.id,
        page_id=page_id,
        key="equipment-point-label",
        text="P2",
        x="0.50",
        y="0.18",
    )
    span_label = text_evidence(
        execution_id=source_execution.id,
        page_id=page_id,
        key="span-label",
        text="V1-2",
        x="0.40",
        y="0.18",
    )
    evidence = (
        *evidence,
        coordinate_east,
        coordinate_north,
        point_label,
        equipment_point_label,
        span_label,
    )
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(project)
        work.execucoes_analise.salvar(source_execution)
        for item in evidence:
            work.evidencias.salvar(item)
        work.commit()
    try:
        yield engine, project, source_execution
    finally:
        engine.dispose()


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
    assert all(item.estado_revisao is EstadoRevisao.CONFIRMADA for item in first.elementos)
    assert all(source_execution.id != item.execucao_id for item in first.elementos)
    with SqlAlchemyUnitOfWork(engine) as work:
        stored = work.propostas.listar_da_execucao(first.execucao.id)
        promoted_project = work.projetos.obter(project.id)
        assert len(stored) == len(first.elementos) + len(first.relacoes)
        assert promoted_project is not None
        assert {item.id for item in project.elementos} < {
            item.id for item in promoted_project.elementos
        }
        promoted_pole = next(
            item
            for item in promoted_project.elementos
            if isinstance(item, Poste) and item.id not in {old.id for old in project.elementos}
        )
        assert promoted_pole.coordenada_campo is not None
        assert promoted_pole.coordenada_campo.leste == Decimal(465702)
        assert promoted_pole.coordenada_campo.norte == Decimal(7772468)
        assert promoted_pole.identificador_operacional == "P1"
        decisions = tuple(
            work.decisoes_revisao.obter_da_proposta(item.id) for item in first.elementos
        )
        assert all(item is not None and item.revisor == "Análise automática" for item in decisions)


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
