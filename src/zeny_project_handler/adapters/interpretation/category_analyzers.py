"""Analisadores pequenos, um para cada categoria do catálogo."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid5

from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.catalog import ItemCatalogoType
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
    TipoGeometria,
)
from zeny_project_handler.domain.interpretation import RegraReconhecimento
from zeny_project_handler.ports.interpretation import SolicitacaoInterpretacao

from .rule_support import contains_code, nearest_context_evidence, situation_from_evidence


class AnalisadorCatalogoPorCodigo:
    """Base reutilizável; subclasses fixam uma única categoria de responsabilidade."""

    nome = "codigo-catalogo"
    versao = "1.0"
    categoria: CategoriaElemento

    def analisar(
        self,
        solicitacao: SolicitacaoInterpretacao,
        regra: RegraReconhecimento,
    ) -> tuple[PropostaElemento, ...]:
        if regra.estrategia != "CODIGO_CATALOGO":
            raise ValueError(f"Estratégia não suportada pelo analisador: {regra.estrategia}")
        items = sorted(
            solicitacao.catalogo.itens_ativos(self.categoria),
            key=lambda item: (-len(item.codigo), item.codigo.casefold()),
        )
        proposals: list[PropostaElemento] = []
        for evidence in sorted(solicitacao.evidencias, key=lambda item: str(item.id)):
            if evidence.tipo not in regra.tipos_evidencia or not evidence.conteudo_bruto:
                continue
            matches = tuple(
                item for item in items if contains_code(evidence.conteudo_bruto or "", item.codigo)
            )
            for item in matches:
                proposal = self._proposal(
                    solicitacao,
                    regra,
                    evidence,
                    item,
                    len(matches) > 1,
                )
                minimum = solicitacao.configuracao.confianca_minima
                if proposal.confianca is not None and proposal.confianca >= minimum:
                    proposals.append(proposal)
        return tuple(proposals)

    def _proposal(
        self,
        request: SolicitacaoInterpretacao,
        rule: RegraReconhecimento,
        evidence: EvidenciaDocumento,
        item: ItemCatalogoType,
        ambiguous: bool,
    ) -> PropostaElemento:
        contextual = nearest_context_evidence(
            evidence,
            request.evidencias,
            rule.distancia_contexto_maxima,
        )
        situation = None
        if contextual is not None:
            situation = situation_from_evidence(contextual, self.categoria, request.catalogo)
        if situation is None:
            situation = situation_from_evidence(evidence, self.categoria, request.catalogo)
        situation = situation or SituacaoProjeto.EXISTENTE
        context_ids = (contextual.id,) if contextual is not None else ()
        evidence_ids = tuple(sorted({evidence.id, *context_ids}, key=str))
        situation_bonus = (
            Decimal("0.08") if situation is not SituacaoProjeto.EXISTENTE else Decimal(0)
        )
        confidence = min(Decimal(1), rule.confianca_base + situation_bonus)
        geometry = (
            contextual.geometria
            if self.categoria is CategoriaElemento.CABO
            and contextual is not None
            and contextual.geometria.tipo is TipoGeometria.POLILINHA
            else evidence.geometria
        )
        proposal_id = uuid5(
            request.execucao_id,
            f"elemento:{rule.id}:{item.id}:{evidence.id}",
        )
        return PropostaElemento(
            id=proposal_id,
            execucao_id=request.execucao_id,
            categoria=self.categoria,
            situacao_projeto=situation,
            estado_revisao=EstadoRevisao.CONFLITANTE if ambiguous else EstadoRevisao.PROPOSTA,
            evidencia_ids=evidence_ids,
            geometria=geometry,
            tipo_catalogo_sugerido_id=item.id,
            codigo_observado=item.codigo,
            atributos_sugeridos=(
                ("registro_regras", request.registro.versao),
                ("regra_id", rule.id),
            ),
            confianca=confidence,
            justificativa=(
                f"A regra {rule.id} reconheceu exatamente o código {item.codigo} em texto ou OCR."
            ),
        )


class AnalisadorPoste(AnalisadorCatalogoPorCodigo):
    nome = "poste-codigo-catalogo"
    categoria = CategoriaElemento.POSTE


class AnalisadorEstruturaMt(AnalisadorCatalogoPorCodigo):
    nome = "estrutura-mt-codigo-catalogo"
    categoria = CategoriaElemento.ESTRUTURA_MT


class AnalisadorEstruturaBt(AnalisadorCatalogoPorCodigo):
    nome = "estrutura-bt-codigo-catalogo"
    categoria = CategoriaElemento.ESTRUTURA_BT


class AnalisadorCabo(AnalisadorCatalogoPorCodigo):
    nome = "cabo-codigo-catalogo"
    categoria = CategoriaElemento.CABO


class AnalisadorEquipamento(AnalisadorCatalogoPorCodigo):
    nome = "equipamento-codigo-catalogo"
    categoria = CategoriaElemento.EQUIPAMENTO
