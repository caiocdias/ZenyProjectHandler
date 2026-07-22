from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import networkx as nx  # type: ignore[import-untyped]
from tests.factories import complete_project

from zeny_project_handler.adapters.graph import NetworkxProjectGraphBuilder
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import EstadoConexao, TipoPontoRede
from zeny_project_handler.domain.project import Cabo, Equipamento
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado


def test_canonical_project_builds_physical_and_electrical_multigraphs(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    builder = NetworkxProjectGraphBuilder()

    result = builder.reconstruir(project, catalogo_inicial)

    assert len(result.fisico.nos) == 4
    assert len(result.fisico.arestas) == 2
    assert len(result.eletrico.nos) == 5
    assert len(result.eletrico.arestas) == 4
    assert isinstance(builder.multigrafo(result.eletrico), nx.MultiGraph)
    assert not result.diagnosticos


def test_parallel_cables_remain_distinct_and_input_order_does_not_change_signature(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    cable = next(item for item in project.elementos if isinstance(item, Cabo))
    parallel = replace(cable, id=uuid4(), codigo_observado="paralelo")
    with_parallel = replace(project, elementos=(*project.elementos, parallel))
    builder = NetworkxProjectGraphBuilder()

    first = builder.reconstruir(with_parallel, catalogo_inicial)
    reordered = replace(
        with_parallel,
        elementos=tuple(reversed(with_parallel.elementos)),
        pontos_rede=tuple(reversed(with_parallel.pontos_rede)),
        terminais=tuple(reversed(with_parallel.terminais)),
        conexoes_internas=tuple(reversed(with_parallel.conexoes_internas)),
    )
    second = builder.reconstruir(reordered, catalogo_inicial)
    graph = builder.multigrafo(first.eletrico)

    assert graph.number_of_edges(cable.ponto_origem_id, cable.ponto_destino_id) == 2
    assert first == builder.reconstruir(with_parallel, catalogo_inicial)
    assert first.assinatura == second.assinatura
    assert first.fisico == second.fisico
    assert first.eletrico == second.eletrico


def test_radial_branch_preserves_each_cable_from_the_derivation_point(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    cable = next(item for item in project.elementos if isinstance(item, Cabo))
    origin, destination = project.pontos_rede[:2]
    third = replace(destination, id=uuid4(), nome="P3-MT")
    fourth = replace(destination, id=uuid4(), nome="P4-MT")
    branch_one = replace(cable, id=uuid4(), ponto_destino_id=third.id)
    branch_two = replace(cable, id=uuid4(), ponto_destino_id=fourth.id)
    scenario = replace(
        project,
        elementos=(*project.elementos, branch_one, branch_two),
        pontos_rede=(*project.pontos_rede, third, fourth),
    )

    result = NetworkxProjectGraphBuilder().reconstruir(scenario, catalogo_inicial)
    graph = NetworkxProjectGraphBuilder.multigrafo(result.eletrico)
    cable_edges = tuple(
        data
        for _source, _target, _key, data in graph.edges(origin.id, keys=True, data=True)
        if data["kind"] == "CABO"
    )

    assert len(cable_edges) == 3


def test_open_switch_does_not_connect_terminals_and_unknown_state_is_diagnosed(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    connection = project.conexoes_internas[0]
    open_project = replace(
        project,
        conexoes_internas=(replace(connection, estado=EstadoConexao.DESCONECTADA),),
    )

    opened = NetworkxProjectGraphBuilder().reconstruir(open_project, catalogo_inicial)

    assert all(edge.referencia_id != connection.id for edge in opened.eletrico.arestas)
    unknown_project = replace(
        project,
        conexoes_internas=(replace(connection, estado=EstadoConexao.DESCONHECIDA),),
    )
    unknown = NetworkxProjectGraphBuilder().reconstruir(unknown_project, catalogo_inicial)
    assert any(
        item.codigo == "ESTADO_CONEXAO_DESCONHECIDO"
        and set(item.referencias_ids)
        == {connection.terminal_origem_id, connection.terminal_destino_id}
        for item in unknown.diagnosticos
    )


def test_graph_reports_island_cycle_mismatch_and_equipment_without_terminals(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    cable = next(item for item in project.elementos if isinstance(item, Cabo))
    first, second = project.pontos_rede[:2]
    third = replace(first, id=uuid4(), nome="P3-MT", poste_id=second.poste_id)
    island = replace(first, id=uuid4(), nome="Ilha", poste_id=None, tipo=TipoPontoRede.ENTREGA)
    phase_group = next(
        item for item in catalogo_inicial.grupos_opcao if item.chave == "configuracao_fases"
    )
    other_phase = next(
        item.id for item in phase_group.opcoes if item.id != second.configuracao_fases_opcao_id
    )
    incompatible_second = replace(second, configuracao_fases_opcao_id=other_phase)
    second_to_third = replace(
        cable,
        id=uuid4(),
        ponto_origem_id=second.id,
        ponto_destino_id=third.id,
    )
    third_to_first = replace(
        cable,
        id=uuid4(),
        ponto_origem_id=third.id,
        ponto_destino_id=first.id,
    )
    equipment = next(item for item in project.elementos if isinstance(item, Equipamento))
    scenario = replace(
        project,
        elementos=(*project.elementos, second_to_third, third_to_first),
        pontos_rede=(first, incompatible_second, *project.pontos_rede[2:], third, island),
        terminais=(),
        conexoes_internas=(),
    )

    result = NetworkxProjectGraphBuilder().reconstruir(scenario, catalogo_inicial)
    codes = {item.codigo for item in result.diagnosticos}

    assert equipment.id in next(
        item.referencias_ids
        for item in result.diagnosticos
        if item.codigo == "EQUIPAMENTO_SEM_TERMINAIS"
    )
    assert {
        "CICLO_INESPERADO",
        "COMPONENTE_DESCONECTADO",
        "EQUIPAMENTO_SEM_TERMINAIS",
        "TENSAO_OU_FASE_INCOMPATIVEL",
    } <= codes


def test_orphan_endpoint_proposes_only_compatible_nearby_connection(
    catalogo_inicial: CatalogoTecnico,
) -> None:
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
    scenario = replace(
        project,
        pontos_rede=(first, orphan, *project.pontos_rede[2:], target),
    )

    result = NetworkxProjectGraphBuilder().reconstruir(scenario, catalogo_inicial)

    assert len(result.sugestoes) == 1
    suggestion = result.sugestoes[0]
    assert suggestion.origem_id == orphan.id
    assert suggestion.destino_id == target.id
    assert any(item.codigo == "PONTA_ORFA" for item in result.diagnosticos)
    assert any(item.codigo == "CONEXAO_SUGERIDA" for item in result.diagnosticos)
    assert any(item.proposta for item in result.eletrico.arestas)
