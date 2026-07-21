"""Value objects geométricos e utilitários de validação."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from typing import TypeAlias
from uuid import UUID

from zeny_project_handler.domain.enums import TipoGeometria
from zeny_project_handler.domain.errors import DomainValidationError

DecimalInput: TypeAlias = Decimal | int | str


def decimal_value(value: DecimalInput, *, field_name: str) -> Decimal:
    """Converta sem aceitar os erros silenciosos de ponto flutuante binário."""
    if isinstance(value, bool):
        raise DomainValidationError(f"{field_name} deve ser numérico")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as error:
        raise DomainValidationError(f"{field_name} deve ser numérico") from error
    if not result.is_finite():
        raise DomainValidationError(f"{field_name} deve ser finito")
    return result


def required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise DomainValidationError(f"{field_name} é obrigatório")
    return normalized


@dataclass(frozen=True, slots=True)
class PontoNormalizado:
    x: Decimal
    y: Decimal

    def __post_init__(self) -> None:
        x = decimal_value(self.x, field_name="x")
        y = decimal_value(self.y, field_name="y")
        if not Decimal(0) <= x <= Decimal(1) or not Decimal(0) <= y <= Decimal(1):
            raise DomainValidationError("Coordenadas normalizadas devem estar entre 0 e 1")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)


@dataclass(frozen=True, slots=True)
class CaixaPagina:
    x_min: Decimal
    y_min: Decimal
    x_max: Decimal
    y_max: Decimal

    def __post_init__(self) -> None:
        x_min = decimal_value(self.x_min, field_name="x_min")
        y_min = decimal_value(self.y_min, field_name="y_min")
        x_max = decimal_value(self.x_max, field_name="x_max")
        y_max = decimal_value(self.y_max, field_name="y_max")
        if x_max <= x_min or y_max <= y_min:
            raise DomainValidationError("A caixa da página deve possuir área positiva")
        object.__setattr__(self, "x_min", x_min)
        object.__setattr__(self, "y_min", y_min)
        object.__setattr__(self, "x_max", x_max)
        object.__setattr__(self, "y_max", y_max)

    @property
    def largura(self) -> Decimal:
        return self.x_max - self.x_min

    @property
    def altura(self) -> Decimal:
        return self.y_max - self.y_min


@dataclass(frozen=True, slots=True, kw_only=True)
class CoordenadaCampo:
    leste: Decimal
    norte: Decimal
    sistema_referencia: str | None = None
    zona: str | None = None
    altitude_m: Decimal | None = None

    def __post_init__(self) -> None:
        east = decimal_value(self.leste, field_name="leste")
        north = decimal_value(self.norte, field_name="norte")
        altitude = self.altitude_m
        if altitude is not None:
            altitude = decimal_value(altitude, field_name="altitude_m")
        reference = self.sistema_referencia.strip() if self.sistema_referencia else None
        zone = self.zona.strip() if self.zona else None
        object.__setattr__(self, "leste", east)
        object.__setattr__(self, "norte", north)
        object.__setattr__(self, "sistema_referencia", reference or None)
        object.__setattr__(self, "zona", zone or None)
        object.__setattr__(self, "altitude_m", altitude)


def _validate_point_geometry(points: tuple[PontoNormalizado, ...]) -> None:
    if len(points) != 1:
        raise DomainValidationError("Geometria de ponto deve conter exatamente um ponto")


def _validate_box_geometry(points: tuple[PontoNormalizado, ...]) -> None:
    if len(points) != 2:
        raise DomainValidationError("Geometria de caixa deve conter dois cantos")
    if points[1].x <= points[0].x or points[1].y <= points[0].y:
        raise DomainValidationError("A caixa normalizada deve possuir área positiva")


def _validate_polyline_geometry(points: tuple[PontoNormalizado, ...]) -> None:
    if len(points) < 2:
        raise DomainValidationError("Polilinha deve conter ao menos dois pontos")
    if any(left == right for left, right in pairwise(points)):
        raise DomainValidationError("Polilinha não aceita pontos consecutivos repetidos")


def _validate_polygon_geometry(points: tuple[PontoNormalizado, ...]) -> None:
    if len(points) < 3 or len(set(points)) < 3:
        raise DomainValidationError("Polígono deve conter ao menos três pontos distintos")
    if any(left == right for left, right in pairwise(points)):
        raise DomainValidationError("Polígono não aceita pontos consecutivos repetidos")


def validar_geometria_normalizada(
    tipo: TipoGeometria, pontos: tuple[PontoNormalizado, ...]
) -> tuple[PontoNormalizado, ...]:
    """Valide uma geometria 0..1 sem vinculá-la a uma página persistida."""
    normalized_points = tuple(pontos)
    validators = {
        TipoGeometria.PONTO: _validate_point_geometry,
        TipoGeometria.CAIXA: _validate_box_geometry,
        TipoGeometria.POLILINHA: _validate_polyline_geometry,
        TipoGeometria.POLIGONO: _validate_polygon_geometry,
    }
    validator = validators.get(tipo)
    if validator is None:
        raise DomainValidationError("Tipo de geometria não suportado")
    validator(normalized_points)
    return normalized_points


@dataclass(frozen=True, slots=True)
class GeometriaDocumento:
    pagina_id: UUID
    tipo: TipoGeometria
    pontos: tuple[PontoNormalizado, ...]

    def __post_init__(self) -> None:
        points = validar_geometria_normalizada(self.tipo, self.pontos)
        object.__setattr__(self, "pontos", points)

    @classmethod
    def ponto(cls, pagina_id: UUID, ponto: PontoNormalizado) -> GeometriaDocumento:
        return cls(pagina_id=pagina_id, tipo=TipoGeometria.PONTO, pontos=(ponto,))

    @classmethod
    def caixa(
        cls,
        pagina_id: UUID,
        superior_esquerdo: PontoNormalizado,
        inferior_direito: PontoNormalizado,
    ) -> GeometriaDocumento:
        return cls(
            pagina_id=pagina_id,
            tipo=TipoGeometria.CAIXA,
            pontos=(superior_esquerdo, inferior_direito),
        )

    @classmethod
    def polilinha(cls, pagina_id: UUID, pontos: tuple[PontoNormalizado, ...]) -> GeometriaDocumento:
        return cls(pagina_id=pagina_id, tipo=TipoGeometria.POLILINHA, pontos=pontos)

    @classmethod
    def poligono(cls, pagina_id: UUID, pontos: tuple[PontoNormalizado, ...]) -> GeometriaDocumento:
        return cls(pagina_id=pagina_id, tipo=TipoGeometria.POLIGONO, pontos=pontos)
