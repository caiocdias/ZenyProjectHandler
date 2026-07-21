"""Persistência da referência ao arquivo original, separada do agregado de domínio."""

from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from zeny_project_handler.ports.pdf import ReferenciaFontePdf

from .errors import PersistenceConflictError
from .schema import document_sources, documents


class SqlPdfSourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, documento_id: UUID) -> ReferenciaFontePdf | None:
        row = (
            self._session.execute(
                select(document_sources).where(document_sources.c.document_id == str(documento_id))
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return ReferenciaFontePdf(
            documento_id=UUID(str(row["document_id"])),
            projeto_id=UUID(str(row["project_id"])),
            caminho_canonico=Path(str(row["canonical_path"])),
            sha256=str(row["sha256"]),
            tamanho_bytes=int(row["size_bytes"]),
            modificado_em_ns=int(row["modified_at_ns"]),
        )

    def salvar(self, referencia: ReferenciaFontePdf) -> None:
        project_id = self._session.scalar(
            select(documents.c.project_id).where(documents.c.id == str(referencia.documento_id))
        )
        if project_id != str(referencia.projeto_id):
            raise PersistenceConflictError("A origem PDF deve pertencer ao documento do projeto")
        values = {
            "project_id": str(referencia.projeto_id),
            "canonical_path": str(referencia.caminho_canonico.expanduser().resolve()),
            "sha256": referencia.sha256,
            "size_bytes": referencia.tamanho_bytes,
            "modified_at_ns": str(referencia.modificado_em_ns),
        }
        statement = sqlite_insert(document_sources).values(
            document_id=str(referencia.documento_id),
            **values,
        )
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[document_sources.c.document_id],
                set_=values,
            )
        )
