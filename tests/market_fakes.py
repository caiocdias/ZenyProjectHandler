"""Doubles explícitos para a classificação externa de mercado."""

from __future__ import annotations

from dataclasses import dataclass, field

from zeny_project_handler.domain.market import Mercado


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
