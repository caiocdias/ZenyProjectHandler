# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from socket import create_server
from threading import Event, Thread
from time import monotonic
from uuid import UUID, uuid4

import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox, QPushButton
from pytestqt.qtbot import QtBot
from starlette.requests import Request
from starlette.responses import Response
from tests.market_fakes import FakeClassificadorMercado, FakeVerificadorAcoesConcluidas
from tests.pdf_fixtures import create_action_requirements_pdf, create_golden_pdf
from tests.remote_gateways import DirectProjectGateway
from uvicorn import Config, Server

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.persistence import SqlAlchemyUnitOfWork
from zeny_project_handler.application.errors import FluxoMvpCanceladoError
from zeny_project_handler.application.mvp_workflow import ResultadoFluxoMvp
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.domain.market import DescricaoAcao
from zeny_project_handler_client.bootstrap import create_application
from zeny_project_handler_client.config import ClientSettings
from zeny_project_handler_client.ui.documentation_gateway import HttpDocumentationGateway
from zeny_project_handler_client.ui.main_window import MainWindow
from zeny_project_handler_client.ui.pdf_gateway import HttpPdfViewerGateway
from zeny_project_handler_client.ui.portability_gateway import HttpPortabilityGateway
from zeny_project_handler_client.ui.project_gateway import (
    HttpProjectGateway,
    ProjectGateway,
    ProjectGatewayError,
)
from zeny_project_handler_client.ui.review_gateway import HttpReviewGateway
from zeny_project_handler_contracts.enums import (
    AnalysisExecutionState,
    JobStatus,
    UploadState,
)
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.jobs import JobStatusResponse
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.composition import ServerRuntime, compose_server_runtime
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.job_manager import JobManager

PASSWORD = "senha segura do servidor HTTP de projetos"


@dataclass
class CancelOnlyRunner:
    started: Event
    calls: int = 0

    def __call__(
        self,
        project_id: UUID,
        progress: Callable[[int, int, str], None],
        cancelled: Callable[[], bool],
    ) -> ResultadoFluxoMvp:
        del project_id
        self.calls += 1
        progress(1, 4, "Extraindo evidências")
        progress(3, 4, "Interpretando evidências")
        progress(2, 4, "Atualização atrasada")
        self.started.set()
        tick = Event()
        while not cancelled():
            tick.wait(0.01)
        raise FluxoMvpCanceladoError("Cancelada em ponto seguro")


@pytest.mark.integration
def test_http_and_direct_search_filter_globally_before_pagination(tmp_path: Path) -> None:
    settings = ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=tmp_path / "server-data",
    )
    runtime = compose_server_runtime(settings, market_classifier=FakeClassificadorMercado())
    assert runtime.project_api is not None
    seed = runtime.project_api.create_project("9000009999", "search-seed")
    expected_ids = [UUID(int=index) for index in (1, 2, 3)]
    with SqlAlchemyUnitOfWork(runtime.core.engine) as work:
        project = work.projetos.obter(seed.project.project_id.root)
        assert project is not None
        for index in range(201):
            work.projetos.salvar(
                replace(
                    project,
                    id=uuid4(),
                    nome=f"900000{index:04d}",
                    criado_em=project.criado_em + timedelta(microseconds=index + 1),
                )
            )
        # Inserção fora da ordem de ID e data empatada exercitam o desempate.
        for index in (3, 1, 2):
            work.projetos.salvar(
                replace(
                    project,
                    id=UUID(int=index),
                    nome=f"00123400{index:02d}",
                    criado_em=project.criado_em + timedelta(seconds=1),
                )
            )
        work.commit()

    direct = DirectProjectGateway(runtime)
    application = create_app(settings, runtime_factory=lambda _settings: runtime)
    with _running_server(application) as base_url:
        http = HttpProjectGateway(base_url, PASSWORD)
        gateways: tuple[ProjectGateway, ...] = (direct, http)
        for gateway in gateways:
            first_page = gateway.list_projects()
            assert first_page.page.total == 205
            assert len(first_page.items) == 200
            assert not set(expected_ids) & {item.project_id.root for item in first_page.items}
            found_ids: list[UUID] = []
            for offset in range(3):
                found = gateway.search_projects("123400", limit=1, offset=offset)
                assert found.page.total == 3
                assert found.page.limit == 1
                assert found.page.offset == offset
                found_ids.extend(item.project_id.root for item in found.items)
            assert found_ids == expected_ids
            past_end = gateway.search_projects("123400", limit=1, offset=3)
            assert past_end.items == ()
            assert past_end.page.total == 3
            empty = gateway.search_projects("888")
            assert empty.items == ()
            assert empty.page.total == 0
            for query in ("0", "0012340001", "123400"):
                assert gateway.search_projects(query) == direct.search_projects(query)
            for query, limit, offset in (
                ("", 200, 0),
                ("\uff11\uff12", 200, 0),
                ("1\n", 200, 0),
                ("12345678901", 200, 0),
                ("%", 200, 0),
                ("0", 0, 0),
                ("0", 201, 0),
                ("0", 1, -1),
            ):
                with pytest.raises(ProjectGatewayError) as invalid:
                    gateway.search_projects(query, limit=limit, offset=offset)
                assert invalid.value.code is ErrorCode.VALIDATION_ERROR
                assert invalid.value.status_code == 422

        with pytest.raises(ProjectGatewayError) as unauthorized:
            HttpProjectGateway(base_url, "incorrect").search_projects("0")
        assert unauthorized.value.code is ErrorCode.AUTHENTICATION_FAILED
        assert unauthorized.value.status_code == 401


@pytest.mark.integration
@pytest.mark.parametrize(
    "failure", ("missing-route", "resource-envelope", "legacy-dynamic", "server")
)
def test_http_search_errors_never_become_absence(failure: str) -> None:
    application = FastAPI()
    expected_status = 404
    expected_code = ErrorCode.INTERNAL_ERROR
    if failure != "missing-route":
        expected_status = (
            500 if failure == "server" else 422 if failure == "legacy-dynamic" else 404
        )
        expected_code = (
            ErrorCode.INTERNAL_ERROR
            if failure == "server"
            else ErrorCode.VALIDATION_ERROR
            if failure == "legacy-dynamic"
            else ErrorCode.RESOURCE_NOT_FOUND
        )

        @application.get("/api/v1/projects/search")
        def unavailable() -> JSONResponse:
            return JSONResponse(
                status_code=expected_status,
                content={
                    "code": expected_code.value,
                    "message": "Pesquisa indisponível",
                    "correlation_id": str(UUID(int=1)),
                    "details": None,
                },
            )

    with _running_server(application) as base_url:
        with pytest.raises(ProjectGatewayError) as error:
            HttpProjectGateway(base_url, PASSWORD).search_projects("001")
        assert error.value.status_code == expected_status
        assert error.value.code is expected_code


@pytest.mark.integration
def test_http_and_direct_gateways_resolve_only_exact_unique_service_notes(tmp_path: Path) -> None:
    settings = ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=tmp_path / "server-data",
    )
    runtime = compose_server_runtime(settings, market_classifier=FakeClassificadorMercado())
    assert runtime.project_api is not None
    unique = runtime.project_api.create_project("0000000011", "gateway-unique")
    ambiguous = runtime.project_api.create_project("0000000012", "gateway-ambiguous")
    with SqlAlchemyUnitOfWork(runtime.core.engine) as work:
        project = work.projetos.obter(ambiguous.project.project_id.root)
        assert project is not None
        work.projetos.salvar(replace(project, id=uuid4(), criado_em=datetime.now(UTC)))
        work.commit()

    direct = DirectProjectGateway(runtime)
    assert direct.find_project_by_service_note("0000000011") == unique
    assert direct.find_project_by_service_note("9999999999") is None
    with pytest.raises(ProjectGatewayError) as direct_ambiguous:
        direct.find_project_by_service_note("0000000012")
    assert direct_ambiguous.value.code is ErrorCode.INTEGRITY_ERROR
    assert direct_ambiguous.value.status_code == 409

    application = create_app(settings, runtime_factory=lambda _settings: runtime)
    with _running_server(application) as base_url:
        gateway = HttpProjectGateway(base_url, PASSWORD)
        assert gateway.find_project_by_service_note("0000000011") == unique
        assert gateway.find_project_by_service_note("9999999999") is None
        with pytest.raises(ProjectGatewayError) as http_ambiguous:
            gateway.find_project_by_service_note("0000000012")
        assert http_ambiguous.value.code is ErrorCode.INTEGRITY_ERROR
        assert http_ambiguous.value.status_code == 409

        with pytest.raises(ProjectGatewayError) as conflict:
            gateway.create_project("0000000011", idempotency_key="gateway-conflict")
        assert conflict.value.code is ErrorCode.PROJECT_ALREADY_EXISTS
        assert conflict.value.status_code == 409
        assert conflict.value.details == {
            "project_id": str(unique.project.project_id.root),
            "service_note": "0000000011",
        }


@pytest.mark.integration
def test_two_http_clients_run_full_project_flow_and_survive_server_restart(
    tmp_path: Path,
) -> None:
    data_directory = tmp_path / "server-data"
    settings = ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=data_directory,
    )
    first_pdf = create_golden_pdf(tmp_path / "primeiro.pdf")
    catalog_code = carregar_catalogo_inicial().itens_ativos(CategoriaElemento.POSTE)[0].codigo
    second_pdf = create_action_requirements_pdf(tmp_path / "segundo.pdf", catalog_code)
    runner = CancelOnlyRunner(Event())
    runtime = _controlled_runtime(settings, runner)

    with _running_server(
        create_app(settings, runtime_factory=lambda _settings: runtime)
    ) as base_url:
        first_client = HttpProjectGateway(base_url, PASSWORD)
        second_client = HttpProjectGateway(base_url, PASSWORD)
        created = first_client.create_project("0001234567", idempotency_key="http-project")
        project_id = created.project.project_id.root
        assert second_client.list_projects().items[0].project_id.root == project_id
        initial_codes = second_client.get_service_codes(project_id)
        assert initial_codes.service_codes == ()
        updated_codes = first_client.replace_service_codes(
            project_id,
            ("9012", "0007"),
            expected_project_version=initial_codes.project_version,
        )
        assert updated_codes.service_codes == ("0007", "9012")
        assert updated_codes.project_version == initial_codes.project_version + 1
        uploaded = first_client.upload_document(
            project_id,
            first_pdf,
            idempotency_key="http-first-pdf",
        )
        assert uploaded.state is UploadState.IMPORTED
        project = first_client.get_project(project_id).project

        accepted = first_client.create_analysis_job(
            project_id,
            expected_project_version=project.project_version,
            force_reanalysis=False,
            idempotency_key="http-analysis-cancelled",
        )
        assert runner.started.wait(2)
        replay = second_client.create_analysis_job(
            project_id,
            expected_project_version=project.project_version,
            force_reanalysis=False,
            idempotency_key="http-analysis-cancelled",
        )
        assert replay == accepted
        assert runner.calls == 1
        operation = second_client.session().global_operation
        assert operation is not None
        assert operation.job_id == accepted.job_id
        assert operation.progress_percent == 75

        with pytest.raises(ProjectGatewayError) as conflict:
            second_client.create_analysis_job(
                project_id,
                expected_project_version=project.project_version,
                force_reanalysis=False,
                idempotency_key="http-analysis-conflict",
            )
        assert conflict.value.status_code == 409
        assert conflict.value.code is ErrorCode.OPERATION_CONFLICT
        assert conflict.value.correlation_id is not None

        cancelled = second_client.cancel_job(accepted.job_id.root)
        assert cancelled.cancellation_requested
        terminal = _wait_job(first_client, accepted.job_id.root, JobStatus.CANCELLED)
        assert terminal.progress_percent == 75
        assert first_client.session().global_operation is None

    restarted_classifier = FakeClassificadorMercado()
    restarted_action_verifier = FakeVerificadorAcoesConcluidas(resultado=False)
    restarted_runtime = compose_server_runtime(
        settings,
        market_classifier=restarted_classifier,
        action_verifier=restarted_action_verifier,
    )
    with _running_server(
        create_app(settings, runtime_factory=lambda _settings: restarted_runtime)
    ) as restarted_url:
        first_client = HttpProjectGateway(restarted_url, PASSWORD)
        second_client = HttpProjectGateway(restarted_url, PASSWORD)
        project = second_client.get_project(project_id).project
        assert len(project.documents) == 1
        persisted_codes = second_client.get_service_codes(project_id)
        assert persisted_codes.service_codes == ("0007", "9012")
        changed_codes = first_client.replace_service_codes(
            project_id,
            ("3456", "0007"),
            expected_project_version=persisted_codes.project_version,
        )
        with pytest.raises(ProjectGatewayError) as stale_codes:
            second_client.replace_service_codes(
                project_id,
                ("1111",),
                expected_project_version=persisted_codes.project_version,
            )
        assert stale_codes.value.status_code == 409
        assert stale_codes.value.code is ErrorCode.STALE_STATE
        assert changed_codes.service_codes == ("0007", "3456")
        project = second_client.get_project(project_id).project
        updated = first_client.update_project(
            project_id,
            "0007654321",
            expected_project_version=project.project_version,
        ).project
        second_upload = second_client.upload_document(
            project_id,
            second_pdf,
            idempotency_key="http-second-pdf",
        )
        assert second_upload.state is UploadState.IMPORTED
        project = first_client.get_project(project_id).project
        assert project.service_note == "0007654321"
        assert len(project.documents) == 2
        page_ids = tuple(page.page_id.root for page in reversed(project.pages))
        reordered = second_client.replace_page_order(
            project_id,
            page_ids,
            expected_project_version=project.project_version,
        )
        assert tuple(page.page_id.root for page in reordered.pages) == page_ids

        project = first_client.get_project(project_id).project
        accepted = first_client.create_analysis_job(
            project_id,
            expected_project_version=project.project_version,
            force_reanalysis=False,
            idempotency_key="http-analysis-success",
        )
        succeeded = _wait_job(second_client, accepted.job_id.root, JobStatus.SUCCEEDED)
        assert succeeded.progress_percent == 100
        assert restarted_classifier.consultas == ["0007654321"]
        assert restarted_action_verifier.consultas == [
            (
                "0007654321",
                ("0007", "3456"),
                DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL,
            ),
            (
                "0007654321",
                ("0007", "3456"),
                DescricaoAcao.FALTA_SERVIDAO,
            ),
        ]
        result = first_client.get_job_result(accepted.job_id.root)
        assert result.result is not None
        assert result.result["project_id"] == str(project_id)
        analyzed = second_client.get_project(project_id).project
        assert analyzed.analysis.last_extraction is AnalysisExecutionState.SUCCEEDED
        assert analyzed.analysis.last_interpretation is AnalysisExecutionState.SUCCEEDED

        document_id = project.documents[-1].document_id.root
        removed = first_client.remove_document(project_id, document_id)
        assert removed.removed
        deleted = second_client.delete_project(project_id)
        assert deleted.deleted
        assert first_client.list_projects().page.total == 0
        assert updated.project_id.root == project_id


def _controlled_runtime(settings: ServerSettings, runner: CancelOnlyRunner) -> ServerRuntime:
    runtime = compose_server_runtime(
        settings,
        market_classifier=FakeClassificadorMercado(),
    )
    runtime.jobs.stop_accepting()
    runtime.jobs.cancel_and_wait()
    assert runtime.project_api is not None
    runtime.jobs = JobManager(
        engine=runtime.core.engine,
        coordinator=runtime.core.operation_coordinator,
        project_versions=runtime.project_api,
        analysis_runner=runner,
        retention_seconds=settings.job_retention_seconds,
        maximum_retained=settings.job_max_retained,
    )
    return runtime


@contextmanager
def _running_server(application: FastAPI) -> Iterator[str]:
    with closing(create_server(("127.0.0.1", 0))) as listener:
        port = int(listener.getsockname()[1])
        server = Server(Config(application, log_level="critical", lifespan="on"))
        thread = Thread(
            target=lambda: server.run(sockets=[listener]),
            name="project-http-test",
            daemon=True,
        )
        thread.start()
        _wait_until_started(server, thread)
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            assert not thread.is_alive()


def _wait_until_started(server: Server, thread: Thread) -> None:
    tick = Event()
    deadline = monotonic() + 10
    while monotonic() < deadline:
        if server.started:
            return
        if not thread.is_alive():
            break
        tick.wait(0.01)
    raise RuntimeError("O servidor HTTP de projetos não iniciou dentro do limite")


def _wait_job(
    gateway: HttpProjectGateway,
    job_id: UUID,
    expected: JobStatus,
) -> JobStatusResponse:
    tick = Event()
    deadline = monotonic() + 30
    while monotonic() < deadline:
        status = gateway.get_job(job_id)
        if status.status is expected:
            return status
        if status.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
            raise AssertionError(f"Job terminou em {status.status.value}: {status.error}")
        tick.wait(0.05)
    raise AssertionError(f"Job não chegou a {expected.value} dentro do limite")


def test_project_gateway_retries_reads_but_never_mutations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str] = []

    def unavailable(
        _self: HttpProjectGateway,
        method: str,
        _path: str,
        *,
        headers: Mapping[str, str] | None,
        body: bytes | Iterable[bytes] | None,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers, body
        attempts.append(method)
        raise TimeoutError

    monkeypatch.setattr(HttpProjectGateway, "_request_once", unavailable)
    gateway = HttpProjectGateway("http://127.0.0.1:1", PASSWORD)
    with pytest.raises(ProjectGatewayError):
        gateway._request("GET", "/read")
    assert attempts == ["GET", "GET"]

    attempts.clear()
    with pytest.raises(ProjectGatewayError):
        gateway._request("POST", "/mutation")
    assert attempts == ["POST"]

    attempts.clear()
    with pytest.raises(ProjectGatewayError):
        gateway._request("PUT", "/service-codes")
    assert attempts == ["PUT"]

    attempts.clear()
    with pytest.raises(ProjectGatewayError) as transport:
        gateway.find_project_by_service_note("0000000011")
    assert transport.value.code is ErrorCode.INTERNAL_ERROR
    assert attempts == ["GET", "GET"]

    attempts.clear()
    with pytest.raises(ProjectGatewayError) as search_transport:
        gateway.search_projects("001")
    assert search_transport.value.code is ErrorCode.INTERNAL_ERROR
    assert search_transport.value.status_code is None
    assert attempts == ["GET", "GET"]


@contextmanager
def _http_window(base_url: str, directory: Path, qtbot: QtBot) -> Iterator[MainWindow]:
    app, window = create_application(
        [],
        settings=ClientSettings(data_directory=directory, pdf_render_dpi=72),
        project_gateway=HttpProjectGateway(base_url, PASSWORD),
        pdf_viewer_gateway=HttpPdfViewerGateway(base_url, PASSWORD),
        review_gateway=HttpReviewGateway(base_url, PASSWORD),
        documentation_gateway=HttpDocumentationGateway(base_url, PASSWORD),
        portability_gateway=HttpPortabilityGateway(base_url, PASSWORD),
    )
    qtbot.addWidget(window)
    window.show()
    try:
        yield window
    finally:
        window.close()
        window.release_resources()
        app.processEvents()


def _assert_http_panels(window: MainWindow, project_id: UUID | None, *, analyzed: bool) -> None:
    panel = window.project_panel
    review, documentation = window.review_panel, window.documentation_panel
    export, gmax = window.portability_panel, window.gmax_panel
    assert panel is not None and review is not None and documentation is not None
    assert export is not None and gmax is not None
    assert panel.projeto_ativo_id == project_id
    assert gmax.projeto_ativo_id == project_id
    assert export._project.currentData() == (str(project_id) if project_id else None)
    if project_id is None:
        assert not panel._settings.contains("last_project_id")
        assert panel._service_codes == () and panel._pages.count() == 0
        assert not panel._service_box.isEnabled() and not export._pdf.isEnabled()
    else:
        assert panel._settings.value("last_project_id") == str(project_id)
        assert panel._service_codes == panel._gateway.get_service_codes(project_id).service_codes
    if analyzed:
        assert review._session is not None and documentation._documentation is not None
        assert review._session.project_id.root == project_id
        assert documentation._documentation.project_id.root == project_id
        assert review._project.currentData() == str(project_id)
        assert documentation._project.currentData() == str(project_id)
        assert window.pdf_viewer.inspecao is not None
    else:
        assert review._session is None and documentation._documentation is None
        assert review._project.currentData() is None
        assert documentation._project.currentData() is None
        assert window.pdf_viewer.inspecao is None


@pytest.mark.integration
@pytest.mark.e2e
def test_qt_http_search_open_create_switch_rename_and_restore(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=tmp_path / "server",
    )
    runtime = compose_server_runtime(settings, market_classifier=FakeClassificadorMercado())
    assert runtime.project_api is not None
    seed = runtime.project_api.create_project("9000000000", "qt-seed")
    with SqlAlchemyUnitOfWork(runtime.core.engine) as work:
        project = work.projetos.obter(seed.project.project_id.root)
        assert project is not None
        for index in range(1, 201):
            work.projetos.salvar(
                replace(
                    project,
                    id=uuid4(),
                    nome=f"900000{index:04d}",
                    criado_em=project.criado_em + timedelta(microseconds=index),
                )
            )
        work.commit()
    application = create_app(settings, runtime_factory=lambda _settings: runtime)
    requests: list[tuple[str, str, int]] = []

    @application.middleware("http")
    async def record(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        requests.append((request.method, request.url.path, response.status_code))
        return response

    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(str(args[-1])))
    with _running_server(application) as url:
        gateway = HttpProjectGateway(url, PASSWORD)
        first = seed.project.project_id.root
        second = gateway.create_project(
            "0012345678", idempotency_key="qt-target"
        ).project.project_id.root
        for index, project_id in enumerate((first, second)):
            gateway.replace_service_codes(
                project_id,
                (f"000{index + 1}",),
                expected_project_version=gateway.get_project(project_id).project.project_version,
            )
            gateway.upload_document(
                project_id,
                _search_catalog_pdf(tmp_path / f"{index}.pdf"),
                idempotency_key=f"qt-pdf-{index}",
            )
            job = gateway.create_analysis_job(
                project_id,
                expected_project_version=gateway.get_project(project_id).project.project_version,
                force_reanalysis=False,
                idempotency_key=f"qt-job-{index}",
            )
            _wait_job(gateway, job.job_id.root, JobStatus.SUCCEEDED)
        assert second not in {item.project_id.root for item in gateway.list_projects().items}
        directory = tmp_path / "client"
        with _http_window(url, directory, qtbot) as window:
            panel = window.project_panel
            assert panel is not None
            assert panel.findChild(QLineEdit, "mvpProjectNameEdit") is None
            assert panel.findChild(QPushButton, "mvpCreateProjectButton") is None
            monkeypatch.setattr(
                QMessageBox, "question", lambda *a, **k: pytest.fail("Unexpected dialog")
            )
            panel._project_search.setText(seed.project.service_note)
            panel.abrir_selecionado()
            qtbot.waitUntil(lambda: not panel._project_action_active)
            _assert_http_panels(window, first, analyzed=True)
            requests.clear()
            panel._project_search.setText("123456")
            qtbot.waitUntil(lambda: "1 projeto(s)" in panel._search_status.text())
            _assert_http_panels(window, first, analyzed=True)
            assert all(method == "GET" for method, _, _ in requests)
            assert panel._projects.itemData(0) == str(second)
            panel._projects.setCurrentIndex(0)
            qtbot.keyClick(panel._project_search, Qt.Key.Key_Return)
            qtbot.waitUntil(lambda: not panel._project_action_active)
            _assert_http_panels(window, second, analyzed=True)
            assert not any(method == "POST" for method, _, _ in requests)

            # Editar a seleção não pode reutilizar o ID da sugestão anterior.
            panel._project_search.setText("0000000777")
            qtbot.waitUntil(lambda: "Nenhuma correspondência" in panel._search_status.text())
            monkeypatch.setattr(
                QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
            )
            panel.abrir_selecionado()
            qtbot.waitUntil(lambda: not panel._project_action_active)
            _assert_http_panels(window, None, analyzed=False)
            assert gateway.list_projects(limit=1).page.total == 202
            assert not any(method == "POST" for method, _, _ in requests)

            panel._project_search.setText("0012345678")
            panel.abrir_selecionado()
            qtbot.waitUntil(lambda: not panel._project_action_active)
            _assert_http_panels(window, second, analyzed=True)

            def confirm(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
                assert "0000000777" in str(args[2])
                panel.abrir_selecionado()
                qtbot.keyClick(panel._project_search, Qt.Key.Key_Return)
                return QMessageBox.StandardButton.Yes

            monkeypatch.setattr(QMessageBox, "question", confirm)
            panel._project_search.setText("0000000777")
            panel.abrir_selecionado()
            qtbot.waitUntil(lambda: not panel._project_action_active)
            created = gateway.find_project_by_service_note("0000000777")
            assert created is not None
            _assert_http_panels(window, created.project.project_id.root, analyzed=False)
            posts = [item for item in requests if item[0] == "POST"]
            assert posts == [("POST", "/api/v1/projects", 201)]
            assert gateway.list_projects(limit=1).page.total == 203

            panel._project_search.setText("0012345678")
            panel.abrir_selecionado()
            qtbot.waitUntil(lambda: not panel._project_action_active)
            _assert_http_panels(window, second, analyzed=True)
            original = gateway.get_project(second).project

            def rename(note: str) -> None:
                def accept() -> None:
                    dialog = QApplication.activeModalWidget()
                    assert isinstance(dialog, QDialog)
                    editor = dialog.findChild(QLineEdit, "mvpRenameServiceNoteEdit")
                    assert editor is not None
                    editor.setText(note)
                    dialog.accept()

                QTimer.singleShot(0, accept)
                panel.alterar_numero_ns()
                qtbot.waitUntil(lambda: not panel._project_action_active)

            rename(seed.project.service_note)
            assert gateway.get_project(second).project == original
            assert gateway.get_project(first).project.service_note == seed.project.service_note
            assert warnings
            warnings.clear()
            # Outra janela altera a versão antes da confirmação do diálogo.
            gateway.replace_service_codes(
                second, ("0009",), expected_project_version=original.project_version
            )
            rename("0012345679")
            assert gateway.get_project(second).project.service_note == original.service_note
            assert warnings
            warnings.clear()
            panel._project_search.setText(original.service_note)
            panel.abrir_selecionado()
            qtbot.waitUntil(lambda: not panel._project_action_active)
            before = gateway.get_project(second).project.project_version
            rename("0012345679")
            assert gateway.get_project(second).project.project_version == before + 1
            assert gateway.get_project(second).project.service_note == "0012345679"
            _assert_http_panels(window, second, analyzed=True)
        with _http_window(url, directory, qtbot) as restored:
            _assert_http_panels(restored, second, analyzed=True)
        gateway.delete_project(second)
        with _http_window(url, directory, qtbot) as removed:
            _assert_http_panels(removed, None, analyzed=False)


@pytest.mark.integration
@pytest.mark.e2e
def test_two_qt_http_clients_observe_absence_then_open_one_persisted_project(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=tmp_path / "server",
    )
    application = create_app(settings)
    requests: list[tuple[str, str, int, str | None]] = []

    @application.middleware("http")
    async def record(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        requests.append(
            (
                request.method,
                request.url.path,
                response.status_code,
                request.headers.get("Idempotency-Key"),
            )
        )
        return response

    with (
        _running_server(application) as url,
        _http_window(url, tmp_path / "one", qtbot) as one,
        _http_window(url, tmp_path / "two", qtbot) as two,
    ):
        first, second = one.project_panel, two.project_panel
        assert first is not None and second is not None
        for panel in (first, second):
            panel._project_search.setText("0000000042")
        confirmations: list[object] = []

        def confirm(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
            confirmations.append(args[0])
            assert "0000000042" in str(args[2])
            if args[0] is first:
                # Barreira na confirmação: ambos os GETs reais retornam 404 antes
                # de qualquer POST. A segunda janela vence enquanto a primeira espera.
                second.abrir_selecionado()
            else:
                assert args[0] is second
                assert (
                    len([r for r in requests if r[1].endswith("/0000000042") and r[2] == 404]) == 2
                )
                assert not any(r[0] == "POST" for r in requests)
            first.abrir_selecionado()  # Reentrada bloqueada durante a confirmação.
            return QMessageBox.StandardButton.Yes

        monkeypatch.setattr(QMessageBox, "question", confirm)
        monkeypatch.setattr(QMessageBox, "warning", lambda *a: pytest.fail(str(a)))
        first.abrir_selecionado()
        qtbot.waitUntil(
            lambda: not first._project_action_active and not second._project_action_active
        )
        gateway = HttpProjectGateway(url, PASSWORD)
        stored = gateway.list_projects()
        assert stored.page.total == 1
        project_id = stored.items[0].project_id.root
        _assert_http_panels(one, project_id, analyzed=False)
        _assert_http_panels(two, project_id, analyzed=False)
        assert confirmations == [first, second]
        posts = [r for r in requests if r[0] == "POST"]
        assert [r[2] for r in posts] == [201, 409]
        assert len({r[3] for r in posts}) == 2


def _search_catalog_pdf(path: Path) -> Path:
    code = carregar_catalogo_inicial().itens_ativos(CategoriaElemento.POSTE)[0].codigo
    with pymupdf.open() as document:
        page = document.new_page(width=240, height=160)
        page.insert_text((20, 25), "P1")
        page.insert_text((20, 40), code)
        document.save(path)
    return path


@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.parametrize("transition", ["edit", "reconnect", "close"])
def test_qt_http_delayed_search_cannot_cross_input_or_connection_context(
    qtbot: QtBot,
    tmp_path: Path,
    transition: str,
) -> None:
    settings = ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=tmp_path / "server",
    )
    application = create_app(settings)
    entered, release = Event(), Event()
    queries: list[str] = []

    @application.middleware("http")
    async def delay(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if request.url.path.endswith("/search"):
            query = request.query_params["query"]
            queries.append(query)
            if query == "111":
                entered.set()
                assert await asyncio.to_thread(release.wait, 10)
        return response

    with (
        _running_server(application) as url,
        _http_window(url, tmp_path / "client", qtbot) as window,
    ):
        gateway = HttpProjectGateway(url, PASSWORD)
        first = gateway.create_project("0000000111", idempotency_key="delay-a")
        second = gateway.create_project("0000000222", idempotency_key="delay-b")
        panel = window.project_panel
        assert panel is not None
        panel._project_search.setText(first.project.service_note)
        panel.abrir_selecionado()
        qtbot.waitUntil(lambda: not panel._project_action_active)
        qtbot.waitUntil(
            lambda: (
                first.project.service_note in queries
                and panel._search_thread is None
                and not panel._search_timer.isActive()
            )
        )
        # A pesquisa da preparação pode terminar durante a abertura síncrona.
        # Só delimite a fase atrasada depois de consumir também o término no Qt.
        queries.clear()
        panel._project_search.setText("111")
        qtbot.waitUntil(entered.is_set)
        worker = panel._search_thread
        assert worker is not None
        try:
            panel._project_search.setText("222")
            if transition == "reconnect":
                window.set_connection_available(False, "Desconectado no teste")
                assert not panel.isEnabled()
                window.set_connection_available(True, "Reconectado no teste")
            elif transition == "close":
                window.close()
            assert panel.projeto_ativo_id == first.project.project_id.root
        finally:
            release.set()
            assert worker.wait(2000)
        qtbot.waitUntil(lambda: panel._search_thread is None)
        if transition == "close":
            assert panel._search_stopped
            assert queries == ["111"]
        else:
            qtbot.waitUntil(lambda: "1 projeto(s)" in panel._search_status.text())
            assert panel._project_search.text() == "222"
            assert panel._projects.itemData(0) == str(second.project.project_id.root)
            assert panel._projects.currentData() is None
            assert queries == ["111", "222"]
            assert panel.projeto_ativo_id == first.project.project_id.root
            panel.set_global_operation(object())
            panel.abrir_selecionado()
            assert panel.projeto_ativo_id == first.project.project_id.root
            assert not panel._open_project.isEnabled()
            panel.set_global_operation(None)
        assert gateway.list_projects().page.total == 2
