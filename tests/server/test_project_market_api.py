from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from tests.server.test_project_document_api import AUTH, _create_project, _settings
from zeny_project_handler.adapters.persistence import SqlAlchemyUnitOfWork
from zeny_project_handler.application.operation_coordinator import TipoOperacao
from zeny_project_handler.domain.market import ClassificacaoProjeto, Mercado
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.composition import ServerRuntime


def _seed_initialization(runtime: ServerRuntime, project_id: UUID) -> None:
    with SqlAlchemyUnitOfWork(runtime.core.engine) as work:
        project = work.projetos.obter(project_id)
        assert project is not None
        work.projetos.salvar(
            replace(
                project,
                classificacao_mercado=ClassificacaoProjeto.inicializar(
                    project.nome, Mercado.RURAL, datetime.now(UTC)
                ),
            )
        )
        work.commit()


@pytest.mark.parametrize("choice", ["RURAL", "URBANO", "AMBOS"])
def test_market_edit_reopen_conflict_and_service_note_invalidation(
    tmp_path: Path, choice: str
) -> None:
    settings = _settings(tmp_path / "server")
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        created = _create_project(client)
        project_id = UUID(str(created["project_id"]))
        route = f"/api/v1/projects/{project_id}/market"
        for method in ("GET", "PUT"):
            assert client.request(method, route).status_code == 401
        assert client.get(f"/api/v1/projects/{uuid4()}/market", headers=AUTH).status_code == 404
        assert client.get(route, headers=AUTH).json() == {
            "project_id": str(project_id),
            "project_version": 0,
            "classification": None,
        }
        payload = {"effective_market": choice, "expected_project_version": 0}
        assert client.put(route, headers=AUTH, json=payload).status_code == 422
        runtime = cast(ServerRuntime, app.state.runtime)
        _seed_initialization(runtime, project_id)
        initial = client.get(route, headers=AUTH).json()
        assert initial["classification"]["source"] == "SQL"
        payload["expected_project_version"] = initial["project_version"]
        with runtime.core.operation_coordinator.adquirir(TipoOperacao.ANALISE):
            assert client.put(route, headers=AUTH, json=payload).status_code == 409
        saved_response = client.put(route, headers=AUTH, json=payload)
        assert saved_response.status_code == 200, saved_response.text
        saved = saved_response.json()
        assert saved["project_version"] == initial["project_version"] + 1
        state = saved["classification"]
        assert state["effective_market"] == choice
        assert state["database_market"] == "RURAL"
        assert state["source"] == "MANUAL"
        assert state["initialized_at"] == initial["classification"]["initialized_at"]
        assert state["revision_id"] != initial["classification"]["revision_id"]
        assert state["classification_version"] == 2
        conflict = client.put(route, headers=AUTH, json=payload)
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "STALE_STATE"
        for invalid in ("", "rural", "SUBURBANO", None, 1):
            response = client.put(
                route,
                headers=AUTH,
                json={
                    "effective_market": invalid,
                    "expected_project_version": saved["project_version"],
                },
            )
            assert response.status_code == 422
        assert client.get(route, headers=AUTH).json() == saved
    with TestClient(create_app(settings)) as client:
        assert client.get(route, headers=AUTH).json() == saved
        for ns in ("0001234567", "9999999999", "0001234567"):
            version = client.get(route, headers=AUTH).json()["project_version"]
            renamed = client.patch(
                f"/api/v1/projects/{project_id}",
                headers=AUTH,
                json={
                    "service_note": ns,
                    "expected_project_version": version,
                },
            )
            assert renamed.status_code == 200
            current = client.get(route, headers=AUTH).json()["classification"]
            if version == saved["project_version"]:
                assert current == saved["classification"]  # Mesma NS preserva a escolha.
            else:
                assert current is None


def test_two_market_editors_cannot_overwrite_the_same_version(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path / "server"))
    with TestClient(app, raise_server_exceptions=False) as client:
        project_id = UUID(str(_create_project(client)["project_id"]))
        _seed_initialization(cast(ServerRuntime, app.state.runtime), project_id)
        route = f"/api/v1/projects/{project_id}/market"
        version = client.get(route, headers=AUTH).json()["project_version"]

        def edit(choice: str) -> int:
            return client.put(
                route,
                headers=AUTH,
                json={
                    "effective_market": choice,
                    "expected_project_version": version,
                },
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = tuple(pool.map(edit, ("URBANO", "AMBOS")))
        assert sorted(statuses) == [200, 409]
        assert client.get(route, headers=AUTH).json()["project_version"] == version + 1
