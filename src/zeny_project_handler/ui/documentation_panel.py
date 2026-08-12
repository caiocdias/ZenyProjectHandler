"""Painel de cabeçalho, controles documentais, vãos e conformidade."""

from __future__ import annotations

from decimal import Decimal
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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from zeny_project_handler.adapters.compliance import (
    carregar_registro_conformidade_json_com_avisos,
)
from zeny_project_handler.application.compliance_registry import (
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.errors import ApplicationError
from zeny_project_handler.application.human_review import (
    ServicoRevisaoHumana,
    SessaoRevisao,
)
from zeny_project_handler.application.project_compliance import (
    ResultadoConformidadeProjeto,
    analisar_conformidade_projeto,
)
from zeny_project_handler.domain.compliance import (
    AlvoConformidade,
    CondicaoConformidade,
    OperadorCondicao,
    RegistroRegrasConformidade,
    RegraConformidade,
    ResultadoConformidade,
)
from zeny_project_handler.domain.compliance_facts import fato_conformidade_por_chave
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import GeometriaDocumento

from .pdf_viewer import PdfViewerWidget


class DocumentationPanelWidget(QWidget):
    status_changed = Signal(str)

    def __init__(
        self,
        *,
        service: ServicoRevisaoHumana,
        registry_service: ServicoRegistroRegrasConformidade | None = None,
        registry: RegistroRegrasConformidade | None = None,
        viewer: PdfViewerWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("documentationCompliancePanel")
        self._service = service
        self._registry_service = registry_service
        if registry_service is not None:
            self._registry = registry_service.obter_revisao_ativa().registro
        elif registry is not None:
            self._registry = registry
        else:
            raise ValueError("Painel requer um registro de conformidade")
        self._viewer = viewer
        self._session: SessaoRevisao | None = None
        self._result: ResultadoConformidadeProjeto | None = None
        self._build_ui()
        self.atualizar_projetos()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
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
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

        tabs = QTabWidget()
        tabs.setObjectName("documentationTabs")
        self._documents = _tree(
            "documentationTree",
            ("Grupo / documento", "Campo", "Valor", "Estado", "Confiança"),
            (170, 210, 260, 160, 90),
        )
        self._documents.itemSelectionChanged.connect(self._navigate_document_item)
        tabs.addTab(self._documents, "Documentação")

        self._findings = _tree(
            "complianceFindingsTree",
            ("Resultado", "Severidade", "Regra", "Alvo", "Fonte"),
            (130, 100, 300, 180, 230),
        )
        self._findings.itemSelectionChanged.connect(self._navigate_finding_item)
        tabs.addTab(self._findings, "Conformidade")

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
        self._toggle_rule = QPushButton("Ativar/desativar")
        self._toggle_rule.setObjectName("complianceRulesToggleButton")
        self._toggle_rule.clicked.connect(self._toggle_selected_rule)
        actions.addWidget(self._toggle_rule)
        self._remove_rule = QPushButton("Remover")
        self._remove_rule.setObjectName("complianceRulesRemoveButton")
        self._remove_rule.clicked.connect(self._remove_selected_rule)
        actions.addWidget(self._remove_rule)
        actions.addStretch(1)
        rules_layout.addLayout(actions)
        self._rules = _tree(
            "complianceRulesTree",
            ("Número", "Estado", "Título", "ID técnico", "Escopo", "Provedor"),
            (85, 90, 260, 260, 100, 130),
        )
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
            "Divergências são candidatas auditáveis. Ausência de contexto ou baixa confiança "
            "permanece como “não avaliável” e exige revisão humana."
        )
        note.setObjectName("documentationAuditNotice")
        note.setWordWrap(True)
        layout.addWidget(note)
        self._project.currentIndexChanged.connect(self._load_selected_project)
        self._populate_rules()

    def atualizar_projetos(self) -> None:
        selected = self._project.currentData()
        self._project.blockSignals(True)
        self._project.clear()
        self._project.addItem("Selecione um projeto analisado", None)
        for summary in self._service.listar_projetos():
            self._project.addItem(summary.nome, str(summary.projeto_id))
        if selected is not None:
            index = self._project.findData(selected)
            self._project.setCurrentIndex(max(0, index))
        self._project.blockSignals(False)
        if self._project.currentData() is not None:
            self._load_selected_project()

    def abrir_projeto(self, projeto_id: UUID) -> None:
        self.atualizar_projetos()
        index = self._project.findData(str(projeto_id))
        if index < 0:
            self.status_changed.emit("Projeto ainda não possui documentação analisável")
            return
        self._project.blockSignals(True)
        self._project.setCurrentIndex(index)
        self._project.blockSignals(False)
        self._activate(self._service.carregar_sessao(projeto_id))

    def abrir_sessao(self, session: object) -> None:
        if isinstance(session, SessaoRevisao):
            self._activate(session)
        elif session is None:
            self.limpar()

    def limpar(self) -> None:
        self._session = None
        self._result = None
        self._documents.clear()
        self._findings.clear()
        self._summary.setText("Selecione um projeto analisado")

    def _load_selected_project(self) -> None:
        value = self._project.currentData()
        if value is None:
            return
        try:
            self._activate(self._service.carregar_sessao(UUID(str(value))))
        except (DomainValidationError, ValueError) as error:
            self.status_changed.emit(str(error))

    def _activate(self, session: SessaoRevisao) -> None:
        self._session = session
        self._result = analisar_conformidade_projeto(session, self._registry)
        index = self._project.findData(str(session.projeto.id))
        if index >= 0:
            self._project.blockSignals(True)
            self._project.setCurrentIndex(index)
            self._project.blockSignals(False)
        self._populate_documents()
        self._populate_findings()
        divergent = sum(
            item.resultado is ResultadoConformidade.DIVERGENCIA for item in self._result.achados
        )
        not_evaluable = sum(
            item.resultado is ResultadoConformidade.NAO_AVALIAVEL for item in self._result.achados
        )
        self._summary.setText(
            f"{len(self._result.itens_documentais)} controles documentais · "
            f"{divergent} possível(is) divergência(s) · "
            f"{not_evaluable} regra(s) não avaliável(is)"
        )

    def _populate_documents(self) -> None:
        result = self._result
        session = self._session
        if result is None or session is None:
            return
        self._documents.clear()
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

    def _populate_findings(self) -> None:
        result = self._result
        if result is None:
            return
        self._findings.clear()
        targets = {item.id: item for item in result.alvos}
        order = {
            ResultadoConformidade.DIVERGENCIA: 0,
            ResultadoConformidade.NAO_AVALIAVEL: 1,
            ResultadoConformidade.CONFORME: 2,
        }
        for finding in sorted(
            result.achados,
            key=lambda item: (order[item.resultado], item.regra_id, str(item.alvo_id)),
        ):
            target = targets[finding.alvo_id]
            row = QTreeWidgetItem(
                (
                    _result_label(finding.resultado),
                    finding.severidade.value.title(),
                    finding.titulo,
                    target.rotulo,
                    f"{finding.fonte.documento} · {finding.fonte.item}",
                )
            )
            row.setToolTip(2, finding.mensagem)
            row.setToolTip(
                4,
                f"Revisão {finding.fonte.revisao}"
                + (f" · página {finding.fonte.pagina}" if finding.fonte.pagina is not None else ""),
            )
            row.setData(0, Qt.ItemDataRole.UserRole + 2, str(target.id))
            self._findings.addTopLevelItem(row)

    def _populate_rules(self) -> None:
        self._rules.clear()
        service = self._registry_service
        number_by_id = (
            {item.regra_id: item.numero for item in service.listar_numeros()}
            if service is not None
            else {rule.id: index for index, rule in enumerate(self._registry.regras, start=1)}
        )
        for rule in sorted(self._registry.regras, key=lambda item: number_by_id[item.id]):
            conditions = (*rule.aplicabilidade, *rule.excecoes, *rule.requisitos)
            planned = any(
                definition is not None and definition.disponibilidade.value == "PLANEJADO"
                for condition in conditions
                if (definition := fato_conformidade_por_chave(condition.chave_fato)) is not None
            )
            row = QTreeWidgetItem(
                (
                    f"Regra {number_by_id[rule.id]}",
                    "Ativa" if rule.ativa else "Inativa",
                    rule.titulo,
                    rule.id,
                    rule.escopo.value.title(),
                    "Planejado" if planned else "Disponível",
                )
            )
            row.setData(0, Qt.ItemDataRole.UserRole, rule.id)
            self._rules.addTopLevelItem(row)
        active_count = sum(item.ativa for item in self._registry.regras)
        inactive_count = len(self._registry.regras) - active_count
        if service is not None:
            revision = service.obter_revisao_ativa()
            revision_text = f"Revisão ativa {revision.id} · versão {revision.registro.versao}"
        else:
            revision_text = f"Registro empacotado · versão {self._registry.versao}"
        self._rules_summary.setText(
            f"{revision_text} · {active_count} regra(s) ativa(s) · "
            f"{inactive_count} regra(s) inativa(s)"
        )
        enabled = service is not None
        self._import_rules.setEnabled(enabled)
        self._export_rules.setEnabled(enabled)
        self._toggle_rule.setEnabled(False)
        self._remove_rule.setEnabled(False)
        self._rule_details.clear()

    def _show_rule_details(self) -> None:
        rule = self._selected_rule()
        enabled = rule is not None and self._registry_service is not None
        self._toggle_rule.setEnabled(enabled)
        self._remove_rule.setEnabled(enabled)
        if rule is None:
            self._rule_details.clear()
            return
        self._toggle_rule.setText("Desativar" if rule.ativa else "Ativar")
        source = f"{rule.fonte.documento} · {rule.fonte.revisao} · {rule.fonte.item}"
        if rule.fonte.pagina is not None:
            source += f" · página {rule.fonte.pagina}"
        self._rule_details.setPlainText(
            "\n".join(
                (
                    rule.titulo,
                    rule.descricao,
                    "",
                    f"ID: {rule.id}",
                    f"Fonte: {source}",
                    f"when: {_condition_list(rule.aplicabilidade, 'sem condição')}",
                    f"unless: {_condition_list(rule.excecoes, 'sem exceção')}",
                    f"must: {_condition_list(rule.requisitos, 'sem requisito')}",
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
        self.status_changed.emit(f"Revisão ativa de regras atualizada: {revision.id}")

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

    def _toggle_selected_rule(self) -> None:
        service = self._registry_service
        rule = self._selected_rule()
        if service is None or not isinstance(rule, RegraConformidade):
            return
        try:
            revision = service.definir_regra_ativa(rule.id, ativa=not rule.ativa)
        except (ApplicationError, DomainValidationError, OSError) as error:
            self._show_rules_error("Alteração não concluída", error)
            return
        self._refresh_registry(revision.registro)
        self.status_changed.emit(f"Regra {rule.id} {'ativada' if not rule.ativa else 'desativada'}")

    def _remove_selected_rule(self) -> None:
        service = self._registry_service
        rule = self._selected_rule()
        if service is None or not isinstance(rule, RegraConformidade):
            return
        confirmation = QMessageBox.question(
            self,
            "Remover regra",
            f"Remover '{rule.id}' da próxima revisão ativa? O histórico será preservado.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        try:
            revision = service.remover_regra(rule.id)
        except (ApplicationError, DomainValidationError, OSError) as error:
            self._show_rules_error("Remoção não concluída", error)
            return
        self._refresh_registry(revision.registro)
        self.status_changed.emit(f"Regra {rule.id} removida da revisão ativa")

    def _refresh_registry(self, registry: RegistroRegrasConformidade) -> None:
        self._registry = registry
        self._populate_rules()
        if self._session is not None:
            self._activate(self._session)

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
        if not selected or result is None:
            return
        target_id = selected[0].data(0, Qt.ItemDataRole.UserRole + 2)
        target = next(
            (item for item in result.alvos if str(item.id) == str(target_id)),
            None,
        )
        if target is not None:
            self._navigate_target(target)

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
        ResultadoConformidade.DIVERGENCIA: "Possível divergência",
        ResultadoConformidade.NAO_AVALIAVEL: "Não avaliável",
    }[value]


def _condition_list(
    conditions: tuple[CondicaoConformidade, ...],
    empty: str,
) -> str:
    if not conditions:
        return empty
    labels = {
        OperadorCondicao.EXISTE: "existe",
        OperadorCondicao.AUSENTE: "ausente",
        OperadorCondicao.IGUAL: "igual a",
        OperadorCondicao.DIFERENTE: "diferente de",
        OperadorCondicao.MENOR: "menor que",
        OperadorCondicao.MENOR_OU_IGUAL: "menor ou igual a",
        OperadorCondicao.MAIOR: "maior que",
        OperadorCondicao.MAIOR_OU_IGUAL: "maior ou igual a",
        OperadorCondicao.EM: "em",
        OperadorCondicao.NAO_EM: "não em",
        OperadorCondicao.CONTEM: "contém",
    }
    rendered = []
    for condition in conditions:
        expected = ", ".join(str(item) for item in condition.valores_esperados)
        suffix = f" [{expected}]" if expected else ""
        rendered.append(f"{condition.chave_fato} {labels[condition.operador]}{suffix}")
    return "; ".join(rendered)
