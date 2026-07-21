"""Contratos do conjunto de avaliação, independentes do pipeline semântico."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from zeny_project_handler.domain.enums import PapelAnotacao
from zeny_project_handler.domain.evaluation import (
    AmostraAvaliacao,
    AnotacaoAmostra,
    CriteriosRegressaoAvaliacao,
    ManifestoAvaliacao,
    RotuloElementoAvaliacao,
    RotuloRelacaoAvaliacao,
)


class RepositorioConjuntoAvaliacaoPort(Protocol):
    def carregar_manifesto(self) -> ManifestoAvaliacao: ...

    def carregar_criterios(self) -> CriteriosRegressaoAvaliacao: ...

    def carregar_anotacao(self, amostra_id: str, papel: PapelAnotacao) -> AnotacaoAmostra: ...

    def salvar_anotacao(self, anotacao: AnotacaoAmostra) -> Path: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoInterpretacaoAvaliacao:
    """Saída mínima que qualquer pipeline futuro deve fornecer ao benchmark."""

    elementos: tuple[RotuloElementoAvaliacao, ...]
    relacoes: tuple[RotuloRelacaoAvaliacao, ...] = ()
    falhas_extracao: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "elementos", tuple(self.elementos))
        object.__setattr__(self, "relacoes", tuple(self.relacoes))
        object.__setattr__(self, "falhas_extracao", tuple(sorted(set(self.falhas_extracao))))


class InterpretadorAvaliacaoPort(Protocol):
    nome: str
    versao: str

    def interpretar(
        self, amostra: AmostraAvaliacao, caminho_pdf: Path
    ) -> ResultadoInterpretacaoAvaliacao: ...
