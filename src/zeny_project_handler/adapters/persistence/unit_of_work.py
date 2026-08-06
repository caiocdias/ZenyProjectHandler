"""Unidade de trabalho explícita para delimitar transações SQLite."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from .analysis_repository import (
    SqlAnalysisRunRepository,
    SqlEvidenceRepository,
    SqlProposalRepository,
    SqlReviewDecisionRepository,
)
from .catalog_repository import SqlCatalogRepository
from .import_commit_repository import SqlImportCommitRepository
from .pdf_source_repository import SqlPdfSourceRepository
from .project_repository import (
    SqlDocumentRepository,
    SqlElementRepository,
    SqlProjectRepository,
)


class SqlAlchemyUnitOfWork:
    """Abre uma sessão por contexto e exige commit explícito."""

    def __init__(self, engine: Engine) -> None:
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        if self._session is not None:
            raise RuntimeError("Unidade de trabalho já está aberta")
        self._session = self._session_factory()
        self.catalogos = SqlCatalogRepository(self._session)
        self.projetos = SqlProjectRepository(self._session)
        self.documentos = SqlDocumentRepository(self._session)
        self.fontes_pdf = SqlPdfSourceRepository(self._session)
        self.elementos = SqlElementRepository(self._session)
        self.execucoes_analise = SqlAnalysisRunRepository(self._session)
        self.evidencias = SqlEvidenceRepository(self._session)
        self.propostas = SqlProposalRepository(self._session)
        self.decisoes_revisao = SqlReviewDecisionRepository(self._session)
        self.comprovantes_importacao = SqlImportCommitRepository(self._session)
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        if self._session is not None:
            self._session.rollback()
            self._session.close()
            self._session = None

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Unidade de trabalho não está aberta")
        return self._session
