"""E15: comportamento operacional da composição opcional nos jobs remotos."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from tests.market_fakes import FakeClassificadorMercado, FakeVerificadorAcoesConcluidas
from tests.pdf_fixtures import create_analysis_pdf, create_golden_pdf
from zeny_project_handler.adapters.analysis import raster_symbols
from zeny_project_handler.adapters.analysis.raster_symbols import (
    ConfiguracaoDetectorRaster,
    TemplateRasterVerificado,
)
from zeny_project_handler.adapters.persistence import SqlAlchemyUnitOfWork, create_sqlite_engine
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise, EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import ResultadoMetodoSimbolos
from zeny_project_handler_contracts.enums import JobStatus
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.composition import compose_server_runtime
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

_PASSWORD = "senha segura para E15"
_AUTH = {"Authorization": f"Bearer {_PASSWORD}"}


def _settings(data: Path, *, enabled: bool) -> ServerSettings:
    return ServerSettings(
        password=_PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=data,
        symbol_composition=enabled,
    )


def _client(settings: ServerSettings) -> TestClient:
    runtime = compose_server_runtime(
        settings,
        market_classifier=FakeClassificadorMercado(),
        action_verifier=FakeVerificadorAcoesConcluidas(),
    )
    return TestClient(create_app(settings, runtime_factory=lambda _settings: runtime))


def _create_project_with_pdf(client: TestClient, source: Path) -> tuple[str, int, str]:
    created = client.post(
        "/api/v1/projects",
        headers={**_AUTH, "Idempotency-Key": "e15-project"},
        json={"service_note": "0001234567"},
    )
    assert created.status_code == 201, created.text
    project_id = str(created.json()["project"]["project_id"])
    uploaded = client.post(
        f"/api/v1/projects/{project_id}/document-uploads",
        headers={**_AUTH, "Idempotency-Key": "e15-upload"},
        files={"file": (source.name, source.read_bytes(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    detail = client.get(f"/api/v1/projects/{project_id}", headers=_AUTH)
    assert detail.status_code == 200, detail.text
    project = detail.json()["project"]
    return (
        project_id,
        int(project["project_version"]),
        str(project["documents"][0]["document_id"]),
    )


def _start_analysis(
    client: TestClient,
    project_id: str,
    version: int,
    *,
    key: str,
) -> str:
    response = client.post(
        f"/api/v1/projects/{project_id}/analysis-jobs",
        headers={**_AUTH, "Idempotency-Key": key},
        json={"expected_project_version": version, "force_reanalysis": False},
    )
    assert response.status_code == 202, response.text
    return str(response.json()["job_id"])


def _terminal(client: TestClient, job_id: str) -> dict[str, object]:
    deadline = monotonic() + 10
    while monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}", headers=_AUTH)
        assert response.status_code == 200, response.text
        payload = cast(dict[str, object], response.json())
        if payload["status"] in {
            JobStatus.SUCCEEDED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        }:
            return payload
        sleep(0.01)
    raise AssertionError(f"Job {job_id} não terminou no prazo do teste")


def _project_version(client: TestClient, project_id: str) -> int:
    response = client.get(f"/api/v1/projects/{project_id}", headers=_AUTH)
    assert response.status_code == 200, response.text
    return int(response.json()["project"]["project_version"])


def _interpretation_ids(settings: ServerSettings, project_id: str) -> set[UUID]:
    engine = create_sqlite_engine(settings.core_settings().database_path)
    try:
        with SqlAlchemyUnitOfWork(engine) as work:
            runs = work.execucoes_analise.listar_do_projeto(UUID(project_id))
        return {
            run.id
            for run in runs
            if run.estado is EstadoExecucaoAnalise.CONCLUIDA
            and "execucao_extracao_id" in dict(run.parametros)
        }
    finally:
        engine.dispose()


def test_oom_does_not_complete_or_cache_full_composition_and_retry_runs_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = create_analysis_pdf(tmp_path / "e15-oom.pdf")
    data = tmp_path / "server-data"
    calls = 0
    original_observe_page = SymbolCompositionRunner._observe_page

    def fail_once(
        _self: SymbolCompositionRunner,
        page: Any,
        *,
        document_id: str,
        document_sha256: str,
        page_number: int,
        cancelado: Callable[[], bool] | None,
        progresso: Callable[[int, int], None] | None,
    ) -> Iterator[ResultadoMetodoSimbolos]:
        nonlocal calls
        calls += 1
        original = original_observe_page(
            _self,
            page,
            document_id=document_id,
            document_sha256=document_sha256,
            page_number=page_number,
            cancelado=cancelado,
            progresso=progresso,
        )
        if calls == 1:
            yield next(original)
            raise MemoryError("OOM injetado no motor habilitado")
        yield from original

    monkeypatch.setattr(SymbolCompositionRunner, "_observe_page", fail_once)
    settings = _settings(data, enabled=True)
    with _client(settings) as client:
        project_id, version, document_id = _create_project_with_pdf(client, source)
        managed = data / "project-files" / project_id / "documents" / f"{document_id}.pdf"
        source_digest = sha256(managed.read_bytes()).hexdigest()
        first_id = _start_analysis(client, project_id, version, key="e15-oom-first")
        first = _terminal(client, first_id)
        assert first["status"] == JobStatus.FAILED.value
        assert first["result_available"] is False
        journals = sorted((data / "symbol_partial_runs").glob("*.json"))
        assert len(journals) == 1
        partial = json.loads(journals[0].read_text(encoding="utf-8"))
        assert partial["status"] == "failed"
        assert partial["cache_status"] == "miss"
        assert partial["source_sha256"] == source_digest
        assert len(partial["results"]) == 1
        symbol_cache = settings.core_settings().analysis_cache_directory / "symbols"
        assert not list(symbol_cache.glob("*.json"))
        engine = create_sqlite_engine(settings.core_settings().database_path)
        try:
            with SqlAlchemyUnitOfWork(engine) as work:
                executions = work.execucoes_analise.listar_do_projeto(UUID(project_id))
            assert not any(
                run.estado is EstadoExecucaoAnalise.CONCLUIDA
                and "execucao_extracao_id" in dict(run.parametros)
                for run in executions
            )
        finally:
            engine.dispose()

        retry_id = _start_analysis(client, project_id, version, key="e15-oom-retry")
        retry = _terminal(client, retry_id)
        assert retry["status"] == JobStatus.SUCCEEDED.value
        assert retry["result_available"] is True
        assert calls > 1
        call_count = calls
        replay_id = _start_analysis(client, project_id, version, key="e15-oom-retry")
        assert replay_id == retry_id
        assert calls == call_count
        assert len(list(symbol_cache.glob("*.json"))) == 1
        cached_id = _start_analysis(
            client, project_id, _project_version(client, project_id), key="e15-cache-hit"
        )
        assert _terminal(client, cached_id)["status"] == JobStatus.SUCCEEDED.value
        assert calls == call_count
        assert sha256(managed.read_bytes()).hexdigest() == source_digest
        statuses = {
            json.loads(path.read_text(encoding="utf-8"))["status"]
            for path in (data / "symbol_partial_runs").glob("*.json")
        }
        assert statuses == {"failed", "completed", "cache_hit"}

    with _client(settings) as reopened:
        assert _terminal(reopened, first_id)["status"] == JobStatus.FAILED.value
        assert _terminal(reopened, retry_id)["status"] == JobStatus.SUCCEEDED.value


def test_opt_out_opt_in_opt_out_preserves_history_and_legacy_reuse(tmp_path: Path) -> None:
    source = create_analysis_pdf(tmp_path / "e15-rollback.pdf")
    data = tmp_path / "server-data"
    legacy = _settings(data, enabled=False)
    with _client(legacy) as client:
        project_id, version_at_creation, _document_id = _create_project_with_pdf(client, source)
        old_id = _start_analysis(client, project_id, version_at_creation, key="e15-original-config")
        assert _terminal(client, old_id)["status"] == JobStatus.SUCCEEDED.value
    old_interpretations = _interpretation_ids(legacy, project_id)
    assert old_interpretations

    enabled = replace(_settings(data, enabled=True), symbol_profile="vector-only")
    with _client(enabled) as client:
        version = _project_version(client, project_id)
        stale_key = client.post(
            f"/api/v1/projects/{project_id}/analysis-jobs",
            headers={**_AUTH, "Idempotency-Key": "e15-original-config"},
            json={"expected_project_version": version_at_creation, "force_reanalysis": False},
        )
        assert stale_key.status_code == 409
        assert stale_key.json()["code"] == "IDEMPOTENCY_CONFLICT"
        enabled_id = _start_analysis(client, project_id, version, key="e15-enabled-config")
        assert _terminal(client, enabled_id)["status"] == JobStatus.SUCCEEDED.value
    enabled_interpretations = _interpretation_ids(enabled, project_id)
    assert old_interpretations < enabled_interpretations

    with _client(legacy) as client:
        version = _project_version(client, project_id)
        rollback_id = _start_analysis(client, project_id, version, key="e15-rollback-config")
        assert _terminal(client, rollback_id)["status"] == JobStatus.SUCCEEDED.value
        assert _terminal(client, old_id)["status"] == JobStatus.SUCCEEDED.value
        assert _terminal(client, enabled_id)["status"] == JobStatus.SUCCEEDED.value
    assert _interpretation_ids(legacy, project_id) == enabled_interpretations


def test_opt_in_cancel_keeps_terminal_job_without_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = create_analysis_pdf(tmp_path / "e15-cancel.pdf")
    entered = Event()
    original_observe_page = SymbolCompositionRunner._observe_page

    def wait_for_cancel(
        _self: SymbolCompositionRunner,
        page: Any,
        *,
        document_id: str,
        document_sha256: str,
        page_number: int,
        cancelado: Callable[[], bool] | None,
        progresso: Callable[[int, int], None] | None,
    ) -> Iterator[ResultadoMetodoSimbolos]:
        first = original_observe_page(
            _self,
            page,
            document_id=document_id,
            document_sha256=document_sha256,
            page_number=page_number,
            cancelado=cancelado,
            progresso=progresso,
        )
        yield next(first)
        entered.set()
        deadline = monotonic() + 5
        while monotonic() < deadline:
            _self._check_cancelled(cancelado)
            sleep(0.01)
        raise AssertionError("O cancelamento não chegou ao runner")

    monkeypatch.setattr(SymbolCompositionRunner, "_observe_page", wait_for_cancel)
    settings = _settings(tmp_path / "server-data", enabled=True)
    with _client(settings) as client:
        project_id, version, _document_id = _create_project_with_pdf(client, source)
        job_id = _start_analysis(client, project_id, version, key="e15-cancel")
        assert entered.wait(5)
        cancelled = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=_AUTH)
        assert cancelled.status_code == 200, cancelled.text
        terminal = _terminal(client, job_id)
        assert terminal["status"] == JobStatus.CANCELLED.value
        assert terminal["result_available"] is False
        assert cast(int, terminal["progress_percent"]) < 100
        journals = list((settings.data_directory / "symbol_partial_runs").glob("*.json"))
        assert len(journals) == 1
        partial = json.loads(journals[0].read_text(encoding="utf-8"))
        assert partial["status"] == "cancelled"
        assert partial["cache_status"] == "miss"
        assert len(partial["results"]) == 1
        assert not list(
            (settings.core_settings().analysis_cache_directory / "symbols").glob("*.json")
        )


def test_enabled_tile_failure_is_journaled_and_never_reported_as_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = create_golden_pdf(tmp_path / "e15-tile.pdf")
    original = raster_symbols.observar_simbolos_raster

    def failed_tile(
        page: Any,
        *,
        documento_id: str,
        documento_sha256: str,
        pagina_numero: int,
        templates: tuple[TemplateRasterVerificado, ...],
        configuracao: ConfiguracaoDetectorRaster,
        cancelado: Callable[[], bool] | None = None,
        progresso: Callable[[int, int], None] | None = None,
        hough_enabled: bool = True,
    ) -> tuple[ResultadoMetodoSimbolos, ...]:
        template, hough = original(
            page,
            documento_id=documento_id,
            documento_sha256=documento_sha256,
            pagina_numero=pagina_numero,
            templates=templates,
            configuracao=configuracao,
            cancelado=cancelado,
            progresso=progresso,
            hough_enabled=hough_enabled,
        )
        coverage = replace(
            template.coberturas[0],
            estado=EstadoMetodoSimbolos.FALHA,
            motivo="tile injetado",
        )
        return replace(template, coberturas=(coverage, *template.coberturas[1:])), hough

    monkeypatch.setattr(raster_symbols, "observar_simbolos_raster", failed_tile)
    settings = _settings(tmp_path / "server-data", enabled=True)
    with _client(settings) as client:
        project_id, version, _document_id = _create_project_with_pdf(client, source)
        job_id = _start_analysis(client, project_id, version, key="e15-tile")
        terminal = _terminal(client, job_id)
        assert terminal["status"] == JobStatus.FAILED.value
        assert terminal["result_available"] is False
        journals = list((settings.data_directory / "symbol_partial_runs").glob("*.json"))
        assert len(journals) == 1
        partial = json.loads(journals[0].read_text(encoding="utf-8"))
        assert partial["status"] == "failed"
        assert partial["cache_status"] == "miss"
        assert any(
            coverage["status"] == EstadoMetodoSimbolos.FALHA.value
            for result in partial["results"]
            for coverage in result["coverage"]
        )
        assert not list(
            (settings.core_settings().analysis_cache_directory / "symbols").glob("*.json")
        )


def test_missing_configured_model_fails_closed_and_history_reopens(tmp_path: Path) -> None:
    source = create_golden_pdf(tmp_path / "e15-model.pdf")
    settings = replace(
        _settings(tmp_path / "server-data", enabled=True),
        symbol_model_path=tmp_path / "missing-model.bin",
    )
    with _client(settings) as client:
        project_id, version, _document_id = _create_project_with_pdf(client, source)
        job_id = _start_analysis(client, project_id, version, key="e15-model-missing")
        terminal = _terminal(client, job_id)
        assert terminal["status"] == JobStatus.FAILED.value
        assert terminal["result_available"] is False
        journals = list((settings.data_directory / "symbol_partial_runs").glob("*.json"))
        assert len(journals) == 1
        assert json.loads(journals[0].read_text(encoding="utf-8"))["status"] == "failed"
        assert not list(
            (settings.core_settings().analysis_cache_directory / "symbols").glob("*.json")
        )

    with _client(settings) as reopened:
        assert _terminal(reopened, job_id)["status"] == JobStatus.FAILED.value
