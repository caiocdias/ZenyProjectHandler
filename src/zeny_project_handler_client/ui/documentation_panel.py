"""Painel cliente de cabeçalho, controles documentais, vãos e conformidade."""

from __future__ import annotations

import os
from collections.abc import Callable
from functools import partial
from pathlib import Path
from uuid import UUID, uuid4

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from zeny_project_handler_contracts.common import EvidenceNavigationDto
from zeny_project_handler_contracts.compliance import (
    ComplianceCalloutDto,
    ComplianceExecutionResponse,
)
from zeny_project_handler_contracts.documentation import DocumentationResponse
from zeny_project_handler_contracts.enums import (
    ComplianceStatus,
    DocumentationFieldStatus,
    JobStatus,
)
from zeny_project_handler_contracts.review import ReviewSessionResponse
from zeny_project_handler_contracts.rules import (
    ActiveRuleRegistryResponse,
    ConfirmRuleImportRequest,
    RuleDetailDto,
    RuleImportPreflightResponse,
)

from .documentation_gateway import DocumentationGateway, DocumentationGatewayError
from .pdf_viewer import PdfViewerWidget
from .table_word_wrap import TableWordWrapController
from .visibility import visibility_icon


class DocumentationPanelWidget(QWidget):
    status_changed = Signal(str)

    def __init__(
        self,
        *,
        gateway: DocumentationGateway,
        viewer: PdfViewerWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("documentationCompliancePanel")
        self._gateway = gateway
        self._viewer = viewer
        self._documentation: DocumentationResponse | None = None
        self._result: ComplianceExecutionResponse | None = None
        self._registry: ActiveRuleRegistryResponse | None = None
        self._callouts: tuple[ComplianceCalloutDto, ...] = ()
        self._hidden_finding_ids: set[UUID] = set()
        self._finding_visibility_buttons: dict[UUID, QToolButton] = {}
        self._visibility_context: tuple[UUID, UUID | None] | None = None
        self._syncing_finding_selection = False
        self._compliance_job_id: UUID | None = None
        self._compliance_poll = QTimer(self)
        self._compliance_poll.timeout.connect(self._poll_compliance_job)
        self._build_ui()
        self._viewer.compliance_callout_selected.connect(self._select_finding_id)
        self.atualizar_regras()
        self.atualizar_projetos()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        project_row = QHBoxLayout()
        self._project = QComboBox()
        self._project.setObjectName("documentationProjectCombo")
        project_row.addWidget(self._project, 1)
        refresh = QPushButton("Atualizar")
        refresh.setObjectName("documentationRefreshButton")
        refresh.clicked.connect(self.atualizar_projetos)
        project_row.addWidget(refresh)
        layout.addLayout(project_row)

        self._summary = QLabel("Selecione um projeto analisado")
        self._summary.setObjectName("documentationSummaryLabel")
        self._summary.setProperty("role", "summary")
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

        tabs = QTabWidget()
        tabs.setObjectName("documentationTabs")
        self._tabs = tabs
        self._documents = _tree(
            "documentationTree",
            ("Grupo / documento", "Campo", "Valor", "Estado", "Confiança"),
            (170, 210, 260, 160, 90),
        )
        self._documents.itemSelectionChanged.connect(self._navigate_document_item)
        self._documents_word_wrap = TableWordWrapController(
            self._documents,
            button_name="documentationWordWrapButton",
        )
        documents_view = QWidget()
        documents_layout = QVBoxLayout(documents_view)
        documents_layout.setContentsMargins(0, 0, 0, 0)
        documents_actions = QHBoxLayout()
        documents_actions.addStretch(1)
        documents_actions.addWidget(self._documents_word_wrap.button)
        documents_layout.addLayout(documents_actions)
        documents_layout.addWidget(self._documents, 1)
        tabs.addTab(documents_view, "Documentação")

        compliance_view = QWidget()
        compliance_view.setObjectName("complianceExecutionView")
        self._compliance_view = compliance_view
        compliance_layout = QVBoxLayout(compliance_view)
        compliance_actions = QHBoxLayout()
        self._execution_status = QLabel("Nenhuma execução de conformidade persistida")
        self._execution_status.setObjectName("complianceExecutionStatusLabel")
        self._execution_status.setWordWrap(True)
        compliance_actions.addWidget(self._execution_status, 1)
        self._analyze_compliance = QPushButton("Analisar conformidade")
        self._analyze_compliance.setObjectName("complianceAnalyzeButton")
        self._analyze_compliance.setProperty("role", "primary")
        self._analyze_compliance.clicked.connect(self._analyze_current_compliance)
        compliance_actions.addWidget(self._analyze_compliance)
        compliance_layout.addLayout(compliance_actions)
        visibility_actions = QHBoxLayout()
        self._show_all_findings = QPushButton("Exibir todos")
        self._show_all_findings.setObjectName("complianceShowAllCalloutsButton")
        self._show_all_findings.setToolTip("Exibir todos os problemas localizáveis no PDF")
        self._show_all_findings.clicked.connect(
            lambda: self._set_all_findings_visible(visible=True)
        )
        visibility_actions.addWidget(self._show_all_findings)
        self._hide_all_findings = QPushButton("Ocultar todos")
        self._hide_all_findings.setObjectName("complianceHideAllCalloutsButton")
        self._hide_all_findings.setToolTip("Ocultar todos os problemas localizáveis no PDF")
        self._hide_all_findings.clicked.connect(
            lambda: self._set_all_findings_visible(visible=False)
        )
        visibility_actions.addWidget(self._hide_all_findings)
        visibility_actions.addStretch(1)
        compliance_layout.addLayout(visibility_actions)
        self._findings = _tree(
            "complianceFindingsTree",
            (
                "Resultado",
                "Severidade",
                "Regra",
                "Observado",
                "Esperado",
                "Alvo",
                "Fonte",
                "Revisão",
                "Localização",
                "Exibir",
            ),
            (130, 100, 260, 190, 220, 180, 220, 180, 170, 105),
        )
        self._findings_word_wrap = TableWordWrapController(
            self._findings,
            button_name="complianceFindingsWordWrapButton",
        )
        visibility_actions.addWidget(self._findings_word_wrap.button)
        self._findings.itemSelectionChanged.connect(self._navigate_finding_item)
        compliance_layout.addWidget(self._findings, 1)
        tabs.addTab(compliance_view, "Conformidade")

        rules_view = QWidget()
        rules_view.setObjectName("complianceRulesView")
        rules_layout = QVBoxLayout(rules_view)
        self._rules_summary = QLabel()
        self._rules_summary.setObjectName("complianceRulesSummaryLabel")
        self._rules_summary.setWordWrap(True)
        rules_layout.addWidget(self._rules_summary)
        actions = QHBoxLayout()
        self._import_rules = QPushButton("Importar")
        self._import_rules.setObjectName("complianceRulesImportButton")
        self._import_rules.clicked.connect(self._import_registry)
        actions.addWidget(self._import_rules)
        self._export_rules = QPushButton("Exportar")
        self._export_rules.setObjectName("complianceRulesExportButton")
        self._export_rules.clicked.connect(self._export_registry)
        actions.addWidget(self._export_rules)
        actions.addStretch(1)
        rules_layout.addLayout(actions)
        self._rules = _tree(
            "complianceRulesTree",
            ("Número", "Estado", "Título", "Escopo", "Provedor"),
            (85, 90, 300, 110, 130),
        )
        self._rules_word_wrap = TableWordWrapController(
            self._rules,
            button_name="complianceRulesWordWrapButton",
        )
        actions.addWidget(self._rules_word_wrap.button)
        self._rules.itemSelectionChanged.connect(self._show_rule_details)
        rules_layout.addWidget(self._rules, 1)
        self._rule_details = QTextBrowser()
        self._rule_details.setObjectName("complianceRuleDetails")
        self._rule_details.setOpenExternalLinks(False)
        self._rule_details.setMinimumHeight(150)
        rules_layout.addWidget(self._rule_details)
        tabs.addTab(rules_view, "Regras")
        layout.addWidget(tabs, 1)

        note = QLabel(
            "As regras são avaliadas automaticamente com a simbologia, a topologia, os vãos "
            "e os dados extraídos. Requisito aplicável ausente é indicado como divergência."
        )
        note.setObjectName("documentationAuditNotice")
        note.setProperty("role", "hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        self._project.currentIndexChanged.connect(self._load_selected_project)
        self._tabs.currentChanged.connect(self._refresh_visible_word_wrap)
        self._analyze_compliance.setEnabled(False)
        self._show_all_findings.setEnabled(False)
        self._hide_all_findings.setEnabled(False)
        self._populate_rules()

    def atualizar_projetos(self) -> None:
        selected = self._project.currentData()
        try:
            projects = self._gateway.list_projects(limit=200, offset=0)
        except (DocumentationGatewayError, ValueError) as error:
            self.status_changed.emit(str(error))
            return
        self._project.blockSignals(True)
        try:
            self._project.clear()
            self._project.addItem("Selecione um projeto analisado", None)
            for summary in projects.items:
                self._project.addItem(summary.service_note, str(summary.project_id.root))
            if selected is not None:
                index = self._project.findData(selected)
                self._project.setCurrentIndex(max(0, index))
        finally:
            self._project.blockSignals(False)
        if self._project.currentData() is not None:
            self._load_selected_project()

    def atualizar_regras(self) -> None:
        try:
            registry = self._gateway.get_active_registry()
        except (DocumentationGatewayError, ValueError) as error:
            self.status_changed.emit(str(error))
            return
        self._refresh_registry(registry)

    def abrir_projeto(self, projeto_id: UUID) -> None:
        self.atualizar_projetos()
        index = self._project.findData(str(projeto_id))
        try:
            self._activate(projeto_id)
        except (DocumentationGatewayError, ValueError) as error:
            self.status_changed.emit(str(error))
            return
        if index < 0:
            self.status_changed.emit("Projeto aberto por identificador remoto")

    def abrir_sessao(self, session: object) -> None:
        if isinstance(session, ReviewSessionResponse):
            self.abrir_projeto(session.project_id.root)
        elif session is None:
            self.limpar()

    def limpar(self) -> None:
        self._documentation = None
        self._result = None
        self._callouts = ()
        self._hidden_finding_ids.clear()
        self._finding_visibility_buttons.clear()
        self._visibility_context = None
        self._viewer.definir_callouts_conformidade(())
        self._documents.clear()
        self._findings.clear()
        self._documents_word_wrap.refresh()
        self._findings_word_wrap.refresh()
        self._summary.setText("Selecione um projeto analisado")
        self._execution_status.setText("Nenhuma execução de conformidade persistida")
        self._analyze_compliance.setEnabled(False)
        self._compliance_poll.stop()
        self._compliance_job_id = None
        self._sync_finding_visibility_buttons()

    def _load_selected_project(self) -> None:
        value = self._project.currentData()
        if value is None:
            return
        try:
            self._activate(UUID(str(value)))
        except (DocumentationGatewayError, ValueError) as error:
            self.status_changed.emit(str(error))

    def _activate(self, project_id: UUID) -> None:
        self._documentation = self._gateway.get_documentation(project_id)
        index = self._project.findData(str(project_id))
        if index >= 0:
            self._project.blockSignals(True)
            self._project.setCurrentIndex(index)
            self._project.blockSignals(False)
        self._load_persisted_result()

    def _load_persisted_result(self) -> None:
        documentation = self._documentation
        result = (
            self._gateway.get_latest_compliance(documentation.project_id.root)
            if documentation is not None
            else None
        )
        context = (
            (
                documentation.project_id.root,
                result.execution.execution_id.root if result is not None else None,
            )
            if documentation is not None
            else None
        )
        if context != self._visibility_context:
            self._hidden_finding_ids.clear()
            self._visibility_context = context
        self._result = result
        self._callouts = (
            tuple(item.callout for item in result.findings if item.callout is not None)
            if result is not None
            else ()
        )
        self._update_visible_callouts()
        self._populate_documents()
        self._populate_findings()
        self._analyze_compliance.setEnabled(documentation is not None)
        if documentation is None:
            return
        if self._result is None:
            self._summary.setText("Sessão semântica disponível · conformidade ainda não analisada")
            self._execution_status.setText("Nenhuma execução de conformidade persistida")
            return
        execution = self._result.execution
        documented = sum(len(item.fields) for item in documentation.sections)
        self._summary.setText(
            f"{documented} controles documentais · "
            f"{execution.divergence_count} divergência(s) · "
            f"{execution.compliant_count} regra(s) conforme(s)"
        )
        state = "Resultado desatualizado" if execution.is_stale else "Resultado atual"
        self._execution_status.setText(
            f"{state} · regras {execution.rule_registry_revision} · "
            f"{execution.completed_at.isoformat(timespec='seconds')}"
        )

    def _analyze_current_compliance(self) -> None:
        documentation = self._documentation
        if documentation is None or self._compliance_job_id is not None:
            return
        try:
            accepted = self._gateway.create_compliance_job(
                documentation.project_id.root,
                expected_semantic_signature=documentation.semantic_signature,
                idempotency_key=f"compliance-ui-{uuid4()}",
            )
        except (DocumentationGatewayError, ValueError) as error:
            self.status_changed.emit(str(error))
            QMessageBox.warning(self, "Conformidade não concluída", str(error))
            return
        self._compliance_job_id = accepted.job_id.root
        self._analyze_compliance.setEnabled(False)
        self._execution_status.setText("Análise de conformidade na fila")
        self._compliance_poll.start(accepted.poll_after_ms)
        self._poll_compliance_job()

    def _poll_compliance_job(self) -> None:
        job_id = self._compliance_job_id
        if job_id is None:
            self._compliance_poll.stop()
            return
        try:
            job = self._gateway.get_job(job_id)
        except DocumentationGatewayError as error:
            self._finish_compliance_job_error(str(error))
            return
        self._execution_status.setText(
            f"{job.message or 'Analisando conformidade'} · {job.progress_percent}%"
        )
        if job.status not in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
            return
        self._compliance_poll.stop()
        self._compliance_job_id = None
        self._analyze_compliance.setEnabled(self._documentation is not None)
        if job.status is JobStatus.SUCCEEDED:
            self._gateway.get_job_result(job_id)
            self._load_persisted_result()
            version = self._result.execution.rule_registry_revision if self._result else "ativa"
            self.status_changed.emit(f"Conformidade analisada com as regras {version}")
            return
        message = str(job.error) if job.error is not None else (job.message or "Operação cancelada")
        self._finish_compliance_job_error(message)

    def _finish_compliance_job_error(self, message: str) -> None:
        self._compliance_poll.stop()
        self._compliance_job_id = None
        self._analyze_compliance.setEnabled(self._documentation is not None)
        self.status_changed.emit(message)
        QMessageBox.warning(self, "Conformidade não concluída", message)

    def _populate_documents(self) -> None:
        documentation = self._documentation
        self._documents.clear()
        if documentation is None:
            self._documents_word_wrap.refresh()
            return
        roots: dict[str, QTreeWidgetItem] = {}
        for section in documentation.sections:
            document_name = section.document_name or "Documento"
            root = roots.get(document_name)
            if root is None:
                root = QTreeWidgetItem((document_name, "", "", "", ""))
                roots[document_name] = root
                self._documents.addTopLevelItem(root)
            group = QTreeWidgetItem((section.label, "", "", "", ""))
            root.addChild(group)
            for field in section.fields:
                child = QTreeWidgetItem(
                    (
                        "",
                        field.label,
                        field.value or "",
                        _status_label(field.status),
                        _confidence_label(field.confidence),
                    )
                )
                child.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    field.evidence[0] if field.evidence else None,
                )
                group.addChild(child)
        self._documents.expandAll()
        self._documents_word_wrap.refresh()

    def _populate_findings(self) -> None:
        result = self._result
        self._findings.clear()
        self._finding_visibility_buttons.clear()
        if result is None:
            self._sync_finding_visibility_buttons()
            self._findings_word_wrap.refresh()
            return
        localized_findings = {item.finding_id.root for item in self._callouts}
        for finding in sorted(
            (item for item in result.findings if item.status is ComplianceStatus.DIVERGENCE),
            key=lambda item: (item.rule_id, str(item.target_id)),
        ):
            finding_id = finding.finding_id.root
            observed = finding.observed_value or "—"
            expected = finding.expected_value or "—"
            target_label = finding.target_label or finding.target_scope.value.title()
            rule_revision = (
                finding.rule_registry_revision or result.execution.rule_registry_revision
            )
            row = QTreeWidgetItem(
                (
                    _result_label(finding.status),
                    finding.severity or "—",
                    finding.title or finding.summary,
                    observed,
                    expected,
                    target_label,
                    finding.source_reference,
                    f"Regras {rule_revision}"
                    + (
                        f" · norma {finding.normative_revision}"
                        if finding.normative_revision
                        else ""
                    ),
                    finding.location_label or "Sem localização no PDF",
                    "",
                )
            )
            row.setToolTip(2, finding.summary)
            row.setToolTip(3, observed)
            row.setToolTip(4, expected)
            row.setToolTip(5, target_label)
            row.setToolTip(
                6,
                f"Revisão {finding.normative_revision or '—'}",
            )
            row.setToolTip(
                7,
                f"Regras {rule_revision}"
                + (f" · norma {finding.normative_revision}" if finding.normative_revision else ""),
            )
            row.setData(0, Qt.ItemDataRole.UserRole + 2, finding.navigation)
            row.setData(0, Qt.ItemDataRole.UserRole + 3, str(finding_id))
            self._findings.addTopLevelItem(row)
            localized = finding_id in localized_findings
            tooltip = _finding_visibility_tooltip(
                visible=finding_id not in self._hidden_finding_ids,
                localized=localized,
            )
            button = self._visibility_button(
                visible=localized and finding_id not in self._hidden_finding_ids,
                localized=localized,
                tooltip=tooltip,
                toggled=partial(self._set_finding_visible, finding_id),
            )
            button.setEnabled(localized)
            button.setProperty("findingId", str(finding_id))
            self._finding_visibility_buttons[finding_id] = button
            self._findings.setItemWidget(row, 9, button)
        self._sync_finding_visibility_buttons()
        self._findings_word_wrap.refresh()

    def _visibility_button(
        self,
        *,
        visible: bool,
        localized: bool = True,
        tooltip: str,
        toggled: Callable[[bool], None],
    ) -> QToolButton:
        button = QToolButton(self._findings)
        button.setObjectName("complianceFindingVisibilityButton")
        button.setCheckable(True)
        button.setChecked(visible)
        button.setText(_finding_visibility_button_text(visible, localized=localized))
        button.setIcon(visibility_icon(visible))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.toggled.connect(toggled)
        return button

    def _set_finding_visible(self, finding_id: UUID, visible: bool) -> None:
        callout = next(
            (item for item in self._callouts if item.finding_id.root == finding_id),
            None,
        )
        if callout is None:
            return
        if visible:
            self._hidden_finding_ids.discard(finding_id)
        else:
            self._hidden_finding_ids.add(finding_id)
        self._sync_finding_visibility_buttons()
        self._update_visible_callouts()
        if visible:
            self._navigate(callout.navigation)
            self._viewer.selecionar_callout(str(callout.callout_id.root))

    def _set_all_findings_visible(self, *, visible: bool) -> None:
        localized_ids = {item.finding_id.root for item in self._callouts}
        if visible:
            self._hidden_finding_ids.difference_update(localized_ids)
        else:
            self._hidden_finding_ids.update(localized_ids)
        self._sync_finding_visibility_buttons()
        self._update_visible_callouts()

    def _sync_finding_visibility_buttons(self) -> None:
        localized_ids = {item.finding_id.root for item in self._callouts}
        for finding_id, button in self._finding_visibility_buttons.items():
            localized = finding_id in localized_ids
            visible = localized and finding_id not in self._hidden_finding_ids
            tooltip = _finding_visibility_tooltip(
                visible=visible,
                localized=localized,
            )
            button.blockSignals(True)
            button.setEnabled(localized)
            button.setChecked(visible)
            button.setText(_finding_visibility_button_text(visible, localized=localized))
            button.setIcon(visibility_icon(visible))
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.blockSignals(False)
        self._show_all_findings.setEnabled(bool(localized_ids & self._hidden_finding_ids))
        self._hide_all_findings.setEnabled(bool(localized_ids - self._hidden_finding_ids))

    def _update_visible_callouts(self) -> None:
        self._viewer.definir_callouts_conformidade(
            tuple(
                item
                for item in self._callouts
                if item.finding_id.root not in self._hidden_finding_ids
            )
        )

    def _populate_rules(self) -> None:
        self._rules.clear()
        registry = self._registry
        if registry is None:
            self._rules_summary.setText("Registro de regras indisponível")
            self._import_rules.setEnabled(False)
            self._export_rules.setEnabled(False)
            self._rule_details.clear()
            self._rules_word_wrap.refresh()
            return
        details = {item.summary.rule_id: item for item in registry.details}
        for rule in sorted(registry.rules, key=lambda item: item.rule_number):
            detail = details[rule.rule_id]
            row = QTreeWidgetItem(
                (
                    f"Regra {rule.rule_number}",
                    "Ativa" if rule.enabled else "Inativa",
                    rule.title,
                    detail.target_scope,
                    detail.provider_label,
                )
            )
            row.setData(0, Qt.ItemDataRole.UserRole, rule.rule_id)
            self._rules.addTopLevelItem(row)
        self._rules_summary.setText(
            f"Revisão ativa · versão {registry.revision} · "
            f"{registry.active_rule_count} regra(s) ativa(s) · "
            f"{registry.rule_count - registry.active_rule_count} regra(s) inativa(s)"
        )
        self._import_rules.setEnabled(True)
        self._export_rules.setEnabled(True)
        self._rule_details.clear()
        self._rules_word_wrap.refresh()

    def _refresh_visible_word_wrap(self, index: int) -> None:
        controllers = (
            self._documents_word_wrap,
            self._findings_word_wrap,
            self._rules_word_wrap,
        )
        if 0 <= index < len(controllers):
            controllers[index].refresh()

    def _show_rule_details(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            self._rule_details.clear()
            return
        self._rule_details.setPlainText(
            "\n".join(
                (
                    rule.summary.title,
                    rule.description or "",
                    "",
                    f"Fonte: {rule.source_detail or rule.summary.source_reference}",
                    f"Aplicável quando: {rule.applicability_text or 'sempre'}",
                    f"Exceto quando: {rule.exceptions_text or 'sem exceção'}",
                    f"Deve atender: {rule.requirements_text or 'sem requisito'}",
                )
            )
        )

    def _selected_rule(self) -> RuleDetailDto | None:
        selected = self._rules.selectedItems()
        registry = self._registry
        if not selected or registry is None:
            return None
        rule_id = str(selected[0].data(0, Qt.ItemDataRole.UserRole))
        return next((item for item in registry.details if item.summary.rule_id == rule_id), None)

    def _import_registry(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Importar regras de conformidade",
            "",
            "Registro de regras (*.json);;Todos os arquivos (*)",
        )
        if not selected:
            return
        try:
            summary = self._gateway.preflight_rule_import(
                Path(selected),
                idempotency_key=f"rules-preflight-ui-{uuid4()}",
            )
        except (DocumentationGatewayError, OSError, ValueError) as error:
            self._show_rules_error("Importação recusada", error)
            return
        confirmation = QMessageBox.question(
            self,
            "Resumo da importação",
            _preflight_confirmation(summary),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        try:
            revision = self._gateway.confirm_rule_import(
                ConfirmRuleImportRequest(
                    preflight_id=summary.preflight_id,
                    fingerprint=summary.fingerprint,
                    expected_active_revision=summary.current_revision,
                    confirmed=True,
                )
            )
        except (DocumentationGatewayError, OSError, ValueError) as error:
            self._show_rules_error("Importação não concluída", error)
            return
        self.atualizar_regras()
        self.status_changed.emit(f"Revisão ativa de regras atualizada para {revision.revision}")

    def _export_registry(self) -> None:
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Exportar regras de conformidade",
            "regras-conformidade.json",
            "Registro de regras (*.json)",
        )
        if not selected:
            return
        destination = Path(selected)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(self._gateway.download_active_registry())
            os.replace(temporary, destination)
        except (DocumentationGatewayError, OSError, ValueError) as error:
            temporary.unlink(missing_ok=True)
            self._show_rules_error("Exportação não concluída", error)
            return
        QMessageBox.information(self, "Exportação concluída", "Registro ativo exportado.")

    def _refresh_registry(self, registry: ActiveRuleRegistryResponse) -> None:
        self._registry = registry
        self._populate_rules()
        if self._documentation is not None:
            self._load_persisted_result()

    def _show_rules_error(self, title: str, error: Exception) -> None:
        message = (
            "Não foi possível acessar o arquivo selecionado"
            if isinstance(error, OSError)
            else str(error)
        )
        QMessageBox.warning(self, title, message)
        self.status_changed.emit(message)

    def _navigate_document_item(self) -> None:
        self._navigate_selected(self._documents)

    def _navigate_finding_item(self) -> None:
        selected = self._findings.selectedItems()
        if not selected or self._result is None or self._syncing_finding_selection:
            return
        finding_id = selected[0].data(0, Qt.ItemDataRole.UserRole + 3)
        callout = next(
            (item for item in self._callouts if str(item.finding_id.root) == str(finding_id)),
            None,
        )
        if callout is not None:
            self._navigate(callout.navigation)
            self._viewer.selecionar_callout(str(callout.callout_id.root))
            return
        navigation = selected[0].data(0, Qt.ItemDataRole.UserRole + 2)
        if isinstance(navigation, EvidenceNavigationDto):
            self._navigate(navigation)

    def _select_finding_id(self, finding_id: str) -> None:
        if self._syncing_finding_selection:
            return
        for index in range(self._findings.topLevelItemCount()):
            item = self._findings.topLevelItem(index)
            if item is None or str(item.data(0, Qt.ItemDataRole.UserRole + 3)) != finding_id:
                continue
            self._syncing_finding_selection = True
            signals_were_blocked = self._findings.blockSignals(True)
            try:
                self._tabs.setCurrentWidget(self._compliance_view)
                self._findings.setCurrentItem(item)
                self._findings.scrollToItem(item)
            finally:
                self._findings.blockSignals(signals_were_blocked)
                self._syncing_finding_selection = False
            return

    def _navigate_selected(self, tree: QTreeWidget) -> None:
        selected = tree.selectedItems()
        if not selected:
            return
        navigation = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if isinstance(navigation, EvidenceNavigationDto):
            self._navigate(navigation)

    def _navigate(self, navigation: EvidenceNavigationDto) -> None:
        documentation = self._documentation
        if documentation is None:
            return
        try:
            page_number = documentation.page_order.index(navigation.page_id) + 1
        except (ValueError, TypeError):
            return
        self._viewer.ir_para_folha(page_number)
        self._viewer.definir_destaque_navegacao(navigation)


def _tree(
    name: str,
    headers: tuple[str, ...],
    widths: tuple[int, ...],
) -> QTreeWidget:
    tree = QTreeWidget()
    tree.setObjectName(name)
    tree.setHeaderLabels(headers)
    tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    tree.setUniformRowHeights(True)
    header = tree.header()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(False)
    for column, width in enumerate(widths):
        header.resizeSection(column, width)
    return tree


def _confidence_label(value: str | None) -> str:
    return f"{float(value) * 100:.0f}%" if value is not None else "—"


def _status_label(value: DocumentationFieldStatus) -> str:
    return {
        DocumentationFieldStatus.PRESENT: "Identificado",
        DocumentationFieldStatus.ABSENT: "Não identificado",
        DocumentationFieldStatus.UNCERTAIN: "Revisão visual",
    }[value]


def _result_label(value: ComplianceStatus) -> str:
    return {
        ComplianceStatus.COMPLIANT: "Conforme",
        ComplianceStatus.DIVERGENCE: "Divergência",
        ComplianceStatus.NOT_EVALUABLE: "Não avaliável",
    }[value]


def _finding_visibility_tooltip(
    *,
    visible: bool,
    localized: bool,
) -> str:
    if not localized:
        return "Sem localização no PDF: o resultado não possui geometria rastreável"
    return "Ocultar este achado no PDF" if visible else "Exibir este achado no PDF"


def _finding_visibility_button_text(visible: bool, *, localized: bool = True) -> str:
    if not localized:
        return "Sem local"
    return "Ocultar" if visible else "Exibir"


def _preflight_confirmation(value: RuleImportPreflightResponse) -> str:
    lines = (
        f"Versão informada: {value.proposed_revision}",
        f"Novas: {len(value.added_rule_ids)}",
        f"IDs existentes substituídos: {len(value.changed_rule_ids)}",
        f"IDs atuais omitidos e preservados: {len(value.preserved_rule_ids)}",
    )
    warnings = tuple(item.summary for item in value.issues)
    return "\n".join(
        (
            *lines,
            *(("", "Avisos:", *(f"• {item}" for item in warnings)) if warnings else ()),
            "",
            "Confirmar a criação de uma nova revisão ativa?",
        )
    )
