"""Orquestrador determinístico dos analisadores e relações explícitas."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from zeny_project_handler.application.analysis_regions import classificar_pontos_de_entrega
from zeny_project_handler.application.document_zones import (
    evidencias_sem_anotacoes_de_revisao,
    evidencias_sem_cabecalho,
)
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
from .rule_support import center
from .span_rules import associar_tracados_de_cabos

_MAXIMUM_DUPLICATE_OCCURRENCE_AXIS_DISTANCE = 0.015


class InterpretadorRegrasExplicitas:
    nome = "regras-explicitas-cemig"
    versao = "21.0"

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
            evidencias=evidencias_sem_cabecalho(
                evidencias_sem_anotacoes_de_revisao(solicitacao.evidencias)
            ),
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
        elements = classificar_pontos_de_entrega(
            elements,
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
    result: list[PropostaElemento] = []
    for proposal in proposals:
        attributes = dict(proposal.atributos_sugeridos)
        operational_label = attributes.get("identificador_operacional")
        catalog_reference = proposal.tipo_catalogo_sugerido_id or proposal.codigo_observado
        if (
            proposal.categoria is CategoriaElemento.CABO
            or operational_label is None
            or catalog_reference is None
        ):
            result.append(proposal)
            continue
        key = (
            proposal.categoria,
            catalog_reference,
            operational_label,
            proposal.situacao_projeto,
            attributes.get("qualificador_estrutura"),
        )
        groups.setdefault(key, []).append(proposal)
    for semantic_key in sorted(
        groups,
        key=lambda key: tuple(str(part) for part in key),
    ):
        for candidates in _occurrence_groups(tuple(groups[semantic_key])):
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
    return tuple(sorted(result, key=lambda item: str(item.id)))


def _occurrence_groups(
    proposals: tuple[PropostaElemento, ...],
) -> tuple[tuple[PropostaElemento, ...], ...]:
    groups: list[list[PropostaElemento]] = []
    for proposal in sorted(proposals, key=lambda item: str(item.id)):
        matching = next(
            (
                group
                for group in groups
                if all(_same_physical_occurrence(proposal, current) for current in group)
            ),
            None,
        )
        if matching is None:
            groups.append([proposal])
        else:
            matching.append(proposal)
    return tuple(tuple(group) for group in groups)


def _same_physical_occurrence(
    first: PropostaElemento,
    second: PropostaElemento,
) -> bool:
    first_attributes = dict(first.atributos_sugeridos)
    second_attributes = dict(second.atributos_sugeridos)
    first_source = first_attributes.get("evidencia_ocorrencia_id")
    second_source = second_attributes.get("evidencia_ocorrencia_id")
    if first_source is not None and first_source == second_source:
        return first_attributes.get("identidade_ocorrencia") == second_attributes.get(
            "identidade_ocorrencia"
        )
    if first.geometria.pagina_id != second.geometria.pagina_id:
        return False
    first_x, first_y = center(first.geometria)
    second_x, second_y = center(second.geometria)
    return (
        abs(first_x - second_x) <= _MAXIMUM_DUPLICATE_OCCURRENCE_AXIS_DISTANCE
        and abs(first_y - second_y) <= _MAXIMUM_DUPLICATE_OCCURRENCE_AXIS_DISTANCE
    )


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
