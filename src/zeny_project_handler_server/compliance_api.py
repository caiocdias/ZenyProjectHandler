"""Projeções remotas de documentação, conformidade, regras e callouts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Event, RLock
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Engine

from zeny_project_handler.adapters.compliance import registro_conformidade_e_avisos_de_dict
from zeny_project_handler.adapters.persistence import SqlAlchemyUnitOfWork
from zeny_project_handler.application.compliance_analysis import ExecutarAnaliseConformidade
from zeny_project_handler.application.compliance_callouts import (
    CalloutConformidade,
    LayoutCalloutsImpossivelError,
    projetar_callouts_conformidade,
)
from zeny_project_handler.application.compliance_presentation import (
    formatar_alvo,
    formatar_escopo,
    formatar_lista_condicoes,
    formatar_texto_achado,
    formatar_valores_achado,
)
from zeny_project_handler.application.compliance_registry import (
    ResumoImportacaoRegras,
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.document_compliance import prover_fatos_documentais
from zeny_project_handler.application.human_review import ServicoRevisaoHumana, SessaoRevisao
from zeny_project_handler.application.project_compliance import prover_fatos_regionais
from zeny_project_handler.application.span_compliance import prover_fatos_vaos
from zeny_project_handler.application.topology_compliance import prover_fatos_topologicos
from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.compliance import (
    AchadoConformidade,
    AlvoConformidade,
    ExecucaoConformidade,
    FonteNormativa,
    ItemInspecaoDocumental,
    RegraConformidade,
    ResultadoConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.documents import DocumentoProjeto
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import GeometriaDocumento
from zeny_project_handler_contracts.base import (
    CalloutId,
    ComplianceExecutionId,
    DocumentId,
    EvidenceId,
    FindingId,
    PageId,
    ProjectId,
    RuleImportPreflightId,
)
from zeny_project_handler_contracts.common import (
    EvidenceNavigationDto,
    NormalizedBoxDto,
    NormalizedPointDto,
    PageMetadataDto,
    PreflightIssueDto,
)
from zeny_project_handler_contracts.compliance import (
    ComplianceCalloutDto,
    ComplianceExecutionResponse,
    ComplianceExecutionSummaryDto,
    ComplianceFindingDto,
    ComplianceHistoryResponse,
)
from zeny_project_handler_contracts.documentation import (
    DocumentationResponse,
    DocumentationSectionDto,
    DocumentFieldDto,
)
from zeny_project_handler_contracts.enums import (
    ComplianceStatus,
    ComplianceTargetScope,
    DocumentationFieldStatus,
    IssueSeverity,
    PreflightDisposition,
)
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.review import ReviewProjectSummaryListResponse
from zeny_project_handler_contracts.rules import (
    ActiveRuleRegistryResponse,
    ConfirmRuleImportRequest,
    RuleDetailDto,
    RuleImportPreflightResponse,
    RuleImportResponse,
    RuleSummaryDto,
)
from zeny_project_handler_server.api_errors import ApiError, resource_not_found, validation_error
from zeny_project_handler_server.review_api import ReviewApiService

_PREFLIGHT_TTL = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class _RulePreflight:
    response: RuleImportPreflightResponse
    summary: ResumoImportacaoRegras
    expected_active_revision: str


class DocumentationComplianceApiService:
    """Mantenha toda inspeção e decisão normativa no processo servidor."""

    def __init__(
        self,
        *,
        engine: Engine,
        data_directory: Path,
        review_api: ReviewApiService,
        upload_max_bytes: int,
        review_service: ServicoRevisaoHumana | None = None,
        analysis_service: ExecutarAnaliseConformidade | None = None,
        registry_service: ServicoRegistroRegrasConformidade | None = None,
    ) -> None:
        self._engine = engine
        self._review_api = review_api
        self._upload_max_bytes = upload_max_bytes
        self._review = review_service or ServicoRevisaoHumana(self._unit_of_work)
        self._analysis = analysis_service or ExecutarAnaliseConformidade(
            self._unit_of_work,
            self._review.carregar_sessao_semantica,
            provedores_fatos=(
                prover_fatos_documentais,
                prover_fatos_regionais,
                prover_fatos_vaos,
                prover_fatos_topologicos,
            ),
        )
        self._registry = registry_service or ServicoRegistroRegrasConformidade(
            self._unit_of_work,
            diretorio_dados=data_directory,
        )
        self._preflights: dict[UUID, _RulePreflight] = {}
        self._preflight_keys: dict[str, tuple[str, UUID]] = {}
        self._lock = RLock()

    def _unit_of_work(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._engine)

    @property
    def analysis_service(self) -> ExecutarAnaliseConformidade:
        return self._analysis

    def semantic_signature(self, project_id: UUID) -> str:
        return self._review_api.get_semantic_session(project_id).semantic_signature

    def list_projects(
        self,
        *,
        limit: int,
        offset: int,
    ) -> ReviewProjectSummaryListResponse:
        return self._review_api.list_semantic_projects(limit=limit, offset=offset)

    def execute_compliance(self, project_id: UUID, cancellation: Event) -> UUID:
        result = self._analysis.executar(
            project_id,
            cancelado=cancellation.is_set,
        )
        return result.id

    def get_documentation(self, project_id: UUID) -> DocumentationResponse:
        review = self._review_api.get_semantic_session(project_id)
        session = self._review.carregar_sessao_semantica(project_id)
        execution = self._analysis.obter_ultima(project_id)
        items = execution.itens_documentais if execution is not None else ()
        return _documentation_response(session, review.semantic_signature, items)

    def get_latest(self, project_id: UUID) -> ComplianceExecutionResponse:
        execution = self._analysis.obter_ultima(project_id)
        if execution is None:
            raise resource_not_found("O projeto ainda não possui execução de conformidade.")
        return self._execution_response(execution)

    def list_history(
        self,
        project_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> ComplianceHistoryResponse:
        history = self._analysis.listar_historico(project_id)
        return ComplianceHistoryResponse(
            items=tuple(self._execution_summary(item) for item in history[offset : offset + limit]),
            page=PageMetadataDto(limit=limit, offset=offset, total=len(history)),
        )

    def get_active_registry(self) -> ActiveRuleRegistryResponse:
        revision = self._registry.obter_revisao_ativa()
        numbers = {item.regra_id: item.numero for item in self._registry.listar_numeros()}
        serialized_rules = cast(list[object], revision.registro.para_dict()["rules"])
        definitions = {
            str(item["id"]): item
            for item in serialized_rules
            if isinstance(item, dict) and "id" in item
        }
        summaries = tuple(
            _rule_summary(rule, numbers[rule.id])
            for rule in sorted(revision.registro.regras, key=lambda item: numbers[item.id])
        )
        summary_by_id = {item.rule_id: item for item in summaries}
        details = tuple(
            RuleDetailDto(
                summary=summary_by_id[rule.id],
                target_scope=formatar_escopo(rule.escopo),
                fact_keys=tuple(
                    dict.fromkeys(
                        item.chave_fato
                        for item in (*rule.aplicabilidade, *rule.excecoes, *rule.requisitos)
                    )
                ),
                definition=definitions[rule.id],
                description=rule.descricao,
                source_detail=_source_detail(rule.fonte),
                applicability_text=formatar_lista_condicoes(
                    rule.aplicabilidade,
                    vazio="sempre",
                ),
                exceptions_text=formatar_lista_condicoes(
                    rule.excecoes,
                    vazio="sem exceção",
                ),
                requirements_text=formatar_lista_condicoes(
                    rule.requisitos,
                    vazio="sem requisito",
                ),
            )
            for rule in sorted(revision.registro.regras, key=lambda item: numbers[item.id])
        )
        return ActiveRuleRegistryResponse(
            revision=revision.registro.versao,
            sha256=revision.assinatura,
            rule_count=len(summaries),
            active_rule_count=sum(item.enabled for item in summaries),
            activated_at=revision.criada_em,
            rules=summaries,
            details=details,
        )

    def preflight_rule_import(
        self,
        content: bytes,
        *,
        idempotency_key: str,
    ) -> RuleImportPreflightResponse:
        if not content:
            raise validation_error("O arquivo de regras está vazio.")
        if len(content) > self._upload_max_bytes:
            raise ApiError(
                413,
                ErrorCode.UPLOAD_TOO_LARGE,
                "O arquivo de regras excede o limite configurado.",
            )
        fingerprint = sha256(content).hexdigest()
        with self._lock:
            self._prune_preflights()
            previous = self._preflight_keys.get(idempotency_key)
            if previous is not None:
                previous_fingerprint, preflight_id = previous
                if previous_fingerprint != fingerprint:
                    raise ApiError(
                        409,
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        "A chave de idempotência já foi usada para outro arquivo.",
                    )
                stored = self._preflights.get(preflight_id)
                if stored is not None:
                    return stored.response
        try:
            decoded = json.loads(content.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise DomainValidationError("root deve ser um objeto JSON")
            registry, warnings = registro_conformidade_e_avisos_de_dict(decoded)
            summary = self._registry.preparar_importacao(registry, avisos=warnings)
        except UnicodeDecodeError as error:
            raise validation_error("O arquivo de regras deve usar UTF-8.") from error
        except json.JSONDecodeError as error:
            raise validation_error(
                f"JSON de regras inválido na linha {error.lineno}, coluna {error.colno}"
            ) from error
        except DomainValidationError as error:
            raise validation_error(str(error)) from error
        active = self._registry.obter_revisao_ativa()
        now = datetime.now(UTC)
        response = RuleImportPreflightResponse(
            preflight_id=RuleImportPreflightId(uuid4()),
            fingerprint=fingerprint,
            disposition=PreflightDisposition.CONFIRMATION_REQUIRED,
            current_revision=active.registro.versao,
            proposed_revision=summary.registro.versao,
            added_rule_ids=summary.novos_ids,
            changed_rule_ids=summary.substituidos_ids,
            preserved_rule_ids=summary.omitidos_preservados_ids,
            issues=tuple(
                PreflightIssueDto(
                    code="RULE_IMPORT_WARNING",
                    severity=IssueSeverity.WARNING,
                    summary=item,
                )
                for item in summary.avisos
            ),
            expires_at=now + _PREFLIGHT_TTL,
        )
        stored = _RulePreflight(response, summary, active.registro.versao)
        with self._lock:
            self._preflights[response.preflight_id.root] = stored
            self._preflight_keys[idempotency_key] = (
                fingerprint,
                response.preflight_id.root,
            )
        return response

    def confirm_rule_import(self, request: ConfirmRuleImportRequest) -> RuleImportResponse:
        with self._lock:
            self._prune_preflights()
            stored = self._preflights.get(request.preflight_id.root)
        if stored is None:
            raise resource_not_found("O preflight de regras expirou ou não existe.")
        if request.fingerprint != stored.response.fingerprint:
            raise ApiError(
                409,
                ErrorCode.INTEGRITY_ERROR,
                "O fingerprint não corresponde ao arquivo validado.",
            )
        active = self._registry.obter_revisao_ativa()
        if (
            request.expected_active_revision != stored.expected_active_revision
            or active.registro.versao != stored.expected_active_revision
        ):
            raise ApiError(
                409,
                ErrorCode.STALE_STATE,
                "A revisão ativa mudou; execute um novo preflight.",
            )
        revision = self._registry.importar(stored.summary)
        with self._lock:
            self._preflights.pop(request.preflight_id.root, None)
        return RuleImportResponse(
            revision=revision.registro.versao,
            sha256=revision.assinatura,
            imported_at=revision.criada_em,
            active_rule_count=sum(item.ativa for item in revision.registro.regras),
        )

    def active_registry_json(self) -> bytes:
        registry = self._registry.obter_revisao_ativa().registro
        return (json.dumps(registry.para_dict(), ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )

    def _execution_response(
        self,
        execution: ExecucaoConformidade,
    ) -> ComplianceExecutionResponse:
        session = self._review.carregar_sessao_semantica(execution.projeto_id)
        targets = {item.id: item for item in execution.alvos}
        numbers = {item.regra_id: item.numero for item in self._registry.listar_numeros()}
        presentation = {
            finding.id: formatar_texto_achado(finding, targets[finding.alvo_id])
            for finding in execution.achados
        }
        pages = tuple(page for document in session.projeto.documentos for page in document.paginas)
        try:
            callouts = {
                item.id: item
                for item in projetar_callouts_conformidade(
                    execution,
                    evidencias=session.evidencias,
                    paginas=pages,
                    textos_apresentacao=presentation,
                )
            }
        except LayoutCalloutsImpossivelError:
            callouts = {}
        return ComplianceExecutionResponse(
            execution=self._execution_summary(execution),
            findings=tuple(
                _finding_dto(
                    item,
                    execution=execution,
                    target=targets[item.alvo_id],
                    number=numbers[item.regra_id],
                    callout=callouts.get(item.id),
                    session=session,
                    summary=presentation[item.id],
                )
                for item in execution.achados
            ),
        )

    def _execution_summary(
        self,
        execution: ExecucaoConformidade,
    ) -> ComplianceExecutionSummaryDto:
        return ComplianceExecutionSummaryDto(
            execution_id=ComplianceExecutionId(execution.id),
            project_id=ProjectId(execution.projeto_id),
            rule_registry_revision=execution.versao_regras,
            semantic_signature=execution.assinatura_sessao,
            method_version=execution.versao_metodo,
            is_stale=self._analysis.resultado_desatualizado(execution),
            compliant_count=sum(
                item.resultado is ResultadoConformidade.CONFORME for item in execution.achados
            ),
            divergence_count=sum(
                item.resultado is ResultadoConformidade.DIVERGENCIA for item in execution.achados
            ),
            not_evaluable_count=sum(
                item.resultado is ResultadoConformidade.NAO_AVALIAVEL for item in execution.achados
            ),
            completed_at=execution.executada_em,
        )

    def _prune_preflights(self) -> None:
        now = datetime.now(UTC)
        expired = {
            preflight_id
            for preflight_id, item in self._preflights.items()
            if item.response.expires_at <= now
        }
        for preflight_id in expired:
            self._preflights.pop(preflight_id, None)
        if expired:
            self._preflight_keys = {
                key: value for key, value in self._preflight_keys.items() if value[1] not in expired
            }


def _documentation_response(
    session: SessaoRevisao,
    semantic_signature: str,
    items: tuple[ItemInspecaoDocumental, ...],
) -> DocumentationResponse:
    documents = {item.id: item for item in session.projeto.documentos}
    evidence = {item.id: item for item in session.evidencias}
    document_by_page = {
        page.id: document for document in session.projeto.documentos for page in document.paginas
    }
    grouped: dict[tuple[UUID, str], list[ItemInspecaoDocumental]] = {}
    for item in items:
        grouped.setdefault((item.documento_id, item.grupo), []).append(item)
    sections = tuple(
        DocumentationSectionDto(
            section_key=f"{document_id}:{group}",
            label=group,
            document_id=DocumentId(document_id),
            document_name=documents[document_id].nome_arquivo,
            fields=tuple(
                _document_field(item, evidence=evidence, document_by_page=document_by_page)
                for item in values
            ),
        )
        for (document_id, group), values in grouped.items()
    )
    return DocumentationResponse(
        project_id=ProjectId(session.projeto.id),
        semantic_signature=semantic_signature,
        page_order=tuple(PageId(item) for item in session.projeto.ordem_leitura_paginas),
        sections=sections,
    )


def _document_field(
    item: ItemInspecaoDocumental,
    *,
    evidence: dict[UUID, EvidenciaDocumento],
    document_by_page: dict[UUID, DocumentoProjeto],
) -> DocumentFieldDto:
    navigation = _evidence_navigation(
        item.evidencia_ids,
        evidence=evidence,
        document_by_page=document_by_page,
    )
    if not navigation and item.pagina_id is not None:
        navigation = (
            EvidenceNavigationDto(
                document_id=DocumentId(item.documento_id),
                page_id=PageId(item.pagina_id),
                geometry=_box(item.geometria) if item.geometria is not None else None,
                label=item.campo,
            ),
        )
    return DocumentFieldDto(
        field_key=f"{item.documento_id}:{item.grupo}:{item.campo}",
        label=item.campo,
        value=item.valor,
        status=_documentation_status(item.estado),
        confidence=str(item.confianca) if item.confianca is not None else None,
        evidence=navigation,
    )


def _finding_dto(
    finding: AchadoConformidade,
    *,
    execution: ExecucaoConformidade,
    target: AlvoConformidade,
    number: int,
    callout: CalloutConformidade | None,
    session: SessaoRevisao,
    summary: str,
) -> ComplianceFindingDto:
    evidence = {item.id: item for item in session.evidencias}
    document_by_page = {
        page.id: document for document in session.projeto.documentos for page in document.paginas
    }
    navigations = _evidence_navigation(
        finding.evidencia_ids,
        evidence=evidence,
        document_by_page=document_by_page,
    )
    target_navigation = _target_navigation(target, document_by_page)
    if target_navigation is not None and target_navigation not in navigations:
        navigations = (*navigations, target_navigation)
    observed, expected = formatar_valores_achado(
        finding.avaliacoes_condicoes,
        finding.resultado,
    )
    callout_dto = (
        _callout_dto(callout, finding.id, document_by_page) if callout is not None else None
    )
    return ComplianceFindingDto(
        finding_id=FindingId(finding.id),
        rule_id=finding.regra_id,
        rule_number=number,
        status=_compliance_status(finding.resultado),
        target_scope=_target_scope(target.tipo),
        target_id=str(target.id),
        summary=summary,
        title=finding.titulo,
        severity=finding.severidade.value.title(),
        target_label=formatar_alvo(target),
        observed_value=observed,
        expected_value=expected,
        source_reference=f"{finding.fonte.documento} · {finding.fonte.item}",
        rule_registry_revision=execution.versao_regras,
        normative_revision=finding.fonte.revisao,
        location_label=(
            "Localizado no PDF" if callout_dto is not None else "Sem localização no PDF"
        ),
        navigation=callout_dto.navigation if callout_dto is not None else target_navigation,
        evidence=navigations,
        callout=callout_dto,
    )


def _callout_dto(
    callout: CalloutConformidade,
    finding_id: UUID,
    document_by_page: dict[UUID, DocumentoProjeto],
) -> ComplianceCalloutDto:
    page_id = callout.pagina_id
    document = document_by_page[page_id]
    anchors = tuple(
        NormalizedPointDto(x=str(item.ponto.x), y=str(item.ponto.y)) for item in callout.ancoras
    )
    box = callout.caixa_sugerida
    box_dto = NormalizedBoxDto(
        x=str(box.esquerda),
        y=str(box.topo),
        width=str(box.largura),
        height=str(box.altura),
    )
    navigation = EvidenceNavigationDto(
        document_id=DocumentId(document.id),
        page_id=PageId(page_id),
        geometry=box_dto,
        label=callout.texto,
    )
    return ComplianceCalloutDto(
        callout_id=CalloutId(finding_id),
        finding_id=FindingId(finding_id),
        text=callout.texto,
        anchor=anchors[0],
        anchors=anchors,
        box=box_dto,
        font_size_points=str(callout.tamanho_fonte_pontos),
        status=_compliance_status(callout.resultado),
        navigation=navigation,
    )


def _evidence_navigation(
    evidence_ids: tuple[UUID, ...],
    *,
    evidence: dict[UUID, EvidenciaDocumento],
    document_by_page: dict[UUID, DocumentoProjeto],
) -> tuple[EvidenceNavigationDto, ...]:
    result: list[EvidenceNavigationDto] = []
    for evidence_id in evidence_ids:
        item = evidence.get(evidence_id)
        document = document_by_page.get(item.pagina_id) if item is not None else None
        if item is None or document is None:
            continue
        result.append(
            EvidenceNavigationDto(
                evidence_id=EvidenceId(item.id),
                document_id=DocumentId(document.id),
                page_id=PageId(item.pagina_id),
                geometry=_box(item.geometria),
                label=item.conteudo_bruto,
            )
        )
    return tuple(result)


def _target_navigation(
    target: AlvoConformidade,
    document_by_page: dict[UUID, DocumentoProjeto],
) -> EvidenceNavigationDto | None:
    if target.pagina_id is None:
        return None
    document = document_by_page.get(target.pagina_id)
    if document is None:
        return None
    return EvidenceNavigationDto(
        document_id=DocumentId(document.id),
        page_id=PageId(target.pagina_id),
        geometry=_box(target.geometria) if target.geometria is not None else None,
        label=target.rotulo,
    )


def _box(geometry: GeometriaDocumento) -> NormalizedBoxDto:
    xs = tuple(item.x for item in geometry.pontos)
    ys = tuple(item.y for item in geometry.pontos)
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    return NormalizedBoxDto(
        x=str(left),
        y=str(top),
        width=str(right - left),
        height=str(bottom - top),
    )


def _documentation_status(value: str) -> DocumentationFieldStatus:
    if value in {"IDENTIFICADO", "CONFIRMADO", "ASSINATURA_PDF_PRESENTE"}:
        return DocumentationFieldStatus.PRESENT
    if value in {"NAO_IDENTIFICADO", "NAO_AVALIAVEL"}:
        return DocumentationFieldStatus.ABSENT
    return DocumentationFieldStatus.UNCERTAIN


def _compliance_status(value: ResultadoConformidade) -> ComplianceStatus:
    return {
        ResultadoConformidade.CONFORME: ComplianceStatus.COMPLIANT,
        ResultadoConformidade.DIVERGENCIA: ComplianceStatus.DIVERGENCE,
        ResultadoConformidade.NAO_AVALIAVEL: ComplianceStatus.NOT_EVALUABLE,
    }[value]


def _target_scope(value: TipoEscopoConformidade) -> ComplianceTargetScope:
    return {
        TipoEscopoConformidade.PROJETO: ComplianceTargetScope.PROJECT,
        TipoEscopoConformidade.DOCUMENTO: ComplianceTargetScope.DOCUMENT,
        TipoEscopoConformidade.PAGINA: ComplianceTargetScope.PAGE,
        TipoEscopoConformidade.REGIAO: ComplianceTargetScope.REGION,
        TipoEscopoConformidade.ELEMENTO: ComplianceTargetScope.ELEMENT,
    }[value]


def _rule_summary(rule: RegraConformidade, number: int) -> RuleSummaryDto:
    source = rule.fonte
    return RuleSummaryDto(
        rule_id=rule.id,
        rule_number=number,
        title=rule.titulo,
        enabled=rule.ativa,
        source_reference=f"{source.documento} · {source.item}",
    )


def _source_detail(source: FonteNormativa) -> str:
    result = f"{source.documento} · {source.revisao} · {source.item}"
    page = source.pagina
    return f"{result} · página {page}" if page is not None else result
