"""Orquestração auditável e idempotente do pipeline de interpretação."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid5

from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    ExecucaoAnalise,
    PropostaElemento,
    PropostaRelacao,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico, ExtraAttributes, TipoEquipamento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    SituacaoProjeto,
    TipoEvidencia,
    TipoGeometria,
)
from zeny_project_handler.domain.interpretation import RegistroRegrasInterpretacao
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.domain.symbols import GeometriaObservacaoSimbolo, ObservacaoSimbolo
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.interpretation import (
    ConfiguracaoInterpretacao,
    InterpretadorEvidenciasPort,
    ResultadoInterpretacao,
    SolicitacaoInterpretacao,
)
from zeny_project_handler.ports.interpretation import (
    InterpretacaoCanceladaError as PortInterpretacaoCanceladaError,
)
from zeny_project_handler.ports.persistence import UnitOfWorkPort

from .automatic_promotion import promover_resultado_automatico
from .errors import (
    InterpretacaoCanceladaError,
    InterpretacaoProjetoError,
    ProjetoNaoEncontradoError,
)
from .method_reconciliation import COMPOSITION_VERSION, attach_method_conflicts
from .symbol_reconciliation import SymbolReconciliation
from .technical_revisions import preserve_revision_decision


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoExecucaoInterpretacao:
    execucao: ExecucaoAnalise
    elementos: tuple[PropostaElemento, ...]
    relacoes: tuple[PropostaRelacao, ...]
    resultado_reutilizado: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextoInterpretacao:
    projeto: Projeto
    catalogo: CatalogoTecnico
    execucao_extracao: ExecucaoAnalise
    evidencias: tuple[EvidenciaDocumento, ...]


SYMBOL_SEMANTICS_VERSION = "e14-symbol-review-1"


class ExecutarPipelineInterpretacao:
    def __init__(
        self,
        interpretador: InterpretadorEvidenciasPort,
        registro: RegistroRegrasInterpretacao,
        unidade_de_trabalho: Callable[[], UnitOfWorkPort],
        *,
        relogio: Callable[[], datetime] | None = None,
    ) -> None:
        self._interpreter = interpretador
        self._registry = registro
        self._unit_of_work = unidade_de_trabalho
        self._clock = relogio or (lambda: datetime.now(UTC))

    def executar(
        self,
        projeto_id: UUID,
        execucao_extracao_id: UUID,
        *,
        configuracao: ConfiguracaoInterpretacao | None = None,
        cancelado: Callable[[], bool] | None = None,
        simbolos: SymbolReconciliation | None = None,
        symbol_configuration_signature: str | None = None,
    ) -> ResultadoExecucaoInterpretacao:
        config = configuracao or ConfiguracaoInterpretacao()
        context = self._load_context(projeto_id, execucao_extracao_id)
        symbol_signature = _symbol_signature(simbolos, symbol_configuration_signature)
        execution_id = _execution_id(
            projeto_id,
            execucao_extracao_id,
            self._registry,
            config,
            interpreter_name=self._interpreter.nome,
            interpreter_version=self._interpreter.versao,
            symbol_signature=symbol_signature,
        )
        stored = self._load_completed(execution_id)
        if stored is not None:
            return stored
        started_at = self._aware_now()
        parameters = _execution_parameters(
            execucao_extracao_id,
            self._registry,
            config,
            symbol_signature=symbol_signature,
            symbol_configuration_signature=symbol_configuration_signature,
        )
        self._persist_execution(
            ExecucaoAnalise(
                id=execution_id,
                projeto_id=projeto_id,
                metodo=self._interpreter.nome,
                versao_metodo=self._interpreter.versao,
                parametros=parameters,
                estado=EstadoExecucaoAnalise.INICIADA,
                iniciada_em=started_at,
            )
        )
        request = SolicitacaoInterpretacao(
            projeto_id=projeto_id,
            execucao_id=execution_id,
            execucao_extracao_id=execucao_extracao_id,
            catalogo=context.catalogo,
            evidencias=context.evidencias,
            registro=self._registry,
            configuracao=config,
        )
        if simbolos is not None:
            consumed_legacy_ids = {
                uuid5(execucao_extracao_id, observation.chave_legada)
                for occurrence in simbolos.occurrences
                for observation in occurrence.observations
                if observation.chave_legada
            }
            request = replace(
                request,
                evidencias=tuple(
                    item for item in request.evidencias if item.id not in consumed_legacy_ids
                ),
            )
        try:
            result = self._interpreter.interpretar(request, cancelado=cancelado)
            symbol_evidence: tuple[EvidenciaDocumento, ...] = ()
            if simbolos is not None:
                symbol_evidence, symbol_elements, symbol_relations = _symbol_proposals(
                    simbolos, context, execution_id, result.elementos
                )
                result = replace(
                    result,
                    elementos=(*result.elementos, *symbol_elements),
                    relacoes=(*result.relacoes, *symbol_relations),
                )
            result = replace(
                result,
                elementos=attach_method_conflicts(
                    result.elementos, (*context.evidencias, *symbol_evidence)
                ),
            )
        except PortInterpretacaoCanceladaError as error:
            cancelled = self._finished_execution(
                execution_id,
                projeto_id,
                parameters,
                started_at,
                EstadoExecucaoAnalise.CANCELADA,
            )
            self._persist_execution(cancelled)
            raise InterpretacaoCanceladaError(
                f"Interpretação cancelada. Execução retomável: {execution_id}"
            ) from error
        except Exception as error:
            failed = self._finished_execution(
                execution_id,
                projeto_id,
                parameters,
                started_at,
                EstadoExecucaoAnalise.FALHOU,
                erro=(str(error).strip() or error.__class__.__name__)[:1000],
            )
            self._persist_execution(failed)
            raise InterpretacaoProjetoError(
                f"A interpretação falhou. Execução registrada: {execution_id}"
            ) from error
        completed = self._finished_execution(
            execution_id,
            projeto_id,
            parameters,
            started_at,
            EstadoExecucaoAnalise.CONCLUIDA,
            result=result,
        )
        promoted = self._persist_result(completed, result, context, symbol_evidence)
        return ResultadoExecucaoInterpretacao(
            execucao=completed,
            elementos=promoted.elementos,
            relacoes=promoted.relacoes,
            resultado_reutilizado=False,
        )

    def _load_context(self, project_id: UUID, source_execution_id: UUID) -> ContextoInterpretacao:
        with self._unit_of_work() as work:
            project = work.projetos.obter(project_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para interpretação")
            catalog = work.catalogos.obter(project.catalogo_versao_id)
            if catalog is None:
                raise InterpretacaoProjetoError("Catálogo do projeto não está disponível")
            source_execution = work.execucoes_analise.obter(source_execution_id)
            if source_execution is None or source_execution.projeto_id != project_id:
                raise InterpretacaoProjetoError("Execução de extração não pertence ao projeto")
            if source_execution.estado is not EstadoExecucaoAnalise.CONCLUIDA:
                raise InterpretacaoProjetoError("Execução de extração precisa estar concluída")
            evidence = work.evidencias.listar_da_execucao(source_execution_id)
            return ContextoInterpretacao(
                projeto=project,
                catalogo=catalog,
                execucao_extracao=source_execution,
                evidencias=evidence,
            )

    def _load_completed(self, execution_id: UUID) -> ResultadoExecucaoInterpretacao | None:
        with self._unit_of_work() as work:
            execution = work.execucoes_analise.obter(execution_id)
            if execution is None or execution.estado is not EstadoExecucaoAnalise.CONCLUIDA:
                return None
            proposals = work.propostas.listar_da_execucao(execution_id)
        return ResultadoExecucaoInterpretacao(
            execucao=execution,
            elementos=tuple(item for item in proposals if isinstance(item, PropostaElemento)),
            relacoes=tuple(item for item in proposals if isinstance(item, PropostaRelacao)),
            resultado_reutilizado=True,
        )

    def _persist_execution(self, execution: ExecucaoAnalise) -> None:
        with self._unit_of_work() as work:
            if work.projetos.obter(execution.projeto_id) is None:
                raise ProjetoNaoEncontradoError("Projeto removido durante a interpretação")
            work.execucoes_analise.salvar(execution)
            work.commit()

    def _persist_result(
        self,
        execution: ExecucaoAnalise,
        result: ResultadoInterpretacao,
        context: ContextoInterpretacao,
        symbol_evidence: tuple[EvidenciaDocumento, ...] = (),
    ) -> ResultadoInterpretacao:
        with self._unit_of_work() as work:
            project = work.projetos.obter(execution.projeto_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto removido durante a interpretação")
            result = _preserve_previous_review(work, execution, result)
            promoted = promover_resultado_automatico(
                project,
                context.catalogo,
                result.elementos,
                result.relacoes,
                promovido_em=execution.finalizada_em or self._aware_now(),
            )
            work.execucoes_analise.salvar(execution)
            work.projetos.salvar(promoted.projeto)
            for evidence in symbol_evidence:
                if work.evidencias.obter(evidence.id) is None:
                    work.evidencias.salvar(evidence)
            for element_proposal in promoted.elementos:
                work.propostas.salvar(element_proposal)
            for relation_proposal in promoted.relacoes:
                work.propostas.salvar(relation_proposal)
            for decision in promoted.decisoes:
                if work.decisoes_revisao.obter_da_proposta(decision.proposta_id) is None:
                    work.decisoes_revisao.salvar(decision)
            work.commit()
        return ResultadoInterpretacao(
            elementos=promoted.elementos,
            relacoes=promoted.relacoes,
            diagnosticos=result.diagnosticos,
        )

    def _finished_execution(
        self,
        execution_id: UUID,
        project_id: UUID,
        parameters: ExtraAttributes,
        started_at: datetime,
        state: EstadoExecucaoAnalise,
        *,
        erro: str | None = None,
        result: ResultadoInterpretacao | None = None,
    ) -> ExecucaoAnalise:
        return ExecucaoAnalise(
            id=execution_id,
            projeto_id=project_id,
            metodo=self._interpreter.nome,
            versao_metodo=self._interpreter.versao,
            parametros=parameters,
            estado=state,
            iniciada_em=started_at,
            finalizada_em=max(started_at, self._aware_now()),
            erro=erro,
            diagnosticos=result.diagnosticos if result is not None else (),
        )

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("Relógio da aplicação deve retornar data com fuso horário")
        return value


def _preserve_previous_review(
    work: UnitOfWorkPort,
    execution: ExecucaoAnalise,
    result: ResultadoInterpretacao,
) -> ResultadoInterpretacao:
    previous_proposals = tuple(
        proposal
        for previous in work.execucoes_analise.listar_do_projeto(execution.projeto_id)
        if previous.id != execution.id
        for proposal in work.propostas.listar_da_execucao(previous.id)
        if isinstance(proposal, PropostaElemento)
    )
    result = replace(
        result,
        elementos=tuple(
            item
            if dict(item.atributos_sugeridos).get("reconciliacao_metodos_pendente")
            else preserve_revision_decision(work, item, previous_proposals)
            for item in result.elementos
        ),
    )
    reviewed_pages = {
        proposal.geometria.pagina_id
        for previous in work.execucoes_analise.listar_do_projeto(execution.projeto_id)
        if previous.id != execution.id
        and previous.metodo == execution.metodo
        and previous.estado is EstadoExecucaoAnalise.CONCLUIDA
        for proposal in work.propostas.listar_da_execucao(previous.id)
        if isinstance(proposal, PropostaElemento)
        and work.decisoes_revisao.obter_da_proposta(proposal.id) is not None
    }
    elements = tuple(
        replace(
            item,
            estado_revisao=EstadoRevisao.CONFLITANTE,
            atributos_sugeridos=(
                *item.atributos_sugeridos,
                ("reconciliacao_reanalise_pendente", True),
            ),
            justificativa=(
                f"{item.justificativa or ''} Esta folha possui decisões anteriores; "
                "reconciliar a nova interpretação com o histórico antes de confirmar."
            ),
        )
        if item.geometria.pagina_id in reviewed_pages
        and not dict(item.atributos_sugeridos).get("revisao_tecnica_decidida")
        else item
        for item in result.elementos
    )
    return replace(result, elementos=elements)


def _execution_parameters(
    source_execution_id: UUID,
    registry: RegistroRegrasInterpretacao,
    config: ConfiguracaoInterpretacao,
    *,
    symbol_signature: str | None = None,
    symbol_configuration_signature: str | None = None,
) -> ExtraAttributes:
    return tuple(
        sorted(
            (
                *config.parametros(),
                ("execucao_extracao_id", str(source_execution_id)),
                ("registro_regras_assinatura", registry.assinatura()),
                ("registro_regras_versao", registry.versao),
                ("reconciliacao_metodos_versao", COMPOSITION_VERSION),
                *(
                    (
                        ("simbolos_reconciliados_assinatura", symbol_signature),
                        ("semantica_simbolos_versao", SYMBOL_SEMANTICS_VERSION),
                        *(
                            (("configuracao_simbolos_assinatura", symbol_configuration_signature),)
                            if symbol_configuration_signature is not None
                            else ()
                        ),
                    )
                    if symbol_signature is not None
                    else ()
                ),
            )
        )
    )


def _execution_id(
    project_id: UUID,
    source_execution_id: UUID,
    registry: RegistroRegrasInterpretacao,
    config: ConfiguracaoInterpretacao,
    *,
    interpreter_name: str,
    interpreter_version: str,
    symbol_signature: str | None = None,
) -> UUID:
    identity = ":".join(
        (
            str(project_id),
            str(source_execution_id),
            registry.assinatura(),
            config.assinatura(),
            interpreter_name,
            interpreter_version,
            COMPOSITION_VERSION,
            *((SYMBOL_SEMANTICS_VERSION, symbol_signature) if symbol_signature else ()),
        )
    )
    return uuid5(registry.id, identity)


def _symbol_signature(
    symbols: SymbolReconciliation | None, configuration_signature: str | None = None
) -> str | None:
    if symbols is None and configuration_signature is None:
        return None
    # E12 IDs identify observations, but its decision and calibration may change
    # without changing those IDs. Include the entire immutable result in the cache key.
    if configuration_signature is None:
        return sha256(repr(symbols).encode("utf-8")).hexdigest()
    return sha256(f"{configuration_signature}:{symbols!r}".encode()).hexdigest()


def _symbol_proposals(
    symbols: SymbolReconciliation,
    context: ContextoInterpretacao,
    execution_id: UUID,
    documentary_proposals: tuple[PropostaElemento, ...],
) -> tuple[
    tuple[EvidenciaDocumento, ...], tuple[PropostaElemento, ...], tuple[PropostaRelacao, ...]
]:
    pages: dict[tuple[str, int], list[tuple[str, UUID]]] = {}
    for document in context.projeto.documentos:
        for page in document.paginas:
            pages.setdefault((document.sha256, page.numero), []).append((str(document.id), page.id))
    known_evidence = {evidence.id for evidence in context.evidencias}
    evidence: dict[UUID, EvidenciaDocumento] = {}
    proposals: list[PropostaElemento] = []
    relations: list[PropostaRelacao] = []
    # Reconciler output already groups one physical occurrence. Never iterate its
    # alternatives into separate proposals or count its primitives as assets.
    for occurrence in symbols.occurrences:
        sources = {
            (
                observation.fonte.documento_id,
                observation.fonte.documento_sha256,
                observation.fonte.pagina_numero,
                observation.fonte.camada,
            )
            for observation in occurrence.observations
        }
        if len(sources) != 1:
            raise ValueError("Ocorrência simbólica mistura documentos, páginas ou camadas")
        document_id, document_sha, page_number, layer = next(iter(sources))
        matching_pages = pages.get((document_sha, page_number), [])
        page_id: UUID | None
        if len(matching_pages) == 1:
            page_id = matching_pages[0][1]
        else:
            matching_ids = [
                page_id for source_id, page_id in matching_pages if source_id == document_id
            ]
            page_id = matching_ids[0] if len(matching_ids) == 1 else None
        if page_id is None:
            raise ValueError("Ocorrência simbólica não pertence ao projeto ou à página")
        observation_ids: list[UUID] = []
        for observation in occurrence.observations:
            evidence_id = (
                uuid5(context.execucao_extracao.id, observation.chave_legada)
                if observation.chave_legada
                else uuid5(context.execucao_extracao.id, f"simbolo:{observation.id}")
            )
            observation_ids.append(evidence_id)
            if evidence_id not in known_evidence and evidence_id not in evidence:
                evidence[evidence_id] = _symbol_evidence(
                    observation, evidence_id, page_id, context.execucao_extracao
                )
        geometry = _symbol_geometry(occurrence.geometry, page_id)
        classes = {alternative.classe for alternative in occurrence.alternatives}
        symbol_class = next(iter(classes)) if len(classes) == 1 else None
        attributes = [dict(observation.atributos) for observation in occurrence.observations]
        legend = any(
            str(item.get("contexto", "")).casefold() in {"legenda", "legend"} for item in attributes
        )
        informative = legend or any(
            item.get("papel") == "informative" or item.get("destino") == "informative_only"
            for item in attributes
        )
        pending_variant = "pending_variant" in occurrence.reasons or any(
            str(item.get("status", "")).casefold() == "pending" for item in attributes
        )
        support_symbol = bool(symbol_class and "ESTAI" in symbol_class)
        category = _symbol_category(symbol_class)
        recognized_role = _recognized_symbol_role(symbol_class)
        role = "informativo" if informative else "suporte" if support_symbol else recognized_role
        # The closed legacy category has no observation-only member. Equipment is
        # an envelope for an unsupported support/informative symbol, never an asset.
        asset_candidate = (
            not informative
            and not pending_variant
            and not support_symbol
            and recognized_role != "desconhecido"
            and category in {CategoriaElemento.POSTE, CategoriaElemento.EQUIPAMENTO}
            and symbol_class is not None
            and layer == "base"
        )
        situations = {observation.situacao for observation in occurrence.observations}
        situation_resolved = (
            len(situations) == 1
            and None not in situations
            and all(
                item.get("situacao_validada") is True
                or item.get("convencao_local_verificada") is True
                for item in attributes
            )
        )
        situation = (
            next((value for value in situations if value is not None), SituacaoProjeto.EXISTENTE)
            if situation_resolved
            else SituacaoProjeto.EXISTENTE
        )
        quantities = {
            quantity
            for item in attributes
            if isinstance((quantity := item.get("quantidade_ativos")), int)
            and not isinstance(quantity, bool)
            and quantity > 0
        }
        quantity_resolved = len(quantities) == 1 and all(
            isinstance(item.get("quantidade_ativos"), int)
            and not isinstance(item.get("quantidade_ativos"), bool)
            and item["quantidade_ativos"] in quantities
            for item in attributes
        )
        catalog_ids = {
            str(item[key])
            for item in attributes
            for key in ("tipo_catalogo_id", "catalogo_item_id")
            if item.get(key)
        }
        catalog_id = None
        if asset_candidate and len(catalog_ids) == 1:
            try:
                candidate_id = UUID(next(iter(catalog_ids)))
            except ValueError:
                candidate_id = None
            if candidate_id is not None:
                catalog_item = context.catalogo.item_por_id(candidate_id)
                if (
                    catalog_item is not None
                    and catalog_item.ativo
                    and catalog_item.categoria is category
                    and _catalog_matches_symbol_class(context.catalogo, catalog_item, symbol_class)
                ):
                    catalog_id = candidate_id
        identity_resolved = (
            len(occurrence.reference_ids) <= 1
            and len({(alt.classe, alt.subtipo) for alt in occurrence.alternatives}) == 1
            and "invalid_reference_id" not in occurrence.reasons
        )
        class_resolved = symbol_class is not None
        support, support_candidates = _symbol_support(geometry, layer, documentary_proposals)
        association_resolved = category is CategoriaElemento.POSTE or support is not None
        if not asset_candidate:
            association_resolved = False
        pending = (
            not asset_candidate
            or occurrence.decision != "eligible"
            or not class_resolved
            or not identity_resolved
            or not situation_resolved
            or not quantity_resolved
            or not association_resolved
            or catalog_id is None
        )
        reasons = [*occurrence.reasons]
        if informative:
            reasons.append("contexto_informativo")
        if support_symbol:
            reasons.append("suporte_sem_tipo_patrimonial")
        if role == "desconhecido" and symbol_class is not None:
            reasons.append("familia_sem_modelo_de_ativo")
        if not class_resolved:
            reasons.append("classe_pendente")
        if not identity_resolved:
            reasons.append("identidade_alternativa")
        if not situation_resolved:
            reasons.append("situacao_pendente")
        if not quantity_resolved:
            reasons.append("quantidade_pendente")
        if not association_resolved:
            reasons.append("associacao_pendente")
        if catalog_id is None:
            reasons.append("catalogo_nao_localizado")
        proposal_id = uuid5(execution_id, f"ocorrencia-simbolo:{occurrence.id}")
        proposal = PropostaElemento(
            id=proposal_id,
            execucao_id=execution_id,
            categoria=category,
            situacao_projeto=situation,
            estado_revisao=EstadoRevisao.CONFLITANTE if pending else EstadoRevisao.PROPOSTA,
            evidencia_ids=tuple(sorted(set(observation_ids), key=str)),
            geometria=geometry,
            tipo_catalogo_sugerido_id=catalog_id if identity_resolved else None,
            codigo_observado=symbol_class,
            atributos_sugeridos=(
                ("origem_simbolo_ocorrencia_id", occurrence.id),
                ("simbolo_suporte_metodos", json.dumps(occurrence.support)),
                (
                    "simbolo_observacoes",
                    json.dumps(
                        [
                            {
                                "observation_id": obs.id,
                                "method_signature": obs.metodo_assinatura,
                                "raw_score": str(obs.score_bruto)
                                if obs.score_bruto is not None
                                else None,
                                "evidence_id": str(evidence_id),
                            }
                            for obs, evidence_id in zip(
                                occurrence.observations, observation_ids, strict=True
                            )
                        ],
                        sort_keys=True,
                    ),
                ),
                (
                    "simbolo_matriz_metodos",
                    json.dumps(
                        [
                            {
                                "method_signature": row.method_signature,
                                "state": row.state,
                                "classes": row.classes,
                            }
                            for row in symbols.method_matrix
                            if row.occurrence_id == occurrence.id
                        ],
                        sort_keys=True,
                    ),
                ),
                ("simbolo_decisao_e12", occurrence.decision),
                ("simbolo_classe", symbol_class),
                (
                    "simbolo_alternativas",
                    json.dumps(
                        [
                            {"classe": alt.classe, "subtipo": alt.subtipo}
                            for alt in occurrence.alternatives
                        ],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                ),
                ("simbolo_reference_ids", json.dumps(occurrence.reference_ids)),
                (
                    "simbolo_observacao_ids",
                    json.dumps(tuple(obs.id for obs in occurrence.observations)),
                ),
                (
                    "simbolo_situacoes_observadas",
                    json.dumps(
                        [
                            {
                                "observacao_id": obs.id,
                                "situacao": obs.situacao.value if obs.situacao else None,
                                "metodo_assinatura": obs.metodo_assinatura,
                                "camada": obs.fonte.camada,
                                "origem_pdf": obs.fonte.origem_pdf.tipo.value,
                                "indicio": _observed_situation_source(obs),
                            }
                            for obs in sorted(occurrence.observations, key=lambda item: item.id)
                        ],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
                (
                    "simbolo_quantidades_observadas",
                    json.dumps(
                        [
                            {
                                "observacao_id": obs.id,
                                "quantidade_ativos": _json_scalar(
                                    dict(obs.atributos).get("quantidade_ativos")
                                ),
                                "metodo_assinatura": obs.metodo_assinatura,
                            }
                            for obs in sorted(occurrence.observations, key=lambda item: item.id)
                        ],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
                (
                    "simbolo_suportes_candidatos",
                    json.dumps(
                        [
                            {
                                "proposta_id": str(candidate.id),
                                "pagina_id": str(candidate.geometria.pagina_id),
                                "distancia_normalizada": round(distance, 6),
                            }
                            for distance, candidate in support_candidates
                        ],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
                ("simbolo_probabilidade_calibrada", occurrence.calibrated_probability),
                ("simbolo_motivo_pendencia", ",".join(dict.fromkeys(reasons))),
                ("simbolo_papel", role),
                ("simbolo_camada", layer),
                ("simbolo_legenda", legend),
                ("simbolo_ativo_elegivel", asset_candidate),
                ("simbolo_classe_resolvida", class_resolved),
                ("simbolo_identidade_resolvida", identity_resolved),
                ("simbolo_situacao_resolvida", situation_resolved),
                ("simbolo_quantidade_resolvida", quantity_resolved),
                ("simbolo_associacao_resolvida", association_resolved),
                ("simbolo_catalogo_resolvido", catalog_id is not None),
                (
                    "simbolo_familia_nao_suportada",
                    pending_variant or (not asset_candidate and not informative),
                ),
                ("situacao_pendente", not situation_resolved),
                ("quantidade_pendente", not quantity_resolved),
                ("associacao_pendente", not association_resolved),
                ("catalogo_nao_localizado", catalog_id is None),
                ("revisao_tecnica_pendente", layer != "base"),
                ("suporte_proposta_id", str(support.id) if support else None),
                ("quantidade_ativos", next(iter(quantities)) if quantity_resolved else None),
            ),
            confianca=occurrence.calibrated_probability,
            justificativa=(
                "Ocorrência visual reconciliada; campos sem evidência direta permanecem pendentes."
            ),
        )
        proposals.append(proposal)
        if support is not None and asset_candidate:
            relations.append(
                PropostaRelacao(
                    id=uuid5(execution_id, f"suporte-simbolo:{proposal_id}:{support.id}"),
                    execucao_id=execution_id,
                    origem_referencia_id=proposal_id,
                    destino_referencia_id=support.id,
                    tipo_relacao="INSTALADO_EM",
                    evidencia_ids=tuple(
                        sorted({*proposal.evidencia_ids, *support.evidencia_ids}, key=str)
                    ),
                    estado_revisao=EstadoRevisao.PROPOSTA
                    if not pending
                    else EstadoRevisao.CONFLITANTE,
                    confianca=occurrence.calibrated_probability,
                    justificativa="Suporte único na mesma página e próximo ao símbolo visual.",
                )
            )
    return tuple(evidence.values()), tuple(proposals), tuple(relations)


def _symbol_category(symbol_class: str | None) -> CategoriaElemento:
    if symbol_class in {"POSTE", "POSTE_AT"} or (
        symbol_class is not None and "_POSTE_" in symbol_class
    ):
        return CategoriaElemento.POSTE
    # A cable symbol does not establish a traced span. Keep it reviewable as an
    # observation instead of inventing a Cabo from a point-like glyph.
    return CategoriaElemento.EQUIPAMENTO


def _recognized_symbol_role(symbol_class: str | None) -> str:
    if symbol_class is None:
        return "desconhecido"
    if symbol_class.startswith(("POSTE", "ESTRUTURA_POSTE")):
        return "suporte"
    if symbol_class.startswith(("ESTAI", "RASCUNHO_EXISTENTE_ESTAI", "RASCUNHO_RETIRAR_ESTAI")):
        return "suporte"
    if symbol_class.startswith(
        (
            "ATERRAMENTO",
            "CHAVE_FACA",
            "CHAVE_FUSIVEL",
            "TRANSFORMADOR",
            "PARA_RAIOS",
            "REGULADOR_TENSAO",
            "EQUIPAMENTO_INTERRUPCAO",
            "EQUIPAMENTO_PROTECAO",
            "EQUIPAMENTO_REGULACAO",
            "RASCUNHO_EXISTENTE_TRANSFORMADOR",
            "RASCUNHO_RETIRAR_TRANSFORMADOR",
            "RASCUNHO_EXISTENTE_EP_",
            "RASCUNHO_RETIRAR_EP_",
            "RASCUNHO_EXISTENTE_EI_",
            "RASCUNHO_RETIRAR_EI_",
            "RASCUNHO_EXISTENTE_ATERRAMENTO",
            "RASCUNHO_RETIRAR_ATERRAMENTO",
            "RASCUNHO_EXISTENTE_REGULADOR",
            "RASCUNHO_RETIRAR_REGULADOR",
        )
    ):
        return "equipamento"
    return "desconhecido"


def _catalog_matches_symbol_class(
    catalog: CatalogoTecnico, item: object, symbol_class: str | None
) -> bool:
    if symbol_class is None:
        return False
    if isinstance(item, TipoEquipamento):
        options = {
            option.id: option.codigo
            for group in catalog.grupos_opcao
            if group.chave == "classe_equipamento"
            for option in group.opcoes
        }
        return options.get(item.classe_equipamento_opcao_id) == symbol_class
    # A pole glyph does not encode material, height or load class.
    return False


def _symbol_geometry(
    source_geometry: GeometriaObservacaoSimbolo, page_id: UUID
) -> GeometriaDocumento:
    points = source_geometry.pontos_normalizados
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    if min(xs) == max(xs) or min(ys) == max(ys):
        return GeometriaDocumento(
            pagina_id=page_id,
            tipo=TipoGeometria.PONTO,
            pontos=(PontoNormalizado(x=(min(xs) + max(xs)) / 2, y=(min(ys) + max(ys)) / 2),),
        )
    return GeometriaDocumento(
        pagina_id=page_id,
        tipo=TipoGeometria.CAIXA,
        pontos=(PontoNormalizado(x=min(xs), y=min(ys)), PontoNormalizado(x=max(xs), y=max(ys))),
    )


def _symbol_evidence(
    observation: ObservacaoSimbolo,
    evidence_id: UUID,
    page_id: UUID,
    extraction: ExecucaoAnalise,
) -> EvidenciaDocumento:
    geometry = _symbol_geometry(observation.geometria, page_id)
    return EvidenciaDocumento(
        id=evidence_id,
        execucao_id=extraction.id,
        pagina_id=page_id,
        tipo=TipoEvidencia.VETOR if observation.primitivas else TipoEvidencia.IMAGEM,
        geometria=geometry,
        metodo=f"simbolo:{observation.metodo_assinatura}",
        versao_metodo=SYMBOL_SEMANTICS_VERSION,
        parametros=(("documento_sha256", observation.fonte.documento_sha256),),
        conteudo_bruto=observation.conteudo_bruto,
        criada_em=extraction.iniciada_em,
        origem_pdf=observation.fonte.origem_pdf,
        atributos_extraidos=(
            ("simbolo_observacao_id", observation.id),
            ("simbolo_score_bruto", observation.score_bruto),
            ("simbolo_camada", observation.fonte.camada),
            (
                "simbolo_situacao_observada",
                observation.situacao.value if observation.situacao else None,
            ),
            ("simbolo_situacao_indicio", _observed_situation_source(observation)),
            (
                "simbolo_quantidade_observada",
                dict(observation.atributos).get("quantidade_ativos"),
            ),
            (
                "simbolo_classe_visual",
                ",".join(sorted({alt.classe for alt in observation.alternativas if alt.classe})),
            ),
            (
                "simbolo_geometria_original",
                json.dumps([[str(x), str(y)] for x, y in observation.geometria.pontos_originais]),
            ),
        ),
    )


def _symbol_support(
    geometry: GeometriaDocumento,
    layer: str,
    proposals: tuple[PropostaElemento, ...],
) -> tuple[PropostaElemento | None, tuple[tuple[float, PropostaElemento], ...]]:
    if layer != "base":
        return None, ()
    center = _geometry_center(geometry)
    candidates = sorted(
        (
            (_distance(center, _geometry_center(item.geometria)), item)
            for item in proposals
            if item.categoria is CategoriaElemento.POSTE
            and item.geometria.pagina_id == geometry.pagina_id
            and item.estado_revisao is not EstadoRevisao.REJEITADA
            and dict(item.atributos_sugeridos).get("simbolo_camada", "base") == layer
            and dict(item.atributos_sugeridos).get("camada", "base") == layer
        ),
        key=lambda item: (item[0], str(item[1].id)),
    )
    nearby = tuple(item for item in candidates if item[0] <= 0.025)
    if not nearby:
        return None, ()
    if len(nearby) > 1 and nearby[1][0] - nearby[0][0] <= 0.004:
        return None, nearby
    return nearby[0][1], nearby


def _observed_situation_source(observation: ObservacaoSimbolo) -> str | None:
    attributes = dict(observation.atributos)
    for key in ("situacao_evidencia", "situacao_origem", "cor", "situacao_projeto_forcada"):
        value = attributes.get(key)
        if value is not None:
            return f"{key}={value}"
    return None


def _json_scalar(value: object) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _geometry_center(geometry: GeometriaDocumento) -> tuple[float, float]:
    return (
        (
            min(float(point.x) for point in geometry.pontos)
            + max(float(point.x) for point in geometry.pontos)
        )
        / 2,
        (
            min(float(point.y) for point in geometry.pontos)
            + max(float(point.y) for point in geometry.pontos)
        )
        / 2,
    )


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.dist(first, second)
