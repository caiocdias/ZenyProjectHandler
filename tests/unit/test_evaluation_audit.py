from __future__ import annotations

from pathlib import Path

from tests.evaluation_factories import make_annotation, make_criteria, make_manifest, make_sample

from zeny_project_handler.application.evaluation_audit import AuditarConjuntoAvaliacao
from zeny_project_handler.domain.enums import PapelAnotacao
from zeny_project_handler.domain.evaluation import AnotacaoAmostra


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


def test_audit_blocks_freeze_when_double_annotation_and_coverage_are_missing() -> None:
    result = AuditarConjuntoAvaliacao(IncompleteRepository()).executar()

    assert not result.pronto_para_congelar
    assert "ANOTACAO_DUPLA_AUSENTE:amostra-001" in result.lacunas
    assert "ESCALAS_INSUFICIENTES" in result.lacunas
    assert "CATEGORIA_TESTE_AUSENTE:CABO" in result.lacunas
