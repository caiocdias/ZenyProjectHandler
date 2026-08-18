from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from typing import cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from zeny_project_handler.application.errors import FluxoMvpCanceladoError
from zeny_project_handler.application.mvp_workflow import ResultadoFluxoMvp
from zeny_project_handler_contracts.enums import JobKind, JobStatus
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.composition import ServerRuntime, compose_server_runtime
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.job_manager import JobManager
from zeny_project_handler_server.job_store import JobStore

PASSWORD = "senha segura para jobs remotos"
AUTH = {"Authorization": f"Bearer {PASSWORD}"}


@dataclass
class ControlledRunner:
    succeed: Event
    started: Event
    calls: int = 0

    def __call__(
        self,
        project_id: UUID,
        progress: Callable[[int, int, str], None],
        cancelled: Callable[[], bool],
    ) -> ResultadoFluxoMvp:
        self.calls += 1
        progress(1, 4, "Extraindo evidências")
        progress(3, 4, "Interpretando evidências")
        progress(2, 4, "Progresso atrasado que deve ser ignorado")
        self.started.set()
        while not self.succeed.wait(0.01):
            if cancelled():
                raise FluxoMvpCanceladoError("Cancelada em ponto seguro")
        if cancelled():
            raise FluxoMvpCanceladoError("Cancelada em ponto seguro")
        progress(4, 4, "Análise concluída")
        return ResultadoFluxoMvp(
            projeto_id=project_id,
            execucoes_interpretacao=(uuid4(),),
            execucao_conformidade_id=uuid4(),
            propostas_geradas=2,
            documentos_processados=1,
        )


def _settings(tmp_path: Path) -> ServerSettings:
    return ServerSettings(
        password=PASSWORD,
        data_directory=tmp_path,
        job_retention_seconds=3_600,
        job_max_retained=10,
    )


def _controlled_runtime(tmp_path: Path, runner: ControlledRunner) -> ServerRuntime:
    runtime = compose_server_runtime(_settings(tmp_path))
    runtime.jobs.stop_accepting()
    runtime.jobs.cancel_and_wait()
    assert runtime.project_api is not None
    runtime.jobs = JobManager(
        engine=runtime.core.engine,
        coordinator=runtime.core.operation_coordinator,
        project_versions=runtime.project_api,
        analysis_runner=runner,
        retention_seconds=3_600,
        maximum_retained=10,
    )
    return runtime


def _create_project(client: TestClient, key: str = "project-key") -> dict[str, object]:
    response = client.post(
        "/api/v1/projects",
        headers={**AUTH, "Idempotency-Key": key},
        json={"service_note": "0001234567"},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json()["project"])


def _wait_status(client: TestClient, job_id: str, expected: JobStatus) -> dict[str, object]:
    deadline = monotonic() + 5
    while monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}", headers=AUTH)
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] == expected.value:
            return cast(dict[str, object], payload)
        sleep(0.01)
    raise AssertionError(f"O job {job_id} não chegou a {expected.value}")


def test_two_clients_observe_one_global_job_idempotency_progress_and_cancel(
    tmp_path: Path,
) -> None:
    runner = ControlledRunner(Event(), Event())
    runtime = _controlled_runtime(tmp_path / "data", runner)
    application = create_app(
        _settings(tmp_path / "data"), runtime_factory=lambda _settings: runtime
    )

    with TestClient(application) as first_client:
        project = _create_project(first_client)
        project_id = str(project["project_id"])
        payload = {
            "force_reanalysis": False,
            "expected_project_version": project["project_version"],
        }
        accepted = first_client.post(
            f"/api/v1/projects/{project_id}/analysis-jobs",
            headers={**AUTH, "Idempotency-Key": "analysis-same-key"},
            json=payload,
        )
        assert accepted.status_code == 202, accepted.text
        job_id = accepted.json()["job_id"]
        assert runner.started.wait(2)

        replay = first_client.post(
            f"/api/v1/projects/{project_id}/analysis-jobs",
            headers={**AUTH, "Idempotency-Key": "analysis-same-key"},
            json=payload,
        )
        assert replay.status_code == 202
        assert replay.json() == accepted.json()
        assert runner.calls == 1

        observed = first_client.get("/api/v1/session", headers=AUTH)
        assert observed.status_code == 200
        operation = observed.json()["global_operation"]
        assert operation["job_id"] == job_id
        assert operation["status"] == JobStatus.RUNNING.value
        assert operation["progress_percent"] == 75

        conflicting = first_client.post(
            f"/api/v1/projects/{project_id}/analysis-jobs",
            headers={**AUTH, "Idempotency-Key": "analysis-other-client"},
            json=payload,
        )
        assert conflicting.status_code == 409
        assert conflicting.json()["code"] == "OPERATION_CONFLICT"

        cancellation = first_client.post(f"/api/v1/jobs/{job_id}/cancel", headers=AUTH)
        assert cancellation.status_code == 200
        assert cancellation.json()["status"] == JobStatus.CANCELLING.value
        terminal = _wait_status(first_client, job_id, JobStatus.CANCELLED)
        assert terminal["progress_percent"] == 75
        assert terminal["result_available"] is False
        assert runner.calls == 1

        deadline = monotonic() + 2
        while monotonic() < deadline:
            if first_client.get("/api/v1/session", headers=AUTH).json()["global_operation"] is None:
                break
            sleep(0.01)
        else:
            raise AssertionError("A operação global não foi liberada depois do cancelamento")


def test_job_success_result_and_terminal_replay_execute_once(tmp_path: Path) -> None:
    succeed = Event()
    runner = ControlledRunner(succeed, Event())
    runtime = _controlled_runtime(tmp_path / "data", runner)
    application = create_app(
        _settings(tmp_path / "data"), runtime_factory=lambda _settings: runtime
    )

    with TestClient(application) as client:
        project = _create_project(client)
        project_id = str(project["project_id"])
        payload = {
            "force_reanalysis": True,
            "expected_project_version": project["project_version"],
        }
        accepted = client.post(
            f"/api/v1/projects/{project_id}/analysis-jobs",
            headers={**AUTH, "Idempotency-Key": "successful-analysis"},
            json=payload,
        )
        assert accepted.status_code == 202
        job_id = accepted.json()["job_id"]
        assert runner.started.wait(2)
        succeed.set()
        terminal = _wait_status(client, job_id, JobStatus.SUCCEEDED)
        assert terminal["progress_percent"] == 100
        result = client.get(f"/api/v1/jobs/{job_id}/result", headers=AUTH)
        assert result.status_code == 200
        assert result.json()["result"]["project_id"] == project_id
        assert result.json()["result"]["proposals_generated"] == 2

        replay = client.post(
            f"/api/v1/projects/{project_id}/analysis-jobs",
            headers={**AUTH, "Idempotency-Key": "successful-analysis"},
            json=payload,
        )
        assert replay.status_code == 202
        assert replay.json()["job_id"] == job_id
        assert runner.calls == 1
        changed_payload = client.post(
            f"/api/v1/projects/{project_id}/analysis-jobs",
            headers={**AUTH, "Idempotency-Key": "successful-analysis"},
            json={**payload, "force_reanalysis": False},
        )
        assert changed_payload.status_code == 409
        assert changed_payload.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_restart_reconciles_active_job_as_recoverable_failure_without_false_success(
    tmp_path: Path,
) -> None:
    runtime = compose_server_runtime(_settings(tmp_path / "data"))
    runtime.jobs.stop_accepting()
    runtime.jobs.cancel_and_wait()
    assert runtime.project_api is not None
    project = runtime.project_api.create_project("0007654321", "restart-project").project
    job_id = uuid4()
    store = JobStore(
        runtime.core.engine,
        retention=timedelta(hours=1),
        maximum_retained=10,
    )
    store.create(job_id, project.project_id.root, JobKind.ANALYSIS)
    store.update_progress(
        job_id,
        status=JobStatus.RUNNING,
        progress_percent=55,
        message="Operação interrompida abruptamente",
    )
    runner = ControlledRunner(Event(), Event())
    manager = JobManager(
        engine=runtime.core.engine,
        coordinator=runtime.core.operation_coordinator,
        project_versions=runtime.project_api,
        analysis_runner=runner,
        retention_seconds=3_600,
        maximum_retained=10,
    )
    runtime.jobs = manager
    try:
        assert manager.interrupted_on_startup == 1
        reconciled = manager.get_job(job_id)
        assert reconciled.status is JobStatus.FAILED
        assert reconciled.progress_percent == 55
        assert reconciled.result_available is False
        assert reconciled.error is not None
        assert reconciled.error.details == {
            "recoverable": True,
            "restart_interrupted": True,
        }
    finally:
        runtime.close()


def test_job_store_accepts_complete_state_matrix_without_progress_regression(
    tmp_path: Path,
) -> None:
    runtime = compose_server_runtime(_settings(tmp_path / "data"))
    runtime.jobs.stop_accepting()
    runtime.jobs.cancel_and_wait()
    assert runtime.project_api is not None
    project = runtime.project_api.create_project("0005554433", "state-matrix").project
    job_id = uuid4()
    store = JobStore(
        runtime.core.engine,
        retention=timedelta(hours=1),
        maximum_retained=10,
    )
    try:
        queued = store.create(job_id, project.project_id.root, JobKind.ANALYSIS)
        assert queued.status is JobStatus.QUEUED
        running = store.update_progress(
            job_id,
            status=JobStatus.RUNNING,
            progress_percent=60,
            message="Executando",
        )
        assert running.progress_percent == 60
        waiting = store.update_progress(
            job_id,
            status=JobStatus.WAITING_CONFIRMATION,
            progress_percent=40,
            message="Aguardando confirmação",
        )
        assert waiting.status is JobStatus.WAITING_CONFIRMATION
        assert waiting.progress_percent == 60
        cancelling = store.update_progress(
            job_id,
            status=JobStatus.CANCELLING,
            progress_percent=20,
            message="Cancelando",
        )
        assert cancelling.status is JobStatus.CANCELLING
        assert cancelling.progress_percent == 60
        cancelled = store.finish(
            job_id,
            status=JobStatus.CANCELLED,
            message="Cancelado em ponto seguro",
        )
        assert cancelled.status is JobStatus.CANCELLED
        unchanged = store.finish(
            job_id,
            status=JobStatus.SUCCEEDED,
            message="Sucesso falso não permitido",
            result_json="{}",
        )
        assert unchanged.status is JobStatus.CANCELLED
        assert unchanged.result_json is None

        limited = JobStore(
            runtime.core.engine,
            retention=timedelta(hours=1),
            maximum_retained=1,
        )
        second_id = uuid4()
        limited.create(second_id, project.project_id.root, JobKind.ANALYSIS)
        limited.finish(second_id, status=JobStatus.FAILED, message="Falha segura")
        third_id = uuid4()
        limited.create(third_id, project.project_id.root, JobKind.ANALYSIS)
        limited.finish(third_id, status=JobStatus.SUCCEEDED, message="Concluído", result_json="{}")
        assert limited.prune() == 2
        assert limited.get(job_id) is None
        assert limited.get(second_id) is None
        assert limited.get(third_id) is not None
    finally:
        runtime.close()
