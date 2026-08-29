# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

import json
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import cast
from uuid import UUID

import pymupdf
import pytest
from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTreeWidget,
)
from pytestqt.qtbot import QtBot

from tests.conftest import ApplicationFactory
from tests.market_fakes import FakeVerificadorAcoesConcluidas
from tests.pdf_fixtures import create_action_requirements_pdf, create_golden_pdf
from tests.remote_gateways import DirectProjectGateway
from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer, TesseractCliOcr
from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
)
from zeny_project_handler.config import DATABASE_FILE_NAME
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.domain.market import DescricaoAcao
from zeny_project_handler.domain.project_metadata import MetadadosProjeto
from zeny_project_handler_client.config import ClientSettings
from zeny_project_handler_client.ui.project_panel import ProjectPanelWidget
from zeny_project_handler_contracts.base import ComplianceExecutionId
from zeny_project_handler_contracts.compliance import ComplianceExecutionResponse
from zeny_project_handler_contracts.enums import ComplianceStatus
from zeny_project_handler_contracts.projects import ProjectServiceCodesResponse

pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
]


def _catalog_pdf(path: Path) -> Path:
    code = carregar_catalogo_inicial().itens_ativos(CategoriaElemento.POSTE)[0].codigo
    document = pymupdf.open()
    try:
        first = document.new_page(width=240, height=160)
        first.insert_text((20, 25), "P1")
        first.insert_text((20, 40), code)
        second = document.new_page(width=240, height=160)
        second.insert_text((20, 40), "SEGUNDA FOLHA")
        document.save(path)
    finally:
        document.close()
    return path


def _application_log(*data_directories: Path) -> tuple[dict[str, object], ...]:
    payloads: list[dict[str, object]] = []
    for data_directory in data_directories:
        for file_name in ("client.jsonl", "application.jsonl"):
            log_path = data_directory / "logs" / file_name
            if not log_path.exists():
                continue
            for line in log_path.read_text(encoding="utf-8").splitlines():
                decoded = json.loads(line)
                assert isinstance(decoded, dict)
                payloads.append(cast(dict[str, object], decoded))
    return tuple(payloads)


def test_user_can_reorder_project_pdfs_and_reopen_in_reading_order(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    settings = ClientSettings(data_directory=tmp_path / "data", pdf_render_dpi=72)
    first = _catalog_pdf(tmp_path / "folha-01.pdf")
    second = create_golden_pdf(tmp_path / "folha-02.pdf")
    _application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)

    name = panel.findChild(QLineEdit, "mvpProjectNameEdit")
    create = panel.findChild(QPushButton, "mvpCreateProjectButton")
    assert name is not None and create is not None
    assert name.inputMask() == ""
    assert name.maxLength() == 10
    assert name.validator() is not None
    assert name.placeholderText() == "Número da NS"
    name.setText("0000000082")
    assert name.hasAcceptableInput()
    qtbot.mouseClick(create, Qt.MouseButton.LeftButton)
    project_combo = panel.findChild(QComboBox, "mvpProjectCombo")
    assert project_combo is not None
    project_id = project_combo.currentData()

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *_args, **_kwargs: (
            [str(first), str(second)],
            "Documentos PDF (*.pdf)",
        ),
    )
    add_pdfs = panel.findChild(QPushButton, "mvpAddPdfsButton")
    pages = panel.findChild(QListWidget, "mvpPageOrderList")
    move_down = panel.findChild(QPushButton, "mvpMovePageDownButton")
    assert add_pdfs is not None and pages is not None and move_down is not None
    qtbot.mouseClick(add_pdfs, Qt.MouseButton.LeftButton)
    assert pages.count() == 3

    pages.setCurrentRow(0)
    qtbot.mouseClick(move_down, Qt.MouseButton.LeftButton)

    assert "folha-01.pdf · página 2" in pages.item(0).text()
    assert "folha-01.pdf · página 1" in pages.item(1).text()

    _reopened_application, reopened = application_factory([], settings=settings)
    qtbot.addWidget(reopened)
    reopened_panel = reopened.project_panel
    assert isinstance(reopened_panel, ProjectPanelWidget)
    reopened_combo = reopened_panel.findChild(QComboBox, "mvpProjectCombo")
    assert reopened_combo is not None
    assert reopened_combo.currentData() == project_id
    reopened_pages = reopened_panel.findChild(QListWidget, "mvpPageOrderList")
    assert reopened_pages is not None
    assert "folha-01.pdf · página 2" in reopened_pages.item(0).text()
    assert "folha-01.pdf · página 1" in reopened_pages.item(1).text()


def test_project_service_codes_ui_is_remote_canonical_accessible_and_conflict_safe(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    settings = ClientSettings(data_directory=tmp_path / "service-codes", pdf_render_dpi=72)
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )
    application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    window.show()
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    panel_layout = panel.layout()
    assert panel_layout is not None
    group_titles: list[str] = []
    for index in range(panel_layout.count()):
        layout_item = panel_layout.itemAt(index)
        if layout_item is None:
            continue
        widget = layout_item.widget()
        if isinstance(widget, QGroupBox):
            group_titles.append(widget.title())
    assert group_titles[:3] == ["Projeto", "Serviços do projeto", "Folhas PDF"]

    service_box = panel.findChild(QGroupBox, "mvpProjectServiceCodesBox")
    service_field = panel.findChild(QLineEdit, "mvpProjectServiceCodeEdit")
    service_list = panel.findChild(QListWidget, "mvpProjectServiceCodeList")
    add_service = panel.findChild(QPushButton, "mvpAddServiceCodeButton")
    remove_services = panel.findChild(QPushButton, "mvpRemoveServiceCodesButton")
    assert service_box is not None
    assert service_field is not None
    assert service_list is not None
    assert add_service is not None
    assert remove_services is not None
    assert not service_box.isEnabled()
    assert service_list.count() == 0
    assert service_box.accessibleName() == "Serviços do projeto"
    assert service_field.accessibleName() == "Código do serviço"
    assert service_list.accessibleName() == "Códigos de serviço do projeto"
    assert add_service.accessibleName() == "Adicionar código de serviço"
    assert remove_services.accessibleName() == "Remover códigos de serviço selecionados"
    assert service_field.inputMask() == ""
    assert service_field.maxLength() == 4
    assert service_field.validator() is not None
    assert service_field.placeholderText() == "0000"

    name = panel.findChild(QLineEdit, "mvpProjectNameEdit")
    create = panel.findChild(QPushButton, "mvpCreateProjectButton")
    project_combo = panel.findChild(QComboBox, "mvpProjectCombo")
    assert name is not None and create is not None and project_combo is not None
    name.setText("0000000701")
    qtbot.mouseClick(create, Qt.MouseButton.LeftButton)
    first_project_id = UUID(str(project_combo.currentData()))
    assert service_box.isEnabled()
    initial_version = panel._session.project_version if panel._session is not None else -1

    service_field.setText("007")
    assert not service_field.hasAcceptableInput()
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    assert service_list.count() == 0
    assert panel._session is not None
    assert panel._session.project_version == initial_version

    service_field.setText("\uff11\uff12\uff13\uff14")
    assert not service_field.hasAcceptableInput()
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    assert service_list.count() == 0

    clipboard = application.clipboard()
    previous_clipboard_text = clipboard.text()
    try:
        clipboard.setText("Serviço 0007-x")
        qtbot.keyClick(
            service_field,
            Qt.Key.Key_V,
            Qt.KeyboardModifier.ControlModifier,
        )
        assert service_field.text() == "0007"
        assert service_field.hasAcceptableInput()
        service_field.selectAll()
        clipboard.clear()
        qtbot.keyClick(
            service_field,
            Qt.Key.Key_C,
            Qt.KeyboardModifier.ControlModifier,
        )
        assert clipboard.text() == "0007"
    finally:
        clipboard.setText(previous_clipboard_text)

    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    assert [service_list.item(index).text() for index in range(service_list.count())] == ["0007"]
    assert panel._session is not None
    version_after_first_add = panel._session.project_version
    service_field.setText("0007")
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    assert panel._session.project_version == version_after_first_add
    assert service_list.count() == 1
    assert any("já está cadastrado" in message for message in warnings)

    service_field.setText("9012")
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    assert [service_list.item(index).text() for index in range(service_list.count())] == [
        "0007",
        "9012",
    ]
    service_list.selectAll()
    assert remove_services.isEnabled()
    qtbot.mouseClick(remove_services, Qt.MouseButton.LeftButton)
    assert service_list.count() == 0
    assert panel._gateway.get_service_codes(first_project_id).service_codes == ()

    service_field.setText("0007")
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    name.setText("0000000702")
    qtbot.mouseClick(create, Qt.MouseButton.LeftButton)
    second_project_id = UUID(str(project_combo.currentData()))
    assert service_list.count() == 0
    service_field.setText("1234")
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)

    first_index = project_combo.findData(str(first_project_id))
    project_combo.setCurrentIndex(first_index)
    panel.abrir_selecionado()
    assert [service_list.item(index).text() for index in range(service_list.count())] == ["0007"]
    second_index = project_combo.findData(str(second_project_id))
    project_combo.setCurrentIndex(second_index)
    panel.abrir_selecionado()
    assert [service_list.item(index).text() for index in range(service_list.count())] == ["1234"]

    assert panel._session is not None
    external = panel._gateway.replace_service_codes(
        second_project_id,
        ("3456", "1234"),
        expected_project_version=panel._session.project_version,
    )
    service_field.setText("9999")
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    assert [service_list.item(index).text() for index in range(service_list.count())] == [
        "1234",
        "3456",
    ]
    assert panel._session is not None
    assert panel._session.project_version == external.project_version
    assert "9999" not in panel._gateway.get_service_codes(second_project_id).service_codes
    assert any("outra janela" in message for message in warnings)

    panel.set_global_operation(object())
    assert not service_box.isEnabled()
    panel.set_global_operation(None)
    assert service_box.isEnabled()
    fake_analysis_thread = QThread()
    panel._thread = fake_analysis_thread
    panel._apply_operation_state()
    assert not service_box.isEnabled()
    panel._thread = None
    panel._apply_operation_state()
    fake_analysis_thread.deleteLater()
    assert service_box.isEnabled()
    assert all("service" not in key.casefold() for key in panel._settings.allKeys())

    _reopened_application, reopened = application_factory([], settings=settings)
    qtbot.addWidget(reopened)
    reopened_panel = reopened.project_panel
    assert isinstance(reopened_panel, ProjectPanelWidget)
    reopened_combo = reopened_panel.findChild(QComboBox, "mvpProjectCombo")
    reopened_services = reopened_panel.findChild(QListWidget, "mvpProjectServiceCodeList")
    assert reopened_combo is not None and reopened_services is not None
    assert UUID(str(reopened_combo.currentData())) == second_project_id
    assert [reopened_services.item(index).text() for index in range(reopened_services.count())] == [
        "1234",
        "3456",
    ]
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    reopened_delete = reopened_panel.findChild(QPushButton, "mvpDeleteProjectButton")
    reopened_service_box = reopened_panel.findChild(QGroupBox, "mvpProjectServiceCodesBox")
    assert reopened_delete is not None and reopened_service_box is not None
    qtbot.mouseClick(reopened_delete, Qt.MouseButton.LeftButton)
    assert reopened_combo.findData(str(second_project_id)) < 0
    assert not reopened_service_box.isEnabled()
    assert reopened_services.count() == 0


def test_environmental_actions_full_client_matrix_uses_current_service_codes(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    settings = ClientSettings(data_directory=tmp_path / "actions-flow", pdf_render_dpi=72)
    catalog_code = carregar_catalogo_inicial().itens_ativos(CategoriaElemento.POSTE)[0].codigo
    source = create_action_requirements_pdf(tmp_path / "acoes-sinteticas.pdf", catalog_code)
    verifier = FakeVerificadorAcoesConcluidas(resultado=False)
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )
    _application, window = application_factory(
        [],
        settings=settings,
        action_verifier=verifier,
    )
    qtbot.addWidget(window)
    window.show()
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)

    name = panel.findChild(QLineEdit, "mvpProjectNameEdit")
    create = panel.findChild(QPushButton, "mvpCreateProjectButton")
    project_combo = panel.findChild(QComboBox, "mvpProjectCombo")
    service_field = panel.findChild(QLineEdit, "mvpProjectServiceCodeEdit")
    service_list = panel.findChild(QListWidget, "mvpProjectServiceCodeList")
    add_service = panel.findChild(QPushButton, "mvpAddServiceCodeButton")
    assert name is not None and create is not None and project_combo is not None
    assert service_field is not None and service_list is not None and add_service is not None
    name.setText("0000007401")
    qtbot.mouseClick(create, Qt.MouseButton.LeftButton)
    project_id = UUID(str(project_combo.currentData()))
    for code in ("0007", "9012"):
        service_field.setText(code)
        qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)

    assert isinstance(panel._gateway, DirectProjectGateway)
    assert panel._session is not None
    second_client = DirectProjectGateway(panel._gateway._runtime)
    server_wins = second_client.replace_service_codes(
        project_id,
        ("1234", "0007"),
        expected_project_version=panel._session.project_version,
    )
    assert isinstance(server_wins, ProjectServiceCodesResponse)
    service_field.setText("9999")
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    current_codes = tuple(service_list.item(index).text() for index in range(service_list.count()))
    assert current_codes == ("0007", "1234")
    assert any("outra janela" in message for message in warnings)
    canonical = panel._gateway.get_service_codes(project_id)
    assert isinstance(canonical, ProjectServiceCodesResponse)
    assert canonical.service_codes == current_codes
    assert canonical.project_version == server_wins.project_version

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *_args, **_kwargs: ([str(source)], "Documentos PDF (*.pdf)"),
    )
    add_pdfs = panel.findChild(QPushButton, "mvpAddPdfsButton")
    run = panel.findChild(QPushButton, "mvpRunAnalysisButton")
    assert add_pdfs is not None and run is not None
    qtbot.mouseClick(add_pdfs, Qt.MouseButton.LeftButton)
    assert window.pdf_viewer.inspecao is not None
    qtbot.mouseClick(run, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel.processando, timeout=30_000)

    documentation = window.documentation_panel
    assert documentation is not None
    findings_tree = documentation.findChild(QTreeWidget, "complianceFindingsTree")
    reanalyze = documentation.findChild(QPushButton, "complianceAnalyzeButton")
    assert findings_tree is not None and reanalyze is not None
    action_rules = {
        "bi.acoes.impacto-ambiental": (
            "IMPACTO AMBIENTAL PENDENTE",
            DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL,
        ),
        "bi.acoes.falta-servidao": (
            "FALTA SERVIDÃO PENDENTE",
            DescricaoAcao.FALTA_SERVIDAO,
        ),
    }

    def assert_action_projection(
        impact_completed: bool,
        servitude_completed: bool,
    ) -> ComplianceExecutionResponse:
        result = documentation._result
        assert isinstance(result, ComplianceExecutionResponse)
        by_rule = {item.rule_id: item for item in result.findings if item.rule_id in action_rules}
        assert set(by_rule) == set(action_rules)
        completed_by_rule = {
            "bi.acoes.impacto-ambiental": impact_completed,
            "bi.acoes.falta-servidao": servitude_completed,
        }
        visible_action_titles = {
            item.text(2)
            for index in range(findings_tree.topLevelItemCount())
            if (item := findings_tree.topLevelItem(index)) is not None
            and item.text(2) in {value[0] for value in action_rules.values()}
        }
        assert visible_action_titles == {
            action_rules[rule_id][0]
            for rule_id, completed in completed_by_rule.items()
            if not completed
        }
        for rule_id, finding in by_rule.items():
            title, _action = action_rules[rule_id]
            assert finding.title == title
            expected_status = (
                ComplianceStatus.COMPLIANT
                if completed_by_rule[rule_id]
                else ComplianceStatus.DIVERGENCE
            )
            assert finding.status is expected_status
            assert bool(finding.callout) is not completed_by_rule[rule_id]
            assert finding.evidence
            if finding.callout is None:
                continue
            assert finding.navigation is not None
            assert finding.callout.navigation.page_id == finding.navigation.page_id
            assert finding.callout.finding_id == finding.finding_id
        impact_callout = by_rule["bi.acoes.impacto-ambiental"].callout
        servitude_callout = by_rule["bi.acoes.falta-servidao"].callout
        if impact_callout is not None:
            assert float(impact_callout.anchor.y) >= 0.76
        if servitude_callout is not None:
            assert float(servitude_callout.anchor.y) < 0.76
        divergent = next((item for item in by_rule.values() if item.callout is not None), None)
        callout = divergent.callout if divergent is not None else None
        if divergent is not None and callout is not None:
            row = next(
                item
                for index in range(findings_tree.topLevelItemCount())
                if (item := findings_tree.topLevelItem(index)) is not None
                and item.text(2) == divergent.title
            )
            findings_tree.setCurrentItem(row)
            qtbot.waitUntil(
                lambda: (
                    window.pdf_viewer._selected_compliance_callout_id
                    == str(callout.callout_id.root)
                ),
                timeout=10_000,
            )
            assert window.pdf_viewer.folha_atual == 1
            assert str(callout.callout_id.root) in window.pdf_viewer.view._callout_items
        return result

    def result_changed(expected_id: ComplianceExecutionId) -> bool:
        result = documentation._result
        return (
            documentation._compliance_job_id is None
            and result is not None
            and result.execution.execution_id != expected_id
        )

    expected_calls = [
        ("0000007401", current_codes, action_rules[rule_id][1]) for rule_id in action_rules
    ]
    assert verifier.consultas == expected_calls
    previous = assert_action_projection(False, False)
    matrix = ((True, False), (False, True), (True, True))
    for impact_completed, servitude_completed in matrix:
        verifier.resultados = {
            DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL: impact_completed,
            DescricaoAcao.FALTA_SERVIDAO: servitude_completed,
        }
        before_calls = len(verifier.consultas)
        previous_id = previous.execution.execution_id
        qtbot.mouseClick(reanalyze, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            partial(result_changed, previous_id),
            timeout=30_000,
        )
        assert verifier.consultas[before_calls:] == expected_calls
        previous = assert_action_projection(impact_completed, servitude_completed)

    _reopened_application, reopened = application_factory(
        [],
        settings=settings,
        action_verifier=verifier,
    )
    qtbot.addWidget(reopened)
    reopened.show()
    reopened_panel = reopened.project_panel
    assert isinstance(reopened_panel, ProjectPanelWidget)
    reopened_services = reopened_panel.findChild(
        QListWidget,
        "mvpProjectServiceCodeList",
    )
    assert reopened_services is not None
    assert (
        tuple(reopened_services.item(index).text() for index in range(reopened_services.count()))
        == current_codes
    )
    reopened_documentation = reopened.documentation_panel
    assert reopened_documentation is not None
    reopened_documentation.abrir_projeto(project_id)
    assert reopened_documentation._result == previous


def test_user_can_create_import_analyze_review_and_reopen_from_ui(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    settings = ClientSettings(data_directory=tmp_path / "data", pdf_render_dpi=72)
    source = _catalog_pdf(tmp_path / "projeto.pdf")
    _application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    window.show()
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)

    name = panel.findChild(QLineEdit, "mvpProjectNameEdit")
    create = panel.findChild(QPushButton, "mvpCreateProjectButton")
    assert name is not None and create is not None
    name.setText("0000000139")
    qtbot.mouseClick(create, Qt.MouseButton.LeftButton)
    project_combo = panel.findChild(QComboBox, "mvpProjectCombo")
    assert project_combo is not None
    project_id = project_combo.currentData()
    assert project_id is not None

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *_args, **_kwargs: ([str(source)], "Documentos PDF (*.pdf)"),
    )
    add_pdfs = panel.findChild(QPushButton, "mvpAddPdfsButton")
    assert add_pdfs is not None
    assert panel.findChild(QPushButton, "mvpMergePdfsButton") is None
    qtbot.mouseClick(add_pdfs, Qt.MouseButton.LeftButton)
    assert window.pdf_viewer.inspecao is not None

    assert window.review_panel is not None
    server_database = (
        settings.data_directory.parent
        / f"{settings.data_directory.name}-server"
        / DATABASE_FILE_NAME
    )
    persistence = create_sqlite_engine(server_database)
    with SqlAlchemyUnitOfWork(persistence) as work:
        project = work.projetos.obter(UUID(str(project_id)))
        assert project is not None
        work.projetos.salvar(
            replace(project, metadados=MetadadosProjeto(tipo_servico="Rede urbana"))
        )
        work.commit()
    persistence.dispose()
    panel.abrir_selecionado()

    run = panel.findChild(QPushButton, "mvpRunAnalysisButton")
    assert run is not None
    qtbot.mouseClick(run, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel.processando, timeout=30_000)

    server_data_directory = (
        settings.data_directory.parent / f"{settings.data_directory.name}-server"
    )
    log_payloads = _application_log(settings.data_directory, server_data_directory)
    for operation in (
        "client.bootstrap",
        "pdf.viewer.open",
        "pdf.viewer.render",
    ):
        records = [item for item in log_payloads if item.get("operation") == operation]
        assert {item.get("status") for item in records} >= {
            "started",
            "succeeded",
        }, operation
    serialized_log = json.dumps(log_payloads, ensure_ascii=False)
    assert str(source.resolve()) not in serialized_log
    assert "password" not in serialized_log.casefold()
    assert "senha" not in serialized_log.casefold()

    review_panel = window.review_panel
    assert review_panel is not None
    review_project = review_panel.findChild(QComboBox, "reviewProjectCombo")
    results = review_panel.findChild(QTreeWidget, "analysisRelationshipTree")
    assert review_project is not None and results is not None
    assert review_project.currentData() == project_id
    assert results.topLevelItemCount() >= 1

    documentation_panel = window.documentation_panel
    assert documentation_panel is not None
    compliance_tree = documentation_panel.findChild(QTreeWidget, "complianceFindingsTree")
    compliance_status = documentation_panel.findChild(QLabel, "complianceExecutionStatusLabel")
    reapply = documentation_panel.findChild(QPushButton, "complianceAnalyzeButton")
    assert compliance_tree is not None
    assert compliance_status is not None
    assert reapply is not None
    assert compliance_tree.topLevelItemCount() >= 1
    divergence = compliance_tree.topLevelItem(0)
    assert divergence is not None
    assert divergence.text(0) == "Divergência"
    assert "ausente" in divergence.text(3).casefold()
    assert "presente" in divergence.text(4).casefold()
    assert "Resultado atual" in compliance_status.text()

    def forbidden_call(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Reaplicar conformidade não pode executar extração ou OCR")

    monkeypatch.setattr(PyMuPdfDocumentAnalyzer, "analisar", forbidden_call)
    monkeypatch.setattr(TesseractCliOcr, "reconhecer", forbidden_call)
    previous_count = compliance_tree.topLevelItemCount()
    qtbot.mouseClick(reapply, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: "Resultado atual" in compliance_status.text(), timeout=30_000)
    assert compliance_tree.topLevelItemCount() == previous_count
    assert "Resultado atual" in compliance_status.text()

    window.pdf_viewer.ir_para_folha(2)
    assert window.pdf_viewer.folha_atual == 2
    _second_application, reopened = application_factory([], settings=settings)
    qtbot.addWidget(reopened)
    reopened.show()
    reopened_panel = reopened.project_panel
    assert isinstance(reopened_panel, ProjectPanelWidget)
    reopened_combo = reopened_panel.findChild(QComboBox, "mvpProjectCombo")
    assert reopened_combo is not None
    assert reopened_combo.currentData() == project_id
    assert reopened.pdf_viewer.folha_atual == 2
    reopened_documentation = reopened.documentation_panel
    assert reopened_documentation is not None
    reopened_findings = reopened_documentation.findChild(QTreeWidget, "complianceFindingsTree")
    assert reopened_findings is not None
    assert reopened_findings.topLevelItemCount() == previous_count

    confirmations: list[str] = []

    def confirm(*args: object, **_kwargs: object) -> QMessageBox.StandardButton:
        confirmations.extend(item for item in args if isinstance(item, str))
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)
    document_list = reopened_panel.findChild(QListWidget, "mvpPageOrderList")
    remove_pdf = reopened_panel.findChild(QPushButton, "mvpRemovePdfsButton")
    assert document_list is not None and remove_pdf is not None
    document_list.item(0).setSelected(True)
    qtbot.mouseClick(remove_pdf, Qt.MouseButton.LeftButton)
    assert document_list.count() == 0
    assert reopened.pdf_viewer.inspecao is None
    assert any(
        "Análises, propostas" in message
        and "Cópias mantidas fora do servidor serão preservadas" in message
        for message in confirmations
    )

    delete_project = reopened_panel.findChild(QPushButton, "mvpDeleteProjectButton")
    assert delete_project is not None
    qtbot.mouseClick(delete_project, Qt.MouseButton.LeftButton)
    assert reopened_combo.findData(project_id) < 0
    assert any(
        "arquivos gerenciados no servidor" in message
        and "Arquivos já baixados ou mantidos fora do servidor" in message
        for message in confirmations
    )
