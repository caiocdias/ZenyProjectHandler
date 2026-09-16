"""Physical drawing spans, including proposals still awaiting human review."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from uuid import UUID

from zeny_project_handler.application.drawing_continuations import drawing_continuations
from zeny_project_handler.application.physical_topology import physical_point_id, physical_span_id
from zeny_project_handler.domain.analysis import (
    DecisaoRevisao,
    EvidenciaDocumento,
    PropostaElemento,
)
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    ModalidadeTrecho,
    SituacaoProjeto,
    TipoGeometria,
    TipoTrechoRede,
)
from zeny_project_handler.domain.project import Cabo, Projeto
from zeny_project_handler.domain.values import GeometriaDocumento


@dataclass(frozen=True, slots=True)
class TrechoFisico:
    id: UUID
    geometria: GeometriaDocumento
    origem_id: UUID
    destino_id: UUID | None
    origem: str
    destino: str
    rotulo: str
    propostas: tuple[UUID, ...]
    cabos: tuple[UUID, ...]
    codigos: tuple[str, ...]
    situacoes: tuple[SituacaoProjeto, ...]
    comprimento_m: Decimal | None
    tipo: TipoTrechoRede
    modalidade: ModalidadeTrecho
    pendencias: tuple[str, ...]
    continuidade: bool = False
    evidencias: tuple[UUID, ...] = ()


def projetar_trechos_fisicos(
    projeto: Projeto,
    propostas: tuple[PropostaElemento, ...],
    decisoes: tuple[DecisaoRevisao, ...],
    evidencias: tuple[EvidenciaDocumento, ...] = (),
) -> tuple[TrechoFisico, ...]:
    """Group full coincident paths, never cables merely sharing length/endpoints.

    This is a read-only projection, not a new asset or an electrical connection.
    Rejected proposals and unresolved trace associations do not create spans.
    """
    groups: dict[UUID, list[PropostaElemento]] = defaultdict(list)
    labels: dict[UUID, set[str]] = defaultdict(set)
    confirmed = {item.id: item for item in projeto.elementos if isinstance(item, Cabo)}
    by_proposal = {
        decision.proposta_id: confirmed[decision.elemento_confirmado_id]
        for decision in decisoes
        if decision.elemento_confirmado_id in confirmed
    }
    effective = tuple(_effective_proposal(p, by_proposal.get(p.id)) for p in propostas)
    for proposal in effective:
        attributes = dict(proposal.atributos_sugeridos)
        if (
            proposal.categoria is not CategoriaElemento.CABO
            or proposal.estado_revisao is EstadoRevisao.REJEITADA
            or proposal.geometria.tipo is not TipoGeometria.POLILINHA
            or not attributes.get("evidencia_geometria_id")
            or attributes.get("associacao_pendente")
        ):
            continue
        geometry = proposal.geometria
        groups[physical_span_id(geometry)].append(proposal)
        for suffix, point in zip(
            ("origem", "destino"), (geometry.pontos[0], geometry.pontos[-1]), strict=True
        ):
            label = attributes.get(f"ponto_operacional_{suffix}")
            if label:
                labels[physical_point_id(geometry.pagina_id, point)].add(str(label))
    resolved = tuple(
        _physical_span(identity, tuple(sorted(group, key=lambda p: str(p.id))), labels, by_proposal)
        for identity, group in sorted(groups.items(), key=lambda pair: str(pair[0]))
    )
    continuations = tuple(
        TrechoFisico(
            id=physical_span_id(c.trace.geometria),
            geometria=GeometriaDocumento.polilinha(
                c.trace.pagina_id, (c.known_end, c.boundary_end)
            ),
            origem_id=physical_point_id(c.trace.pagina_id, c.known_end),
            destino_id=None,
            origem=_point_label(
                labels.get(physical_point_id(c.trace.pagina_id, c.known_end), set())
            ),
            destino="Continua além do desenho; endpoint não visível",
            rotulo="Continuidade do desenho",
            propostas=(),
            cabos=(),
            codigos=(),
            situacoes=(c.anchor.situacao_projeto,),
            comprimento_m=None,
            tipo=TipoTrechoRede.DESCONHECIDO,
            modalidade=ModalidadeTrecho.DESCONHECIDO,
            pendencias=(
                "Extremidade e comprimento fora do desenho não identificados",
                "Tipo/modalidade sem classificação comprovada; requer revisão",
            ),
            continuidade=True,
            evidencias=(c.trace.id, c.frame.id, *c.anchor.evidencia_ids),
        )
        for c in drawing_continuations(evidencias, effective)
    )
    return tuple(sorted((*resolved, *continuations), key=lambda item: str(item.id)))


def _effective_proposal(proposal: PropostaElemento, cable: Cabo | None) -> PropostaElemento:
    if cable is None:
        return proposal
    attributes = dict(proposal.atributos_sugeridos)
    attributes.pop("comprimento_m", None)
    if cable.comprimento_m is not None:
        attributes["comprimento_m"] = cable.comprimento_m
    if cable.geometria != proposal.geometria:
        attributes.pop("ponto_operacional_origem", None)
        attributes.pop("ponto_operacional_destino", None)
    if cable.geometria is None:
        attributes.pop("evidencia_geometria_id", None)
    return replace(
        proposal,
        geometria=cable.geometria or proposal.geometria,
        situacao_projeto=cable.situacao,
        codigo_observado=cable.codigo_observado,
        atributos_sugeridos=tuple(attributes.items()),
    )


def _physical_span(
    identity: UUID,
    proposals: tuple[PropostaElemento, ...],
    labels: dict[UUID, set[str]],
    confirmed: dict[UUID, Cabo],
) -> TrechoFisico:
    geometry = proposals[0].geometria
    endpoints = tuple(
        physical_point_id(geometry.pagina_id, p) for p in (geometry.pontos[0], geometry.pontos[-1])
    )
    cables = tuple(confirmed[p.id] for p in proposals if p.id in confirmed)
    lengths = {
        Decimal(str(value))
        for p in proposals
        if (value := dict(p.atributos_sugeridos).get("comprimento_m")) is not None
    }
    pending = []
    if len(cables) != len(proposals):
        pending.append("Há cabos aguardando revisão; a projeção não confirma ativos")
    if len(lengths) > 1:
        pending.append("Comprimentos divergentes no mesmo traçado")
    elif not lengths:
        pending.append("Comprimento não identificado")
    types = {c.tipo_trecho for c in cables}
    modes = {c.modalidade for c in cables}
    span_type = next(iter(types)) if len(types) == 1 else TipoTrechoRede.DESCONHECIDO
    mode = next(iter(modes)) if len(modes) == 1 else ModalidadeTrecho.DESCONHECIDO
    if span_type is TipoTrechoRede.DESCONHECIDO:
        pending.append("Tipo indeterminado: endpoints sem classificação comprovada")
    if mode is ModalidadeTrecho.DESCONHECIDO:
        pending.append("Modalidade sem evidência positiva")
    names = tuple(_point_label(labels.get(endpoint, set())) for endpoint in endpoints)
    identifiers = {
        str(value)
        for p in proposals
        if (value := dict(p.atributos_sugeridos).get("identificador_operacional"))
    }
    return TrechoFisico(
        id=identity,
        geometria=geometry,
        origem_id=endpoints[0],
        destino_id=endpoints[1],
        origem=names[0],
        destino=names[1],
        rotulo=next(iter(identifiers)) if len(identifiers) == 1 else "Trecho sem identificador",
        propostas=tuple(p.id for p in proposals),
        cabos=tuple(c.id for c in cables),
        codigos=tuple(p.codigo_observado or "Código não identificado" for p in proposals),
        situacoes=tuple(sorted({p.situacao_projeto for p in proposals}, key=lambda s: s.value)),
        comprimento_m=next(iter(lengths)) if len(lengths) == 1 else None,
        tipo=span_type,
        modalidade=mode,
        pendencias=tuple(pending),
    )


def _point_label(labels: set[str]) -> str:
    if len(labels) == 1:
        return next(iter(labels))
    return "Identificadores conflitantes" if labels else "Ponto sem identificador"
