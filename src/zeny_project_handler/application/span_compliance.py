"""Fatos auditáveis da família de vãos reconhecidos no projeto."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid5

from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.compliance import (
    AlvoConformidade,
    FatoConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    OrigemComprimentoVao,
)
from zeny_project_handler.domain.values import GeometriaDocumento

from .compliance_fact_providers import ContextoProvedorFatos, criar_fato_conformidade
from .document_zones import evidencia_eh_anotacao_de_revisao
from .spans import VaoDetectado, detectar_vaos

_EXCEPTION_FLAG = "excecao_45_60_demonstrada"
_EXCEPTION_EVIDENCE_ID = "evidencia_excecao_45_60_id"
_LENGTH_EVIDENCE_ID = "evidencia_comprimento_id"
_ORDINARY_MAX_LENGTH = Decimal("45")
_EXCEPTION_MAX_LENGTH = Decimal("60")


def prover_fatos_vaos(contexto: ContextoProvedorFatos) -> tuple[FatoConformidade, ...]:
    """Publique medidas e avalie todo vão cujo comprimento esteja disponível."""
    session = contexto.sessao
    evidence_by_id = {item.id: item for item in session.evidencias}
    proposals = {
        item.id: item
        for item in session.propostas
        if isinstance(item, PropostaElemento)
        and item.estado_revisao is not EstadoRevisao.REJEITADA
        and not _proposal_uses_review_annotation(item, evidence_by_id)
    }
    proposals_by_element = _proposals_by_confirmed_element(contexto, proposals)
    targets_by_region = {
        item.referencia_id: item
        for item in contexto.alvos
        if item.tipo is TipoEscopoConformidade.REGIAO and item.referencia_id is not None
    }
    facts: list[FatoConformidade] = []
    for span in detectar_vaos(session.projeto):
        proposal = _span_proposal(span, proposals, proposals_by_element)
        region_target = _region_target(contexto, proposal, targets_by_region)
        if proposal is None or region_target is None or not _same_page(span, region_target):
            continue
        evidence = _measurement_evidence(
            span,
            proposal,
            proposals_by_element,
            evidence_by_id,
            page_id=region_target.pagina_id,
        )
        if span.comprimento_m is not None and span.origem_comprimento is not None:
            facts.append(
                criar_fato_conformidade(
                    region_target.id,
                    "vao.comprimento_m",
                    span.comprimento_m,
                    f"detectar_vaos:{span.origem_comprimento.value}",
                    evidencias=evidence,
                    confianca=proposal.confianca,
                    geometria=_measurement_geometry(span, evidence),
                )
            )
        candidate_exception_evidence = _positive_exception_evidence(
            proposal,
            evidence_by_id,
            page_id=region_target.pagina_id,
        )
        exception_evidence = (
            candidate_exception_evidence
            if span.comprimento_m is not None
            and _ORDINARY_MAX_LENGTH < span.comprimento_m <= _EXCEPTION_MAX_LENGTH
            else ()
        )
        if span.comprimento_m is not None:
            applicability_evidence = tuple(dict.fromkeys((*evidence, *exception_evidence)))
            facts.append(
                criar_fato_conformidade(
                    region_target.id,
                    "vao.aplicabilidade_excecao_45_60_resolvida",
                    True,
                    "faixa excepcional resolvida por comprimento ou evidência positiva",
                    evidencias=applicability_evidence,
                    confianca=proposal.confianca,
                    geometria=_measurement_geometry(span, evidence),
                )
            )
        if exception_evidence:
            facts.append(
                criar_fato_conformidade(
                    region_target.id,
                    "vao.excecao_45_60_demonstrada",
                    True,
                    "evidência positiva declarada para o vão",
                    evidencias=exception_evidence,
                    confianca=proposal.confianca,
                    geometria=exception_evidence[0].geometria,
                )
            )
    return tuple(facts)


def _proposals_by_confirmed_element(
    contexto: ContextoProvedorFatos,
    proposals: dict[UUID, PropostaElemento],
) -> dict[UUID, PropostaElemento]:
    result = {
        decision.elemento_confirmado_id: proposals[decision.proposta_id]
        for decision in contexto.sessao.decisoes
        if decision.elemento_confirmado_id is not None and decision.proposta_id in proposals
    }
    for proposal in proposals.values():
        result.setdefault(uuid5(proposal.id, "elemento-confirmado"), proposal)
        result.setdefault(proposal.id, proposal)
    return result


def _proposal_uses_review_annotation(
    proposal: PropostaElemento,
    evidence_by_id: dict[UUID, EvidenciaDocumento],
) -> bool:
    return any(
        evidencia_eh_anotacao_de_revisao(evidence)
        for evidence_id in proposal.evidencia_ids
        if (evidence := evidence_by_id.get(evidence_id)) is not None
    )


def _span_proposal(
    span: VaoDetectado,
    proposals: dict[UUID, PropostaElemento],
    proposals_by_element: dict[UUID, PropostaElemento],
) -> PropostaElemento | None:
    if proposal := proposals_by_element.get(span.cabo_id):
        return proposal if proposal.categoria is CategoriaElemento.CABO else None
    same_geometry = tuple(
        proposal
        for proposal in proposals.values()
        if proposal.categoria is CategoriaElemento.CABO and proposal.geometria == span.geometria
    )
    return same_geometry[0] if len(same_geometry) == 1 else None


def _region_target(
    contexto: ContextoProvedorFatos,
    proposal: PropostaElemento | None,
    targets_by_region: dict[UUID, AlvoConformidade],
) -> AlvoConformidade | None:
    if proposal is None:
        return None
    regions = tuple(
        region for region in contexto.sessao.regioes if proposal.id in region.elemento_ids
    )
    if len(regions) != 1:
        return None
    return targets_by_region.get(regions[0].id)


def _same_page(span: VaoDetectado, target: AlvoConformidade) -> bool:
    return span.geometria is None or span.geometria.pagina_id == target.pagina_id


def _measurement_evidence(
    span: VaoDetectado,
    proposal: PropostaElemento,
    proposals_by_element: dict[UUID, PropostaElemento],
    evidence_by_id: dict[UUID, EvidenciaDocumento],
    *,
    page_id: UUID | None,
) -> tuple[EvidenciaDocumento, ...]:
    if span.origem_comprimento is OrigemComprimentoVao.ANOTACAO_DESENHO:
        exact = _evidence_from_attribute(proposal, _LENGTH_EVIDENCE_ID, evidence_by_id, page_id)
        if exact:
            return exact
    source_proposals = [proposal]
    if span.origem_comprimento is OrigemComprimentoVao.COORDENADAS:
        source_proposals.extend(
            proposals_by_element[element_id]
            for element_id in (span.poste_origem_id, span.poste_destino_id)
            if element_id is not None and element_id in proposals_by_element
        )
    evidence_ids = tuple(
        dict.fromkeys(
            evidence_id
            for source_proposal in source_proposals
            for evidence_id in source_proposal.evidencia_ids
        )
    )
    return tuple(
        evidence_by_id[evidence_id]
        for evidence_id in evidence_ids
        if evidence_id in evidence_by_id and evidence_by_id[evidence_id].pagina_id == page_id
    )


def _measurement_geometry(
    span: VaoDetectado,
    evidence: tuple[EvidenciaDocumento, ...],
) -> GeometriaDocumento | None:
    if span.origem_comprimento is OrigemComprimentoVao.ANOTACAO_DESENHO and evidence:
        return evidence[0].geometria
    return span.geometria


def _positive_exception_evidence(
    proposal: PropostaElemento,
    evidence_by_id: dict[UUID, EvidenciaDocumento],
    *,
    page_id: UUID | None,
) -> tuple[EvidenciaDocumento, ...]:
    attributes = dict(proposal.atributos_sugeridos)
    if attributes.get(_EXCEPTION_FLAG) is not True:
        return ()
    return _evidence_from_attribute(
        proposal,
        _EXCEPTION_EVIDENCE_ID,
        evidence_by_id,
        page_id,
    )


def _evidence_from_attribute(
    proposal: PropostaElemento,
    attribute: str,
    evidence_by_id: dict[UUID, EvidenciaDocumento],
    page_id: UUID | None,
) -> tuple[EvidenciaDocumento, ...]:
    raw_id = dict(proposal.atributos_sugeridos).get(attribute)
    try:
        evidence_id = UUID(str(raw_id))
    except (TypeError, ValueError):
        return ()
    evidence = evidence_by_id.get(evidence_id)
    if (
        evidence is None
        or evidence.pagina_id != page_id
        or evidencia_eh_anotacao_de_revisao(evidence)
    ):
        return ()
    return (evidence,)
