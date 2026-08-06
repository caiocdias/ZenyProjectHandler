"""Contratos mínimos de persistência consumidos pela aplicação."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from zeny_project_handler.domain.analysis import (
    DecisaoRevisao,
    EvidenciaDocumento,
    ExecucaoAnalise,
    ReferenciaProposta,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.pdf import FontePdfRepositoryPort


@dataclass(frozen=True, slots=True, kw_only=True)
class ComprovanteCommitImportacao:
    """Prova persistida na mesma transação dos dados importados."""

    operacao_id: UUID
    projeto_id: UUID
    pacote_sha256: str
    plano_sha256: str
    arquivos_sha256: str
    confirmado_em: datetime


class ComprovanteCommitImportacaoRepositoryPort(Protocol):
    def obter(self, operacao_id: UUID) -> ComprovanteCommitImportacao | None: ...

    def salvar(self, comprovante: ComprovanteCommitImportacao) -> None: ...


class CatalogRepositoryPort(Protocol):
    def obter(self, catalog_id: UUID) -> CatalogoTecnico | None: ...

    def salvar(self, catalog: CatalogoTecnico) -> None: ...


class ProjectRepositoryPort(Protocol):
    def obter(self, project_id: UUID) -> Projeto | None: ...

    def listar(self) -> tuple[Projeto, ...]: ...

    def salvar(self, project: Projeto) -> None: ...

    def remover(self, project_id: UUID) -> bool: ...


class AnalysisRunRepositoryPort(Protocol):
    def obter(self, execution_id: UUID) -> ExecucaoAnalise | None: ...

    def listar_do_projeto(self, project_id: UUID) -> tuple[ExecucaoAnalise, ...]: ...

    def salvar(self, execution: ExecucaoAnalise) -> None: ...

    def remover(self, execution_id: UUID) -> bool: ...


class EvidenceRepositoryPort(Protocol):
    def obter(self, evidence_id: UUID) -> EvidenciaDocumento | None: ...

    def listar_da_execucao(self, execution_id: UUID) -> tuple[EvidenciaDocumento, ...]: ...

    def salvar(self, evidence: EvidenciaDocumento) -> None: ...


class ProposalRepositoryPort(Protocol):
    def obter(self, proposal_id: UUID) -> ReferenciaProposta | None: ...

    def listar_da_execucao(self, execution_id: UUID) -> tuple[ReferenciaProposta, ...]: ...

    def salvar(self, proposal: ReferenciaProposta) -> None: ...


class ReviewDecisionRepositoryPort(Protocol):
    def obter(self, decision_id: UUID) -> DecisaoRevisao | None: ...

    def obter_da_proposta(self, proposal_id: UUID) -> DecisaoRevisao | None: ...

    def salvar(self, decision: DecisaoRevisao) -> None: ...


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

    @property
    def propostas(self) -> ProposalRepositoryPort: ...

    @property
    def decisoes_revisao(self) -> ReviewDecisionRepositoryPort: ...

    @property
    def comprovantes_importacao(self) -> ComprovanteCommitImportacaoRepositoryPort: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
