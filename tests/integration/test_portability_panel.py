from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFileDialog, QMessageBox, QPushButton
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
from zeny_project_handler.domain.portability import EstadoIntegridadePacote
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
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


def _project_with_pdf_source(tmp_path: Path, catalog: CatalogoTecnico):  # type: ignore[no-untyped-def]
    source_path = tmp_path / "origem-privada-nao-exibir.pdf"
    source_path.write_bytes(b"%PDF-1.7\nconteudo do teste")
    payload = source_path.read_bytes()
    base = complete_project(catalog)
    document = replace(
        base.documentos[0],
        sha256=sha256(payload).hexdigest(),
        tamanho_bytes=len(payload),
    )
    project = replace(
        base,
        documentos=(document,),
        elementos=tuple(replace(element, fotos=()) for element in base.elementos),
    )
    stat_result = source_path.stat()
    source = ReferenciaFontePdf(
        documento_id=document.id,
        projeto_id=project.id,
        caminho_canonico=source_path.resolve(),
        sha256=document.sha256,
        tamanho_bytes=len(payload),
        modificado_em_ns=stat_result.st_mtime_ns,
    )
    return project, source


def test_user_exports_imports_and_restores_backup_from_ui(
    qtbot: QtBot,
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_data = tmp_path / "source-data"
    source_engine, source_service = _service(source_data)
    project, pdf_source = _project_with_pdf_source(tmp_path, catalogo_inicial)
    with SqlAlchemyUnitOfWork(source_engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(project)
        work.fontes_pdf.salvar(pdf_source)
        work.commit()
    panel = PortabilityPanelWidget(service=source_service)
    qtbot.addWidget(panel)
    panel.show()
    project_combo = panel.findChild(QComboBox, "portabilityProjectCombo")
    assert project_combo is not None
    project_combo.setCurrentIndex(project_combo.findData(str(project.id)))
    assert panel.findChild(QPushButton, "portabilityAttachPhotoButton") is None
    assert panel.findChild(QPushButton, "portabilityIntegrityButton") is None
    assert panel.findChild(QPushButton, "portabilityLocatePdfButton") is None

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


def test_user_cancels_degraded_backup_without_package_or_temporaries(
    qtbot: QtBot,
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = tmp_path / "cancel-data"
    engine, service = _service(data)
    project, pdf_source = _project_with_pdf_source(tmp_path, catalogo_inicial)
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(project)
        work.fontes_pdf.salvar(pdf_source)
        work.commit()
    pdf_source.caminho_canonico.unlink()
    panel = PortabilityPanelWidget(service=service)
    qtbot.addWidget(panel)
    destination = tmp_path / "cancelled.zphbackup"
    destination.write_bytes(b"backup-anterior")
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "Backup Zeny (*.zphbackup)"),
    )
    questions: list[tuple[str, str]] = []

    def reject_backup(_parent, title, message, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        questions.append((str(title), str(message)))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", reject_backup)
    statuses: list[str] = []
    panel.status_changed.connect(statuses.append)

    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        _button(panel, "portabilityBackupButton"), Qt.MouseButton.LeftButton
    )

    assert destination.read_bytes() == b"backup-anterior"
    assert not tuple(tmp_path.glob(".z-*"))
    assert len(questions) == 1
    message = questions[0][1]
    assert str(project.documentos[0].id)[:8] in message
    assert project.documentos[0].nome_arquivo not in message
    assert str(pdf_source.caminho_canonico) not in message
    assert "ausente" in message
    assert not any("criado" in item.casefold() for item in statuses)
    engine.dispose()


@pytest.mark.parametrize(
    ("problem", "expected_code", "expected_label"),
    [
        ("missing", "PDF_AUSENTE", "ausente"),
        ("changed", "PDF_ADULTERADO", "alterado desde a importação"),
        ("unreadable", "PDF_ILEGIVEL", "ilegível"),
    ],
)
def test_user_explicitly_confirms_different_degraded_backup_problems(
    qtbot: QtBot,
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
    problem: str,
    expected_code: str,
    expected_label: str,
) -> None:
    data = tmp_path / f"confirmed-{problem}-data"
    engine, service = _service(data)
    project, pdf_source = _project_with_pdf_source(tmp_path, catalogo_inicial)
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(project)
        work.fontes_pdf.salvar(pdf_source)
        work.commit()
    if problem == "missing":
        pdf_source.caminho_canonico.unlink()
    elif problem == "changed":
        pdf_source.caminho_canonico.write_bytes(
            pdf_source.caminho_canonico.read_bytes() + b"alterado"
        )
    else:
        pdf_source.caminho_canonico.write_bytes(b"arquivo sem assinatura PDF")

    panel = PortabilityPanelWidget(service=service)
    qtbot.addWidget(panel)
    destination = tmp_path / f"confirmed-{problem}.zphbackup"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "Backup Zeny (*.zphbackup)"),
    )
    questions: list[str] = []

    def accept_backup(_parent, _title, message, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        questions.append(str(message))
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", accept_backup)
    statuses: list[str] = []
    panel.status_changed.connect(statuses.append)

    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        _button(panel, "portabilityBackupButton"), Qt.MouseButton.LeftButton
    )

    assert destination.is_file()
    assert len(questions) == 1
    assert expected_label in questions[0]
    assert project.documentos[0].nome_arquivo not in questions[0]
    extracted = ZipProjectArchive().extrair_validado(destination, tmp_path / f"extracted-{problem}")
    assert extracted.integridade.integro
    assert extracted.manifesto.estado_integridade is EstadoIntegridadePacote.DEGRADADO
    assert [item.codigo for item in extracted.manifesto.omissoes] == [expected_code]
    assert any("criado com ressalvas" in item.casefold() for item in statuses)
    assert not any("íntegro" in item.casefold() for item in statuses)
    engine.dispose()


def test_cancelled_portability_dialogs_are_correlated_without_running_service(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    app_log_capture: pytest.LogCaptureFixture,
) -> None:
    engine, service = _service(tmp_path / "data")
    panel = PortabilityPanelWidget(service=service)
    qtbot.addWidget(panel)
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: ("", ""),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: ("", ""),
    )

    panel.criar_backup()
    panel.importar_projeto()
    panel.restaurar_backup()

    for operation in (
        "portability.backup.selection",
        "portability.import.selection",
        "portability.restore.selection",
    ):
        records = [
            record
            for record in app_log_capture.records
            if getattr(record, "operation", None) == operation
        ]
        assert [getattr(record, "status", None) for record in records] == [
            "started",
            "cancelled",
        ]
        assert len({getattr(record, "correlation_id", None) for record in records}) == 1
    engine.dispose()
