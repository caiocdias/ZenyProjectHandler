"""Remoção pura dos dados de projeto dependentes de documentos excluídos."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from zeny_project_handler.domain.project import (
    Cabo,
    Equipamento,
    EstruturaBt,
    EstruturaMt,
    Poste,
    Projeto,
    RelacaoConfirmada,
)


@dataclass(frozen=True, slots=True)
class _RemovedProjectReferences:
    elements: frozenset[UUID]
    points: frozenset[UUID]
    terminals: frozenset[UUID]

    @property
    def all(self) -> frozenset[UUID]:
        return self.elements | self.points | self.terminals


def project_without_documents(
    project: Projeto,
    document_ids: set[UUID],
    page_ids: set[UUID],
) -> Projeto:
    """Retorne o projeto sem documentos e sem referências que dependam de suas páginas."""
    removed_elements, removed_points = _references_on_pages(project, page_ids)
    removed_elements, removed_points = _expand_transitive_references(
        project,
        removed_elements,
        removed_points,
    )
    removed_equipment = frozenset(
        element.id
        for element in project.elementos
        if isinstance(element, Equipamento) and element.id in removed_elements
    )
    removed_terminals = frozenset(
        terminal.id
        for terminal in project.terminais
        if terminal.equipamento_id in removed_equipment or terminal.ponto_rede_id in removed_points
    )
    removed = _RemovedProjectReferences(
        elements=frozenset(removed_elements),
        points=frozenset(removed_points),
        terminals=removed_terminals,
    )
    retained_relations, removed_relation_ids = _partition_relations(project, removed.all)
    return _retain_independent_project_data(
        project,
        document_ids=document_ids,
        page_ids=page_ids,
        removed=removed,
        removed_equipment=removed_equipment,
        retained_relations=retained_relations,
        removed_relation_ids=removed_relation_ids,
    )


def _references_on_pages(project: Projeto, page_ids: set[UUID]) -> tuple[set[UUID], set[UUID]]:
    removed_elements = {
        element.id
        for element in project.elementos
        if element.geometria is not None and element.geometria.pagina_id in page_ids
    }
    removed_points = {
        point.id
        for point in project.pontos_rede
        if point.geometria is not None and point.geometria.pagina_id in page_ids
    }
    return removed_elements, removed_points


def _expand_transitive_references(
    project: Projeto,
    removed_elements: set[UUID],
    removed_points: set[UUID],
) -> tuple[set[UUID], set[UUID]]:
    changed = True
    while changed:
        before = len(removed_elements) + len(removed_points)
        removed_poles = {
            element.id
            for element in project.elementos
            if isinstance(element, Poste) and element.id in removed_elements
        }
        removed_points.update(
            point.id for point in project.pontos_rede if point.poste_id in removed_poles
        )
        removed_elements.update(
            element.id
            for element in project.elementos
            if _element_depends_on_removed_reference(element, removed_poles, removed_points)
        )
        changed = before != len(removed_elements) + len(removed_points)
    return removed_elements, removed_points


def _partition_relations(
    project: Projeto,
    removed_references: frozenset[UUID],
) -> tuple[tuple[RelacaoConfirmada, ...], frozenset[UUID]]:
    retained = tuple(
        relation
        for relation in project.relacoes_confirmadas
        if relation.origem_id not in removed_references
        and relation.destino_id not in removed_references
    )
    removed_ids = frozenset(
        relation.id for relation in project.relacoes_confirmadas if relation not in retained
    )
    return retained, removed_ids


def _retain_independent_project_data(
    project: Projeto,
    *,
    document_ids: set[UUID],
    page_ids: set[UUID],
    removed: _RemovedProjectReferences,
    removed_equipment: frozenset[UUID],
    retained_relations: tuple[RelacaoConfirmada, ...],
    removed_relation_ids: frozenset[UUID],
) -> Projeto:
    return replace(
        project,
        documentos=tuple(
            document for document in project.documentos if document.id not in document_ids
        ),
        ordem_leitura_paginas=tuple(
            page_id for page_id in project.ordem_leitura_paginas if page_id not in page_ids
        ),
        elementos=tuple(
            element for element in project.elementos if element.id not in removed.elements
        ),
        pontos_rede=tuple(point for point in project.pontos_rede if point.id not in removed.points),
        terminais=tuple(
            terminal for terminal in project.terminais if terminal.id not in removed.terminals
        ),
        conexoes_internas=tuple(
            connection
            for connection in project.conexoes_internas
            if connection.equipamento_id not in removed_equipment
            and connection.terminal_origem_id not in removed.terminals
            and connection.terminal_destino_id not in removed.terminals
        ),
        vinculos_obra=tuple(
            link
            for link in project.vinculos_obra
            if link.elemento_origem_id not in removed.elements
            and link.elemento_destino_id not in removed.elements
        ),
        relacoes_confirmadas=retained_relations,
        historico_revisao_manual=tuple(
            record
            for record in project.historico_revisao_manual
            if record.referencia_criada_id not in removed.elements
            and record.referencia_criada_id not in removed_relation_ids
        ),
    )


def _element_depends_on_removed_reference(
    element: object,
    removed_poles: set[UUID],
    removed_points: set[UUID],
) -> bool:
    if isinstance(element, (EstruturaMt, EstruturaBt)):
        return element.poste_id in removed_poles or bool(
            set(element.pontos_fixados_ids).intersection(removed_points)
        )
    if isinstance(element, Equipamento):
        return element.poste_id in removed_poles
    if isinstance(element, Cabo):
        return bool(
            {
                element.ponto_origem_id,
                element.ponto_destino_id,
                *element.pontos_intermediarios_ids,
            }.intersection(removed_points)
            or set(element.postes_apoio_ids).intersection(removed_poles)
        )
    return False
