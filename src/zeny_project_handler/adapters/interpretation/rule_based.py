"""Orquestrador determinístico dos analisadores e relações explícitas."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from zeny_project_handler.application.document_zones import evidencias_sem_cabecalho
from zeny_project_handler.domain.analysis import (
    DiagnosticoAnalise,
    EvidenciaDocumento,
    PropostaElemento,
)
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.domain.interpretation import RegistroRegrasInterpretacao
from zeny_project_handler.ports.interpretation import (
    AnalisadorCategoriaPort,
    InterpretacaoCanceladaError,
    ResultadoInterpretacao,
    SolicitacaoInterpretacao,
)

from .category_analyzers import (
    AnalisadorCabo,
    AnalisadorEquipamento,
    AnalisadorEstruturaBt,
    AnalisadorEstruturaMt,
    AnalisadorPoste,
)
from .operational_labels import filtrar_propostas_identificadas
from .relation_rules import generate_relations, mark_conflicts
from .span_rules import associar_tracados_de_cabos


class InterpretadorRegrasExplicitas:
    nome = "regras-explicitas-cemig"
    versao = "15.0"

    def __init__(
        self,
        registro: RegistroRegrasInterpretacao,
        analisadores: tuple[AnalisadorCategoriaPort, ...] | None = None,
    ) -> None:
        self.registro = registro
        self._analyzers = analisadores or (
            AnalisadorPoste(),
            AnalisadorEstruturaMt(),
            AnalisadorEstruturaBt(),
            AnalisadorCabo(),
            AnalisadorEquipamento(),
        )

    def interpretar(
        self,
        solicitacao: SolicitacaoInterpretacao,
        *,
        cancelado: Callable[[], bool] | None = None,
    ) -> ResultadoInterpretacao:
        if solicitacao.registro.assinatura() != self.registro.assinatura():
            raise ValueError("Solicitação usa um registro diferente do interpretador")
        cancellation = cancelado or (lambda: False)
        project_request = replace(
            solicitacao,
            evidencias=evidencias_sem_cabecalho(solicitacao.evidencias),
        )
        proposals: list[PropostaElemento] = []
        diagnostics: list[DiagnosticoAnalise] = []
        for analyzer in self._analyzers:
            _raise_if_cancelled(cancellation)
            if analyzer.categoria not in solicitacao.configuracao.categorias_habilitadas:
                continue
            try:
                rule = self.registro.regra_da_categoria(analyzer.categoria)
                proposals.extend(analyzer.analisar(project_request, rule))
            except Exception as error:
                diagnostics.append(_analyzer_diagnostic(analyzer.nome, error))
        identified_proposals = filtrar_propostas_identificadas(
            tuple(proposals),
            project_request.evidencias,
        )
        if len(identified_proposals) > solicitacao.configuracao.maximo_propostas:
            raise ValueError("Quantidade de propostas excedeu o limite configurado")
        proposals_with_paths = associar_tracados_de_cabos(
            identified_proposals,
            project_request.evidencias,
            solicitacao.catalogo,
        )
        elements = mark_conflicts(
            _deduplicate_point_proposals(
                proposals_with_paths,
                project_request.evidencias,
            ),
            project_request.evidencias,
        )
        relations = (
            generate_relations(
                solicitacao.execucao_id,
                elements,
                self.registro,
                solicitacao.catalogo,
            )
            if solicitacao.configuracao.gerar_relacoes
            else ()
        )
        _raise_if_cancelled(cancellation)
        return ResultadoInterpretacao(
            elementos=tuple(sorted(elements, key=lambda item: str(item.id))),
            relacoes=tuple(sorted(relations, key=lambda item: str(item.id))),
            diagnosticos=tuple(diagnostics),
        )


def _raise_if_cancelled(cancelled: Callable[[], bool]) -> None:
    if cancelled():
        raise InterpretacaoCanceladaError("Interpretação cancelada")


def _deduplicate_point_proposals(
    proposals: tuple[PropostaElemento, ...],
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[PropostaElemento, ...]:
    targeted_evidence_ids = {
        item.id
        for item in evidence
        if dict(item.atributos_extraidos).get("motor_ocr")
        in {
            "tesseract-bloco-operacional-localizado",
            "tesseract-rotulo-linear-retificado",
            "tesseract-rotulo-operacional-localizado",
        }
    }
    groups: dict[tuple[object, ...], list[PropostaElemento]] = {}
    keys: dict[object, tuple[object, ...] | None] = {}
    for proposal in proposals:
        attributes = dict(proposal.atributos_sugeridos)
        operational_label = attributes.get("identificador_operacional")
        catalog_reference = proposal.tipo_catalogo_sugerido_id or proposal.codigo_observado
        if (
            proposal.categoria is CategoriaElemento.CABO
            or operational_label is None
            or catalog_reference is None
        ):
            keys[proposal.id] = None
            continue
        key = (
            proposal.categoria,
            catalog_reference,
            operational_label,
            proposal.situacao_projeto,
        )
        keys[proposal.id] = key
        groups.setdefault(key, []).append(proposal)
    result = []
    emitted: set[tuple[object, ...]] = set()
    for proposal in proposals:
        proposal_key = keys[proposal.id]
        if proposal_key is None:
            result.append(proposal)
            continue
        if proposal_key in emitted:
            continue
        emitted.add(proposal_key)
        candidates = groups[proposal_key]
        selected = max(
            candidates,
            key=lambda item: (
                any(reference in targeted_evidence_ids for reference in item.evidencia_ids),
                item.confianca or 0,
                str(item.id),
            ),
        )
        result.append(
            replace(
                selected,
                evidencia_ids=tuple(
                    sorted(
                        {
                            reference
                            for candidate in candidates
                            for reference in candidate.evidencia_ids
                        },
                        key=str,
                    )
                ),
            )
        )
    return tuple(result)


def _analyzer_diagnostic(name: str, error: Exception) -> DiagnosticoAnalise:
    return DiagnosticoAnalise(
        codigo="interpretacao.analisador_falhou",
        mensagem=str(error).strip() or error.__class__.__name__,
        extrator=name,
    )


__all__ = [
    "AnalisadorCabo",
    "AnalisadorEquipamento",
    "AnalisadorEstruturaBt",
    "AnalisadorEstruturaMt",
    "AnalisadorPoste",
    "InterpretadorRegrasExplicitas",
]
