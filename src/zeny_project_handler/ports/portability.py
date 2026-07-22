"""Porta para empacotamento local e verificação de integridade."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from zeny_project_handler.domain.analysis import (
    DecisaoRevisao,
    EvidenciaDocumento,
    ExecucaoAnalise,
    ReferenciaProposta,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.portability import (
    ArquivoPacoteProjeto,
    ManifestoProjetoPortatil,
    RelatorioIntegridadeProjeto,
)
from zeny_project_handler.domain.project import Projeto


@dataclass(frozen=True, slots=True, kw_only=True)
class OrigemArquivoPacote:
    arquivo: ArquivoPacoteProjeto
    caminho_origem: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class PacoteProjetoExtraido:
    manifesto: ManifestoProjetoPortatil
    diretorio: Path
    integridade: RelatorioIntegridadeProjeto


@dataclass(frozen=True, slots=True, kw_only=True)
class ConteudoBancoProjetoPortatil:
    projeto: Projeto
    catalogo: CatalogoTecnico
    execucoes: tuple[ExecucaoAnalise, ...] = ()
    evidencias: tuple[EvidenciaDocumento, ...] = ()
    propostas: tuple[ReferenciaProposta, ...] = ()
    decisoes: tuple[DecisaoRevisao, ...] = ()


class ArquivoProjetoPortatilPort(Protocol):
    def criar(
        self,
        destino: Path,
        manifesto: ManifestoProjetoPortatil,
        origens: tuple[OrigemArquivoPacote, ...],
    ) -> Path: ...

    def extrair_validado(self, pacote: Path, destino: Path) -> PacoteProjetoExtraido: ...


class BancoProjetoPortatilPort(Protocol):
    def criar(self, destino: Path, conteudo: ConteudoBancoProjetoPortatil) -> Path: ...

    def carregar(self, origem: Path, projeto_id: UUID) -> ConteudoBancoProjetoPortatil: ...


class BackupLocalPort(Protocol):
    def criar_snapshot(self, banco: Path, destino: Path) -> Path: ...

    def restaurar_snapshot(self, origem: Path, banco: Path) -> Path: ...

    def preparar_origens_pdf(self, snapshot: Path, caminhos: dict[UUID, Path]) -> None: ...
