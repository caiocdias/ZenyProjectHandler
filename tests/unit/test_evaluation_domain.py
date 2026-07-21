from __future__ import annotations

from decimal import Decimal

import pytest
from tests.evaluation_factories import make_annotation, make_manifest, make_sample

from zeny_project_handler.adapters.evaluation import JsonEvaluationDataset
from zeny_project_handler.domain.enums import (
    EstadoConjuntoAvaliacao,
    EstadoCriteriosAvaliacao,
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
