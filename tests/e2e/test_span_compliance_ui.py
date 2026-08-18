# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pymupdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
)
from pytestqt.qtbot import QtBot

from tests.conftest import ApplicationFactory
from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.config import AppSettings
from zeny_project_handler.domain.analysis import (
    DecisaoRevisao,
    EvidenciaDocumento,
    ExecucaoAnalise,
    PropostaElemento,
)
from zeny_project_handler.domain.catalog import TipoCabo
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    NivelRede,
    OrigemComprimentoVao,
    SituacaoProjeto,
    TipoDecisaoRevisao,
    TipoEvidencia,
)
from zeny_project_handler.domain.project import Cabo, PontoRede, Poste
from zeny_project_handler.domain.project_metadata import MetadadosProjeto
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ui.project_panel import ProjectPanelWidget

pytestmark = [pytest.mark.integration, pytest.mark.e2e]

_NOW = datetime(2026, 8, 12, 21, tzinfo=UTC)
_RULE_ID = "fixture.e2e.vao-maximo"
_RULE_TITLE = "Vão sintético acima do limite importado"
_CURRENT_SPAN_RULE_TITLE = "Vão máximo de rede compacta ou isolada urbana"


def test_span_rule_full_ui_cycle_survives_restart(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    settings = AppSettings(data_directory=tmp_path / "data", pdf_render_dpi=72)
    source = _span_pdf(tmp_path / "vao-sintetico.pdf")
    imported_rules = _span_rule_file(tmp_path / "regra-vao.json")
    disabled_rules = _span_rule_file(tmp_path / "regra-vao-inativa.json", enabled=False)
    application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    window.show()
    project_id = _create_project_with_pdf(qtbot, monkeypatch, window.project_panel, source)
    _persist_span_semantic_session(window.project_panel, project_id)

    confirmations: list[str] = []

    def confirm(_parent: object, _title: str, message: str, *_args: object) -> object:
        confirmations.append(message)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(imported_rules), ""),
    )
    documentation = window.documentation_panel
    assert documentation is not None
    documentation.atualizar_projetos()
    documentation.abrir_projeto(project_id)
    tabs = documentation.findChild(QTabWidget, "documentationTabs")
    rules = documentation.findChild(QTreeWidget, "complianceRulesTree")
    import_button = documentation.findChild(QPushButton, "complianceRulesImportButton")
    analyze = documentation.findChild(QPushButton, "complianceAnalyzeButton")
    findings = documentation.findChild(QTreeWidget, "complianceFindingsTree")
    assert tabs is not None and rules is not None and import_button is not None
    assert analyze is not None and findings is not None

    tabs.setCurrentIndex(2)
    qtbot.mouseClick(import_button, Qt.MouseButton.LeftButton)
    imported_row = _rule_row(rules, _RULE_ID)
    assert imported_row.text(4) == "Automático"
    tabs.setCurrentIndex(1)
    qtbot.mouseClick(analyze, Qt.MouseButton.LeftButton)

    finding = _finding_row(findings, _RULE_TITLE)
    finding_id = UUID(str(finding.data(0, Qt.ItemDataRole.UserRole + 3)))
    assert finding.text(0) == "Divergência"
    assert "52" in finding.text(3)
    assert "45" in finding.text(4)
    assert finding.text(8) == "Localizado no PDF"
    assert finding_id in {item.id for item in window.pdf_viewer._compliance_callouts}
    current_rule_finding = _finding_row(findings, _CURRENT_SPAN_RULE_TITLE)
    current_rule_finding_id = UUID(str(current_rule_finding.data(0, Qt.ItemDataRole.UserRole + 3)))
    assert current_rule_finding.text(0) == "Divergência"
    assert current_rule_finding_id in {item.id for item in window.pdf_viewer._compliance_callouts}
    qtbot.waitUntil(
        lambda: str(finding_id) in window.pdf_viewer.view._callout_items,
        timeout=10_000,
    )
    qtbot.waitUntil(
        lambda: str(current_rule_finding_id) in window.pdf_viewer.view._callout_items,
        timeout=10_000,
    )

    first_execution = documentation._result
    assert first_execution is not None
    assert any(item.regra_id == _RULE_ID for item in first_execution.achados)
    assert confirmations and "IDs existentes substituídos: 0" in confirmations[0]

    window.close()
    window.release_resources()
    application.processEvents()

    _reopened_application, reopened = application_factory([], settings=settings)
    qtbot.addWidget(reopened)
    reopened.show()
    reopened_documentation = reopened.documentation_panel
    assert reopened_documentation is not None
    reopened_documentation.abrir_projeto(project_id)
    reopened_rules = reopened_documentation.findChild(QTreeWidget, "complianceRulesTree")
    reopened_findings = reopened_documentation.findChild(QTreeWidget, "complianceFindingsTree")
    reopened_tabs = reopened_documentation.findChild(QTabWidget, "documentationTabs")
    toggle_button = reopened_documentation.findChild(
        QPushButton,
        "complianceRulesToggleButton",
    )
    remove_button = reopened_documentation.findChild(
        QPushButton,
        "complianceRulesRemoveButton",
    )
    import_button = reopened_documentation.findChild(
        QPushButton,
        "complianceRulesImportButton",
    )
    reanalyze = reopened_documentation.findChild(QPushButton, "complianceAnalyzeButton")
    status = reopened_documentation.findChild(QLabel, "complianceExecutionStatusLabel")
    assert reopened_rules is not None and reopened_findings is not None
    assert reopened_tabs is not None
    assert toggle_button is None and remove_button is None
    assert import_button is not None and reanalyze is not None and status is not None

    _rule_row(reopened_rules, _RULE_ID)
    reopened_finding = _finding_row(reopened_findings, _RULE_TITLE)
    reopened_finding_id = UUID(str(reopened_finding.data(0, Qt.ItemDataRole.UserRole + 3)))
    assert reopened_finding_id == finding_id
    assert reopened_documentation._result == first_execution
    assert reopened_finding_id in {item.id for item in reopened.pdf_viewer._compliance_callouts}

    visibility = reopened_findings.itemWidget(reopened_finding, 9)
    assert isinstance(visibility, QToolButton)
    assert visibility.isChecked()
    qtbot.mouseClick(visibility, Qt.MouseButton.LeftButton)
    assert reopened_finding_id not in {item.id for item in reopened.pdf_viewer._compliance_callouts}
    qtbot.mouseClick(visibility, Qt.MouseButton.LeftButton)
    assert reopened_finding_id in {item.id for item in reopened.pdf_viewer._compliance_callouts}

    reopened_tabs.setCurrentIndex(2)
    reopened_rules.setCurrentItem(_rule_row(reopened_rules, _RULE_ID))
    assert _RULE_ID in _rule_ids(reopened_rules)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(disabled_rules), ""),
    )
    qtbot.mouseClick(import_button, Qt.MouseButton.LeftButton)
    assert _rule_row(reopened_rules, _RULE_ID).text(1) == "Inativa"
    assert "Resultado desatualizado" in status.text()

    reopened_tabs.setCurrentIndex(1)
    qtbot.mouseClick(reanalyze, Qt.MouseButton.LeftButton)
    assert all(
        (item := reopened_findings.topLevelItem(index)) is not None and item.text(2) != _RULE_TITLE
        for index in range(reopened_findings.topLevelItemCount())
    )
    latest = reopened_documentation._result
    assert latest is not None and latest.id != first_execution.id
    assert all(item.regra_id != _RULE_ID for item in latest.achados)
    analysis_service = reopened_documentation._analysis_service
    assert analysis_service is not None
    history = analysis_service.listar_historico(project_id)
    assert history == (first_execution, latest)
    assert any(item.regra_id == _RULE_ID for item in history[0].achados)
    assert "IDs existentes substituídos: 1" in confirmations[-1]
    assert "IDs atuais omitidos e preservados: 39" in confirmations[-1]


def _create_project_with_pdf(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    panel: object,
    source: Path,
) -> UUID:
    assert isinstance(panel, ProjectPanelWidget)
    name = panel.findChild(QLineEdit, "mvpProjectNameEdit")
    create = panel.findChild(QPushButton, "mvpCreateProjectButton")
    add_pdf = panel.findChild(QPushButton, "mvpAddPdfsButton")
    project_combo = panel.findChild(QComboBox, "mvpProjectCombo")
    assert name is not None and create is not None and add_pdf is not None
    assert project_combo is not None
    name.setText("0000000224")
    qtbot.mouseClick(create, Qt.MouseButton.LeftButton)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *_args, **_kwargs: ([str(source)], "Documentos PDF (*.pdf)"),
    )
    qtbot.mouseClick(add_pdf, Qt.MouseButton.LeftButton)
    return UUID(str(project_combo.currentData()))


def _persist_span_semantic_session(panel: object, project_id: UUID) -> None:
    assert isinstance(panel, ProjectPanelWidget)
    catalog = carregar_catalogo_inicial()
    cable_type = _protected_cable(catalog)
    pole_type_id = catalog.itens_ativos(CategoriaElemento.POSTE)[0].id
    execution_id = _id("semantic-execution")
    with panel._review_panel._service._unit_of_work() as work:
        project = work.projetos.obter(project_id)
        assert project is not None
        page = project.documentos[0].paginas[0]
        first_pole = Poste(
            id=_id("pole-1"),
            tipo_catalogo_id=pole_type_id,
            situacao=SituacaoProjeto.INSTALAR,
            geometria=_point(page.id, "0.20", "0.45"),
        )
        second_pole = Poste(
            id=_id("pole-2"),
            tipo_catalogo_id=pole_type_id,
            situacao=SituacaoProjeto.INSTALAR,
            geometria=_point(page.id, "0.80", "0.45"),
        )
        first_point = PontoRede(
            id=_id("point-1"),
            poste_id=first_pole.id,
            nome="P1-MT",
            nivel_rede=NivelRede.MT,
            nivel_tensao_opcao_id=cable_type.nivel_tensao_opcao_id,
            configuracao_fases_opcao_id=cable_type.configuracao_fases_opcao_id,
            geometria=first_pole.geometria,
        )
        second_point = PontoRede(
            id=_id("point-2"),
            poste_id=second_pole.id,
            nome="P2-MT",
            nivel_rede=NivelRede.MT,
            nivel_tensao_opcao_id=cable_type.nivel_tensao_opcao_id,
            configuracao_fases_opcao_id=cable_type.configuracao_fases_opcao_id,
            geometria=second_pole.geometria,
        )
        cable_geometry = GeometriaDocumento.polilinha(
            page.id,
            (
                PontoNormalizado(Decimal("0.20"), Decimal("0.45")),
                PontoNormalizado(Decimal("0.80"), Decimal("0.45")),
            ),
        )
        cable = Cabo(
            id=_id("cable"),
            tipo_catalogo_id=cable_type.id,
            situacao=SituacaoProjeto.INSTALAR,
            geometria=cable_geometry,
            ponto_origem_id=first_point.id,
            ponto_destino_id=second_point.id,
            comprimento_m=Decimal("52"),
            origem_comprimento=OrigemComprimentoVao.ANOTACAO_DESENHO,
        )
        updated = replace(
            project,
            elementos=(first_pole, second_pole, cable),
            pontos_rede=(first_point, second_point),
            metadados=MetadadosProjeto(tipo_servico="Rede urbana"),
        )
        execution = ExecucaoAnalise(
            id=execution_id,
            projeto_id=project_id,
            metodo="fixture-e2e",
            versao_metodo="1",
            parametros=(),
            estado=EstadoExecucaoAnalise.CONCLUIDA,
            iniciada_em=_NOW,
            finalizada_em=_NOW,
        )
        evidence = EvidenciaDocumento(
            id=_id("length-evidence"),
            execucao_id=execution.id,
            pagina_id=page.id,
            tipo=TipoEvidencia.TEXTO,
            geometria=_point(page.id, "0.50", "0.39"),
            metodo="fixture-e2e",
            versao_metodo="1",
            parametros=(),
            conteudo_bruto="52 m",
            criada_em=_NOW,
        )
        proposal = PropostaElemento(
            id=_id("cable-proposal"),
            execucao_id=execution.id,
            categoria=CategoriaElemento.CABO,
            situacao_projeto=SituacaoProjeto.INSTALAR,
            estado_revisao=EstadoRevisao.CONFIRMADA,
            evidencia_ids=(evidence.id,),
            geometria=cable_geometry,
            tipo_catalogo_sugerido_id=cable_type.id,
            codigo_observado=cable_type.codigo,
            atributos_sugeridos=(
                ("comprimento_m", Decimal("52")),
                ("comprimento_origem", "anotacao_desenho"),
                ("evidencia_comprimento_id", str(evidence.id)),
            ),
            confianca=Decimal("0.99"),
        )
        decision = DecisaoRevisao(
            id=_id("cable-decision"),
            proposta_id=proposal.id,
            decisao=TipoDecisaoRevisao.ACEITAR,
            revisor="fixture-e2e",
            decidida_em=_NOW,
            elemento_confirmado_id=cable.id,
        )
        work.projetos.salvar(updated)
        work.execucoes_analise.salvar(execution)
        work.evidencias.salvar(evidence)
        work.propostas.salvar(proposal)
        work.decisoes_revisao.salvar(decision)
        work.commit()


def _span_rule_file(path: Path, *, enabled: bool = True) -> Path:
    payload = deepcopy(carregar_registro_conformidade_inicial().para_dict())
    registry = payload["registry"]
    rules = payload["rules"]
    assert isinstance(registry, dict) and isinstance(rules, list)
    registry["id"] = str(_id("registry"))
    registry["version"] = f"fixture-e2e-span-{'active' if enabled else 'inactive'}-1"
    rules[:] = [
        {
            "id": _RULE_ID,
            "title": _RULE_TITLE,
            "description": "Regra pública sintética para provar o fluxo configurável de vãos.",
            "scope": "REGIAO",
            "severity": "ERRO",
            "source": {
                "document": "Fixture sintética pública",
                "revision": "1",
                "item": "E2E",
                "page": 1,
                "url": None,
            },
            "when": [
                {"fact": "rede.contexto_urbano", "operator": "IGUAL", "expected": [True]},
                {
                    "fact": "cabo.tecnologia",
                    "operator": "EM",
                    "expected": ["PROTEGIDA", "ISOLADA"],
                    "quantifier": "QUALQUER",
                },
            ],
            "unless": [
                {"fact": "vao.excecao_45_60_demonstrada", "operator": "EXISTE", "expected": []}
            ],
            "must": [{"fact": "vao.comprimento_m", "operator": "MENOR_OU_IGUAL", "expected": [45]}],
            "enabled": enabled,
        }
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _span_pdf(path: Path) -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page(width=595, height=842)
        page.insert_text((110, 380), "P1")
        page.insert_text((285, 335), "52 m")
        page.insert_text((460, 380), "P2")
        page.draw_line((120, 380), (475, 380))
        document.save(path)
    finally:
        document.close()
    return path


def _protected_cable(catalog: object) -> TipoCabo:
    assert hasattr(catalog, "grupos_opcao") and hasattr(catalog, "itens_ativos")
    protected_id = next(
        option.id
        for group in catalog.grupos_opcao
        if group.chave == "tecnologia_rede"
        for option in group.opcoes
        if option.codigo == "PROTEGIDA"
    )
    return next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.CABO)
        if isinstance(item, TipoCabo) and item.tecnologia_rede_opcao_id == protected_id
    )


def _rule_row(tree: QTreeWidget, rule_id: str) -> QTreeWidgetItem:
    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        if item is not None and item.data(0, Qt.ItemDataRole.UserRole) == rule_id:
            return item
    raise AssertionError(f"Regra ausente: {rule_id}")


def _rule_ids(tree: QTreeWidget) -> tuple[str, ...]:
    return tuple(
        str(item.data(0, Qt.ItemDataRole.UserRole))
        for index in range(tree.topLevelItemCount())
        if (item := tree.topLevelItem(index)) is not None
    )


def _finding_row(tree: QTreeWidget, title: str) -> QTreeWidgetItem:
    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        if item is not None and item.text(2) == title:
            return item
    raise AssertionError(f"Achado ausente: {title}")


def _point(page_id: UUID, x: str, y: str) -> GeometriaDocumento:
    return GeometriaDocumento.ponto(
        page_id,
        PontoNormalizado(Decimal(x), Decimal(y)),
    )


def _id(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"span-compliance-e2e:{value}")
