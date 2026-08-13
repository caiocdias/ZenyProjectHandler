"""Persistência dos snapshots imutáveis do registro de conformidade."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from zeny_project_handler.adapters.compliance import registro_conformidade_de_dict
from zeny_project_handler.domain.compliance import (
    NumeroRegraConformidade,
    RevisaoRegistroConformidade,
)
from zeny_project_handler.domain.errors import DomainValidationError

from .errors import PersistenceConflictError
from .schema import compliance_rule_numbers, compliance_rule_revisions


class SqlComplianceRuleRegistryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter_ativa(self) -> RevisaoRegistroConformidade | None:
        row = (
            self._session.execute(
                select(compliance_rule_revisions).where(
                    compliance_rule_revisions.c.active.is_(True)
                )
            )
            .mappings()
            .one_or_none()
        )
        return _revision(row) if row is not None else None

    def obter_por_assinatura(self, assinatura: str) -> RevisaoRegistroConformidade | None:
        row = (
            self._session.execute(
                select(compliance_rule_revisions).where(
                    compliance_rule_revisions.c.signature == assinatura
                )
            )
            .mappings()
            .one_or_none()
        )
        return _revision(row) if row is not None else None

    def listar_revisoes(self) -> tuple[RevisaoRegistroConformidade, ...]:
        rows = self._session.execute(
            select(compliance_rule_revisions).order_by(compliance_rule_revisions.c.created_at)
        ).mappings()
        return tuple(_revision(row) for row in rows)

    def salvar_ativa(
        self,
        revisao: RevisaoRegistroConformidade,
    ) -> RevisaoRegistroConformidade:
        if not revisao.ativa:
            raise PersistenceConflictError("Nova revisão de regras deve ser ativa")
        current = self.obter_ativa()
        if current is not None:
            current_ids = {item.id for item in current.registro.regras}
            revision_ids = {item.id for item in revisao.registro.regras}
            missing_ids = current_ids - revision_ids
            if missing_ids:
                formatted_ids = ", ".join(sorted(missing_ids))
                raise PersistenceConflictError(
                    f"Nova revisão de regras não pode remover IDs da revisão ativa: {formatted_ids}"
                )
        stored = self.obter_por_assinatura(revisao.assinatura)
        if current is not None and current.assinatura == revisao.assinatura:
            return current
        self._session.execute(
            update(compliance_rule_revisions)
            .where(compliance_rule_revisions.c.active.is_(True))
            .values(active=False)
        )
        if stored is not None:
            self._session.execute(
                update(compliance_rule_revisions)
                .where(compliance_rule_revisions.c.revision_id == str(stored.id))
                .values(active=True)
            )
            return RevisaoRegistroConformidade(
                id=stored.id,
                registro=stored.registro,
                assinatura=stored.assinatura,
                json_canonico=stored.json_canonico,
                criada_em=stored.criada_em,
                ativa=True,
            )
        self._session.execute(
            insert(compliance_rule_revisions).values(
                revision_id=str(revisao.id),
                registry_id=str(revisao.registro.id),
                registry_version=revisao.registro.versao,
                schema_version=revisao.registro.versao_schema,
                signature=revisao.assinatura,
                canonical_json=revisao.json_canonico,
                created_at=revisao.criada_em.isoformat(),
                active=True,
            )
        )
        return revisao

    def listar_numeros(self) -> tuple[NumeroRegraConformidade, ...]:
        rows = self._session.execute(
            select(compliance_rule_numbers).order_by(compliance_rule_numbers.c.number)
        ).mappings()
        return tuple(_rule_number(row) for row in rows)

    def reservar_numeros(
        self,
        regra_ids: tuple[str, ...],
        *,
        atribuido_em: datetime,
    ) -> tuple[NumeroRegraConformidade, ...]:
        existing = {item.regra_id: item for item in self.listar_numeros()}
        next_number = int(
            self._session.scalar(select(func.max(compliance_rule_numbers.c.number))) or 0
        )
        for rule_id in regra_ids:
            if rule_id in existing:
                continue
            next_number += 1
            item = NumeroRegraConformidade(
                regra_id=rule_id,
                numero=next_number,
                atribuido_em=atribuido_em,
            )
            self._session.execute(
                insert(compliance_rule_numbers).values(
                    rule_id=item.regra_id,
                    number=item.numero,
                    assigned_at=item.atribuido_em.isoformat(),
                )
            )
            existing[rule_id] = item
        return tuple(sorted(existing.values(), key=lambda item: item.numero))


def _revision(row: Any) -> RevisaoRegistroConformidade:
    canonical_json = str(row["canonical_json"])
    try:
        payload = cast(dict[str, Any], json.loads(canonical_json))
        registry = registro_conformidade_de_dict(payload)
    except (ValueError, TypeError, DomainValidationError) as error:
        raise PersistenceConflictError("Snapshot de regras persistido é inválido") from error
    return RevisaoRegistroConformidade(
        id=_uuid(row["revision_id"]),
        registro=registry,
        assinatura=str(row["signature"]),
        json_canonico=canonical_json,
        criada_em=datetime.fromisoformat(str(row["created_at"])),
        ativa=bool(row["active"]),
    )


def _rule_number(row: Any) -> NumeroRegraConformidade:
    return NumeroRegraConformidade(
        regra_id=str(row["rule_id"]),
        numero=int(row["number"]),
        atribuido_em=datetime.fromisoformat(str(row["assigned_at"])),
    )


def _uuid(value: object) -> UUID:
    return UUID(str(value))
