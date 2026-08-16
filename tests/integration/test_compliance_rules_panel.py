from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
)
from pytestqt.qtbot import QtBot
from sqlalchemy import Engine

from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.compliance_analysis import ExecutarAnaliseConformidade
from zeny_project_handler.application.compliance_registry import (
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler.ui.documentation_panel import DocumentationPanelWidget
from zeny_project_handler.ui.pdf_viewer import PdfViewerWidget


class _ViewerStub(QObject):
    compliance_callout_selected = Signal(str)

    def definir_callouts_conformidade(self, _callouts: tuple[object, ...]) -> None:
        pass


pytestmark = pytest.mark.integration


def _synthetic_file(path: Path) -> Path:
    payload = deepcopy(carregar_registro_conformidade_inicial().para_dict())
    registry = payload["registry"]
    rules = payload["rules"]
    assert isinstance(registry, dict)
    assert isinstance(rules, list)
    registry["id"] = str(uuid4())
    registry["version"] = "ui-synthetic-1"
    rules[:] = [
        {
            "id": "fixture.ui.circuito",
            "title": "Circuito obrigatório pela interface",
            "description": "Regra sintética pública para o teste Qt.",
            "scope": "PROJETO",
            "severity": "ALERTA",
            "source": {
                "document": "Fixture pública",
                "revision": "1",
                "item": "1",
                "page": 1,
                "url": None,
            },
            "when": [],
            "unless": [],
            "must": [
                {
                    "fact": "projeto.circuito",
                    "operator": "EXISTE",
                    "expected": [],
                }
            ],
            "enabled": True,
        }
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _panel(
    qtbot: QtBot,
    database: Path,
    data: Path,
) -> tuple[DocumentationPanelWidget, ServicoRegistroRegrasConformidade, Engine]:
    engine = create_sqlite_engine(database)
    upgrade_database(engine)

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    registry_service = ServicoRegistroRegrasConformidade(
        unit_of_work,
        diretorio_dados=data,
    )
    registry_service.inicializar(carregar_registro_conformidade_inicial())
    review_service = ServicoRevisaoHumana(unit_of_work)
    panel = DocumentationPanelWidget(
        service=review_service,
        analysis_service=ExecutarAnaliseConformidade(
            unit_of_work,
            review_service.carregar_sessao_semantica,
        ),
        registry_service=registry_service,
        viewer=cast(PdfViewerWidget, _ViewerStub()),
    )
    qtbot.addWidget(panel)
    panel.show()
    return panel, registry_service, engine


def _row(tree: QTreeWidget, rule_id: str) -> QTreeWidgetItem:
    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        if item is not None and item.data(0, Qt.ItemDataRole.UserRole) == rule_id:
            return item
    raise AssertionError(f"Regra não encontrada: {rule_id}")


def _rule_ids(tree: QTreeWidget) -> tuple[str, ...]:
    result: list[str] = []
    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        if item is not None:
            result.append(str(item.data(0, Qt.ItemDataRole.UserRole)))
    return tuple(result)


def test_rule_ids_stay_internal_and_details_use_the_fact_catalog(
    qtbot: QtBot, tmp_path: Path
) -> None:
    panel, _service, engine = _panel(qtbot, tmp_path / "details.sqlite3", tmp_path / "data")
    tree = panel.findChild(QTreeWidget, "complianceRulesTree")
    details = panel.findChild(QTextBrowser, "complianceRuleDetails")
    assert tree is not None and details is not None
    assert tuple(tree.headerItem().text(index) for index in range(tree.columnCount())) == (
        "Número",
        "Estado",
        "Título",
        "Escopo",
        "Provedor",
    )
    cases = (
        ("pacote.documentacao.gd", "projeto.documentacao_gd_identificada"),
        ("nd31.transformador.chave-fusivel", "regiao.chave_fusivel_presente"),
    )

    for rule_id, technical_key in cases:
        row = _row(tree, rule_id)
        assert row.data(0, Qt.ItemDataRole.UserRole) == rule_id
        assert all(rule_id not in row.text(column) for column in range(tree.columnCount()))
        tree.setCurrentItem(row)
        rendered = details.toPlainText()
        assert "Aplicável quando:" in rendered
        assert "Exceto quando:" in rendered
        assert "Deve atender:" in rendered
        assert "igual a Sim" in rendered
        assert rule_id not in rendered
        assert technical_key not in rendered
        assert "when:" not in rendered
        assert "unless:" not in rendered
        assert "must:" not in rendered
        assert "ID:" not in rendered

    panel.close()
    engine.dispose()


def test_rules_view_only_imports_exports_and_survives_restart(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "rules-panel.sqlite3"
    data = tmp_path / "data"
    imported_file = _synthetic_file(tmp_path / "import.json")
    exported_file = tmp_path / "export.json"
    confirmations: list[str] = []

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(imported_file), ""),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(exported_file), ""),
    )

    def confirm(_parent: object, _title: str, message: str, *_args: object) -> object:
        confirmations.append(message)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args, **_kwargs: None)

    panel, service, engine = _panel(qtbot, database, data)
    tree = panel.findChild(QTreeWidget, "complianceRulesTree")
    import_button = panel.findChild(QPushButton, "complianceRulesImportButton")
    toggle_button = panel.findChild(QPushButton, "complianceRulesToggleButton")
    remove_button = panel.findChild(QPushButton, "complianceRulesRemoveButton")
    export_button = panel.findChild(QPushButton, "complianceRulesExportButton")
    assert tree is not None
    assert import_button is not None
    assert toggle_button is None
    assert remove_button is None
    assert export_button is not None

    qtbot.mouseClick(import_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]
    assert _row(tree, "fixture.ui.circuito").text(1) == "Ativa"
    assert "nd31.desenho.numero-projeto" in _rule_ids(tree)

    stable_number = {item.regra_id: item.numero for item in service.listar_numeros()}[
        "fixture.ui.circuito"
    ]
    qtbot.mouseClick(export_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]

    exported = json.loads(exported_file.read_text(encoding="utf-8"))
    exported_ids = {item["id"] for item in exported["rules"]}
    assert "fixture.ui.circuito" in exported_ids
    assert "nd31.desenho.numero-projeto" in exported_ids
    imported_rule = next(item for item in exported["rules"] if item["id"] == "fixture.ui.circuito")
    assert imported_rule["must"][0]["fact"] == "projeto.circuito"
    assert "IDs existentes substituídos: 0" in confirmations[0]
    assert "IDs atuais omitidos e preservados: 39" in confirmations[0]
    assert f"Regra {stable_number}" in service.caminho_catalogo.read_text(encoding="utf-8")

    panel.close()
    engine.dispose()
    reopened, reopened_service, reopened_engine = _panel(qtbot, database, data)
    reopened_tree = reopened.findChild(QTreeWidget, "complianceRulesTree")
    assert reopened_tree is not None
    assert "fixture.ui.circuito" in _rule_ids(reopened_tree)
    assert len(reopened_service.listar_historico()) == 2
    reopened_engine.dispose()
