from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest
from tests.evaluation_factories import FIXED_TIME, make_annotation, make_manifest, make_sample

from zeny_project_handler.adapters.evaluation import JsonEvaluationDataset
from zeny_project_handler.domain.enums import (
    EstadoConjuntoAvaliacao,
    EstadoCriteriosAvaliacao,
    ParticaoAvaliacao,
    TipoGeometria,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.evaluation import (
    GeometriaAvaliacao,
    lacunas_cobertura_manifesto,
    validar_anotacao_no_manifesto,
)
from zeny_project_handler.domain.values import PontoNormalizado


def test_geometry_rejects_points_outside_normalized_page() -> None:
    with pytest.raises(DomainValidationError, match="entre 0 e 1"):
        GeometriaAvaliacao(
            pagina_numero=1,
            tipo=TipoGeometria.PONTO,
            pontos=(PontoNormalizado(Decimal("1.1"), Decimal("0.5")),),
        )


def test_annotation_must_match_manifest_hash_and_page_bounds() -> None:
    sample = make_sample()
    manifest = make_manifest(test_sample=sample)
    annotation = make_annotation(sample=sample)

    validar_anotacao_no_manifesto(annotation, manifest)

    foreign = make_annotation(sample=make_sample(digest="c" * 64))
    with pytest.raises(DomainValidationError, match="Hash"):
        validar_anotacao_no_manifesto(foreign, manifest)


def test_real_manifest_records_current_coverage_gap() -> None:
    dataset = JsonEvaluationDataset(__import__("pathlib").Path("evaluation"))
    manifest = dataset.carregar_manifesto()
    criteria = dataset.carregar_criterios()

    assert manifest.estado is EstadoConjuntoAvaliacao.EM_PREPARACAO
    assert criteria.estado is EstadoCriteriosAvaliacao.PROPOSTO
    assert len(manifest.amostras) == 9
    assert {item.particao.value for item in manifest.amostras} == {"DESENVOLVIMENTO", "TESTE"}
    assert lacunas_cobertura_manifesto(manifest) == ("ESCALAS_INSUFICIENTES",)


def test_sample_metadata_rejects_invalid_digest_size_and_page_count() -> None:
    sample = make_sample()

    with pytest.raises(DomainValidationError, match="SHA-256"):
        replace(sample, sha256="inválido")
    with pytest.raises(DomainValidationError, match="Tamanho"):
        replace(sample, tamanho_bytes=0)
    with pytest.raises(DomainValidationError, match="página"):
        replace(sample, total_paginas=0)

    normalized = replace(
        sample,
        sha256="A" * 64,
        orientacao=" paisagem ",
        qualidade=" hibrido ",
        densidade=" alta ",
        casos_especiais=("edge-b", "edge-a", "edge-a"),
    )
    assert normalized.sha256 == "a" * 64
    assert (normalized.orientacao, normalized.qualidade, normalized.densidade) == (
        "PAISAGEM",
        "HIBRIDO",
        "ALTA",
    )
    assert normalized.casos_especiais == ("edge-a", "edge-b")


def test_manifest_rejects_inconsistent_versions_dates_and_state() -> None:
    manifest = make_manifest()

    with pytest.raises(DomainValidationError, match="schema"):
        replace(manifest, schema_version=2)
    with pytest.raises(DomainValidationError, match="Criação"):
        replace(manifest, criado_em=datetime(2026, 7, 21))
    with pytest.raises(DomainValidationError, match="Congelamento"):
        replace(manifest, congelado_em=datetime(2026, 7, 21))
    with pytest.raises(DomainValidationError, match="deve registrar"):
        replace(manifest, congelado_em=None)
    with pytest.raises(DomainValidationError, match="não pode possuir"):
        replace(
            manifest,
            estado=EstadoConjuntoAvaliacao.EM_PREPARACAO,
            congelado_em=FIXED_TIME,
        )


def test_manifest_requires_unique_samples_and_both_partitions() -> None:
    manifest = make_manifest()
    development, test = manifest.amostras

    with pytest.raises(DomainValidationError, match="possuir amostras"):
        replace(manifest, amostras=())
    with pytest.raises(DomainValidationError, match="IDs de amostra"):
        replace(manifest, amostras=(development, replace(test, id=development.id)))
    with pytest.raises(DomainValidationError, match="Hashes de amostra"):
        replace(manifest, amostras=(development, replace(test, sha256=development.sha256)))
    with pytest.raises(DomainValidationError, match="separar desenvolvimento e teste"):
        replace(
            manifest,
            amostras=tuple(
                replace(sample, particao=ParticaoAvaliacao.TESTE) for sample in manifest.amostras
            ),
        )
    with pytest.raises(DomainValidationError, match="não pertence"):
        manifest.obter_amostra("amostra-inexistente")
