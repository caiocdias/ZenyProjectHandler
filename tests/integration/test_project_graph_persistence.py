from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from tests.factories import complete_project

from zeny_project_handler.adapters.graph import NetworkxProjectGraphBuilder
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.errors import ReconstrucaoGrafoError
from zeny_project_handler.application.project_graph import ServicoGrafoProjeto
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import TipoPontoRede
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

pytestmark = pytest.mark.integration


def test_confirmed_suggestion_is_persisted_and_rebuild_is_deterministic(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine = create_sqlite_engine(tmp_path / "project-graph.sqlite3")
    upgrade_database(engine)
    project = complete_project(catalogo_inicial)
    page_id = project.documentos[0].paginas[0].id
    first, destination = project.pontos_rede[:2]
    orphan = replace(
        destination,
        poste_id=None,
        tipo=TipoPontoRede.CONEXAO,
        geometria=GeometriaDocumento.ponto(
            page_id, PontoNormalizado(Decimal("0.80"), Decimal("0.40"))
        ),
    )
    target = replace(
        destination,
        id=uuid4(),
        nome="Ponto compatível",
        geometria=GeometriaDocumento.ponto(
            page_id, PontoNormalizado(Decimal("0.81"), Decimal("0.40"))
        ),
    )
    project = replace(
        project,
        pontos_rede=(first, orphan, *project.pontos_rede[2:], target),
    )
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(project)
        work.commit()

    service = ServicoGrafoProjeto(
        lambda: SqlAlchemyUnitOfWork(engine),
        NetworkxProjectGraphBuilder(),
        relogio=lambda: datetime(2026, 7, 21, 20, tzinfo=UTC),
    )
    initial = service.reconstruir(project.id)
    suggestion = initial.resultado.sugestoes[0]

    confirmed = service.confirmar_sugestao(
        project.id,
        suggestion.id,
        assinatura_esperada=initial.resultado.assinatura,
        revisor="Caio",
    )

    assert not confirmed.resultado.sugestoes
    confirmed_relation = confirmed.projeto.relacoes_confirmadas[-1]
    assert any(
        edge.referencia_id == confirmed_relation.id and not edge.proposta
        for edge in confirmed.resultado.eletrico.arestas
    )
    reopened = ServicoGrafoProjeto(
        lambda: SqlAlchemyUnitOfWork(engine), NetworkxProjectGraphBuilder()
    ).reconstruir(project.id)
    assert reopened.resultado.assinatura == confirmed.resultado.assinatura
    assert reopened.projeto.relacoes_confirmadas[-1].origem_id == suggestion.origem_id
    assert reopened.projeto.historico_revisao_manual[-1].revisor == "Caio"
    with pytest.raises(ReconstrucaoGrafoError, match="mudou desde"):
        service.confirmar_sugestao(
            project.id,
            suggestion.id,
            assinatura_esperada=initial.resultado.assinatura,
            revisor="Caio",
        )
    engine.dispose()
