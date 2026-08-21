# mypy: disable-error-code="no-untyped-call"
"""Geração servidor-side dos arquivos finais baixados pelo usuário."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pymupdf
from sqlalchemy import Engine

from zeny_project_handler.adapters.pdf.errors import (
    PdfOrigemAlteradaError,
    PdfProtegidoError,
)
from zeny_project_handler.adapters.persistence.unit_of_work import SqlAlchemyUnitOfWork
from zeny_project_handler.application.pdf_credentials import IdentidadeCredencialPdf
from zeny_project_handler.domain.documents import DocumentoProjeto
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler_contracts.common import DownloadMetadataDto, NormalizedBoxDto
from zeny_project_handler_contracts.compliance import (
    ComplianceCalloutDto,
    ComplianceExecutionResponse,
)
from zeny_project_handler_contracts.documentation import DocumentationResponse
from zeny_project_handler_contracts.enums import (
    ComplianceStatus,
    DocumentationFieldStatus,
    ElementCategory,
)
from zeny_project_handler_contracts.exports import (
    CalloutPositionOverrideDto,
    CreateDeliverableExportRequest,
    DeliverableExportKind,
)
from zeny_project_handler_contracts.review import ReviewSessionResponse
from zeny_project_handler_contracts.rules import ActiveRuleRegistryResponse
from zeny_project_handler_server.api_errors import ApiError, resource_not_found, validation_error
from zeny_project_handler_server.compliance_api import DocumentationComplianceApiService
from zeny_project_handler_server.project_api import ProjectApiService
from zeny_project_handler_server.review_api import ReviewApiService
from zeny_project_handler_server.transfer_storage import ManagedTransferStorage
from zeny_project_handler_server.xlsx_export import WorksheetData, write_xlsx

_CHUNK_SIZE = 1024 * 1024
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PDF_MIME = "application/pdf"


@dataclass(frozen=True, slots=True)
class _ProjectExportSnapshot:
    project: Projeto
    sources: dict[UUID, ReferenciaFontePdf]


class DeliverableExportService:
    """Compile PDF e tabelas a partir da mesma projeção canônica usada pela interface."""

    def __init__(
        self,
        *,
        engine: Engine,
        projects: ProjectApiService,
        review: ReviewApiService,
        compliance: DocumentationComplianceApiService,
        storage: ManagedTransferStorage,
    ) -> None:
        self._engine = engine
        self._projects = projects
        self._review = review
        self._compliance = compliance
        self._storage = storage

    def create(
        self,
        project_id: UUID,
        request: CreateDeliverableExportRequest,
    ) -> DownloadMetadataDto:
        self._projects.require_project_version(project_id, request.expected_project_version)
        snapshot = self._snapshot(project_id)
        service_note = snapshot.project.nome
        definitions: dict[
            DeliverableExportKind,
            tuple[str, str, Callable[[Path], None]],
        ] = {
            DeliverableExportKind.ANNOTATED_PDF: (
                f"{service_note}-pdf-anotado.pdf",
                _PDF_MIME,
                lambda path: self._write_annotated_pdf(
                    snapshot,
                    path,
                    request.callout_positions,
                ),
            ),
            DeliverableExportKind.RESULTS_XLSX: (
                f"{service_note}-resultados.xlsx",
                _XLSX_MIME,
                lambda path: self._write_results(project_id, path),
            ),
            DeliverableExportKind.DOCUMENTATION_XLSX: (
                f"{service_note}-documentacao.xlsx",
                _XLSX_MIME,
                lambda path: self._write_documentation(project_id, path),
            ),
            DeliverableExportKind.COMPLIANCE_XLSX: (
                f"{service_note}-conformidade.xlsx",
                _XLSX_MIME,
                lambda path: self._write_compliance(project_id, path),
            ),
        }
        file_name, mime_type, writer = definitions[request.kind]
        pending = self._storage.pending_download_path(uuid4(), Path(file_name).suffix)
        try:
            writer(pending)
            self._projects.require_project_version(
                project_id,
                request.expected_project_version,
            )
            return self._storage.publish_download(
                pending,
                file_name=file_name,
                mime_type=mime_type,
            )
        except BaseException:
            pending.unlink(missing_ok=True)
            raise

    def _snapshot(self, project_id: UUID) -> _ProjectExportSnapshot:
        with SqlAlchemyUnitOfWork(self._engine) as work:
            project = work.projetos.obter(project_id)
            if project is None:
                raise resource_not_found("Projeto não encontrado.")
            sources: dict[UUID, ReferenciaFontePdf] = {}
            for document in project.documentos:
                source = work.fontes_pdf.obter(document.id)
                if source is None:
                    raise resource_not_found("A origem gerenciada do PDF não foi encontrada.")
                sources[document.id] = source
        return _ProjectExportSnapshot(project, sources)

    def _write_annotated_pdf(
        self,
        snapshot: _ProjectExportSnapshot,
        destination: Path,
        overrides: tuple[CalloutPositionOverrideDto, ...],
    ) -> None:
        project = snapshot.project
        if not project.documentos:
            raise validation_error("O projeto não possui PDFs para exportação.")
        callouts = self._latest_callouts(project.id)
        positions = _callout_positions(overrides, callouts)
        passwords = self._projects.analysis_passwords(project.id)
        sources: dict[UUID, pymupdf.Document] = {}
        output = pymupdf.open()
        try:
            pages = {
                page.id: (document, page.numero)
                for document in project.documentos
                for page in document.paginas
            }
            for page_id in project.ordem_leitura_paginas:
                pair = pages.get(page_id)
                if pair is None:
                    raise PdfOrigemAlteradaError("A ordem do projeto referencia uma página ausente")
                document, source_page_number = pair
                source = sources.get(document.id)
                if source is None:
                    reference = snapshot.sources[document.id]
                    _verify_source(reference, document)
                    source = pymupdf.open(filename=str(reference.caminho_canonico))
                    if source.needs_pass and not source.authenticate(
                        passwords.get(document.id, "")
                    ):
                        source.close()
                        raise PdfProtegidoError(senha_fornecida=document.id in passwords)
                    sources[document.id] = source
                output.insert_pdf(
                    source,
                    from_page=source_page_number - 1,
                    to_page=source_page_number - 1,
                    links=True,
                    annots=True,
                )
            output.set_metadata(
                {
                    "title": f"Projeto {project.nome} com anotações",
                    "author": "Zeny Project Handler",
                    "subject": "PDF comissionado com anotações de conformidade",
                    "creator": "Zeny Project Handler",
                    "producer": "Zeny Project Handler / PyMuPDF",
                }
            )
            page_indexes = {
                page_id: index for index, page_id in enumerate(project.ordem_leitura_paginas)
            }
            for callout in callouts:
                page_index = page_indexes.get(callout.navigation.page_id.root)
                if page_index is not None:
                    _add_callout_annotation(
                        output[page_index],
                        callout,
                        positions.get(callout.callout_id.root, callout.box),
                    )
            output.save(str(destination), garbage=3, deflate=True)
        finally:
            passwords.clear()
            output.close()
            for source in sources.values():
                source.close()

    def _latest_callouts(self, project_id: UUID) -> tuple[ComplianceCalloutDto, ...]:
        try:
            result = self._compliance.get_latest(project_id)
        except ApiError as error:
            if error.status_code == 404:
                return ()
            raise
        return tuple(finding.callout for finding in result.findings if finding.callout is not None)

    def _write_results(self, project_id: UUID, destination: Path) -> None:
        session = self._review.get_session(project_id)
        write_xlsx(destination, _results_sheets(session))

    def _write_documentation(self, project_id: UUID, destination: Path) -> None:
        documentation = self._compliance.get_documentation(project_id)
        write_xlsx(destination, (_documentation_sheet(documentation),))

    def _write_compliance(self, project_id: UUID, destination: Path) -> None:
        result: ComplianceExecutionResponse | None
        try:
            result = self._compliance.get_latest(project_id)
        except ApiError as error:
            if error.status_code != 404:
                raise
            result = None
        registry = self._compliance.get_active_registry()
        write_xlsx(destination, _compliance_sheets(result, registry))


def _results_sheets(session: ReviewSessionResponse) -> tuple[WorksheetData, WorksheetData]:
    regions = {
        proposal_id.root: region
        for region in session.regions
        for proposal_id in region.proposal_ids
    }
    element_rows = tuple(
        (
            (region.label if (region := regions.get(item.proposal_id.root)) is not None else ""),
            region.location_label if region is not None else "",
            region.action_summary if region is not None else "",
            region.coordinate_label if region is not None else "",
            item.label,
            item.situation_label,
            _category_label(item.category),
            item.catalog_label,
            item.state_label,
            item.confidence or "",
            item.observed_code or "",
            "; ".join(item.relationship_labels),
            "Sim" if item.requires_review else "Não",
            _page_id(item.overlay.geometry.page_id.root, session.page_order),
            str(item.proposal_id.root),
        )
        for item in session.proposals
    )
    span_rows = tuple(
        (
            item.label,
            item.situation_label,
            item.start_label,
            item.end_label,
            item.cable_label,
            item.length_label,
            item.length_source_label,
            item.page_label,
            str(item.span_id),
        )
        for item in session.spans
    )
    return (
        WorksheetData(
            "Elementos",
            (
                "Ponto / região",
                "Localização",
                "Ação",
                "Coordenada",
                "Elemento",
                "Situação",
                "Categoria",
                "Catálogo",
                "Estado da revisão",
                "Confiança",
                "Código observado",
                "Vínculos",
                "Exige revisão",
                "Folha",
                "ID da identificação",
            ),
            element_rows,
        ),
        WorksheetData(
            "Vãos",
            (
                "Vão",
                "Situação",
                "Poste de origem",
                "Poste de destino",
                "Cabo",
                "Comprimento",
                "Fonte",
                "Folha",
                "ID do vão",
            ),
            span_rows,
        ),
    )


def _documentation_sheet(documentation: DocumentationResponse) -> WorksheetData:
    rows = tuple(
        (
            section.document_name or "Documento",
            section.label,
            field.label,
            field.value or "",
            _documentation_status_label(field.status),
            field.confidence or "",
            _first_evidence_page(field.evidence, documentation.page_order),
        )
        for section in documentation.sections
        for field in section.fields
    )
    return WorksheetData(
        "Documentação",
        ("Documento", "Grupo", "Campo", "Valor", "Estado", "Confiança", "Folha"),
        rows,
    )


def _compliance_sheets(
    result: ComplianceExecutionResponse | None,
    registry: ActiveRuleRegistryResponse,
) -> tuple[WorksheetData, WorksheetData]:
    finding_rows = (
        tuple(
            (
                _compliance_status_label(item.status),
                item.severity or "",
                f"Regra {item.rule_number}",
                item.title or item.summary,
                item.summary,
                item.observed_value or "",
                item.expected_value or "",
                item.target_label or item.target_scope.value,
                item.source_reference,
                item.rule_registry_revision or result.execution.rule_registry_revision,
                item.normative_revision or "",
                item.location_label or "",
                str(item.finding_id.root),
            )
            for item in result.findings
        )
        if result is not None
        else ()
    )
    details = {item.summary.rule_id: item for item in registry.details}
    rule_rows = tuple(
        (
            f"Regra {rule.rule_number}",
            "Ativa" if rule.enabled else "Inativa",
            rule.rule_id,
            rule.title,
            details[rule.rule_id].target_scope,
            details[rule.rule_id].provider_label,
            details[rule.rule_id].source_detail or rule.source_reference,
            details[rule.rule_id].description or "",
            details[rule.rule_id].applicability_text or "Sempre",
            details[rule.rule_id].exceptions_text or "Sem exceção",
            details[rule.rule_id].requirements_text or "Sem requisito",
            registry.revision,
        )
        for rule in sorted(registry.rules, key=lambda value: value.rule_number)
    )
    return (
        WorksheetData(
            "Conformidade",
            (
                "Resultado",
                "Severidade",
                "Regra",
                "Título",
                "Resumo",
                "Observado",
                "Esperado",
                "Alvo",
                "Fonte",
                "Revisão das regras",
                "Revisão normativa",
                "Localização",
                "ID do achado",
            ),
            finding_rows,
        ),
        WorksheetData(
            "Regras",
            (
                "Número",
                "Estado",
                "ID",
                "Título",
                "Escopo",
                "Provedor",
                "Fonte",
                "Descrição",
                "Aplicabilidade",
                "Exceções",
                "Requisitos",
                "Revisão ativa",
            ),
            rule_rows,
        ),
    )


def _callout_positions(
    overrides: tuple[CalloutPositionOverrideDto, ...],
    callouts: tuple[ComplianceCalloutDto, ...],
) -> dict[UUID, NormalizedBoxDto]:
    result = {item.callout_id.root: item.box for item in overrides}
    if len(result) != len(overrides):
        raise validation_error("Uma posição de anotação foi enviada mais de uma vez.")
    available = {item.callout_id.root for item in callouts}
    if not result.keys() <= available:
        raise validation_error("Uma posição de anotação não pertence à conformidade atual.")
    return result


def _verify_source(reference: ReferenciaFontePdf, document: DocumentoProjeto) -> None:
    identity = IdentidadeCredencialPdf.da_fonte(reference)
    if not identity.ainda_descreve(reference.caminho_canonico):
        raise PdfOrigemAlteradaError("A origem PDF mudou desde a importação")
    digest = sha256()
    try:
        with reference.caminho_canonico.open("rb") as stream:
            while chunk := stream.read(_CHUNK_SIZE):
                digest.update(chunk)
    except OSError as error:
        raise PdfOrigemAlteradaError("A origem PDF não está disponível") from error
    if digest.hexdigest() != document.sha256:
        raise PdfOrigemAlteradaError("O conteúdo da origem PDF mudou")


def _add_callout_annotation(
    page: pymupdf.Page,
    callout: ComplianceCalloutDto,
    box: NormalizedBoxDto,
) -> None:
    page_rect = page.rect
    rotated_box = pymupdf.Rect(
        _number(box.x) * page_rect.width,
        _number(box.y) * page_rect.height,
        (_number(box.x) + _number(box.width)) * page_rect.width,
        (_number(box.y) + _number(box.height)) * page_rect.height,
    )
    annotation_rect = _derotated_rect(page, rotated_box)
    stroke, fill = _callout_colors(callout.status)
    annotation = page.add_freetext_annot(
        annotation_rect,
        callout.text,
        fontsize=max(4.0, _number(callout.font_size_points)),
        fontname="Helv",
        text_color=stroke,
        fill_color=fill,
        border_width=1.2,
        opacity=0.96,
        align=0,
    )
    annotation.set_info(
        title="Zeny Project Handler",
        subject=f"Conformidade · {callout.status.value}",
        content=callout.text,
    )
    annotation.update()
    for anchor in callout.anchors or (callout.anchor,):
        rotated_anchor = pymupdf.Point(
            _number(anchor.x) * page_rect.width,
            _number(anchor.y) * page_rect.height,
        )
        connection = _box_connection(rotated_box, rotated_anchor)
        page.draw_line(
            rotated_anchor * page.derotation_matrix,
            connection * page.derotation_matrix,
            color=stroke,
            width=1.2,
            overlay=True,
        )


def _derotated_rect(page: pymupdf.Page, rectangle: pymupdf.Rect) -> pymupdf.Rect:
    points = tuple(
        point * page.derotation_matrix
        for point in (rectangle.tl, rectangle.tr, rectangle.br, rectangle.bl)
    )
    return pymupdf.Rect(
        min(point.x for point in points),
        min(point.y for point in points),
        max(point.x for point in points),
        max(point.y for point in points),
    )


def _box_connection(box: pymupdf.Rect, anchor: pymupdf.Point) -> pymupdf.Point:
    candidates = (
        pymupdf.Point(box.x0, min(max(anchor.y, box.y0), box.y1)),
        pymupdf.Point(box.x1, min(max(anchor.y, box.y0), box.y1)),
        pymupdf.Point(min(max(anchor.x, box.x0), box.x1), box.y0),
        pymupdf.Point(min(max(anchor.x, box.x0), box.x1), box.y1),
    )
    return min(candidates, key=lambda point: (point.x - anchor.x) ** 2 + (point.y - anchor.y) ** 2)


def _callout_colors(status: ComplianceStatus) -> tuple[tuple[float, ...], tuple[float, ...]]:
    return {
        ComplianceStatus.DIVERGENCE: ((0.78, 0.16, 0.16), (1.0, 0.95, 0.88)),
        ComplianceStatus.COMPLIANT: ((0.12, 0.48, 0.2), (0.91, 0.97, 0.91)),
        ComplianceStatus.NOT_EVALUABLE: ((0.55, 0.43, 0.0), (1.0, 0.98, 0.88)),
    }[status]


def _number(value: object) -> float:
    return float(str(value))


def _page_id(page_id: UUID, order: tuple[object, ...]) -> str:
    for index, candidate in enumerate(order, start=1):
        if getattr(candidate, "root", candidate) == page_id:
            return str(index)
    return ""


def _first_evidence_page(evidence: tuple[object, ...], order: tuple[object, ...]) -> str:
    if not evidence:
        return ""
    page_id = getattr(evidence[0], "page_id", None)
    root = getattr(page_id, "root", page_id)
    return _page_id(root, order) if isinstance(root, UUID) else ""


def _category_label(value: ElementCategory) -> str:
    return {
        ElementCategory.POLE: "Poste",
        ElementCategory.MV_STRUCTURE: "Estrutura MT",
        ElementCategory.LV_STRUCTURE: "Estrutura BT",
        ElementCategory.CABLE: "Cabo",
        ElementCategory.EQUIPMENT: "Equipamento",
    }[value]


def _documentation_status_label(value: DocumentationFieldStatus) -> str:
    return {
        DocumentationFieldStatus.PRESENT: "Identificado",
        DocumentationFieldStatus.ABSENT: "Não identificado",
        DocumentationFieldStatus.UNCERTAIN: "Revisão visual",
    }[value]


def _compliance_status_label(value: ComplianceStatus) -> str:
    return {
        ComplianceStatus.COMPLIANT: "Conforme",
        ComplianceStatus.DIVERGENCE: "Divergência",
        ComplianceStatus.NOT_EVALUABLE: "Não avaliável",
    }[value]
