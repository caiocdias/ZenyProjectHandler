from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine
from tests.factories import complete_analysis, complete_project

from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.errors import RevisaoHumanaError
from zeny_project_handler.application.human_review import (
    DadosElementoRevisao,
    ServicoRevisaoHumana,
)
from zeny_project_handler.domain.analysis import PropostaElemento, PropostaRelacao
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
    TipoDecisaoRevisao,
)
from zeny_project_handler.domain.project import Cabo, Poste
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

pytestmark = pytest.mark.integration


@pytest.fixture
def review_context(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> Iterator[
    tuple[Engine, ServicoRevisaoHumana, PropostaElemento, PropostaElemento, PropostaRelacao]
]:
    engine = create_sqlite_engine(tmp_path / "human-review.sqlite3")
    upgrade_database(engine)
    project = complete_project(catalogo_inicial)
    execution, evidence, template, _, _ = complete_analysis(project)
    first = replace(template, id=uuid4(), estado_revisao=EstadoRevisao.PROPOSTA)
    second = replace(
        template,
        id=uuid4(),
        estado_revisao=EstadoRevisao.CONFLITANTE,
        geometria=GeometriaDocumento.ponto(
            template.geometria.pagina_id,
            PontoNormalizado(Decimal("0.6"), Decimal("0.6")),
        ),
    )
    relation = PropostaRelacao(
        id=uuid4(),
        execucao_id=execution.id,
        origem_referencia_id=project.elementos[0].id,
        destino_referencia_id=project.elementos[1].id,
        tipo_relacao="ASSOCIADO_A",
        evidencia_ids=(evidence.id,),
    )
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(project)
        work.execucoes_analise.salvar(execution)
        work.evidencias.salvar(evidence)
        work.propostas.salvar(first)
        work.propostas.salvar(second)
        work.propostas.salvar(relation)
        work.commit()
    service = ServicoRevisaoHumana(
        lambda: SqlAlchemyUnitOfWork(engine),
        relogio=lambda: datetime(2026, 7, 21, 16, tzinfo=UTC),
    )
    try:
        yield engine, service, first, second, relation
    finally:
        engine.dispose()


def _pole_data(proposal: PropostaElemento, catalog: CatalogoTecnico) -> DadosElementoRevisao:
    pole_type = catalog.itens_ativos(CategoriaElemento.POSTE)[0]
    return DadosElementoRevisao(
        categoria=CategoriaElemento.POSTE,
        tipo_catalogo_id=pole_type.id,
        situacao=SituacaoProjeto.EXISTENTE,
        geometria=proposal.geometria,
        codigo_observado=pole_type.codigo,
    )


def test_accept_adjust_reject_and_reopen_preserve_immutable_history(
    review_context: tuple[
        Engine,
        ServicoRevisaoHumana,
        PropostaElemento,
        PropostaElemento,
        PropostaRelacao,
    ],
) -> None:
    engine, service, accepted, rejected, _ = review_context
    session = service.carregar_sessao(next(item.projeto_id for item in service.listar_projetos()))
    data = _pole_data(accepted, session.catalogo)

    decision = service.confirmar_elemento(accepted.id, data, revisor="Caio")
    rejection = service.rejeitar(rejected.id, revisor="Caio", motivo="símbolo incorreto")

    assert decision.decisao is TipoDecisaoRevisao.ACEITAR
    assert rejection.decisao is TipoDecisaoRevisao.REJEITAR
    with pytest.raises(RevisaoHumanaError, match="imutável"):
        service.rejeitar(accepted.id, revisor="Outro")
    with SqlAlchemyUnitOfWork(engine) as work:
        project = work.projetos.obter(session.projeto.id)
        stored_accepted = work.propostas.obter(accepted.id)
        stored_rejected = work.propostas.obter(rejected.id)
        stored_decision = work.decisoes_revisao.obter_da_proposta(accepted.id)
    assert project is not None
    assert decision.elemento_confirmado_id in {item.id for item in project.elementos}
    assert stored_accepted is not None
    assert stored_accepted.estado_revisao is EstadoRevisao.CONFIRMADA
    assert stored_rejected is not None
    assert stored_rejected.estado_revisao is EstadoRevisao.REJEITADA
    assert stored_decision == decision


def test_confirm_relation_and_manual_creations_are_persisted_with_author(
    review_context: tuple[
        Engine,
        ServicoRevisaoHumana,
        PropostaElemento,
        PropostaElemento,
        PropostaRelacao,
    ],
) -> None:
    engine, service, element_proposal, _, relation_proposal = review_context
    summary = service.listar_projetos()[0]
    session = service.carregar_sessao(summary.projeto_id)

    relation_decision = service.confirmar_relacao(
        relation_proposal.id,
        revisor="Caio",
        motivo="conferido no PDF",
    )
    manual_element_id = service.criar_elemento_manual(
        session.projeto.id,
        _pole_data(element_proposal, session.catalogo),
        revisor="Caio",
        motivo="ausente na análise",
    )
    manual_relation_id = service.criar_relacao_manual(
        session.projeto.id,
        tipo_relacao="VIZINHO_DE",
        origem_id=session.projeto.elementos[0].id,
        destino_id=manual_element_id,
        revisor="Caio",
    )

    with SqlAlchemyUnitOfWork(engine) as work:
        reopened = work.projetos.obter(session.projeto.id)
        stored_relation_decision = work.decisoes_revisao.obter_da_proposta(relation_proposal.id)
    assert reopened is not None
    assert relation_decision.relacao_confirmada_id in {
        item.id for item in reopened.relacoes_confirmadas
    }
    assert manual_relation_id in {item.id for item in reopened.relacoes_confirmadas}
    assert isinstance(
        next(item for item in reopened.elementos if item.id == manual_element_id), Poste
    )
    assert {item.revisor for item in reopened.historico_revisao_manual} == {"Caio"}
    assert stored_relation_decision == relation_decision


def test_equivalent_proposal_from_new_analysis_cannot_override_previous_rejection(
    review_context: tuple[
        Engine,
        ServicoRevisaoHumana,
        PropostaElemento,
        PropostaElemento,
        PropostaRelacao,
    ],
) -> None:
    engine, service, rejected, _, _ = review_context
    session = service.carregar_sessao(service.listar_projetos()[0].projeto_id)
    service.rejeitar(rejected.id, revisor="Caio")
    later_execution = replace(
        session.execucao,
        id=uuid4(),
        iniciada_em=datetime(2026, 7, 21, 19, tzinfo=UTC),
        finalizada_em=datetime(2026, 7, 21, 19, 1, tzinfo=UTC),
    )
    repeated = replace(rejected, id=uuid4(), execucao_id=later_execution.id)
    with SqlAlchemyUnitOfWork(engine) as work:
        work.execucoes_analise.salvar(later_execution)
        work.propostas.salvar(repeated)
        work.commit()

    with pytest.raises(RevisaoHumanaError, match="equivalente"):
        service.confirmar_elemento(
            repeated.id,
            _pole_data(repeated, session.catalogo),
            revisor="Outro",
        )

    with SqlAlchemyUnitOfWork(engine) as work:
        stored = work.propostas.obter(repeated.id)
    assert stored is not None
    assert stored.estado_revisao is EstadoRevisao.PROPOSTA


def test_accepting_cable_creates_missing_network_endpoints(
    review_context: tuple[
        Engine,
        ServicoRevisaoHumana,
        PropostaElemento,
        PropostaElemento,
        PropostaRelacao,
    ],
) -> None:
    engine, service, template, _, _ = review_context
    session = service.carregar_sessao(service.listar_projetos()[0].projeto_id)
    cable_type = session.catalogo.itens_ativos(CategoriaElemento.CABO)[0]
    cable_proposal = replace(
        template,
        id=uuid4(),
        categoria=CategoriaElemento.CABO,
        tipo_catalogo_sugerido_id=cable_type.id,
        codigo_observado=cable_type.codigo,
        geometria=GeometriaDocumento.caixa(
            template.geometria.pagina_id,
            PontoNormalizado(Decimal("0.1"), Decimal("0.1")),
            PontoNormalizado(Decimal("0.8"), Decimal("0.8")),
        ),
    )
    with SqlAlchemyUnitOfWork(engine) as work:
        work.propostas.salvar(cable_proposal)
        work.commit()
    original_point_ids = {item.id for item in session.projeto.pontos_rede}

    decision = service.confirmar_elemento(
        cable_proposal.id,
        DadosElementoRevisao(
            categoria=CategoriaElemento.CABO,
            tipo_catalogo_id=cable_type.id,
            situacao=SituacaoProjeto.EXISTENTE,
            geometria=cable_proposal.geometria,
            codigo_observado=cable_type.codigo,
        ),
        revisor="Caio",
    )

    with SqlAlchemyUnitOfWork(engine) as work:
        project = work.projetos.obter(session.projeto.id)
    assert project is not None
    cable = next(item for item in project.elementos if item.id == decision.elemento_confirmado_id)
    assert isinstance(cable, Cabo)
    assert cable.geometria is not None
    assert cable.geometria.tipo.value == "POLILINHA"
    assert {cable.ponto_origem_id, cable.ponto_destino_id}.isdisjoint(original_point_ids)
    assert {cable.ponto_origem_id, cable.ponto_destino_id} <= {
        item.id for item in project.pontos_rede
    }
