"""Painel de cabeçalho, controles documentais, vãos e conformidade."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from functools import partial
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import Qt, Signal
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

from zeny_project_handler.adapters.compliance import (
    carregar_registro_conformidade_json_com_avisos,
)
from zeny_project_handler.adapters.pdf.errors import PdfError
from zeny_project_handler.application.compliance_analysis import (
    ExecutarAnaliseConformidade,
    resultado_conformidade_desatualizado,
)
from zeny_project_handler.application.compliance_callouts import (
    CalloutConformidade,
    LayoutCalloutsImpossivelError,
    projetar_callouts_conformidade,
)
from zeny_project_handler.application.compliance_registry import (
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.errors import ApplicationError
from zeny_project_handler.application.human_review import (
    ServicoRevisaoHumana,
    SessaoRevisao,
)
from zeny_project_handler.domain.compliance import (
    AlvoConformidade,
    ExecucaoConformidade,
    RegistroRegrasConformidade,
    RegraConformidade,
    ResultadoConformidade,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import GeometriaDocumento

from .compliance_presentation import (
    formatar_alvo,
    formatar_escopo,
    formatar_lista_condicoes,
    formatar_texto_achado,
    formatar_valores_achado,
)
from .pdf_viewer import PdfViewerWidget
from .table_word_wrap import TableWordWrapController
from .visibility import visibility_icon


class DocumentationPanelWidget(QWidget):
    status_changed = Signal(str)

    def __init__(
        self,
        *,
        service: ServicoRevisaoHumana,
        analysis_service: ExecutarAnaliseConformidade | None = None,
        registry_service: ServicoRegistroRegrasConformidade | None = None,
        registry: RegistroRegrasConformidade | None = None,
        viewer: PdfViewerWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("documentationCompliancePanel")
        self._service = service
        self._analysis_service = analysis_service
        self._registry_service = registry_service
        if registry_service is not None:
            self._registry = registry_service.obter_revisao_ativa().registro
        elif registry is not None:
            self._registry = registry
        else:
            raise ValueError("Painel requer um registro de conformidade")
        self._viewer = viewer
        self._session: SessaoRevisao | None = None
        self._result: ExecucaoConformidade | None = None
        self._callouts: tuple[CalloutConformidade, ...] = ()
        self._hidden_finding_ids: set[UUID] = set()
        self._finding_visibility_buttons: dict[UUID, QToolButton] = {}
        self._visibility_context: tuple[UUID, UUID | None] | None = None
        self._syncing_finding_selection = False
        self._build_ui()
        self._viewer.compliance_callout_selected.connect(self._select_finding_id)
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
        self._project.blockSignals(True)
        self._project.clear()
        self._project.addItem("Selecione um projeto analisado", None)
        for summary in self._service.listar_projetos_semanticos():
            self._project.addItem(summary.nome, str(summary.projeto_id))
        if selected is not None:
            index = self._project.findData(selected)
            self._project.setCurrentIndex(max(0, index))
        self._project.blockSignals(False)
        if self._project.currentData() is not None:
            self._load_selected_project()

    def atualizar_regras(self) -> None:
        service = self._registry_service
        if service is None:
            return
        self._refresh_registry(service.obter_revisao_ativa().registro)

    def abrir_projeto(self, projeto_id: UUID) -> None:
        self.atualizar_projetos()
        index = self._project.findData(str(projeto_id))
        if index < 0:
            self.status_changed.emit("Projeto ainda não possui documentação analisável")
            return
        self._project.blockSignals(True)
        self._project.setCurrentIndex(index)
        self._project.blockSignals(False)
        self._activate(self._service.carregar_sessao_semantica(projeto_id))

    def abrir_sessao(self, session: object) -> None:
        if isinstance(session, SessaoRevisao):
            self._activate(session)
        elif session is None:
            self.limpar()

    def limpar(self) -> None:
        self._session = None
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
        self._sync_finding_visibility_buttons()

    def _load_selected_project(self) -> None:
        value = self._project.currentData()
        if value is None:
            return
        try:
            self._activate(self._service.carregar_sessao_semantica(UUID(str(value))))
        except (DomainValidationError, ValueError) as error:
            self.status_changed.emit(str(error))

    def _activate(self, session: SessaoRevisao) -> None:
        self._session = session
        index = self._project.findData(str(session.projeto.id))
        if index >= 0:
            self._project.blockSignals(True)
            self._project.setCurrentIndex(index)
            self._project.blockSignals(False)
        self._load_persisted_result()

    def _load_persisted_result(self) -> None:
        session = self._session
        service = self._analysis_service
        result = (
            service.obter_ultima(session.projeto.id)
            if session is not None and service is not None
            else None
        )
        context = (
            (session.projeto.id, result.id if result is not None else None)
            if session is not None
            else None
        )
        if context != self._visibility_context:
            self._hidden_finding_ids.clear()
            self._visibility_context = context
        self._result = result
        pages = (
            tuple(page for document in session.projeto.documentos for page in document.paginas)
            if session is not None
            else ()
        )
        presentation_texts: dict[UUID, str] = {}
        if self._result is not None:
            targets = {item.id: item for item in self._result.alvos}
            presentation_texts = {
                finding.id: formatar_texto_achado(finding, targets[finding.alvo_id])
                for finding in self._result.achados
            }
        self._callouts = ()
        if self._result is not None and session is not None:
            try:
                initial_callouts = projetar_callouts_conformidade(
                    self._result,
                    evidencias=session.evidencias,
                    paginas=pages,
                    textos_apresentacao=presentation_texts,
                )
                # Preserve o layout determinístico já disponível caso a
                # rasterização usada apenas para refiná-lo falhe.
                self._callouts = initial_callouts
                visual_mapper = getattr(self._viewer, "mapear_ocupacao_visual", None)
                visual_maps = (
                    visual_mapper(frozenset(item.pagina_id for item in initial_callouts))
                    if callable(visual_mapper)
                    else {}
                )
                self._callouts = projetar_callouts_conformidade(
                    self._result,
                    evidencias=session.evidencias,
                    paginas=pages,
                    textos_apresentacao=presentation_texts,
                    mapas_ocupacao_visual=visual_maps,
                )
            except (LayoutCalloutsImpossivelError, PdfError) as error:
                self.status_changed.emit(str(error))
        self._update_visible_callouts()
        self._populate_documents()
        self._populate_findings()
        self._analyze_compliance.setEnabled(session is not None and service is not None)
        if session is None:
            return
        if self._result is None:
            self._summary.setText("Sessão semântica disponível · conformidade ainda não analisada")
            self._execution_status.setText("Nenhuma execução de conformidade persistida")
            return
        divergent = sum(
            item.resultado is ResultadoConformidade.DIVERGENCIA for item in self._result.achados
        )
        conforming = sum(
            item.resultado is ResultadoConformidade.CONFORME for item in self._result.achados
        )
        self._summary.setText(
            f"{len(self._result.itens_documentais)} controles documentais · "
            f"{divergent} divergência(s) · "
            f"{conforming} regra(s) conforme(s)"
        )
        stale = resultado_conformidade_desatualizado(
            self._result,
            self._registry.assinatura(),
        )
        state = "Resultado desatualizado" if stale else "Resultado atual"
        self._execution_status.setText(
            f"{state} · regras {self._result.versao_regras} · "
            f"{self._result.executada_em.isoformat(timespec='seconds')}"
        )

    def _analyze_current_compliance(self) -> None:
        session = self._session
        service = self._analysis_service
        if session is None or service is None:
            return
        try:
            self._result = service.executar(session.projeto.id)
        except (ApplicationError, DomainValidationError, ValueError) as error:
            self.status_changed.emit(str(error))
            QMessageBox.warning(self, "Conformidade não concluída", str(error))
            return
        self._load_persisted_result()
        self.status_changed.emit(
            f"Conformidade analisada com as regras {self._result.versao_regras}"
        )

    def _populate_documents(self) -> None:
        result = self._result
        session = self._session
        self._documents.clear()
        if result is None or session is None:
            self._documents_word_wrap.refresh()
            return
        by_document = {item.id: item for item in session.projeto.documentos}
        roots: dict[UUID, QTreeWidgetItem] = {}
        groups: dict[tuple[UUID, str], QTreeWidgetItem] = {}
        for item in result.itens_documentais:
            document = by_document[item.documento_id]
            root = roots.get(document.id)
            if root is None:
                root = QTreeWidgetItem((document.nome_arquivo, "", "", "", ""))
                roots[document.id] = root
                self._documents.addTopLevelItem(root)
            group_key = (document.id, item.grupo)
            group = groups.get(group_key)
            if group is None:
                group = QTreeWidgetItem((item.grupo, "", "", "", ""))
                groups[group_key] = group
                root.addChild(group)
            child = QTreeWidgetItem(
                (
                    "",
                    item.campo,
                    item.valor,
                    _status_label(item.estado),
                    _confidence_label(item.confianca),
                )
            )
            _set_navigation_data(child, item.pagina_id, item.geometria)
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
        targets = {item.id: item for item in result.alvos}
        localized_findings = {item.id for item in self._callouts}
        for finding in sorted(
            (
                item
                for item in result.achados
                if item.resultado is ResultadoConformidade.DIVERGENCIA
            ),
            key=lambda item: (item.regra_id, str(item.alvo_id)),
        ):
            target = targets[finding.alvo_id]
            observed, expected = formatar_valores_achado(
                finding.avaliacoes_condicoes,
                finding.resultado,
            )
            target_label = formatar_alvo(target)
            presentation_text = formatar_texto_achado(finding, target)
            row = QTreeWidgetItem(
                (
                    _result_label(finding.resultado),
                    finding.severidade.value.title(),
                    finding.titulo,
                    observed,
                    expected,
                    target_label,
                    f"{finding.fonte.documento} · {finding.fonte.item}",
                    f"Regras {result.versao_regras} · norma {finding.fonte.revisao}",
                    _location_label(target, projected=finding.id in localized_findings),
                    "",
                )
            )
            row.setToolTip(2, presentation_text)
            row.setToolTip(3, observed)
            row.setToolTip(4, expected)
            row.setToolTip(5, target_label)
            row.setToolTip(
                6,
                f"Revisão {finding.fonte.revisao}"
                + (f" · página {finding.fonte.pagina}" if finding.fonte.pagina is not None else ""),
            )
            row.setToolTip(
                7,
                f"Regras {result.versao_regras} · norma {finding.fonte.revisao}",
            )
            row.setData(0, Qt.ItemDataRole.UserRole + 2, str(target.id))
            row.setData(0, Qt.ItemDataRole.UserRole + 3, str(finding.id))
            self._findings.addTopLevelItem(row)
            localized = finding.id in localized_findings
            tooltip = _finding_visibility_tooltip(
                visible=finding.id not in self._hidden_finding_ids,
                localized=localized,
            )
            button = self._visibility_button(
                visible=localized and finding.id not in self._hidden_finding_ids,
                localized=localized,
                tooltip=tooltip,
                toggled=partial(self._set_finding_visible, finding.id),
            )
            button.setEnabled(localized)
            button.setProperty("findingId", str(finding.id))
            self._finding_visibility_buttons[finding.id] = button
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
        callout = next((item for item in self._callouts if item.id == finding_id), None)
        if callout is None:
            return
        if visible:
            self._hidden_finding_ids.discard(finding_id)
        else:
            self._hidden_finding_ids.add(finding_id)
        self._sync_finding_visibility_buttons()
        self._update_visible_callouts()
        if visible:
            self._navigate(callout.pagina_id, None)
            self._viewer.selecionar_callout(str(callout.id))

    def _set_all_findings_visible(self, *, visible: bool) -> None:
        localized_ids = {item.id for item in self._callouts}
        if visible:
            self._hidden_finding_ids.difference_update(localized_ids)
        else:
            self._hidden_finding_ids.update(localized_ids)
        self._sync_finding_visibility_buttons()
        self._update_visible_callouts()

    def _sync_finding_visibility_buttons(self) -> None:
        localized_ids = {item.id for item in self._callouts}
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
            tuple(item for item in self._callouts if item.id not in self._hidden_finding_ids)
        )

    def _populate_rules(self) -> None:
        self._rules.clear()
        service = self._registry_service
        number_by_id = (
            {item.regra_id: item.numero for item in service.listar_numeros()}
            if service is not None
            else {rule.id: index for index, rule in enumerate(self._registry.regras, start=1)}
        )
        for rule in sorted(self._registry.regras, key=lambda item: number_by_id[item.id]):
            row = QTreeWidgetItem(
                (
                    f"Regra {number_by_id[rule.id]}",
                    "Ativa" if rule.ativa else "Inativa",
                    rule.titulo,
                    formatar_escopo(rule.escopo),
                    "Automático",
                )
            )
            row.setData(0, Qt.ItemDataRole.UserRole, rule.id)
            self._rules.addTopLevelItem(row)
        active_count = sum(item.ativa for item in self._registry.regras)
        inactive_count = len(self._registry.regras) - active_count
        if service is not None:
            revision = service.obter_revisao_ativa()
            revision_text = f"Revisão ativa · versão {revision.registro.versao}"
        else:
            revision_text = f"Registro empacotado · versão {self._registry.versao}"
        self._rules_summary.setText(
            f"{revision_text} · {active_count} regra(s) ativa(s) · "
            f"{inactive_count} regra(s) inativa(s)"
        )
        enabled = service is not None
        self._import_rules.setEnabled(enabled)
        self._export_rules.setEnabled(enabled)
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
        source = f"{rule.fonte.documento} · {rule.fonte.revisao} · {rule.fonte.item}"
        if rule.fonte.pagina is not None:
            source += f" · página {rule.fonte.pagina}"
        self._rule_details.setPlainText(
            "\n".join(
                (
                    rule.titulo,
                    rule.descricao,
                    "",
                    f"Fonte: {source}",
                    "Aplicável quando: "
                    + formatar_lista_condicoes(rule.aplicabilidade, vazio="sempre"),
                    "Exceto quando: "
                    + formatar_lista_condicoes(rule.excecoes, vazio="sem exceção"),
                    "Deve atender: "
                    + formatar_lista_condicoes(rule.requisitos, vazio="sem requisito"),
                )
            )
        )

    def _selected_rule(self) -> RegraConformidade | None:
        selected = self._rules.selectedItems()
        if not selected:
            return None
        rule_id = str(selected[0].data(0, Qt.ItemDataRole.UserRole))
        return next((item for item in self._registry.regras if item.id == rule_id), None)

    def _import_registry(self) -> None:
        service = self._registry_service
        if service is None:
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Importar regras de conformidade",
            "",
            "Registro de regras (*.json);;Todos os arquivos (*)",
        )
        if not selected:
            return
        try:
            registry, warnings = carregar_registro_conformidade_json_com_avisos(Path(selected))
            summary = service.preparar_importacao(registry, avisos=warnings)
        except (ApplicationError, DomainValidationError, OSError) as error:
            self._show_rules_error("Importação recusada", error)
            return
        confirmation = QMessageBox.question(
            self,
            "Resumo da importação",
            summary.texto_confirmacao(),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        try:
            revision = service.importar(summary)
        except (ApplicationError, DomainValidationError, OSError) as error:
            self._show_rules_error("Importação não concluída", error)
            return
        self._refresh_registry(revision.registro)
        self.status_changed.emit(
            f"Revisão ativa de regras atualizada para {revision.registro.versao}"
        )

    def _export_registry(self) -> None:
        service = self._registry_service
        if service is None:
            return
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Exportar regras de conformidade",
            "regras-conformidade.json",
            "Registro de regras (*.json)",
        )
        if not selected:
            return
        try:
            service.exportar(Path(selected))
        except (ApplicationError, DomainValidationError, OSError) as error:
            self._show_rules_error("Exportação não concluída", error)
            return
        QMessageBox.information(self, "Exportação concluída", "Registro ativo exportado.")

    def _refresh_registry(self, registry: RegistroRegrasConformidade) -> None:
        self._registry = registry
        self._populate_rules()
        if self._session is not None:
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
        result = self._result
        if not selected or result is None or self._syncing_finding_selection:
            return
        finding_id = selected[0].data(0, Qt.ItemDataRole.UserRole + 3)
        callout = next(
            (item for item in self._callouts if str(item.id) == str(finding_id)),
            None,
        )
        if callout is not None:
            self._navigate(callout.pagina_id, None)
            self._viewer.selecionar_callout(str(callout.id))
            return
        target_id = selected[0].data(0, Qt.ItemDataRole.UserRole + 2)
        target = next(
            (item for item in result.alvos if str(item.id) == str(target_id)),
            None,
        )
        if target is not None:
            self._navigate_target(target)

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
        page_id = selected[0].data(0, Qt.ItemDataRole.UserRole)
        geometry = selected[0].data(0, Qt.ItemDataRole.UserRole + 1)
        self._navigate(page_id, geometry if isinstance(geometry, GeometriaDocumento) else None)

    def _navigate_target(self, target: AlvoConformidade) -> None:
        self._navigate(target.pagina_id, target.geometria)

    def _navigate(self, page_id: object, geometry: GeometriaDocumento | None) -> None:
        session = self._session
        if session is None or page_id is None:
            return
        try:
            page_number = session.projeto.ordem_leitura_paginas.index(UUID(str(page_id))) + 1
        except (ValueError, TypeError):
            return
        self._viewer.ir_para_folha(page_number)
        if geometry is not None:
            self._viewer.definir_sobreposicoes((geometry.pontos,))


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


def _set_navigation_data(
    item: QTreeWidgetItem,
    page_id: UUID | None,
    geometry: GeometriaDocumento | None,
) -> None:
    item.setData(
        0,
        Qt.ItemDataRole.UserRole,
        str(page_id) if page_id is not None else None,
    )
    item.setData(0, Qt.ItemDataRole.UserRole + 1, geometry)


def _confidence_label(value: Decimal | None) -> str:
    return f"{value * 100:.0f}%" if value is not None else "—"


def _status_label(value: str) -> str:
    return {
        "IDENTIFICADO": "Identificado",
        "CONFIRMADO": "Confirmado",
        "INFERIDO_PELA_PAGINA": "Inferido pela página",
        "NAO_IDENTIFICADO": "Não identificado",
        "NAO_AVALIAVEL": "Não avaliável",
        "REQUER_REVISAO_VISUAL": "Revisão visual",
        "ASSINATURA_PDF_PRESENTE": "Campo PDF preenchido",
    }.get(value, value.replace("_", " ").title())


def _result_label(value: ResultadoConformidade) -> str:
    return {
        ResultadoConformidade.CONFORME: "Conforme",
        ResultadoConformidade.DIVERGENCIA: "Divergência",
        ResultadoConformidade.NAO_AVALIAVEL: "Não avaliável",
    }[value]


def _location_label(target: AlvoConformidade, *, projected: bool = False) -> str:
    if projected:
        return "Localizado no PDF"
    if target.pagina_id is None:
        return "Sem localização no PDF"
    if target.geometria is None:
        return "Sem localização no PDF"
    return "Localizado no PDF"


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
