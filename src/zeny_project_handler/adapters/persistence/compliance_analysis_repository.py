"""Persistência imutável dos snapshots de execução de conformidade."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from zeny_project_handler.domain.compliance import ExecucaoConformidade
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise

from .domain_json import dumps_domain, loads_domain
from .errors import PersistenceConflictError, PersistenceNotFoundError
from .schema import (
    analysis_runs,
    compliance_executions,
    compliance_rule_revisions,
    projects,
)


class SqlComplianceAnalysisRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, execution_id: UUID) -> ExecucaoConformidade | None:
        payload = self._session.scalar(
            select(compliance_executions.c.payload).where(
                compliance_executions.c.id == str(execution_id)
            )
        )
        return loads_domain(payload, ExecucaoConformidade) if payload is not None else None

    def obter_ultima(self, project_id: UUID) -> ExecucaoConformidade | None:
        payload = self._session.scalar(
            select(compliance_executions.c.payload)
            .where(compliance_executions.c.project_id == str(project_id))
            .order_by(compliance_executions.c.sequence.desc())
            .limit(1)
        )
        return loads_domain(payload, ExecucaoConformidade) if payload is not None else None

    def listar_do_projeto(self, project_id: UUID) -> tuple[ExecucaoConformidade, ...]:
        payloads = self._session.scalars(
            select(compliance_executions.c.payload)
            .where(compliance_executions.c.project_id == str(project_id))
            .order_by(compliance_executions.c.sequence)
        )
        return tuple(loads_domain(payload, ExecucaoConformidade) for payload in payloads)

    def salvar(self, execution: ExecucaoConformidade) -> None:
        payload = dumps_domain(execution)
        stored = self._session.scalar(
            select(compliance_executions.c.payload).where(
                compliance_executions.c.id == str(execution.id)
            )
        )
        if stored is not None:
            if stored == payload:
                return
            raise PersistenceConflictError(
                "Execução de conformidade já existe com conteúdo diferente"
            )
        self._validate_references(execution)
        self._session.execute(
            insert(compliance_executions).values(
                id=str(execution.id),
                project_id=str(execution.projeto_id),
                rule_revision_id=str(execution.revisao_regras_id),
                rule_version=execution.versao_regras,
                rule_signature=execution.assinatura_regras,
                session_signature=execution.assinatura_sessao,
                executed_at=execution.executada_em.isoformat(),
                payload=payload,
            )
        )

    def _validate_references(self, execution: ExecucaoConformidade) -> None:
        project_id = str(execution.projeto_id)
        if self._session.scalar(select(projects.c.id).where(projects.c.id == project_id)) is None:
            raise PersistenceNotFoundError("Projeto da conformidade não foi persistido")
        revision_signature = self._session.scalar(
            select(compliance_rule_revisions.c.signature).where(
                compliance_rule_revisions.c.revision_id == str(execution.revisao_regras_id)
            )
        )
        if revision_signature != execution.assinatura_regras:
            raise PersistenceConflictError(
                "Revisão de regras da execução de conformidade não corresponde ao snapshot"
            )
        rows = self._session.execute(
            select(analysis_runs.c.id, analysis_runs.c.project_id, analysis_runs.c.state).where(
                analysis_runs.c.id.in_(
                    tuple(str(item) for item in execution.execucoes_semanticas_ids)
                )
            )
        ).all()
        if len(rows) != len(execution.execucoes_semanticas_ids) or any(
            row.project_id != project_id or row.state != EstadoExecucaoAnalise.CONCLUIDA.value
            for row in rows
        ):
            raise PersistenceConflictError(
                "Origens semânticas devem estar concluídas e pertencer ao mesmo projeto"
            )
