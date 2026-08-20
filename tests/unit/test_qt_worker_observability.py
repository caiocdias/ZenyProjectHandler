from __future__ import annotations

from datetime import UTC, datetime
from threading import Event
from typing import cast
from uuid import UUID

from zeny_project_handler_client.ui.project_gateway import ProjectGateway
from zeny_project_handler_client.ui.project_panel import _JobPollingWorker
from zeny_project_handler_contracts.base import JobId, ProjectId
from zeny_project_handler_contracts.enums import JobKind, JobStatus
from zeny_project_handler_contracts.jobs import (
    CancelJobResponse,
    JobResultResponse,
    JobStatusResponse,
)

PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
JOB_ID = UUID("20000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 8, 18, 17, 0, tzinfo=UTC)


class SequencedGateway:
    def __init__(
        self,
        *statuses: JobStatusResponse,
        result: JobResultResponse | None = None,
    ) -> None:
        self.statuses = list(statuses)
        self.result = result
        self.cancelled: list[UUID] = []

    def get_job(self, _job_id: UUID) -> JobStatusResponse:
        if len(self.statuses) > 1:
            return self.statuses.pop(0)
        return self.statuses[0]

    def get_job_result(self, _job_id: UUID) -> JobResultResponse:
        assert self.result is not None
        return self.result

    def cancel_job(self, job_id: UUID) -> CancelJobResponse:
        self.cancelled.append(job_id)
        return CancelJobResponse(
            job_id=JobId(job_id),
            status=JobStatus.CANCELLING,
            cancellation_requested=True,
        )


def _status(status: JobStatus, progress: int, message: str) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=JobId(JOB_ID),
        project_id=ProjectId(PROJECT_ID),
        kind=JobKind.ANALYSIS,
        status=status,
        progress_percent=progress,
        message=message,
        result_available=status is JobStatus.SUCCEEDED,
        created_at=NOW,
        updated_at=NOW,
    )


def test_job_polling_worker_emits_monotonic_remote_progress_and_result() -> None:
    result = JobResultResponse(
        job_id=JobId(JOB_ID),
        status=JobStatus.SUCCEEDED,
        result={"project_id": str(PROJECT_ID), "proposals_generated": 2},
    )
    gateway = SequencedGateway(
        _status(JobStatus.QUEUED, 0, "Na fila"),
        _status(JobStatus.RUNNING, 40, "Extraindo"),
        _status(JobStatus.SUCCEEDED, 100, "Concluída"),
        result=result,
    )
    worker = _JobPollingWorker(
        cast(ProjectGateway, gateway),
        JOB_ID,
        250,
        Event(),
    )
    progress: list[tuple[int, str]] = []
    completed: list[object] = []
    finished: list[bool] = []
    worker.progress.connect(lambda percent, message: progress.append((percent, message)))
    worker.completed.connect(completed.append)
    worker.finished.connect(lambda: finished.append(True))

    worker.run()

    assert [item[0] for item in progress] == [0, 40, 100]
    assert completed == [result]
    assert finished == [True]


def test_job_polling_worker_requests_cooperative_cancel_once() -> None:
    gateway = SequencedGateway(_status(JobStatus.CANCELLED, 30, "Cancelada em ponto seguro"))
    cancellation = Event()
    cancellation.set()
    worker = _JobPollingWorker(
        cast(ProjectGateway, gateway),
        JOB_ID,
        250,
        cancellation,
    )
    failures: list[tuple[str, bool]] = []
    worker.failed.connect(lambda message, cancelled: failures.append((message, cancelled)))

    worker.run()

    assert gateway.cancelled == [JOB_ID]
    assert failures == [("Cancelada em ponto seguro", True)]
