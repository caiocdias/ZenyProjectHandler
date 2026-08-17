from __future__ import annotations

from typing import cast

from zeny_project_handler.adapters.analysis.tesseract_runtime import RuntimeTesseract
from zeny_project_handler.composition import CoreServices
from zeny_project_handler_server.composition import JobLifecycle, ServerRuntime


class RecordingCore:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def close(self) -> None:
        self.events.append("engine-disposed")


class RecordingJobs:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def stop_accepting(self) -> None:
        self.events.append("jobs-stopped")

    def cancel_and_wait(self) -> None:
        self.events.append("jobs-cancelled-and-waited")


def test_server_shutdown_orders_jobs_before_engine_and_is_idempotent() -> None:
    events: list[str] = []
    runtime = ServerRuntime(
        core=cast(CoreServices, RecordingCore(events)),
        ocr=RuntimeTesseract(executavel=None, diretorio_tessdata=None),
        jobs=cast(JobLifecycle, RecordingJobs(events)),
    )

    runtime.close()
    runtime.close()

    assert events == ["jobs-stopped", "jobs-cancelled-and-waited", "engine-disposed"]
