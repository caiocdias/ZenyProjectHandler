from __future__ import annotations

from pathlib import Path

from tests.evaluation_factories import (
    make_annotation,
    make_criteria,
    make_element,
    make_manifest,
    make_sample,
)

from zeny_project_handler.application.evaluation_audit import AuditarConjuntoAvaliacao
from zeny_project_handler.domain.enums import CategoriaElemento, PapelAnotacao
from zeny_project_handler.domain.evaluation import (
    AnotacaoAmostra,
    CriteriosRegressaoAvaliacao,
    ManifestoAvaliacao,
)


class IncompleteRepository:
    def __init__(self) -> None:
        self.sample = make_sample(double_annotation=True)
        self.manifest = make_manifest(test_sample=self.sample)

    def carregar_manifesto(self):  # type: ignore[no-untyped-def]
        return self.manifest

    def carregar_criterios(self):  # type: ignore[no-untyped-def]
        return make_criteria()

    def carregar_anotacao(self, amostra_id: str, papel: PapelAnotacao) -> AnotacaoAmostra:
        if amostra_id != self.sample.id or papel is not PapelAnotacao.CONSENSO:
            raise ValueError("ausente")
        return make_annotation(sample=self.sample)

    def salvar_anotacao(self, anotacao: AnotacaoAmostra) -> Path:
        raise NotImplementedError


class ReviewedRepository:
    def __init__(self) -> None:
        self.sample = make_sample(double_annotation=True)
        self.manifest = make_manifest(test_sample=self.sample)
        self.elements = tuple(
            make_element(
                element_id=f"elemento-{category.value.lower().replace('_', '-')}",
                category=category,
            )
            for category in CategoriaElemento
        )

    def carregar_manifesto(self) -> ManifestoAvaliacao:
        return self.manifest

    def carregar_criterios(self) -> CriteriosRegressaoAvaliacao:
        return make_criteria()

    def carregar_anotacao(self, amostra_id: str, papel: PapelAnotacao) -> AnotacaoAmostra:
        sample = self.manifest.obter_amostra(amostra_id)
        elements = self.elements if sample.id == self.sample.id else (make_element(),)
        return make_annotation(
            sample=sample,
            role=papel,
            annotator_id=f"anotador-{papel.value.lower()}",
            elements=elements,
        )

    def salvar_anotacao(self, anotacao: AnotacaoAmostra) -> Path:
        raise NotImplementedError


def test_audit_blocks_freeze_when_double_annotation_and_coverage_are_missing() -> None:
    result = AuditarConjuntoAvaliacao(IncompleteRepository()).executar()

    assert not result.pronto_para_congelar
    assert "ANOTACAO_DUPLA_AUSENTE:amostra-001" in result.lacunas
    assert "ESCALAS_INSUFICIENTES" in result.lacunas
    assert "CATEGORIA_TESTE_AUSENTE:CABO" in result.lacunas


def test_audit_accepts_reviewed_double_annotations_and_all_test_categories() -> None:
    result = AuditarConjuntoAvaliacao(ReviewedRepository()).executar()

    assert len(result.divergencias) == 1
    assert result.divergencias[0].taxa_divergencia == 0
    assert not any(gap.startswith("CATEGORIA_TESTE_AUSENTE") for gap in result.lacunas)
    assert not any(gap.startswith("ANOTACAO_DUPLA_AUSENTE") for gap in result.lacunas)
