"""Operações que relacionam estados de obra de elementos confirmados."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from zeny_project_handler.domain.enums import TipoVinculoObra
from zeny_project_handler.domain.errors import DomainValidationError


@dataclass(frozen=True, slots=True, kw_only=True)
class VinculoObra:
    id: UUID
    tipo: TipoVinculoObra
    elemento_origem_id: UUID
    elemento_destino_id: UUID
    observacao: str | None = None

    def __post_init__(self) -> None:
        if self.elemento_origem_id == self.elemento_destino_id:
            raise DomainValidationError("Vínculo de obra deve referenciar elementos distintos")
        observation = self.observacao.strip() if self.observacao else None
        object.__setattr__(self, "observacao", observation or None)
