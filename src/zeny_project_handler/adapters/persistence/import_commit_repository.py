"""Comprovantes transacionais de importações publicadas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from zeny_project_handler.ports.persistence import ComprovanteCommitImportacao

from .schema import import_commits


class SqlImportCommitRepository:
    """Persista a prova junto com o agregado importado na mesma sessão."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, operacao_id: UUID) -> ComprovanteCommitImportacao | None:
        row = (
            self._session.execute(
                select(import_commits).where(import_commits.c.operation_id == str(operacao_id))
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return ComprovanteCommitImportacao(
            operacao_id=UUID(row["operation_id"]),
            projeto_id=UUID(row["project_id"]),
            pacote_sha256=row["package_sha256"],
            plano_sha256=row["plan_sha256"],
            arquivos_sha256=row["files_sha256"],
            confirmado_em=datetime.fromisoformat(row["committed_at"]),
        )

    def salvar(self, comprovante: ComprovanteCommitImportacao) -> None:
        self._session.execute(
            sqlite_insert(import_commits).values(
                operation_id=str(comprovante.operacao_id),
                project_id=str(comprovante.projeto_id),
                package_sha256=comprovante.pacote_sha256,
                plan_sha256=comprovante.plano_sha256,
                files_sha256=comprovante.arquivos_sha256,
                committed_at=comprovante.confirmado_em.isoformat(),
            )
        )
