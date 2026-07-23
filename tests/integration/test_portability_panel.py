from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFileDialog, QListWidget, QMessageBox, QPushButton
from pytestqt.qtbot import QtBot
from tests.factories import complete_project

from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    SqliteBackupManager,
    SqlitePortableProjectDatabase,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.adapters.portability import ZipProjectArchive
from zeny_project_handler.application.project_portability import ServicoPortabilidadeProjeto
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.ui.portability_panel import PortabilityPanelWidget

pytestmark = pytest.mark.integration


def _service(data: Path):  # type: ignore[no-untyped-def]
    engine = create_sqlite_engine(data / "zeny-project-handler.sqlite3")
    upgrade_database(engine)
    service = ServicoPortabilidadeProjeto(
        lambda: SqlAlchemyUnitOfWork(engine),
        ZipProjectArchive(),
        SqlitePortableProjectDatabase(),
        SqliteBackupManager(),
        diretorio_dados=data,
        caminho_banco=data / "zeny-project-handler.sqlite3",
        descartar_conexoes=engine.dispose,
    )
    return engine, service


def _button(panel: PortabilityPanelWidget, name: str) -> QPushButton:
    button = panel.findChild(QPushButton, name)
    assert button is not None
    return button


def test_user_exports_imports_repairs_attachment_and_restores_backup_from_ui(
    qtbot: QtBot,
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_data = tmp_path / "source-data"
    source_engine, source_service = _service(source_data)
    project = complete_project(catalogo_inicial)
    project = replace(
        project,
        elementos=tuple(replace(element, fotos=()) for element in project.elementos),
    )
    with SqlAlchemyUnitOfWork(source_engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(project)
        work.commit()
    panel = PortabilityPanelWidget(service=source_service)
    qtbot.addWidget(panel)
    panel.show()
    project_combo = panel.findChild(QComboBox, "portabilityProjectCombo")
    element_combo = panel.findChild(QComboBox, "portabilityElementCombo")
    photo_list = panel.findChild(QListWidget, "portabilityPhotoList")
    assert project_combo is not None
    assert element_combo is not None
    assert photo_list is not None
    project_combo.setCurrentIndex(project_combo.findData(str(project.id)))
    element_combo.setCurrentIndex(1)
    photo = tmp_path / "photo.png"
    photo.write_bytes(b"\x89PNG\r\n\x1a\nportable-ui-photo")
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(photo), "Imagens (*.png)"),
    )

    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        _button(panel, "portabilityAttachPhotoButton"), Qt.MouseButton.LeftButton
    )

    assert photo_list.count() == 1
    element_id = UUID(str(element_combo.currentData()))
    stored_photo = source_service.listar_elementos(project.id)[0].fotos[0]
    managed = source_data / "project-files" / str(project.id) / stored_photo.caminho_relativo
    managed.unlink()
    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        _button(panel, "portabilityIntegrityButton"), Qt.MouseButton.LeftButton
    )
    photo_list.setCurrentRow(0)
    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        _button(panel, "portabilityLocatePhotoButton"), Qt.MouseButton.LeftButton
    )
    assert managed.is_file()
    assert source_service.verificar_integridade(project.id).problemas[0].codigo == (
        "ORIGEM_PDF_AUSENTE"
    )
    assert source_service.listar_elementos(project.id)[0].elemento_id == element_id

    package = tmp_path / "ui-project.zphproj"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(package), "Projeto Zeny (*.zphproj)"),
    )
    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        _button(panel, "portabilityExportButton"), Qt.MouseButton.LeftButton
    )
    assert package.is_file()

    backup = tmp_path / "ui-backup.zphbackup"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(backup), "Backup Zeny (*.zphbackup)"),
    )
    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        _button(panel, "portabilityBackupButton"), Qt.MouseButton.LeftButton
    )
    assert backup.is_file()

    target_data = tmp_path / "target-data"
    target_engine, target_service = _service(target_data)
    target_panel = PortabilityPanelWidget(service=target_service)
    qtbot.addWidget(target_panel)
    target_panel.show()
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(package), "Projeto Zeny (*.zphproj)"),
    )
    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        _button(target_panel, "portabilityImportButton"), Qt.MouseButton.LeftButton
    )
    target_combo = target_panel.findChild(QComboBox, "portabilityProjectCombo")
    assert target_combo is not None
    assert target_combo.findData(str(project.id)) >= 0

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(backup), "Backup Zeny (*.zphbackup)"),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )
    restored: list[bool] = []
    target_panel.data_restored.connect(lambda: restored.append(True))
    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        _button(target_panel, "portabilityRestoreButton"), Qt.MouseButton.LeftButton
    )
    assert restored, warnings
    assert target_service.listar_projetos()[0].projeto_id == project.id

    source_engine.dispose()
    target_engine.dispose()
