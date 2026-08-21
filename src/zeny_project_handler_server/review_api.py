"""Projeções e mutações HTTP da revisão humana pertencentes ao servidor."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from threading import RLock
from typing import Any, Never
from uuid import UUID, uuid5

from sqlalchemy import Engine, select

from zeny_project_handler.adapters.persistence import SqlAlchemyUnitOfWork
from zeny_project_handler.adapters.persistence.schema import projects
from zeny_project_handler.application.errors import RevisaoHumanaError
from zeny_project_handler.application.human_review import (
    DadosElementoRevisao,
    ServicoRevisaoHumana,
    SessaoRevisao,
)
from zeny_project_handler.application.spans import VaoDetectado, detectar_vaos
from zeny_project_handler.domain.analysis import (
    DecisaoRevisao,
    EvidenciaDocumento,
    PropostaElemento,
    PropostaRelacao,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico, TipoEquipamento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    OrigemComprimentoVao,
    SituacaoProjeto,
    TipoDecisaoRevisao,
    TipoGeometria,
)
from zeny_project_handler.domain.project import (
    Cabo,
    ElementoProjetoType,
    Poste,
    Projeto,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler_contracts.base import (
    CatalogItemId,
    DocumentId,
    ElementId,
    EvidenceId,
    PageId,
    ProjectId,
    ProposalId,
    RegionId,
    RelationId,
    ReviewSessionId,
)
from zeny_project_handler_contracts.common import (
    EvidenceNavigationDto,
    NormalizedBoxDto,
    NormalizedPointDto,
    PageMetadataDto,
)
from zeny_project_handler_contracts.enums import (
    ElementCategory,
    ElementSituation,
    ReviewDecision,
    ReviewGeometryKind,
    ReviewProposalKind,
    ReviewReferenceKind,
    ReviewState,
    SpanLengthSource,
)
from zeny_project_handler_contracts.review import (
    AcceptReviewProposalRequest,
    AnalysisRegionDto,
    ConfirmedElementDto,
    ConfirmedRelationDto,
    CreateManualElementRequest,
    CreateManualRelationRequest,
    DetectedSpanDto,
    RejectReviewProposalRequest,
    ReviewAuditDto,
    ReviewCatalogItemDto,
    ReviewDecisionResponse,
    ReviewElementInputDto,
    ReviewGeometryDto,
    ReviewOverlayDto,
    ReviewProjectSummaryDto,
    ReviewProjectSummaryListResponse,
    ReviewProposalDto,
    ReviewReferenceDto,
    ReviewRelationDto,
    ReviewSessionResponse,
)
from zeny_project_handler_server.api_errors import (
    StaleStateError,
    resource_not_found,
    validation_error,
)
from zeny_project_handler_server.dto_values import decimal_string

_SESSION_NAMESPACE = UUID("8314f77e-f4d8-4518-a63d-90a44785ef5f")


class ReviewApiService:
    """Converta o domínio em DTOs prontos e serialize decisões concorrentes."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._service = ServicoRevisaoHumana(self._unit_of_work)
        self._lock = RLock()

    def _unit_of_work(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._engine)

    def list_projects(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ReviewProjectSummaryListResponse:
        summaries = self._service.listar_projetos()
        items = tuple(
            self._project_summary(summary.projeto_id)
            for summary in summaries[offset : offset + limit]
        )
        return ReviewProjectSummaryListResponse(
            items=items,
            page=PageMetadataDto(limit=limit, offset=offset, total=len(summaries)),
        )

    def get_session(self, project_id: UUID) -> ReviewSessionResponse:
        try:
            session = self._service.carregar_sessao(project_id)
        except RevisaoHumanaError as error:
            raise validation_error(str(error)) from error
        version, _updated_at = self._project_metadata(project_id)
        return _session_dto(session, project_version=version)

    def list_semantic_projects(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> ReviewProjectSummaryListResponse:
        """Liste sessões analisadas mesmo quando não produziram propostas."""
        summaries = self._service.listar_projetos_semanticos()
        items = tuple(
            self._semantic_project_summary(summary.projeto_id)
            for summary in summaries[offset : offset + limit]
        )
        return ReviewProjectSummaryListResponse(
            items=items,
            page=PageMetadataDto(limit=limit, offset=offset, total=len(summaries)),
        )

    def get_semantic_session(self, project_id: UUID) -> ReviewSessionResponse:
        """Projete uma sessão concluída sem exigir propostas de revisão."""
        try:
            session = self._service.carregar_sessao_semantica(project_id)
        except RevisaoHumanaError as error:
            raise validation_error(str(error)) from error
        version, _updated_at = self._project_metadata(project_id)
        return _session_dto(session, project_version=version)

    def accept(
        self,
        proposal_id: UUID,
        request: AcceptReviewProposalRequest,
    ) -> ReviewDecisionResponse:
        with self._lock:
            project_id, current, proposal = self._proposal_context(proposal_id)
            self._require_session(current, request.expected_review_session_id)
            try:
                if isinstance(proposal, PropostaRelacao):
                    if request.adjustments is not None:
                        raise validation_error("Uma relação não aceita ajustes de elemento.")
                    decision = self._service.confirmar_relacao(
                        proposal_id,
                        revisor=request.author,
                        motivo=request.reason,
                    )
                else:
                    if request.adjustments is None:
                        raise validation_error("Informe os dados confirmados do elemento.")
                    self._validate_element_scope(project_id, request.adjustments)
                    decision = self._service.confirmar_elemento(
                        proposal_id,
                        _element_data(request.adjustments),
                        revisor=request.author,
                        motivo=request.reason,
                    )
            except RevisaoHumanaError as error:
                self._raise_review_mutation_error(error, project_id)
            return self._decision_response(project_id, decision)

    def reject(
        self,
        proposal_id: UUID,
        request: RejectReviewProposalRequest,
    ) -> ReviewDecisionResponse:
        with self._lock:
            project_id, current, _proposal = self._proposal_context(proposal_id)
            self._require_session(current, request.expected_review_session_id)
            try:
                decision = self._service.rejeitar(
                    proposal_id,
                    revisor=request.author,
                    motivo=request.reason,
                )
            except RevisaoHumanaError as error:
                self._raise_review_mutation_error(error, project_id)
            return self._decision_response(project_id, decision)

    def create_manual_element(
        self,
        project_id: UUID,
        request: CreateManualElementRequest,
    ) -> ReviewDecisionResponse:
        with self._lock:
            self._require_project_version(project_id, request.expected_project_version)
            self._validate_element_scope(project_id, request.element)
            try:
                element_id = self._service.criar_elemento_manual(
                    project_id,
                    _element_data(request.element),
                    revisor=request.author,
                    motivo=request.reason,
                )
            except RevisaoHumanaError as error:
                raise validation_error(str(error)) from error
            return self._manual_response(
                project_id,
                reference_id=element_id,
                author=request.author,
                reason=request.reason,
                element=True,
            )

    def create_manual_relation(
        self,
        project_id: UUID,
        request: CreateManualRelationRequest,
    ) -> ReviewDecisionResponse:
        with self._lock:
            self._require_project_version(project_id, request.expected_project_version)
            self._validate_relation_scope(
                project_id,
                request.source_reference_id,
                request.target_reference_id,
            )
            try:
                relation_id = self._service.criar_relacao_manual(
                    project_id,
                    tipo_relacao=request.relation_type,
                    origem_id=request.source_reference_id,
                    destino_id=request.target_reference_id,
                    revisor=request.author,
                    motivo=request.reason,
                )
            except RevisaoHumanaError as error:
                raise validation_error(str(error)) from error
            return self._manual_response(
                project_id,
                reference_id=relation_id,
                author=request.author,
                reason=request.reason,
                element=False,
            )

    def _project_summary(self, project_id: UUID) -> ReviewProjectSummaryDto:
        session = self._service.carregar_sessao(project_id)
        pending = sum(
            item.estado_revisao in {EstadoRevisao.PROPOSTA, EstadoRevisao.CONFLITANTE}
            for item in session.propostas
        )
        analyzed_at = max(
            (item.finalizada_em or item.iniciada_em for item in session.execucoes),
        )
        return ReviewProjectSummaryDto(
            project_id=ProjectId(project_id),
            service_note=session.projeto.nome,
            pending_proposal_count=pending,
            analyzed_at=analyzed_at,
        )

    def _semantic_project_summary(self, project_id: UUID) -> ReviewProjectSummaryDto:
        session = self._service.carregar_sessao_semantica(project_id)
        pending = sum(
            item.estado_revisao in {EstadoRevisao.PROPOSTA, EstadoRevisao.CONFLITANTE}
            for item in session.propostas
        )
        analyzed_at = max(item.finalizada_em or item.iniciada_em for item in session.execucoes)
        return ReviewProjectSummaryDto(
            project_id=ProjectId(project_id),
            service_note=session.projeto.nome,
            pending_proposal_count=pending,
            analyzed_at=analyzed_at,
        )

    def _proposal_context(
        self,
        proposal_id: UUID,
    ) -> tuple[UUID, ReviewSessionResponse, PropostaElemento | PropostaRelacao]:
        with self._unit_of_work() as work:
            proposal = work.propostas.obter(proposal_id)
            if proposal is None:
                raise resource_not_found("Proposta de revisão não encontrada.")
            execution = work.execucoes_analise.obter(proposal.execucao_id)
            if execution is None:
                raise resource_not_found("Execução da proposta não encontrada.")
            project_id = execution.projeto_id
        return project_id, self.get_session(project_id), proposal

    @staticmethod
    def _require_session(current: ReviewSessionResponse, expected: ReviewSessionId) -> None:
        if current.review_session_id != expected:
            raise StaleStateError(current.project_version)

    def _require_project_version(self, project_id: UUID, expected: int) -> None:
        current, _updated_at = self._project_metadata(project_id)
        if current != expected:
            raise StaleStateError(current)

    def _project_metadata(self, project_id: UUID) -> tuple[int, datetime]:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(projects.c.version, projects.c.updated_at).where(
                    projects.c.id == str(project_id)
                )
            ).one_or_none()
        if row is None:
            raise resource_not_found("Projeto não encontrado para revisão.")
        return int(row.version), datetime.fromisoformat(str(row.updated_at))

    def _project(self, project_id: UUID) -> Projeto:
        with self._unit_of_work() as work:
            project = work.projetos.obter(project_id)
        if project is None:
            raise resource_not_found("Projeto não encontrado para revisão.")
        return project

    def _validate_element_scope(
        self,
        project_id: UUID,
        value: ReviewElementInputDto,
    ) -> None:
        project = self._project(project_id)
        page_ids = {page.id for document in project.documentos for page in document.paginas}
        if value.geometry.page_id.root not in page_ids:
            raise validation_error("A geometria deve pertencer a uma página do projeto.")
        element_ids = {item.id for item in project.elementos}
        point_ids = {item.id for item in project.pontos_rede}
        if value.pole_id is not None and value.pole_id.root not in element_ids:
            raise validation_error("O poste informado não pertence ao projeto.")
        if value.origin_point_id is not None and value.origin_point_id not in point_ids:
            raise validation_error("O ponto de origem não pertence ao projeto.")
        if value.target_point_id is not None and value.target_point_id not in point_ids:
            raise validation_error("O ponto de destino não pertence ao projeto.")

    def _validate_relation_scope(
        self,
        project_id: UUID,
        source_id: UUID,
        target_id: UUID,
    ) -> None:
        project = self._project(project_id)
        reference_ids = {
            *(item.id for item in project.elementos),
            *(item.id for item in project.pontos_rede),
            *(item.id for item in project.terminais),
        }
        if source_id not in reference_ids or target_id not in reference_ids:
            raise validation_error("As referências da relação devem pertencer ao projeto.")

    def _raise_review_mutation_error(
        self,
        error: RevisaoHumanaError,
        project_id: UUID,
    ) -> Never:
        message = str(error)
        if "já possui" in message or "não está pendente" in message:
            current, _updated_at = self._project_metadata(project_id)
            raise StaleStateError(current) from error
        raise validation_error(message) from error

    def _decision_response(
        self,
        project_id: UUID,
        decision: DecisaoRevisao,
    ) -> ReviewDecisionResponse:
        version, _updated_at = self._project_metadata(project_id)
        return ReviewDecisionResponse(
            proposal_id=ProposalId(decision.proposta_id),
            element_id=(
                ElementId(decision.elemento_confirmado_id)
                if decision.elemento_confirmado_id is not None
                else None
            ),
            relation_id=(
                RelationId(decision.relacao_confirmada_id)
                if decision.relacao_confirmada_id is not None
                else None
            ),
            decision=_decision(decision.decisao),
            review_state=_decision_state(decision.decisao),
            author=decision.revisor,
            decided_at=decision.decidida_em,
            reason=decision.motivo,
            project_version=version,
        )

    def _manual_response(
        self,
        project_id: UUID,
        *,
        reference_id: UUID,
        author: str,
        reason: str | None,
        element: bool,
    ) -> ReviewDecisionResponse:
        version, updated_at = self._project_metadata(project_id)
        return ReviewDecisionResponse(
            element_id=ElementId(reference_id) if element else None,
            relation_id=RelationId(reference_id) if not element else None,
            decision=ReviewDecision.CREATE_MANUAL,
            review_state=ReviewState.ACCEPTED,
            author=author,
            decided_at=updated_at,
            reason=reason,
            project_version=version,
        )


def _session_dto(session: SessaoRevisao, *, project_version: int) -> ReviewSessionResponse:
    project = session.projeto
    proposal_elements = tuple(
        item for item in session.propostas if isinstance(item, PropostaElemento)
    )
    proposal_relations = tuple(
        item for item in session.propostas if isinstance(item, PropostaRelacao)
    )
    evidence_by_id = {item.id: item for item in session.evidencias}
    document_by_page = {
        page.id: document for document in project.documentos for page in document.paginas
    }
    page_number = {
        page_id: index for index, page_id in enumerate(project.ordem_leitura_paginas, start=1)
    }
    decisions = {item.proposta_id: item for item in session.decisoes}
    element_by_id = {item.id: item for item in project.elementos}
    proposal_by_id = {item.id: item for item in proposal_elements}
    relation_by_id = {item.id: item for item in proposal_relations}
    proposal_dtos = tuple(
        _proposal_dto(
            proposal,
            session=session,
            evidence_by_id=evidence_by_id,
            document_by_page=document_by_page,
            proposal_by_id=proposal_by_id,
            relation_by_id=relation_by_id,
            decision=decisions.get(proposal.id),
        )
        for proposal in proposal_elements
    )
    relation_dtos = tuple(
        _relation_dto(
            proposal,
            evidence_by_id=evidence_by_id,
            document_by_page=document_by_page,
            decision=decisions.get(proposal.id),
        )
        for proposal in proposal_relations
    )
    spans = tuple(
        _span_dto(
            item,
            index=index,
            project=project,
            catalog=session.catalogo,
            decisions=session.decisoes,
            page_number=page_number,
        )
        for index, item in enumerate(detectar_vaos(project), start=1)
    )
    signature = _semantic_signature(session, project_version=project_version, spans=spans)
    return ReviewSessionResponse(
        review_session_id=ReviewSessionId(uuid5(_SESSION_NAMESPACE, signature)),
        project_id=ProjectId(project.id),
        service_note=project.nome,
        project_version=project_version,
        semantic_signature=signature,
        page_order=tuple(PageId(item) for item in project.ordem_leitura_paginas),
        catalog_items=tuple(
            ReviewCatalogItemDto(
                catalog_item_id=CatalogItemId(item.id),
                category=_category(item.categoria),
                code=item.codigo,
                description=item.descricao,
                label=f"{item.codigo} — {item.descricao}",
            )
            for item in session.catalogo.itens
            if item.ativo
        ),
        references=_references(project),
        confirmed_elements=tuple(
            ConfirmedElementDto(
                element_id=ElementId(item.id),
                category=_category(item.categoria),
                situation=_situation(item.situacao),
                label=_element_label(item),
                catalog_label=_catalog_label(item.tipo_catalogo_id, session.catalogo),
                geometry=_geometry(item.geometria) if item.geometria is not None else None,
            )
            for item in project.elementos
        ),
        confirmed_relations=tuple(
            ConfirmedRelationDto(
                relation_id=RelationId(item.id),
                relation_type=item.tipo_relacao,
                source_reference_id=item.origem_id,
                target_reference_id=item.destino_id,
                label=f"{item.tipo_relacao}: {item.origem_id} → {item.destino_id}",
            )
            for item in project.relacoes_confirmadas
        ),
        regions=tuple(
            _region_dto(
                region,
                index=index,
                session=session,
                proposal_dtos={item.proposal_id.root: item for item in proposal_dtos},
                document_by_page=document_by_page,
            )
            for index, region in enumerate(session.regioes, start=1)
        ),
        proposals=proposal_dtos,
        relations=relation_dtos,
        spans=spans,
        audit=_audit(session, element_by_id),
    )


def _proposal_dto(
    proposal: PropostaElemento,
    *,
    session: SessaoRevisao,
    evidence_by_id: dict[UUID, EvidenciaDocumento],
    document_by_page: dict[UUID, Any],
    proposal_by_id: dict[UUID, PropostaElemento],
    relation_by_id: dict[UUID, PropostaRelacao],
    decision: DecisaoRevisao | None,
) -> ReviewProposalDto:
    label = _proposal_label(proposal, session.catalogo)
    catalog_label = (
        _catalog_label(proposal.tipo_catalogo_sugerido_id, session.catalogo)
        if proposal.tipo_catalogo_sugerido_id is not None
        else "Não catalogado"
    )
    state = _review_state(proposal.estado_revisao, decision)
    geometry = _geometry(proposal.geometria)
    link = _cable_label_geometry(proposal, evidence_by_id) or proposal.geometria
    relationships = tuple(
        label
        for region in session.regioes
        if proposal.id in region.elemento_ids
        for label in _relationship_labels(
            proposal,
            region.vinculo_ids,
            proposal_by_id,
            relation_by_id,
            session.catalogo,
        )
    )
    confidence = decimal_string(proposal.confianca) if proposal.confianca is not None else None
    return ReviewProposalDto(
        proposal_id=ProposalId(proposal.id),
        kind=ReviewProposalKind.ELEMENT,
        category=_category(proposal.categoria),
        situation=_situation(proposal.situacao_projeto),
        review_state=state,
        state_label=_review_state_label(proposal.estado_revisao, decision),
        situation_label=_situation_label(proposal.situacao_projeto),
        label=label,
        catalog_item_id=(
            CatalogItemId(proposal.tipo_catalogo_sugerido_id)
            if proposal.tipo_catalogo_sugerido_id is not None
            else None
        ),
        catalog_label=catalog_label,
        detection_summary=f"{_category_label(proposal.categoria)} · {catalog_label}",
        observed_code=proposal.codigo_observado,
        confidence=confidence,
        attributes={key: _json_value(value) for key, value in proposal.atributos_sugeridos},
        evidence=_evidence_navigation(
            proposal.evidencia_ids,
            evidence_by_id,
            document_by_page,
        ),
        relationship_labels=relationships,
        requires_review=proposal.estado_revisao
        in {EstadoRevisao.PROPOSTA, EstadoRevisao.CONFLITANTE},
        overlay=ReviewOverlayDto(
            proposal_id=ProposalId(proposal.id),
            geometry=geometry,
            link_geometry=_geometry(link),
            label=label,
            category=_category(proposal.categoria),
            situation=_situation(proposal.situacao_projeto),
            review_state=state,
            confidence=confidence,
        ),
    )


def _relation_dto(
    proposal: PropostaRelacao,
    *,
    evidence_by_id: dict[UUID, EvidenciaDocumento],
    document_by_page: dict[UUID, Any],
    decision: DecisaoRevisao | None,
) -> ReviewRelationDto:
    return ReviewRelationDto(
        proposal_id=ProposalId(proposal.id),
        relation_type=proposal.tipo_relacao,
        label=f"Relação proposta: {proposal.tipo_relacao}",
        source_reference_id=proposal.origem_referencia_id,
        target_reference_id=proposal.destino_referencia_id,
        review_state=_review_state(proposal.estado_revisao, decision),
        state_label=_review_state_label(proposal.estado_revisao, decision),
        confidence=(decimal_string(proposal.confianca) if proposal.confianca is not None else None),
        evidence=_evidence_navigation(
            proposal.evidencia_ids,
            evidence_by_id,
            document_by_page,
        ),
        requires_review=proposal.estado_revisao
        in {EstadoRevisao.PROPOSTA, EstadoRevisao.CONFLITANTE},
        confirmed_relation_id=(
            RelationId(decision.relacao_confirmada_id)
            if decision is not None and decision.relacao_confirmada_id is not None
            else None
        ),
    )


def _region_dto(
    region: Any,
    *,
    index: int,
    session: SessaoRevisao,
    proposal_dtos: dict[UUID, ReviewProposalDto],
    document_by_page: dict[UUID, Any],
) -> AnalysisRegionDto:
    proposals = tuple(proposal_dtos[item] for item in region.elemento_ids if item in proposal_dtos)
    label = region.rotulo_ponto or f"Ponto {index}"
    document = document_by_page.get(region.pagina_id)
    page = (
        next(
            (item for item in document.paginas if item.id == region.pagina_id),
            None,
        )
        if document is not None
        else None
    )
    location = (
        f"{label} · {document.nome_arquivo} · página {page.numero}"
        if document is not None and page is not None
        else label
    )
    coordinate = region.coordenada
    return AnalysisRegionDto(
        region_id=RegionId(region.id),
        page_id=PageId(region.pagina_id),
        label=label,
        location_label=location,
        coordinate_label=(
            f"E {coordinate.leste:.0f} · N {coordinate.norte:.0f}"
            if coordinate is not None
            else "Sem coordenada identificada"
        ),
        action_summary=_region_action_counts(proposals) or "Ponto identificado",
        detail_summary=_region_summary(proposals) or "Identificador de ponto reconhecido no PDF",
        geometry=_geometry(region.geometria),
        proposal_ids=tuple(ProposalId(item) for item in region.elemento_ids),
        relation_proposal_ids=tuple(ProposalId(item) for item in region.vinculo_ids),
        coordinate_east=decimal_string(coordinate.leste) if coordinate is not None else None,
        coordinate_north=decimal_string(coordinate.norte) if coordinate is not None else None,
    )


def _span_dto(
    span: VaoDetectado,
    *,
    index: int,
    project: Projeto,
    catalog: CatalogoTecnico,
    decisions: tuple[DecisaoRevisao, ...],
    page_number: dict[UUID, int],
) -> DetectedSpanDto:
    elements = {item.id: item for item in project.elementos}
    origin = elements.get(span.poste_origem_id) if span.poste_origem_id is not None else None
    destination = elements.get(span.poste_destino_id) if span.poste_destino_id is not None else None
    cable = elements.get(span.cabo_id)
    proposal_id = next(
        (item.proposta_id for item in decisions if item.elemento_confirmado_id == span.cabo_id),
        None,
    )
    label = (
        cable.identificador_operacional
        if isinstance(cable, Cabo) and cable.identificador_operacional
        else f"Vão {index}"
    )
    source = {
        OrigemComprimentoVao.ANOTACAO_DESENHO: SpanLengthSource.DRAWING_LABEL,
        OrigemComprimentoVao.INFORMADO: SpanLengthSource.DRAWING_LABEL,
        OrigemComprimentoVao.COORDENADAS: SpanLengthSource.COORDINATE_DISTANCE,
        None: SpanLengthSource.UNAVAILABLE,
    }[span.origem_comprimento]
    source_label = {
        OrigemComprimentoVao.ANOTACAO_DESENHO: "Anotação do desenho",
        OrigemComprimentoVao.INFORMADO: "Comprimento informado",
        OrigemComprimentoVao.COORDENADAS: "Distância entre coordenadas",
        None: "-",
    }[span.origem_comprimento]
    page = span.geometria.pagina_id if span.geometria is not None else None
    return DetectedSpanDto(
        span_id=span.id,
        proposal_id=ProposalId(proposal_id) if proposal_id is not None else None,
        start_element_id=(
            ElementId(span.poste_origem_id) if span.poste_origem_id is not None else None
        ),
        end_element_id=(
            ElementId(span.poste_destino_id) if span.poste_destino_id is not None else None
        ),
        cable_element_id=ElementId(span.cabo_id),
        label=label,
        situation=_situation(span.situacao),
        situation_label=_situation_label(span.situacao),
        start_label=_project_element_label(origin, catalog=catalog),
        end_label=_project_element_label(destination, catalog=catalog),
        cable_label=_project_element_label(cable, catalog=catalog),
        length=decimal_string(span.comprimento_m) if span.comprimento_m is not None else None,
        length_label=(
            f"{span.comprimento_m.quantize(Decimal('0.01')):f} m".replace(".", ",")
            if span.comprimento_m is not None
            else "Não identificado"
        ),
        length_source=source,
        length_source_label=source_label,
        page_label=f"Folha {page_number[page]}" if page in page_number else "-",
        geometry=_geometry(span.geometria) if span.geometria is not None else None,
        evidence=(),
    )


def _audit(
    session: SessaoRevisao,
    element_by_id: dict[UUID, ElementoProjetoType],
) -> tuple[ReviewAuditDto, ...]:
    proposal_by_id = {item.id: item for item in session.propostas}
    decisions = tuple(
        ReviewAuditDto(
            audit_id=item.id,
            action=_decision(item.decisao),
            author=item.revisor,
            occurred_at=item.decidida_em,
            reason=item.motivo,
            proposal_id=ProposalId(item.proposta_id),
            created_reference_id=item.elemento_confirmado_id or item.relacao_confirmada_id,
            previous_values=_proposal_audit_values(proposal_by_id.get(item.proposta_id)),
            confirmed_values=_element_audit_values(
                element_by_id.get(item.elemento_confirmado_id)
                if item.elemento_confirmado_id is not None
                else None
            ),
        )
        for item in session.decisoes
    )
    manual = tuple(
        ReviewAuditDto(
            audit_id=item.id,
            action=ReviewDecision.CREATE_MANUAL,
            author=item.revisor,
            occurred_at=item.realizada_em,
            reason=item.motivo,
            created_reference_id=item.referencia_criada_id,
            confirmed_values={"manual_action": item.acao.value},
        )
        for item in session.projeto.historico_revisao_manual
    )
    return tuple(
        sorted((*decisions, *manual), key=lambda item: (item.occurred_at, str(item.audit_id)))
    )


def _references(project: Projeto) -> tuple[ReviewReferenceDto, ...]:
    elements = tuple(
        ReviewReferenceDto(
            reference_id=item.id,
            kind=ReviewReferenceKind.ELEMENT,
            label=_element_label(item),
            category=_category(item.categoria),
        )
        for item in project.elementos
    )
    points = tuple(
        ReviewReferenceDto(
            reference_id=item.id,
            kind=ReviewReferenceKind.NETWORK_POINT,
            label=item.nome,
        )
        for item in project.pontos_rede
    )
    terminals = tuple(
        ReviewReferenceDto(
            reference_id=item.id,
            kind=ReviewReferenceKind.TERMINAL,
            label=item.nome,
        )
        for item in project.terminais
    )
    return (*elements, *points, *terminals)


def _element_data(value: ReviewElementInputDto) -> DadosElementoRevisao:
    return DadosElementoRevisao(
        categoria=_domain_category(value.category),
        tipo_catalogo_id=value.catalog_item_id.root,
        situacao=_domain_situation(value.situation),
        geometria=_domain_geometry(value.geometry),
        codigo_observado=value.observed_code,
        poste_id=value.pole_id.root if value.pole_id is not None else None,
        ponto_origem_id=value.origin_point_id,
        ponto_destino_id=value.target_point_id,
    )


def _geometry(value: GeometriaDocumento) -> ReviewGeometryDto:
    return ReviewGeometryDto(
        page_id=PageId(value.pagina_id),
        kind={
            TipoGeometria.PONTO: ReviewGeometryKind.POINT,
            TipoGeometria.CAIXA: ReviewGeometryKind.BOX,
            TipoGeometria.POLILINHA: ReviewGeometryKind.POLYLINE,
            TipoGeometria.POLIGONO: ReviewGeometryKind.POLYGON,
        }[value.tipo],
        points=tuple(
            NormalizedPointDto(x=decimal_string(item.x), y=decimal_string(item.y))
            for item in value.pontos
        ),
    )


def _domain_geometry(value: ReviewGeometryDto) -> GeometriaDocumento:
    return GeometriaDocumento(
        pagina_id=value.page_id.root,
        tipo={
            ReviewGeometryKind.POINT: TipoGeometria.PONTO,
            ReviewGeometryKind.BOX: TipoGeometria.CAIXA,
            ReviewGeometryKind.POLYLINE: TipoGeometria.POLILINHA,
            ReviewGeometryKind.POLYGON: TipoGeometria.POLIGONO,
        }[value.kind],
        pontos=tuple(PontoNormalizado(Decimal(item.x), Decimal(item.y)) for item in value.points),
    )


def _evidence_navigation(
    evidence_ids: tuple[UUID, ...],
    evidence_by_id: dict[UUID, EvidenciaDocumento],
    document_by_page: dict[UUID, Any],
) -> tuple[EvidenceNavigationDto, ...]:
    result: list[EvidenceNavigationDto] = []
    for evidence_id in evidence_ids:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            continue
        document = document_by_page.get(evidence.pagina_id)
        if document is None:
            continue
        result.append(
            EvidenceNavigationDto(
                evidence_id=EvidenceId(evidence.id),
                document_id=DocumentId(document.id),
                page_id=PageId(evidence.pagina_id),
                geometry=_box(evidence.geometria),
                label=evidence.conteudo_bruto,
            )
        )
    return tuple(result)


def _box(geometry: GeometriaDocumento) -> NormalizedBoxDto:
    xs = [item.x for item in geometry.pontos]
    ys = [item.y for item in geometry.pontos]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    return NormalizedBoxDto(
        x=decimal_string(left),
        y=decimal_string(top),
        width=decimal_string(right - left),
        height=decimal_string(bottom - top),
    )


def _semantic_signature(
    session: SessaoRevisao,
    *,
    project_version: int,
    spans: tuple[DetectedSpanDto, ...],
) -> str:
    payload = {
        "project_id": str(session.projeto.id),
        "project_version": project_version,
        "executions": [str(item.id) for item in session.execucoes],
        "proposals": [[str(item.id), item.estado_revisao.value] for item in session.propostas],
        "decisions": [
            [str(item.id), item.decisao.value, item.decidida_em.isoformat()]
            for item in session.decisoes
        ],
        "manual": [
            [str(item.id), item.acao.value, item.realizada_em.isoformat()]
            for item in session.projeto.historico_revisao_manual
        ],
        "regions": [str(item.id) for item in session.regioes],
        "spans": [str(item.span_id) for item in spans],
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _review_state(
    state: EstadoRevisao,
    decision: DecisaoRevisao | None,
) -> ReviewState:
    if state is EstadoRevisao.PROPOSTA:
        return ReviewState.PENDING
    if state is EstadoRevisao.CONFLITANTE:
        return ReviewState.CONFLICTING
    if state is EstadoRevisao.REJEITADA:
        return ReviewState.REJECTED
    if decision is not None and decision.decisao is TipoDecisaoRevisao.AJUSTAR:
        return ReviewState.ADJUSTED
    return ReviewState.ACCEPTED


def _review_state_label(
    state: EstadoRevisao,
    decision: DecisaoRevisao | None,
) -> str:
    return {
        ReviewState.PENDING: "Proposta",
        ReviewState.CONFLICTING: "Conflitante",
        ReviewState.ACCEPTED: "Confirmada",
        ReviewState.ADJUSTED: "Ajustada",
        ReviewState.REJECTED: "Rejeitada",
    }[_review_state(state, decision)]


def _decision(value: TipoDecisaoRevisao) -> ReviewDecision:
    return {
        TipoDecisaoRevisao.ACEITAR: ReviewDecision.ACCEPT,
        TipoDecisaoRevisao.AJUSTAR: ReviewDecision.ADJUST,
        TipoDecisaoRevisao.REJEITAR: ReviewDecision.REJECT,
    }[value]


def _decision_state(value: TipoDecisaoRevisao) -> ReviewState:
    return {
        TipoDecisaoRevisao.ACEITAR: ReviewState.ACCEPTED,
        TipoDecisaoRevisao.AJUSTAR: ReviewState.ADJUSTED,
        TipoDecisaoRevisao.REJEITAR: ReviewState.REJECTED,
    }[value]


def _category(value: CategoriaElemento) -> ElementCategory:
    return {
        CategoriaElemento.POSTE: ElementCategory.POLE,
        CategoriaElemento.ESTRUTURA_MT: ElementCategory.MV_STRUCTURE,
        CategoriaElemento.ESTRUTURA_BT: ElementCategory.LV_STRUCTURE,
        CategoriaElemento.CABO: ElementCategory.CABLE,
        CategoriaElemento.EQUIPAMENTO: ElementCategory.EQUIPMENT,
    }[value]


def _domain_category(value: ElementCategory) -> CategoriaElemento:
    return {
        ElementCategory.POLE: CategoriaElemento.POSTE,
        ElementCategory.MV_STRUCTURE: CategoriaElemento.ESTRUTURA_MT,
        ElementCategory.LV_STRUCTURE: CategoriaElemento.ESTRUTURA_BT,
        ElementCategory.CABLE: CategoriaElemento.CABO,
        ElementCategory.EQUIPMENT: CategoriaElemento.EQUIPAMENTO,
    }[value]


def _situation(value: SituacaoProjeto) -> ElementSituation:
    return {
        SituacaoProjeto.EXISTENTE: ElementSituation.EXISTING,
        SituacaoProjeto.INSTALAR: ElementSituation.INSTALL,
        SituacaoProjeto.REMOVER: ElementSituation.REMOVE,
    }[value]


def _domain_situation(value: ElementSituation) -> SituacaoProjeto:
    return {
        ElementSituation.EXISTING: SituacaoProjeto.EXISTENTE,
        ElementSituation.INSTALL: SituacaoProjeto.INSTALAR,
        ElementSituation.REMOVE: SituacaoProjeto.REMOVER,
    }[value]


def _situation_label(value: SituacaoProjeto) -> str:
    return {
        SituacaoProjeto.INSTALAR: "A instalar",
        SituacaoProjeto.REMOVER: "A remover",
        SituacaoProjeto.EXISTENTE: "Existente",
    }[value]


def _category_label(value: CategoriaElemento) -> str:
    return {
        CategoriaElemento.POSTE: "Poste",
        CategoriaElemento.ESTRUTURA_MT: "Estrutura MT",
        CategoriaElemento.ESTRUTURA_BT: "Estrutura BT",
        CategoriaElemento.CABO: "Cabo",
        CategoriaElemento.EQUIPAMENTO: "Equipamento",
    }[value]


def _proposal_label(proposal: PropostaElemento, catalog: CatalogoTecnico) -> str:
    if proposal.categoria is CategoriaElemento.EQUIPAMENTO:
        category = _equipment_type_label(proposal, catalog)
        if dict(proposal.atributos_sugeridos).get("reconhecido_por_simbologia") is True:
            return category
        return f"{category} {proposal.codigo_observado or ''}".strip()
    return f"{_category_label(proposal.categoria)} {proposal.codigo_observado or ''}".strip()


def _equipment_type_label(proposal: PropostaElemento, catalog: CatalogoTecnico) -> str:
    if proposal.tipo_catalogo_sugerido_id is not None:
        catalog_item = catalog.item_por_id(proposal.tipo_catalogo_sugerido_id)
        if isinstance(catalog_item, TipoEquipamento):
            option_label = next(
                (
                    option.rotulo
                    for group in catalog.grupos_opcao
                    if group.chave == "classe_equipamento"
                    for option in group.opcoes
                    if option.id == catalog_item.classe_equipamento_opcao_id
                ),
                None,
            )
            if option_label is not None:
                return option_label.capitalize()
    suggested = dict(proposal.atributos_sugeridos).get("classe_equipamento")
    if isinstance(suggested, str) and suggested.strip():
        labels = {
            "ATERRAMENTO": "Aterramento",
            "PARA_RAIOS_BT": "Para-raios BT",
            "PARA_RAIOS_MT": "Para-raios MT",
        }
        return labels.get(suggested.strip().upper(), suggested.replace("_", " ").capitalize())
    return "Equipamento"


def _catalog_label(item_id: UUID, catalog: CatalogoTecnico) -> str:
    item = catalog.item_por_id(item_id)
    return f"{item.codigo} — {item.descricao}" if item is not None else "Não catalogado"


def _element_label(element: ElementoProjetoType) -> str:
    return f"{_category_label(element.categoria)}: {element.codigo_observado or element.id}"


def _project_element_label(
    element: ElementoProjetoType | None,
    *,
    catalog: CatalogoTecnico,
) -> str:
    if element is None:
        return "-"
    if isinstance(element, Poste):
        reference = (
            element.identificador_operacional
            or element.referencia_desenho
            or element.codigo_observado
        )
        coordinate = element.coordenada_campo
        if coordinate is not None:
            coordinate_label = f"E {coordinate.leste:f} · N {coordinate.norte:f}"
            return f"{reference} · {coordinate_label}" if reference else coordinate_label
        return f"{reference} · {str(element.id)[:8]}" if reference else str(element.id)
    if isinstance(element, Cabo):
        return _catalog_label(element.tipo_catalogo_id, catalog)
    return element.codigo_observado or element.identificador_operacional or str(element.id)


def _relationship_labels(
    element: PropostaElemento,
    relation_ids: tuple[UUID, ...],
    elements: dict[UUID, PropostaElemento],
    relations: dict[UUID, PropostaRelacao],
    catalog: CatalogoTecnico,
) -> tuple[str, ...]:
    labels: list[str] = []
    for relation_id in relation_ids:
        relation = relations.get(relation_id)
        if relation is None:
            continue
        if relation.origem_referencia_id == element.id:
            related_id, direction = relation.destino_referencia_id, "→"
        elif relation.destino_referencia_id == element.id:
            related_id, direction = relation.origem_referencia_id, "←"
        else:
            continue
        related = elements.get(related_id)
        if related is not None:
            labels.append(
                f"{relation.tipo_relacao.replace('_', ' ').lower()} {direction} "
                f"{_proposal_label(related, catalog)}"
            )
    return tuple(labels)


def _region_action_counts(proposals: tuple[ReviewProposalDto, ...]) -> str:
    parts: list[str] = []
    for situation, singular, plural in (
        (ElementSituation.REMOVE, "remover", "remover"),
        (ElementSituation.INSTALL, "instalar", "instalar"),
        (ElementSituation.EXISTING, "existente", "existentes"),
    ):
        count = sum(item.situation is situation for item in proposals)
        if count:
            parts.append(f"{count} {singular if count == 1 else plural}")
    return " · ".join(parts)


def _region_summary(proposals: tuple[ReviewProposalDto, ...]) -> str:
    parts: list[str] = []
    for situation, verb in (
        (ElementSituation.REMOVE, "Remover"),
        (ElementSituation.INSTALL, "Instalar"),
        (ElementSituation.EXISTING, "Existente"),
    ):
        labels = tuple(item.label for item in proposals if item.situation is situation)
        if labels:
            parts.append(f"{verb}: {', '.join(labels)}")
    return " · ".join(parts)


def _cable_label_geometry(
    proposal: PropostaElemento,
    evidence_by_id: dict[UUID, EvidenciaDocumento],
) -> GeometriaDocumento | None:
    if proposal.categoria is not CategoriaElemento.CABO:
        return None
    attributes = dict(proposal.atributos_sugeridos)
    explicit = _safe_uuid(attributes.get("evidencia_rotulo_id"))
    if explicit is not None and (evidence := evidence_by_id.get(explicit)) is not None:
        return evidence.geometria
    excluded = {
        identifier
        for key in ("evidencia_identificador_id", "evidencia_comprimento_id")
        if (identifier := _safe_uuid(attributes.get(key))) is not None
    }
    candidates = tuple(
        item
        for item_id in proposal.evidencia_ids
        if item_id not in excluded
        if (item := evidence_by_id.get(item_id)) is not None
        and item.pagina_id == proposal.geometria.pagina_id
    )
    observed = (proposal.codigo_observado or "").casefold()
    selected = min(
        candidates,
        key=lambda item: (
            0 if observed and observed in (item.conteudo_bruto or "").casefold() else 1,
            str(item.id),
        ),
        default=None,
    )
    return selected.geometria if selected is not None else None


def _safe_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value is not None else None
    except ValueError:
        return None


def _proposal_audit_values(value: object) -> dict[str, Any] | None:
    if isinstance(value, PropostaElemento):
        return {
            "category": value.categoria.value,
            "situation": value.situacao_projeto.value,
            "catalog_item_id": (
                str(value.tipo_catalogo_sugerido_id)
                if value.tipo_catalogo_sugerido_id is not None
                else None
            ),
            "observed_code": value.codigo_observado,
            "geometry": _geometry(value.geometria).model_dump(mode="json"),
        }
    if isinstance(value, PropostaRelacao):
        return {
            "relation_type": value.tipo_relacao,
            "source_reference_id": str(value.origem_referencia_id),
            "target_reference_id": str(value.destino_referencia_id),
        }
    return None


def _element_audit_values(value: ElementoProjetoType | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "element_id": str(value.id),
        "category": value.categoria.value,
        "situation": value.situacao.value,
        "catalog_item_id": str(value.tipo_catalogo_id),
        "observed_code": value.codigo_observado,
        "geometry": (
            _geometry(value.geometria).model_dump(mode="json")
            if value.geometria is not None
            else None
        ),
    }


def _json_value(value: object) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
