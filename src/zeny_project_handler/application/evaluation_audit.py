"""Auditoria do corpus antes de seu congelamento."""

from __future__ import annotations

from dataclasses import dataclass

from zeny_project_handler.application.evaluation_metrics import medir_divergencia_anotadores
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoAnotacao,
    EstadoConjuntoAvaliacao,
    EstadoCriteriosAvaliacao,
    PapelAnotacao,
    ParticaoAvaliacao,
)
from zeny_project_handler.domain.evaluation import (
    CriteriosRegressaoAvaliacao,
    ManifestoAvaliacao,
    lacunas_cobertura_manifesto,
    validar_anotacao_no_manifesto,
)
from zeny_project_handler.domain.evaluation_metrics import DivergenciaAnotadores
from zeny_project_handler.ports.evaluation import RepositorioConjuntoAvaliacaoPort


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoAuditoriaConjunto:
    lacunas: tuple[str, ...]
    divergencias: tuple[DivergenciaAnotadores, ...]

    @property
    def pronto_para_congelar(self) -> bool:
        return not self.lacunas


class AuditarConjuntoAvaliacao:
    def __init__(self, repository: RepositorioConjuntoAvaliacaoPort) -> None:
        self._repository = repository

    def executar(self) -> ResultadoAuditoriaConjunto:
        manifest = self._repository.carregar_manifesto()
        criteria = self._repository.carregar_criterios()
        gaps = list(lacunas_cobertura_manifesto(manifest))
        divergences: list[DivergenciaAnotadores] = []
        consensus_annotations = []
        if criteria.estado is not EstadoCriteriosAvaliacao.APROVADO:
            gaps.append("CRITERIOS_NAO_APROVADOS")
        for sample in manifest.amostras:
            try:
                consensus = self._repository.carregar_anotacao(sample.id, PapelAnotacao.CONSENSO)
                validar_anotacao_no_manifesto(consensus, manifest)
                consensus_annotations.append((sample, consensus))
                if consensus.estado is not EstadoAnotacao.CONGELADA:
                    gaps.append(f"CONSENSO_NAO_CONGELADO:{sample.id}")
            except (OSError, ValueError):
                gaps.append(f"CONSENSO_AUSENTE:{sample.id}")
            if sample.dupla_anotacao:
                self._audit_double_annotation(sample.id, manifest, criteria, gaps, divergences)
        test_categories = {
            element.categoria
            for sample, annotation in consensus_annotations
            if sample.particao is ParticaoAvaliacao.TESTE
            for element in annotation.elementos
        }
        for category in CategoriaElemento:
            if category not in test_categories:
                gaps.append(f"CATEGORIA_TESTE_AUSENTE:{category.value}")
        if manifest.estado is EstadoConjuntoAvaliacao.CONGELADO and gaps:
            gaps.append("MANIFESTO_CONGELADO_INCONSISTENTE")
        return ResultadoAuditoriaConjunto(
            lacunas=tuple(sorted(set(gaps))),
            divergencias=tuple(sorted(divergences, key=lambda item: item.amostra_id)),
        )

    def _audit_double_annotation(
        self,
        sample_id: str,
        manifest: ManifestoAvaliacao,
        criteria: CriteriosRegressaoAvaliacao,
        gaps: list[str],
        divergences: list[DivergenciaAnotadores],
    ) -> None:
        try:
            primary = self._repository.carregar_anotacao(sample_id, PapelAnotacao.PRIMARIA)
            secondary = self._repository.carregar_anotacao(sample_id, PapelAnotacao.SECUNDARIA)
            validar_anotacao_no_manifesto(primary, manifest)
            validar_anotacao_no_manifesto(secondary, manifest)
            divergence = medir_divergencia_anotadores(primary, secondary, criteria)
            divergences.append(divergence)
            if divergence.taxa_divergencia > criteria.divergencia_humana_maxima:
                gaps.append(f"DIVERGENCIA_HUMANA_ACIMA_LIMITE:{sample_id}")
        except (OSError, ValueError):
            gaps.append(f"ANOTACAO_DUPLA_AUSENTE:{sample_id}")
