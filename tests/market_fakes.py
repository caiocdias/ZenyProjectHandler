"""Doubles explícitos para consultas ao cadastro operacional externo."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from zeny_project_handler.domain.market import DescricaoAcao, Mercado


@dataclass
class FakeClassificadorMercado:
    mercado: Mercado = Mercado.URBANO
    erro: Exception | None = None
    consultas: list[str] = field(default_factory=list)

    def classificar(self, numero_ns: str) -> Mercado:
        self.consultas.append(numero_ns)
        if self.erro is not None:
            raise self.erro
        return self.mercado


@dataclass
class FakeVerificadorAcoesConcluidas:
    resultado: bool = False
    erro: Exception | None = None
    consultas: list[tuple[str, tuple[str, ...], DescricaoAcao]] = field(default_factory=list)

    def existe_acao_concluida(
        self,
        numero_ns: str,
        codigos_servico: Sequence[str],
        acao: DescricaoAcao,
    ) -> bool:
        self.consultas.append((numero_ns, tuple(codigos_servico), acao))
        if self.erro is not None:
            raise self.erro
        return self.resultado
