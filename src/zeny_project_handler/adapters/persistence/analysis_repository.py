"""Repositórios das execuções, evidências, propostas e decisões auditáveis."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from zeny_project_handler.domain.analysis import (
    DecisaoRevisao,
    EvidenciaDocumento,
    ExecucaoAnalise,
    PropostaElemento,
    PropostaRelacao,
    ReferenciaProposta,
)

from .domain_json import dumps_domain, loads_domain
from .errors import PersistenceConflictError, PersistenceNotFoundError
from .schema import (
    analysis_runs,
    confirmed_relations,
    elements,
    evidence,
    pages,
    projects,
    proposal_evidence,
    proposals,
    review_decisions,
)


def _project_for_execution(session: Session, execution_id: UUID) -> str:
    project_id = session.scalar(
        select(analysis_runs.c.project_id).where(analysis_runs.c.id == str(execution_id))
    )
    if project_id is None:
        raise PersistenceNotFoundError("Execução de análise não foi persistida")
    return str(project_id)


class SqlAnalysisRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, execution_id: UUID) -> ExecucaoAnalise | None:
        payload = self._session.scalar(
            select(analysis_runs.c.payload).where(analysis_runs.c.id == str(execution_id))
        )
        return loads_domain(payload, ExecucaoAnalise) if payload is not None else None

    def listar_do_projeto(self, project_id: UUID) -> tuple[ExecucaoAnalise, ...]:
        payloads = self._session.scalars(
            select(analysis_runs.c.payload)
            .where(analysis_runs.c.project_id == str(project_id))
            .order_by(analysis_runs.c.started_at)
        )
        return tuple(loads_domain(payload, ExecucaoAnalise) for payload in payloads)

    def salvar(self, execution: ExecucaoAnalise) -> None:
        if not self._session.scalar(
            select(projects.c.id).where(projects.c.id == str(execution.projeto_id))
        ):
            raise PersistenceNotFoundError("Projeto da execução não foi persistido")
        existing_project = self._session.scalar(
            select(analysis_runs.c.project_id).where(analysis_runs.c.id == str(execution.id))
        )
        values = {
            "project_id": str(execution.projeto_id),
            "method": execution.metodo,
            "state": execution.estado.value,
            "started_at": execution.iniciada_em.isoformat(),
            "payload": dumps_domain(execution),
        }
        if existing_project is None:
            self._session.execute(insert(analysis_runs).values(id=str(execution.id), **values))
        elif existing_project != str(execution.projeto_id):
            raise PersistenceConflictError("Execução não pode ser movida para outro projeto")
        else:
            self._session.execute(
                update(analysis_runs)
                .where(analysis_runs.c.id == str(execution.id))
                .values(**values)
            )

    def remover(self, execution_id: UUID) -> bool:
        persisted_id = str(execution_id)
        proposal_ids = select(proposals.c.id).where(proposals.c.execution_id == persisted_id)
        evidence_ids = select(evidence.c.id).where(evidence.c.execution_id == persisted_id)
        self._session.execute(
            delete(review_decisions).where(review_decisions.c.proposal_id.in_(proposal_ids))
        )
        self._session.execute(
            delete(proposal_evidence).where(proposal_evidence.c.proposal_id.in_(proposal_ids))
        )
        self._session.execute(
            delete(proposal_evidence).where(proposal_evidence.c.evidence_id.in_(evidence_ids))
        )
        self._session.execute(delete(proposals).where(proposals.c.execution_id == persisted_id))
        self._session.execute(delete(evidence).where(evidence.c.execution_id == persisted_id))
        result = cast(
            CursorResult[object],
            self._session.execute(delete(analysis_runs).where(analysis_runs.c.id == persisted_id)),
        )
        return bool(result.rowcount)


class SqlEvidenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, evidence_id: UUID) -> EvidenciaDocumento | None:
        payload = self._session.scalar(
            select(evidence.c.payload).where(evidence.c.id == str(evidence_id))
        )
        return loads_domain(payload, EvidenciaDocumento) if payload is not None else None

    def listar_da_execucao(self, execution_id: UUID) -> tuple[EvidenciaDocumento, ...]:
        payloads = self._session.scalars(
            select(evidence.c.payload)
            .where(evidence.c.execution_id == str(execution_id))
            .order_by(evidence.c.created_at)
        )
        return tuple(loads_domain(payload, EvidenciaDocumento) for payload in payloads)

    def salvar(self, item: EvidenciaDocumento) -> None:
        project_id = _project_for_execution(self._session, item.execucao_id)
        page_project = self._session.scalar(
            select(pages.c.project_id).where(pages.c.id == str(item.pagina_id))
        )
        if page_project != project_id:
            raise PersistenceConflictError(
                "Evidência deve usar página do mesmo projeto da execução"
            )
        existing_execution = self._session.scalar(
            select(evidence.c.execution_id).where(evidence.c.id == str(item.id))
        )
        values = {
            "execution_id": str(item.execucao_id),
            "project_id": project_id,
            "page_id": str(item.pagina_id),
            "kind": item.tipo.value,
            "created_at": item.criada_em.isoformat(),
            "payload": dumps_domain(item),
        }
        if existing_execution is None:
            self._session.execute(insert(evidence).values(id=str(item.id), **values))
        elif existing_execution != str(item.execucao_id):
            raise PersistenceConflictError("Evidência não pode ser movida entre execuções")
        else:
            self._session.execute(
                update(evidence).where(evidence.c.id == str(item.id)).values(**values)
            )


class SqlProposalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, proposal_id: UUID) -> ReferenciaProposta | None:
        row = self._session.execute(
            select(proposals.c.kind, proposals.c.payload).where(proposals.c.id == str(proposal_id))
        ).one_or_none()
        if row is None:
            return None
        proposal_type = PropostaElemento if row.kind == "ELEMENTO" else PropostaRelacao
        return cast(ReferenciaProposta, loads_domain(row.payload, proposal_type))

    def listar_da_execucao(self, execution_id: UUID) -> tuple[ReferenciaProposta, ...]:
        rows = self._session.execute(
            select(proposals.c.kind, proposals.c.payload).where(
                proposals.c.execution_id == str(execution_id)
            )
        )
        return tuple(
            cast(
                ReferenciaProposta,
                loads_domain(
                    row.payload, PropostaElemento if row.kind == "ELEMENTO" else PropostaRelacao
                ),
            )
            for row in rows
        )

    def salvar(self, proposal: ReferenciaProposta) -> None:
        project_id = _project_for_execution(self._session, proposal.execucao_id)
        evidence_rows = self._session.execute(
            select(evidence.c.id, evidence.c.execution_id, evidence.c.project_id).where(
                evidence.c.id.in_([str(item) for item in proposal.evidencia_ids])
            )
        ).all()
        if len(evidence_rows) != len(proposal.evidencia_ids) or any(
            row.project_id != project_id for row in evidence_rows
        ):
            raise PersistenceConflictError(
                "Proposta deve referenciar evidências existentes do mesmo projeto"
            )
        existing_execution = self._session.scalar(
            select(proposals.c.execution_id).where(proposals.c.id == str(proposal.id))
        )
        kind = "ELEMENTO" if isinstance(proposal, PropostaElemento) else "RELACAO"
        values = {
            "execution_id": str(proposal.execucao_id),
            "project_id": project_id,
            "kind": kind,
            "review_state": proposal.estado_revisao.value,
            "payload": dumps_domain(proposal),
        }
        if existing_execution is None:
            self._session.execute(insert(proposals).values(id=str(proposal.id), **values))
        elif existing_execution != str(proposal.execucao_id):
            raise PersistenceConflictError("Proposta não pode ser movida entre execuções")
        else:
            self._session.execute(
                update(proposals).where(proposals.c.id == str(proposal.id)).values(**values)
            )
            self._session.execute(
                delete(proposal_evidence).where(proposal_evidence.c.proposal_id == str(proposal.id))
            )
        self._session.execute(
            insert(proposal_evidence),
            [
                {
                    "proposal_id": str(proposal.id),
                    "evidence_id": str(evidence_id),
                    "project_id": project_id,
                }
                for evidence_id in proposal.evidencia_ids
            ],
        )


class SqlReviewDecisionRepository:
    """Decisões são imutáveis depois de registradas."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, decision_id: UUID) -> DecisaoRevisao | None:
        payload = self._session.scalar(
            select(review_decisions.c.payload).where(review_decisions.c.id == str(decision_id))
        )
        return loads_domain(payload, DecisaoRevisao) if payload is not None else None

    def obter_da_proposta(self, proposal_id: UUID) -> DecisaoRevisao | None:
        payload = self._session.scalar(
            select(review_decisions.c.payload).where(
                review_decisions.c.proposal_id == str(proposal_id)
            )
        )
        return loads_domain(payload, DecisaoRevisao) if payload is not None else None

    def salvar(self, decision: DecisaoRevisao) -> None:
        proposal_project = self._session.scalar(
            select(proposals.c.project_id).where(proposals.c.id == str(decision.proposta_id))
        )
        if proposal_project is None:
            raise PersistenceNotFoundError("Proposta da decisão não foi persistida")
        if decision.elemento_confirmado_id is not None:
            element_project = self._session.scalar(
                select(elements.c.project_id).where(
                    elements.c.id == str(decision.elemento_confirmado_id)
                )
            )
            if element_project != proposal_project:
                raise PersistenceConflictError(
                    "Elemento confirmado deve pertencer ao projeto da proposta"
                )
        if decision.relacao_confirmada_id is not None:
            relation_project = self._session.scalar(
                select(confirmed_relations.c.project_id).where(
                    confirmed_relations.c.id == str(decision.relacao_confirmada_id)
                )
            )
            if relation_project != proposal_project:
                raise PersistenceConflictError(
                    "Relação confirmada deve pertencer ao projeto da proposta"
                )
        payload = dumps_domain(decision)
        stored = self._session.scalar(
            select(review_decisions.c.payload).where(
                (review_decisions.c.id == str(decision.id))
                | (review_decisions.c.proposal_id == str(decision.proposta_id))
            )
        )
        if stored is not None:
            if stored == payload:
                return
            raise PersistenceConflictError("Decisão de revisão já registrada e é imutável")
        self._session.execute(
            insert(review_decisions).values(
                id=str(decision.id),
                proposal_id=str(decision.proposta_id),
                project_id=proposal_project,
                confirmed_element_id=(
                    str(decision.elemento_confirmado_id)
                    if decision.elemento_confirmado_id is not None
                    else None
                ),
                decided_at=decision.decidida_em.isoformat(),
                payload=payload,
            )
        )
