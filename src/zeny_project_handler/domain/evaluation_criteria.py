"""Limites numéricos fixados antes da otimização do interpretador."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from zeny_project_handler.domain.enums import CategoriaElemento, EstadoCriteriosAvaliacao
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.evaluation_common import evaluation_rate
from zeny_project_handler.domain.values import decimal_value, required_text


@dataclass(frozen=True, slots=True, kw_only=True)
class LimiteCategoriaAvaliacao:
    categoria: CategoriaElemento
    precisao_minima: Decimal
    recall_minimo: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "precisao_minima",
            evaluation_rate(self.precisao_minima, field_name="precisao_minima"),
        )
        object.__setattr__(
            self,
            "recall_minimo",
            evaluation_rate(self.recall_minimo, field_name="recall_minimo"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CriteriosRegressaoAvaliacao:
    schema_version: int
    versao: str
    estado: EstadoCriteriosAvaliacao
    limites_categoria: tuple[LimiteCategoriaAvaliacao, ...]
    precisao_relacoes_minima: Decimal
    recall_relacoes_minimo: Decimal
    taxa_falhas_extracao_maxima: Decimal
    latencia_p95_ms_maxima: Decimal
    memoria_python_pico_bytes_maxima: int
    divergencia_humana_maxima: Decimal
    tolerancia_ponto: Decimal
    tolerancia_polilinha: Decimal
    iou_area_minimo: Decimal

    def __post_init__(self) -> None:
        limits = _validated_category_limits(self.schema_version, self.limites_categoria)
        latency = decimal_value(self.latencia_p95_ms_maxima, field_name="latencia_p95_ms_maxima")
        if latency <= 0:
            raise DomainValidationError("Limite de latência deve ser positivo")
        if self.memoria_python_pico_bytes_maxima <= 0:
            raise DomainValidationError("Limite de memória deve ser positivo")
        point_tolerance = evaluation_rate(self.tolerancia_ponto, field_name="tolerancia_ponto")
        polyline_tolerance = evaluation_rate(
            self.tolerancia_polilinha, field_name="tolerancia_polilinha"
        )
        if point_tolerance == 0 or polyline_tolerance == 0:
            raise DomainValidationError("Tolerâncias geométricas devem ser maiores que zero")
        object.__setattr__(self, "versao", required_text(self.versao, field_name="versao"))
        object.__setattr__(
            self, "limites_categoria", tuple(sorted(limits, key=lambda item: item.categoria.value))
        )
        _set_evaluation_rates(self, latency, point_tolerance, polyline_tolerance)


def _validated_category_limits(
    schema_version: int, limits_value: tuple[LimiteCategoriaAvaliacao, ...]
) -> tuple[LimiteCategoriaAvaliacao, ...]:
    if schema_version != 1:
        raise DomainValidationError("Versão de schema dos critérios não suportada")
    limits = tuple(limits_value)
    categories = [item.categoria for item in limits]
    if len(set(categories)) != len(categories):
        raise DomainValidationError("Cada categoria deve possuir apenas um limite")
    if set(categories) != set(CategoriaElemento):
        raise DomainValidationError("Critérios devem cobrir todas as categorias")
    return limits


def _set_evaluation_rates(
    criteria: CriteriosRegressaoAvaliacao,
    latency: Decimal,
    point_tolerance: Decimal,
    polyline_tolerance: Decimal,
) -> None:
    rate_fields = (
        ("precisao_relacoes_minima", criteria.precisao_relacoes_minima),
        ("recall_relacoes_minimo", criteria.recall_relacoes_minimo),
        ("taxa_falhas_extracao_maxima", criteria.taxa_falhas_extracao_maxima),
        ("divergencia_humana_maxima", criteria.divergencia_humana_maxima),
        ("iou_area_minimo", criteria.iou_area_minimo),
    )
    for field_name, value in rate_fields:
        object.__setattr__(criteria, field_name, evaluation_rate(value, field_name=field_name))
    object.__setattr__(criteria, "latencia_p95_ms_maxima", latency)
    object.__setattr__(criteria, "tolerancia_ponto", point_tolerance)
    object.__setattr__(criteria, "tolerancia_polilinha", polyline_tolerance)
