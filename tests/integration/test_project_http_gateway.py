from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from socket import create_server
from threading import Event, Thread
from time import monotonic
from uuid import UUID

import pytest
from fastapi import FastAPI
from tests.pdf_fixtures import create_feature_pdf, create_golden_pdf
from uvicorn import Config, Server

from zeny_project_handler.application.errors import FluxoMvpCanceladoError
from zeny_project_handler.application.mvp_workflow import ResultadoFluxoMvp
from zeny_project_handler.ui.project_gateway import HttpProjectGateway, ProjectGatewayError
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
def test_two_http_clients_run_full_project_flow_and_survive_server_restart(
    tmp_path: Path,
) -> None:
    data_directory = tmp_path / "server-data"
    settings = ServerSettings(password=PASSWORD, data_directory=data_directory)
    first_pdf = create_golden_pdf(tmp_path / "primeiro.pdf")
    second_pdf = create_feature_pdf(tmp_path / "segundo.pdf")
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

    with _running_server(create_app(settings)) as restarted_url:
        first_client = HttpProjectGateway(restarted_url, PASSWORD)
        second_client = HttpProjectGateway(restarted_url, PASSWORD)
        project = second_client.get_project(project_id).project
        assert len(project.documents) == 1
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
    runtime = compose_server_runtime(settings)
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
