"""Contratos mínimos de persistência consumidos pela aplicação."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from zeny_project_handler.domain.analysis import EvidenciaDocumento, ExecucaoAnalise
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.pdf import FontePdfRepositoryPort


class CatalogRepositoryPort(Protocol):
    def obter(self, catalog_id: UUID) -> CatalogoTecnico | None: ...

    def salvar(self, catalog: CatalogoTecnico) -> None: ...


class ProjectRepositoryPort(Protocol):
    def obter(self, project_id: UUID) -> Projeto | None: ...

    def salvar(self, project: Projeto) -> None: ...

    def remover(self, project_id: UUID) -> bool: ...


class AnalysisRunRepositoryPort(Protocol):
    def obter(self, execution_id: UUID) -> ExecucaoAnalise | None: ...

    def listar_do_projeto(self, project_id: UUID) -> tuple[ExecucaoAnalise, ...]: ...

    def salvar(self, execution: ExecucaoAnalise) -> None: ...


class EvidenceRepositoryPort(Protocol):
    def obter(self, evidence_id: UUID) -> EvidenciaDocumento | None: ...

    def listar_da_execucao(self, execution_id: UUID) -> tuple[EvidenciaDocumento, ...]: ...

    def salvar(self, evidence: EvidenciaDocumento) -> None: ...


class UnitOfWorkPort(Protocol):
    @property
    def catalogos(self) -> CatalogRepositoryPort: ...

    @property
    def projetos(self) -> ProjectRepositoryPort: ...

    @property
    def fontes_pdf(self) -> FontePdfRepositoryPort: ...

    @property
    def execucoes_analise(self) -> AnalysisRunRepositoryPort: ...

    @property
    def evidencias(self) -> EvidenceRepositoryPort: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
