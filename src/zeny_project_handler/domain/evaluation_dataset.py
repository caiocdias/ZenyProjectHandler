"""Manifesto e partições do conjunto de avaliação."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from zeny_project_handler.domain.documents import SHA256_PATTERN
from zeny_project_handler.domain.enums import EstadoConjuntoAvaliacao, ParticaoAvaliacao
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.evaluation_common import evaluation_identifier
from zeny_project_handler.domain.values import required_text


@dataclass(frozen=True, slots=True, kw_only=True)
class AmostraAvaliacao:
    id: str
    sha256: str
    tamanho_bytes: int
    total_paginas: int
    particao: ParticaoAvaliacao
    escala: str
    formato: str
    orientacao: str
    qualidade: str
    densidade: str
    dupla_anotacao: bool = False
    casos_especiais: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        digest = self.sha256.strip().lower()
        if not SHA256_PATTERN.fullmatch(digest):
            raise DomainValidationError("SHA-256 da amostra é inválido")
        if self.tamanho_bytes <= 0:
            raise DomainValidationError("Tamanho da amostra deve ser positivo")
        if self.total_paginas <= 0:
            raise DomainValidationError("Amostra deve possuir ao menos uma página")
        special_cases = tuple(
            sorted(
                {
                    evaluation_identifier(item, field_name="caso_especial")
                    for item in self.casos_especiais
                }
            )
        )
        object.__setattr__(self, "id", evaluation_identifier(self.id, field_name="id da amostra"))
        object.__setattr__(self, "sha256", digest)
        object.__setattr__(self, "escala", required_text(self.escala, field_name="escala"))
        object.__setattr__(self, "formato", required_text(self.formato, field_name="formato"))
        object.__setattr__(
            self, "orientacao", required_text(self.orientacao, field_name="orientacao").upper()
        )
        object.__setattr__(
            self, "qualidade", required_text(self.qualidade, field_name="qualidade").upper()
        )
        object.__setattr__(
            self, "densidade", required_text(self.densidade, field_name="densidade").upper()
        )
        object.__setattr__(self, "casos_especiais", special_cases)


@dataclass(frozen=True, slots=True, kw_only=True)
class ManifestoAvaliacao:
    schema_version: int
    conjunto_id: str
    versao: str
    estado: EstadoConjuntoAvaliacao
    politica_acesso: str
    criado_em: datetime
    amostras: tuple[AmostraAvaliacao, ...]
    congelado_em: datetime | None = None

    def __post_init__(self) -> None:
        _validate_manifest_version_and_dates(self)
        samples = _validated_samples(self.amostras)
        object.__setattr__(
            self, "conjunto_id", evaluation_identifier(self.conjunto_id, field_name="conjunto_id")
        )
        object.__setattr__(self, "versao", required_text(self.versao, field_name="versao"))
        object.__setattr__(
            self,
            "politica_acesso",
            required_text(self.politica_acesso, field_name="politica_acesso"),
        )
        object.__setattr__(self, "amostras", tuple(sorted(samples, key=lambda item: item.id)))

    def obter_amostra(self, amostra_id: str) -> AmostraAvaliacao:
        normalized_id = evaluation_identifier(amostra_id, field_name="amostra_id")
        for sample in self.amostras:
            if sample.id == normalized_id:
                return sample
        raise DomainValidationError("Amostra não pertence ao manifesto")


def _validate_manifest_version_and_dates(manifest: ManifestoAvaliacao) -> None:
    if manifest.schema_version != 1:
        raise DomainValidationError("Versão de schema do manifesto não suportada")
    if manifest.criado_em.tzinfo is None:
        raise DomainValidationError("Criação do manifesto deve possuir fuso horário")
    if manifest.congelado_em is not None and manifest.congelado_em.tzinfo is None:
        raise DomainValidationError("Congelamento do manifesto deve possuir fuso horário")
    if manifest.estado is EstadoConjuntoAvaliacao.CONGELADO and manifest.congelado_em is None:
        raise DomainValidationError("Conjunto congelado deve registrar a data de congelamento")
    if (
        manifest.estado is EstadoConjuntoAvaliacao.EM_PREPARACAO
        and manifest.congelado_em is not None
    ):
        raise DomainValidationError("Conjunto em preparação não pode possuir congelamento")


def _validated_samples(samples_value: tuple[AmostraAvaliacao, ...]) -> tuple[AmostraAvaliacao, ...]:
    samples = tuple(samples_value)
    if not samples:
        raise DomainValidationError("Manifesto deve possuir amostras")
    if len({item.id for item in samples}) != len(samples):
        raise DomainValidationError("IDs de amostra devem ser únicos")
    if len({item.sha256 for item in samples}) != len(samples):
        raise DomainValidationError("Hashes de amostra devem ser únicos")
    partitions = {item.particao for item in samples}
    if partitions != {ParticaoAvaliacao.DESENVOLVIMENTO, ParticaoAvaliacao.TESTE}:
        raise DomainValidationError("Manifesto deve separar desenvolvimento e teste")
    return samples


def lacunas_cobertura_manifesto(manifesto: ManifestoAvaliacao) -> tuple[str, ...]:
    """Informe dimensões ainda insuficientes para congelar o corpus."""
    dimensions = {
        "ESCALAS_INSUFICIENTES": {item.escala for item in manifesto.amostras},
        "FORMATOS_INSUFICIENTES": {item.formato for item in manifesto.amostras},
        "ORIENTACOES_INSUFICIENTES": {item.orientacao for item in manifesto.amostras},
        "QUALIDADES_INSUFICIENTES": {item.qualidade for item in manifesto.amostras},
    }
    gaps = [code for code, values in dimensions.items() if len(values) < 2]
    if len({item.densidade for item in manifesto.amostras}) < 3:
        gaps.append("DENSIDADES_INSUFICIENTES")
    if not any(item.dupla_anotacao for item in manifesto.amostras):
        gaps.append("AMOSTRAGEM_DUPLA_AUSENTE")
    return tuple(sorted(gaps))
