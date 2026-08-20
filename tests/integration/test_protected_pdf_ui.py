# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

import os
from pathlib import Path
from time import monotonic, sleep

import pytest
from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QFileDialog, QInputDialog, QLineEdit, QMessageBox, QPushButton
from pytestqt.qtbot import QtBot
from tests.conftest import ApplicationFactory
from tests.pdf_fixtures import create_golden_pdf, create_protected_pdf

from zeny_project_handler.config import AppSettings
from zeny_project_handler.ui.project_panel import ProjectPanelWidget
from zeny_project_handler_contracts.enums import JobStatus

pytestmark = pytest.mark.integration


def _create_project(qtbot: QtBot, panel: ProjectPanelWidget, name: str) -> None:
    name_edit = panel.findChild(QLineEdit, "mvpProjectNameEdit")
    create_button = panel.findChild(QPushButton, "mvpCreateProjectButton")
    assert name_edit is not None and create_button is not None
    name_edit.setText(name)
    qtbot.mouseClick(create_button, Qt.MouseButton.LeftButton)


def _add_button(panel: ProjectPanelWidget) -> QPushButton:
    button = panel.findChild(QPushButton, "mvpAddPdfsButton")
    assert button is not None
    return button


def _run_button(panel: ProjectPanelWidget) -> QPushButton:
    button = panel.findChild(QPushButton, "mvpRunAnalysisButton")
    assert button is not None
    return button


def test_distinct_passwords_are_reused_in_session_and_never_leak_to_artifacts(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    secrets = {
        "protegido-a.pdf": "ZPH_STAGE16_SECRET_ALPHA_8241",
        "protegido-b.pdf": "ZPH_STAGE16_SECRET_BRAVO_9352",
    }
    first = create_protected_pdf(tmp_path / "protegido-a.pdf", secrets["protegido-a.pdf"])
    second = create_protected_pdf(tmp_path / "protegido-b.pdf", secrets["protegido-b.pdf"])
    settings = AppSettings(data_directory=tmp_path / "data", pdf_render_dpi=72)
    application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    window.show()
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    _create_project(qtbot, panel, "0000000058")
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *_args, **_kwargs: ([str(first), str(second)], "Documentos PDF (*.pdf)"),
    )
    prompts: list[tuple[str, QThread]] = []

    def password_dialog(*args: object, **_kwargs: object) -> tuple[str, bool]:
        label = str(args[2])
        assert args[3] is QLineEdit.EchoMode.Password
        prompts.append((label, QThread.currentThread()))
        password = next(value for name, value in secrets.items() if name in label)
        return password, True

    monkeypatch.setattr(QInputDialog, "getText", password_dialog)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args, **_kwargs: None)

    qtbot.mouseClick(_add_button(panel), Qt.MouseButton.LeftButton)

    assert len(window.pdf_viewer.inspecoes) == 2
    assert len(prompts) == 2
    assert all(thread == application.thread() for _label, thread in prompts)

    window.pdf_viewer.limpar()
    qtbot.mouseClick(_run_button(panel), Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel.processando, timeout=30_000)
    assert len(prompts) == 2  # o job usa o cofre efêmero do servidor, sem preflight local
    assert all(thread == application.thread() for _label, thread in prompts)

    source_status = first.stat()
    os.utime(
        first,
        ns=(source_status.st_atime_ns, source_status.st_mtime_ns + 1_000_000),
    )
    panel.abrir_selecionado()
    assert len(prompts) == 2  # a cópia gerenciada não depende mais da origem do cliente

    portability = window.portability_panel
    active_session = panel._session
    assert portability is not None and active_session is not None
    package = tmp_path / "projeto-protegido.zphproj"
    gateway = portability._gateway
    accepted = gateway.create_project_export_job(
        active_session.project_id.root,
        expected_project_version=active_session.project_version,
        idempotency_key="stage8-protected-pdf-export",
    )
    deadline = monotonic() + 15
    job_status = gateway.get_job(accepted.job_id.root)
    while job_status.status not in {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }:
        assert monotonic() < deadline
        sleep(0.02)
        job_status = gateway.get_job(accepted.job_id.root)
    assert job_status.status is JobStatus.SUCCEEDED
    result = gateway.get_job_result(accepted.job_id.root)
    assert result.download is not None
    gateway.download_to(
        result.download.download_id.root,
        package,
        progress=lambda _current, _total, _message: None,
        cancelled=lambda: False,
    )
    artifact_files = (
        *(path for path in settings.data_directory.rglob("*") if path.is_file()),
        package,
    )
    assert artifact_files
    for artifact in artifact_files:
        payload = artifact.read_bytes()
        for secret in secrets.values():
            assert secret.encode() not in payload, artifact

    window.close()
    _restarted_application, restarted = application_factory([], settings=settings)
    qtbot.addWidget(restarted)
    restarted.show()
    restarted.pdf_viewer.ir_para_folha(1)
    qtbot.waitUntil(lambda: len(prompts) >= 3, timeout=10_000)
    restarted.pdf_viewer.ir_para_folha(2)
    qtbot.waitUntil(lambda: len(prompts) >= 4, timeout=10_000)
    assert len(prompts) == 4  # novo processo servidor solicita novamente cada senha usada
    assert restarted.pdf_viewer.inspecao is not None


def test_wrong_password_limit_and_cancel_produce_partial_import_summary(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    regular = create_golden_pdf(tmp_path / "aberto.pdf")
    exhausted = create_protected_pdf(tmp_path / "sem-senha-valida.pdf", "correta")
    cancelled = create_protected_pdf(tmp_path / "cancelado.pdf", "outra")
    settings = AppSettings(data_directory=tmp_path / "data", pdf_render_dpi=72)
    _application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    _create_project(qtbot, panel, "0000000135")
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *_args, **_kwargs: (
            [str(regular), str(exhausted), str(cancelled)],
            "Documentos PDF (*.pdf)",
        ),
    )
    prompts: list[str] = []

    def password_dialog(*args: object, **_kwargs: object) -> tuple[str, bool]:
        label = str(args[2])
        assert args[3] is QLineEdit.EchoMode.Password
        prompts.append(label)
        if "cancelado.pdf" in label:
            return "", False
        return "incorreta-que-nao-deve-vazar", True

    summaries: list[str] = []
    monkeypatch.setattr(QInputDialog, "getText", password_dialog)
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _title, message: summaries.append(str(message)),
    )

    qtbot.mouseClick(_add_button(panel), Qt.MouseButton.LeftButton)

    active_session = panel._session
    assert active_session is not None
    session = panel._gateway.get_project(active_session.project_id.root).project
    assert [document.file.display_name for document in session.documents] == ["aberto.pdf"]
    assert len(prompts) == 4
    assert sum("sem-senha-valida.pdf" in prompt for prompt in prompts) == 3
    assert sum("cancelado.pdf" in prompt for prompt in prompts) == 1
    assert any(
        "1 adicionado(s), 1 cancelado(s), 1 sem senha válida e 0 com erro" in summary
        for summary in summaries
    )
    assert "incorreta-que-nao-deve-vazar" not in "".join(summaries)
