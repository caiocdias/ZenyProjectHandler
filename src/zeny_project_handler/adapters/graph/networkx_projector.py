"""Reconstrução determinística das visões física e elétrica com NetworkX MultiGraph."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
from itertools import pairwise
from uuid import UUID, uuid5

import networkx as nx  # type: ignore[import-untyped]

from zeny_project_handler.domain.catalog import CatalogoTecnico, TipoCabo
from zeny_project_handler.domain.enums import (
    EstadoConexao,
    NivelRede,
    SeveridadeDiagnosticoGrafo,
    TipoNoGrafo,
    TipoPontoRede,
    VisaoGrafo,
)
from zeny_project_handler.domain.graph import (
    ArestaGrafo,
    DiagnosticoGrafo,
    GrafoDerivado,
    NoGrafo,
    ResultadoReconstrucaoGrafo,
    SugestaoConexaoGrafo,
)
from zeny_project_handler.domain.project import (
    Cabo,
    Equipamento,
    EstruturaBt,
    EstruturaMt,
    PontoRede,
    Poste,
    Projeto,
    TerminalEquipamento,
)
from zeny_project_handler.domain.values import GeometriaDocumento

_MAXIMUM_CONNECTION_DISTANCE = 0.03


class NetworkxProjectGraphBuilder:
    nome = "networkx-multigraph"
    versao = "1.0.0"

    def reconstruir(
        self, projeto: Projeto, catalogo: CatalogoTecnico
    ) -> ResultadoReconstrucaoGrafo:
        physical = _physical_graph(projeto, catalogo)
        electrical, state_diagnostics = _electrical_graph(projeto)
        electrical_nx = self.multigrafo(electrical)
        validation_diagnostics = _validate_project(projeto, catalogo, electrical_nx)
        suggestions, suggestion_diagnostics, suggestion_edges = _connection_suggestions(
            projeto, electrical, electrical_nx
        )
        electrical = GrafoDerivado(
            visao=VisaoGrafo.ELETRICA,
            nos=electrical.nos,
            arestas=tuple(
                sorted((*electrical.arestas, *suggestion_edges), key=lambda item: str(item.id))
            ),
        )
        diagnostics = tuple(
            sorted(
                (*state_diagnostics, *validation_diagnostics, *suggestion_diagnostics),
                key=lambda item: (item.severidade.value, item.codigo, str(item.id)),
            )
        )
        signature = _result_signature(physical, electrical, diagnostics, suggestions)
        return ResultadoReconstrucaoGrafo(
            projeto_id=projeto.id,
            versao_metodo=self.versao,
            assinatura=signature,
            fisico=physical,
            eletrico=electrical,
            diagnosticos=diagnostics,
            sugestoes=tuple(sorted(suggestions, key=lambda item: str(item.id))),
        )

    @staticmethod
    def multigrafo(graph: GrafoDerivado) -> nx.MultiGraph:
        result = nx.MultiGraph()
        for node in sorted(graph.nos, key=lambda item: str(item.id)):
            result.add_node(node.id, reference=node.referencia_id, kind=node.tipo.value)
        for edge in sorted(graph.arestas, key=lambda item: str(item.id)):
            result.add_edge(
                edge.origem_id,
                edge.destino_id,
                key=edge.id,
                reference=edge.referencia_id,
                kind=edge.tipo,
                proposed=edge.proposta,
            )
        return result


def _physical_graph(project: Projeto, catalog: CatalogoTecnico) -> GrafoDerivado:
    items = {item.id: item for item in catalog.itens}
    poles = {item.id: item for item in project.elementos if isinstance(item, Poste)}
    equipment = tuple(item for item in project.elementos if isinstance(item, Equipamento))
    points = {item.id: item for item in project.pontos_rede}
    nodes = [
        NoGrafo(
            id=pole.id,
            referencia_id=pole.id,
            tipo=TipoNoGrafo.POSTE,
            rotulo=(
                pole.referencia_desenho
                or pole.codigo_observado
                or items[pole.tipo_catalogo_id].codigo
            ),
            geometria=pole.geometria,
        )
        for pole in poles.values()
    ]
    nodes.extend(
        NoGrafo(
            id=item.id,
            referencia_id=item.id,
            tipo=TipoNoGrafo.EQUIPAMENTO,
            rotulo=(
                item.identificador_operacional
                or item.codigo_observado
                or items[item.tipo_catalogo_id].codigo
            ),
            geometria=item.geometria or poles[item.poste_id].geometria,
        )
        for item in equipment
    )
    edges = [
        _edge(project.id, VisaoGrafo.FISICA, "INSTALADO_EM", item.id, item.id, item.poste_id)
        for item in equipment
    ]
    for cable in (item for item in project.elementos if isinstance(item, Cabo)):
        route = _physical_cable_route(cable, points)
        edges.extend(
            _edge(
                project.id,
                VisaoGrafo.FISICA,
                "CABO",
                cable.id,
                origin,
                destination,
                index=index,
            )
            for index, (origin, destination) in enumerate(pairwise(route))
            if origin != destination
        )
    node_ids = {item.id for item in nodes}
    edges.extend(
        _edge(
            project.id,
            VisaoGrafo.FISICA,
            relation.tipo_relacao,
            relation.id,
            relation.origem_id,
            relation.destino_id,
        )
        for relation in project.relacoes_confirmadas
        if relation.origem_id in node_ids and relation.destino_id in node_ids
    )
    return GrafoDerivado(
        visao=VisaoGrafo.FISICA,
        nos=tuple(sorted(nodes, key=lambda item: str(item.id))),
        arestas=tuple(
            sorted({item.id: item for item in edges}.values(), key=lambda item: str(item.id))
        ),
    )


def _physical_cable_route(cable: Cabo, points: dict[UUID, PontoRede]) -> tuple[UUID, ...]:
    origin = points[cable.ponto_origem_id].poste_id
    destination = points[cable.ponto_destino_id].poste_id
    raw = (origin, *cable.postes_apoio_ids, destination)
    route: list[UUID] = []
    for item in raw:
        if item is not None and (not route or route[-1] != item):
            route.append(item)
    return tuple(route)


def _electrical_graph(
    project: Projeto,
) -> tuple[GrafoDerivado, tuple[DiagnosticoGrafo, ...]]:
    equipment = {item.id: item for item in project.elementos if isinstance(item, Equipamento)}
    poles = {item.id: item for item in project.elementos if isinstance(item, Poste)}
    points = {item.id: item for item in project.pontos_rede}
    terminals = {item.id: item for item in project.terminais}
    nodes = [
        NoGrafo(
            id=point.id,
            referencia_id=point.id,
            tipo=TipoNoGrafo.PONTO_REDE,
            rotulo=point.nome,
            geometria=point.geometria
            or (poles[point.poste_id].geometria if point.poste_id is not None else None),
        )
        for point in points.values()
    ]
    nodes.extend(
        NoGrafo(
            id=terminal.id,
            referencia_id=terminal.id,
            tipo=TipoNoGrafo.TERMINAL,
            rotulo=(
                f"{equipment[terminal.equipamento_id].identificador_operacional or 'Equipamento'}"
                f" / {terminal.nome}"
            ),
            geometria=equipment[terminal.equipamento_id].geometria
            or poles[equipment[terminal.equipamento_id].poste_id].geometria,
        )
        for terminal in terminals.values()
    )
    edges: list[ArestaGrafo] = []
    diagnostics: list[DiagnosticoGrafo] = []
    for cable in (item for item in project.elementos if isinstance(item, Cabo)):
        route = cable.percurso_pontos_ids
        edges.extend(
            _edge(
                project.id,
                VisaoGrafo.ELETRICA,
                "CABO",
                cable.id,
                origin,
                destination,
                index=index,
            )
            for index, (origin, destination) in enumerate(pairwise(route))
        )
    edges.extend(
        _edge(
            project.id,
            VisaoGrafo.ELETRICA,
            "TERMINAL_PONTO",
            terminal.id,
            terminal.id,
            terminal.ponto_rede_id,
        )
        for terminal in terminals.values()
        if terminal.ponto_rede_id is not None
    )
    for connection in project.conexoes_internas:
        if connection.estado is EstadoConexao.CONECTADA:
            edges.append(
                _edge(
                    project.id,
                    VisaoGrafo.ELETRICA,
                    "CONEXAO_INTERNA",
                    connection.id,
                    connection.terminal_origem_id,
                    connection.terminal_destino_id,
                )
            )
        elif connection.estado is EstadoConexao.DESCONHECIDA:
            diagnostics.append(
                _diagnostic(
                    project.id,
                    "ESTADO_CONEXAO_DESCONHECIDO",
                    SeveridadeDiagnosticoGrafo.AVISO,
                    "A continuidade interna do equipamento precisa ser confirmada.",
                    VisaoGrafo.ELETRICA,
                    (connection.terminal_origem_id, connection.terminal_destino_id),
                )
            )
    node_ids = {item.id for item in nodes}
    edges.extend(
        _edge(
            project.id,
            VisaoGrafo.ELETRICA,
            relation.tipo_relacao,
            relation.id,
            relation.origem_id,
            relation.destino_id,
        )
        for relation in project.relacoes_confirmadas
        if relation.origem_id in node_ids and relation.destino_id in node_ids
    )
    return (
        GrafoDerivado(
            visao=VisaoGrafo.ELETRICA,
            nos=tuple(sorted(nodes, key=lambda item: str(item.id))),
            arestas=tuple(
                sorted({item.id: item for item in edges}.values(), key=lambda item: str(item.id))
            ),
        ),
        tuple(diagnostics),
    )


def _validate_project(
    project: Projeto,
    catalog: CatalogoTecnico,
    electrical: nx.MultiGraph,
) -> tuple[DiagnosticoGrafo, ...]:
    diagnostics: list[DiagnosticoGrafo] = []
    diagnostics.extend(_equipment_diagnostics(project))
    diagnostics.extend(_cable_compatibility_diagnostics(project, catalog))
    diagnostics.extend(_component_diagnostics(project.id, electrical))
    diagnostics.extend(_orphan_diagnostics(project, electrical))
    diagnostics.extend(_cycle_diagnostics(project.id, electrical))
    unique = {item.id: item for item in diagnostics}
    return tuple(sorted(unique.values(), key=lambda item: (item.codigo, str(item.id))))


def _equipment_diagnostics(project: Projeto) -> tuple[DiagnosticoGrafo, ...]:
    terminal_counts: dict[UUID, int] = defaultdict(int)
    for terminal in project.terminais:
        terminal_counts[terminal.equipamento_id] += 1
    return tuple(
        _diagnostic(
            project.id,
            "EQUIPAMENTO_SEM_TERMINAIS",
            SeveridadeDiagnosticoGrafo.ERRO,
            "O equipamento não possui terminais elétricos confirmados.",
            VisaoGrafo.FISICA,
            (equipment.id,),
        )
        for equipment in project.elementos
        if isinstance(equipment, Equipamento) and terminal_counts[equipment.id] == 0
    )


def _cable_compatibility_diagnostics(
    project: Projeto, catalog: CatalogoTecnico
) -> tuple[DiagnosticoGrafo, ...]:
    points = {item.id: item for item in project.pontos_rede}
    items = {item.id: item for item in catalog.itens}
    compatible_pairs = {
        (item.tipo_cabo_id, item.tipo_estrutura_id) for item in catalog.compatibilidades
    }
    structures_by_pole: dict[UUID, list[EstruturaMt | EstruturaBt]] = defaultdict(list)
    for element in project.elementos:
        if isinstance(element, (EstruturaMt, EstruturaBt)):
            structures_by_pole[element.poste_id].append(element)
    diagnostics: list[DiagnosticoGrafo] = []
    for cable in (item for item in project.elementos if isinstance(item, Cabo)):
        cable_type = items.get(cable.tipo_catalogo_id)
        if not isinstance(cable_type, TipoCabo):
            continue
        for point_id in cable.percurso_pontos_ids:
            point = points[point_id]
            if (
                point.nivel_tensao_opcao_id != cable_type.nivel_tensao_opcao_id
                or point.configuracao_fases_opcao_id != cable_type.configuracao_fases_opcao_id
            ):
                diagnostics.append(
                    _diagnostic(
                        project.id,
                        "TENSAO_OU_FASE_INCOMPATIVEL",
                        SeveridadeDiagnosticoGrafo.ERRO,
                        "O cabo e o ponto de rede usam tensão ou configuração de fases diferentes.",
                        VisaoGrafo.ELETRICA,
                        (cable.id, point.id),
                    )
                )
        expected_level = _cable_level(catalog, cable_type)
        pole_ids = _physical_cable_route(cable, points)
        for pole_id in pole_ids:
            structures = tuple(
                item
                for item in structures_by_pole[pole_id]
                if (expected_level is NivelRede.MT and isinstance(item, EstruturaMt))
                or (expected_level is NivelRede.BT and isinstance(item, EstruturaBt))
            )
            if structures and not any(
                (cable.tipo_catalogo_id, structure.tipo_catalogo_id) in compatible_pairs
                for structure in structures
            ):
                diagnostics.append(
                    _diagnostic(
                        project.id,
                        "ESTRUTURA_CABO_INCOMPATIVEL",
                        SeveridadeDiagnosticoGrafo.AVISO,
                        "Nenhuma estrutura confirmada no poste é compatível com o tipo do cabo.",
                        VisaoGrafo.FISICA,
                        (cable.id, pole_id, *(item.id for item in structures)),
                    )
                )
    return tuple(diagnostics)


def _cable_level(catalog: CatalogoTecnico, cable: TipoCabo) -> NivelRede:
    option = next(
        option
        for group in catalog.grupos_opcao
        if group.chave == "nivel_tensao"
        for option in group.opcoes
        if option.id == cable.nivel_tensao_opcao_id
    )
    return NivelRede.MT if "MT" in f"{option.codigo} {option.rotulo}".upper() else NivelRede.BT


def _component_diagnostics(project_id: UUID, graph: nx.MultiGraph) -> tuple[DiagnosticoGrafo, ...]:
    if graph.number_of_nodes() == 0:
        return ()
    components = sorted(
        (tuple(sorted(component, key=str)) for component in nx.connected_components(graph)),
        key=lambda item: (-len(item), tuple(map(str, item))),
    )
    return tuple(
        _diagnostic(
            project_id,
            "COMPONENTE_DESCONECTADO",
            SeveridadeDiagnosticoGrafo.AVISO,
            "Este componente elétrico não está conectado ao componente principal.",
            VisaoGrafo.ELETRICA,
            component,
        )
        for component in components[1:]
    )


def _orphan_diagnostics(project: Projeto, graph: nx.MultiGraph) -> tuple[DiagnosticoGrafo, ...]:
    return tuple(
        _diagnostic(
            project.id,
            "PONTA_ORFA",
            SeveridadeDiagnosticoGrafo.AVISO,
            "A ponta de conexão possui somente o próprio cabo e ainda precisa ser vinculada.",
            VisaoGrafo.ELETRICA,
            (point.id,),
        )
        for point in project.pontos_rede
        if point.tipo is TipoPontoRede.CONEXAO
        and point.poste_id is None
        and graph.degree(point.id) <= 1
    )


def _cycle_diagnostics(project_id: UUID, graph: nx.MultiGraph) -> tuple[DiagnosticoGrafo, ...]:
    simple = nx.Graph()
    simple.add_nodes_from(sorted(graph.nodes, key=str))
    simple.add_edges_from(
        sorted(
            (
                (min(origin, destination, key=str), max(origin, destination, key=str))
                for origin, destination in graph.edges()
            ),
            key=lambda item: (str(item[0]), str(item[1])),
        )
    )
    cycles = sorted(
        (tuple(sorted(cycle, key=str)) for cycle in nx.cycle_basis(simple)),
        key=lambda item: tuple(map(str, item)),
    )
    return tuple(
        _diagnostic(
            project_id,
            "CICLO_INESPERADO",
            SeveridadeDiagnosticoGrafo.AVISO,
            "A rede confirmada contém um ciclo; valide se a topologia deveria ser radial.",
            VisaoGrafo.ELETRICA,
            cycle,
        )
        for cycle in cycles
    )


def _connection_suggestions(
    project: Projeto,
    electrical: GrafoDerivado,
    graph: nx.MultiGraph,
) -> tuple[
    tuple[SugestaoConexaoGrafo, ...],
    tuple[DiagnosticoGrafo, ...],
    tuple[ArestaGrafo, ...],
]:
    nodes = {item.id: item for item in electrical.nos}
    points = {item.id: item for item in project.pontos_rede}
    terminals = {item.id: item for item in project.terminais}
    suggestions: list[SugestaoConexaoGrafo] = []
    diagnostics: list[DiagnosticoGrafo] = []
    edges: list[ArestaGrafo] = []
    for point in sorted(points.values(), key=lambda item: str(item.id)):
        if point.tipo is not TipoPontoRede.CONEXAO or point.poste_id is not None:
            continue
        source_node = nodes[point.id]
        if source_node.geometria is None or graph.degree(point.id) > 1:
            continue
        candidates = _compatible_nearby_nodes(
            point,
            source_node,
            nodes,
            points,
            terminals,
            set(graph.neighbors(point.id)),
        )
        for candidate_id, distance in candidates:
            suggestion = _suggestion(project.id, point.id, candidate_id, distance)
            suggestions.append(suggestion)
            edges.append(
                _edge(
                    project.id,
                    VisaoGrafo.ELETRICA,
                    "CONEXAO_SUGERIDA",
                    suggestion.id,
                    point.id,
                    candidate_id,
                    proposed=True,
                )
            )
            diagnostics.append(
                _diagnostic(
                    project.id,
                    "CONEXAO_AMBIGUA" if len(candidates) > 1 else "CONEXAO_SUGERIDA",
                    SeveridadeDiagnosticoGrafo.AVISO,
                    (
                        "Há mais de uma conexão geometricamente compatível; escolha a correta."
                        if len(candidates) > 1
                        else "Uma conexão compatível foi encontrada e aguarda confirmação humana."
                    ),
                    VisaoGrafo.ELETRICA,
                    (point.id, candidate_id),
                    suggestion_id=suggestion.id,
                )
            )
    return tuple(suggestions), tuple(diagnostics), tuple(edges)


def _compatible_nearby_nodes(
    source: PontoRede,
    source_node: NoGrafo,
    nodes: dict[UUID, NoGrafo],
    points: dict[UUID, PontoRede],
    terminals: dict[UUID, TerminalEquipamento],
    excluded: set[UUID],
) -> tuple[tuple[UUID, float], ...]:
    candidates: list[tuple[UUID, float]] = []
    for candidate_id, node in sorted(nodes.items(), key=lambda item: str(item[0])):
        if candidate_id == source.id or candidate_id in excluded or node.geometria is None:
            continue
        if not _electrically_compatible(
            source, points.get(candidate_id), terminals.get(candidate_id)
        ):
            continue
        source_geometry = source_node.geometria
        if source_geometry is None:
            continue
        distance = _geometry_distance(source_geometry, node.geometria)
        if distance <= _MAXIMUM_CONNECTION_DISTANCE:
            candidates.append((candidate_id, distance))
    return tuple(sorted(candidates, key=lambda item: (item[1], str(item[0]))))


def _electrically_compatible(
    source: PontoRede,
    point: PontoRede | None,
    terminal: TerminalEquipamento | None,
) -> bool:
    candidate = point or terminal
    return bool(
        candidate is not None
        and candidate.nivel_rede is source.nivel_rede
        and candidate.nivel_tensao_opcao_id == source.nivel_tensao_opcao_id
        and candidate.configuracao_fases_opcao_id == source.configuracao_fases_opcao_id
    )


def _geometry_distance(first: GeometriaDocumento, second: GeometriaDocumento) -> float:
    if first.pagina_id != second.pagina_id:
        return math.inf
    first_center = _geometry_center(first)
    second_center = _geometry_center(second)
    return math.hypot(first_center[0] - second_center[0], first_center[1] - second_center[1])


def _geometry_center(geometry: GeometriaDocumento) -> tuple[float, float]:
    xs = [float(item.x) for item in geometry.pontos]
    ys = [float(item.y) for item in geometry.pontos]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def _edge(
    project_id: UUID,
    view: VisaoGrafo,
    kind: str,
    reference_id: UUID,
    origin_id: UUID,
    destination_id: UUID | None,
    *,
    index: int = 0,
    proposed: bool = False,
) -> ArestaGrafo:
    if destination_id is None:
        raise ValueError("Aresta deve possuir destino")
    ordered = tuple(sorted((origin_id, destination_id), key=str))
    identifier = uuid5(
        project_id,
        f"grafo:{view.value}:{kind}:{reference_id}:{ordered[0]}:{ordered[1]}:{index}",
    )
    return ArestaGrafo(
        id=identifier,
        origem_id=ordered[0],
        destino_id=ordered[1],
        tipo=kind,
        referencia_id=reference_id,
        proposta=proposed,
    )


def _suggestion(
    project_id: UUID, origin_id: UUID, destination_id: UUID, distance: float
) -> SugestaoConexaoGrafo:
    ordered = tuple(sorted((origin_id, destination_id), key=str))
    identifier = uuid5(project_id, f"sugestao-conexao:{ordered[0]}:{ordered[1]}")
    confidence = Decimal(str(max(0.55, min(0.90, 0.90 - distance * 5)))).quantize(Decimal("0.01"))
    return SugestaoConexaoGrafo(
        id=identifier,
        origem_id=origin_id,
        destino_id=destination_id,
        confianca=confidence,
        justificativa="Proximidade geométrica e compatibilidade exata de nível, tensão e fases.",
    )


def _diagnostic(
    project_id: UUID,
    code: str,
    severity: SeveridadeDiagnosticoGrafo,
    message: str,
    view: VisaoGrafo,
    references: tuple[UUID, ...],
    *,
    suggestion_id: UUID | None = None,
) -> DiagnosticoGrafo:
    ordered = tuple(sorted(set(references), key=str))
    identifier = uuid5(
        project_id,
        f"diagnostico:{view.value}:{code}:{','.join(map(str, ordered))}:{suggestion_id or ''}",
    )
    return DiagnosticoGrafo(
        id=identifier,
        codigo=code,
        severidade=severity,
        mensagem=message,
        visao=view,
        referencias_ids=ordered,
        sugestao_id=suggestion_id,
    )


def _result_signature(
    physical: GrafoDerivado,
    electrical: GrafoDerivado,
    diagnostics: tuple[DiagnosticoGrafo, ...],
    suggestions: tuple[SugestaoConexaoGrafo, ...],
) -> str:
    payload = {
        "graphs": [_graph_payload(physical), _graph_payload(electrical)],
        "diagnostics": [
            {
                "id": str(item.id),
                "code": item.codigo,
                "severity": item.severidade.value,
                "view": item.visao.value,
                "references": list(map(str, item.referencias_ids)),
                "suggestion": str(item.sugestao_id) if item.sugestao_id else None,
            }
            for item in diagnostics
        ],
        "suggestions": [
            {
                "id": str(item.id),
                "origin": str(item.origem_id),
                "destination": str(item.destino_id),
                "confidence": str(item.confianca),
            }
            for item in suggestions
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def _graph_payload(graph: GrafoDerivado) -> dict[str, object]:
    return {
        "view": graph.visao.value,
        "nodes": [
            {
                "id": str(item.id),
                "reference": str(item.referencia_id),
                "kind": item.tipo.value,
                "label": item.rotulo,
                "geometry": _geometry_payload(item.geometria),
            }
            for item in graph.nos
        ],
        "edges": [
            {
                "id": str(item.id),
                "origin": str(item.origem_id),
                "destination": str(item.destino_id),
                "kind": item.tipo,
                "reference": str(item.referencia_id),
                "directed": item.direcionada,
                "proposed": item.proposta,
            }
            for item in graph.arestas
        ],
    }


def _geometry_payload(geometry: GeometriaDocumento | None) -> object:
    if geometry is None:
        return None
    return {
        "page": str(geometry.pagina_id),
        "kind": geometry.tipo.value,
        "points": [[str(item.x), str(item.y)] for item in geometry.pontos],
    }
