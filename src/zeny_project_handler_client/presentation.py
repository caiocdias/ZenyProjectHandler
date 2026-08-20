"""Tipos geométricos locais sem identidade ou comportamento de domínio."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from zeny_project_handler_contracts.enums import ReviewGeometryKind


@dataclass(frozen=True, slots=True)
class NormalizedPoint:
    x: Decimal
    y: Decimal

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.x <= Decimal(1) or not Decimal(0) <= self.y <= Decimal(1):
            raise ValueError("Coordenadas de apresentação devem estar entre zero e um")


@dataclass(frozen=True, slots=True)
class PresentationGeometry:
    page_id: UUID
    kind: ReviewGeometryKind
    points: tuple[NormalizedPoint, ...]

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("Uma geometria de apresentação exige ao menos um ponto")
