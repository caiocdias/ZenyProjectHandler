"""Resultados numéricos do conjunto de avaliação."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.domain.errors import DomainValidationError


def _ratio(numerator: int, denominator: int, *, empty: Decimal) -> Decimal:
    if denominator == 0:
        return empty
    return Decimal(numerator) / Decimal(denominator)


@dataclass(frozen=True, slots=True, kw_only=True)
class ContagemDeteccao:
    verdadeiros_positivos: int
    falsos_positivos: int
    falsos_negativos: int

    def __post_init__(self) -> None:
        if min(self.verdadeiros_positivos, self.falsos_positivos, self.falsos_negativos) < 0:
            raise DomainValidationError("Contagens de avaliação não podem ser negativas")

    @property
    def precisao(self) -> Decimal:
        predicted = self.verdadeiros_positivos + self.falsos_positivos
        empty = Decimal(1) if self.falsos_negativos == 0 else Decimal(0)
        return _ratio(self.verdadeiros_positivos, predicted, empty=empty)

    @property
    def recall(self) -> Decimal:
        expected = self.verdadeiros_positivos + self.falsos_negativos
        return _ratio(self.verdadeiros_positivos, expected, empty=Decimal(1))

    @property
    def f1(self) -> Decimal:
        denominator = self.precisao + self.recall
        if denominator == 0:
            return Decimal(0)
        return Decimal(2) * self.precisao * self.recall / denominator

    def somar(self, outra: ContagemDeteccao) -> ContagemDeteccao:
        return ContagemDeteccao(
            verdadeiros_positivos=self.verdadeiros_positivos + outra.verdadeiros_positivos,
            falsos_positivos=self.falsos_positivos + outra.falsos_positivos,
            falsos_negativos=self.falsos_negativos + outra.falsos_negativos,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class MetricasCategoria:
    categoria: CategoriaElemento
    contagem: ContagemDeteccao


@dataclass(frozen=True, slots=True, kw_only=True)
class MetricasAmostra:
    amostra_id: str
    categorias: tuple[MetricasCategoria, ...]
    relacoes: ContagemDeteccao
    falhas_extracao: tuple[str, ...]
    latencia_ms: Decimal
    memoria_python_pico_bytes: int

    def __post_init__(self) -> None:
        if self.latencia_ms < 0 or self.memoria_python_pico_bytes < 0:
            raise DomainValidationError("Métricas de recursos não podem ser negativas")
        if len({item.categoria for item in self.categorias}) != len(self.categorias):
            raise DomainValidationError("Métrica de categoria duplicada")
        object.__setattr__(self, "falhas_extracao", tuple(sorted(set(self.falhas_extracao))))


@dataclass(frozen=True, slots=True, kw_only=True)
class DivergenciaAnotadores:
    amostra_id: str
    elementos_primarios: int
    elementos_secundarios: int
    elementos_correspondentes: int
    divergencias_categoria: int
    divergencias_situacao: int
    relacoes_primarias: int
    relacoes_secundarias: int
    relacoes_correspondentes: int
    taxa_divergencia: Decimal

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.taxa_divergencia <= Decimal(1):
            raise DomainValidationError("Taxa de divergência deve estar entre 0 e 1")


@dataclass(frozen=True, slots=True, kw_only=True)
class RelatorioBenchmarkAvaliacao:
    dataset_id: str
    dataset_version: str
    criteria_version: str
    interpreter: str
    interpreter_version: str
    rules_version: str
    sample_results: tuple[MetricasAmostra, ...]
    aggregate_categories: tuple[MetricasCategoria, ...]
    aggregate_relations: ContagemDeteccao
    extraction_failure_rate: Decimal
    latency_p95_ms: Decimal
    maximum_python_peak_memory_bytes: int
    semantic_signature: str
    approved: bool
    violations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.extraction_failure_rate <= Decimal(1):
            raise DomainValidationError("Taxa de falhas deve estar entre 0 e 1")
        if self.latency_p95_ms < 0 or self.maximum_python_peak_memory_bytes < 0:
            raise DomainValidationError("Métricas agregadas de recursos são inválidas")
        object.__setattr__(self, "violations", tuple(sorted(set(self.violations))))
