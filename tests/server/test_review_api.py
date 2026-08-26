from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from tests.factories import complete_analysis, complete_project
from zeny_project_handler.adapters.persistence import SqlAlchemyUnitOfWork
from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler.application.spans import detectar_vaos
from zeny_project_handler.domain.enums import EstadoRevisao
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.composition import ServerRuntime, compose_server_runtime
from zeny_project_handler_server.config import ServerSettings

pytestmark = pytest.mark.integration

PASSWORD = "senha do servidor para testes da etapa seis"
AUTH = {"Authorization": f"Bearer {PASSWORD}"}


def _settings(data_directory: Path) -> ServerSettings:
    return ServerSettings(password=PASSWORD, data_directory=data_directory)


def _seed_review(
    runtime: ServerRuntime,
    *,
    evidence_content: str | None = None,
) -> tuple[UUID, UUID, UUID]:
    project = complete_project(runtime.core.catalog)
    other_project = complete_project(runtime.core.catalog)
    execution, evidence, template, relation, _decision = complete_analysis(project)
    if evidence_content is not None:
        evidence = replace(evidence, conteudo_bruto=evidence_content)
    proposal = replace(
        template,
        id=uuid4(),
        estado_revisao=EstadoRevisao.PROPOSTA,
    )
    with SqlAlchemyUnitOfWork(runtime.core.engine) as work:
        work.projetos.salvar(project)
        work.projetos.salvar(other_project)
        work.execucoes_analise.salvar(execution)
        work.evidencias.salvar(evidence)
        work.propostas.salvar(proposal)
        work.propostas.salvar(relation)
        work.commit()
    return project.id, proposal.id, other_project.elementos[0].id


def _json(response: Any) -> dict[str, Any]:
    return cast(dict[str, Any], response.json())


def _element_input(
    proposal: dict[str, Any], *, catalog_item_id: str | None = None
) -> dict[str, Any]:
    return {
        "category": proposal["category"],
        "catalog_item_id": catalog_item_id or proposal["catalog_item_id"],
        "situation": proposal["situation"],
        "geometry": proposal["overlay"]["geometry"],
        "observed_code": proposal["observed_code"],
    }


def test_remote_review_projects_projection_conflict_manual_audit_and_restart(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "server-data")
    runtime = compose_server_runtime(settings)
    project_id, proposal_id, foreign_element_id = _seed_review(runtime)
    local_review = ServicoRevisaoHumana(
        lambda: SqlAlchemyUnitOfWork(runtime.core.engine)
    ).carregar_sessao(project_id)
    expected_region_ids = {str(item.id) for item in local_review.regioes}
    expected_span_ids = {str(item.id) for item in detectar_vaos(local_review.projeto)}

    application = create_app(settings, runtime_factory=lambda _settings: runtime)
    with TestClient(application, raise_server_exceptions=False) as first_client:
        projects = first_client.get("/api/v1/review/projects", headers=AUTH)
        assert projects.status_code == 200, projects.text
        assert _json(projects)["page"]["total"] == 1
        assert _json(projects)["items"][0]["project_id"] == str(project_id)

        first = first_client.get(
            f"/api/v1/projects/{project_id}/review-session",
            headers=AUTH,
        )
        second = first_client.get(
            f"/api/v1/projects/{project_id}/review-session",
            headers=AUTH,
        )
        assert first.status_code == second.status_code == 200
        first_session = _json(first)
        second_session = _json(second)
        assert first_session["review_session_id"] == second_session["review_session_id"]
        assert {item["region_id"] for item in first_session["regions"]} == expected_region_ids
        assert {item["span_id"] for item in first_session["spans"]} == expected_span_ids
        assert first_session["page_order"]
        assert first_session["catalog_items"]
        assert first_session["references"]
        assert first_session["confirmed_elements"]
        assert first_session["confirmed_relations"] == []
        assert str(settings.data_directory) not in first.text

        proposal = next(
            item for item in first_session["proposals"] if item["proposal_id"] == str(proposal_id)
        )
        accepted = first_client.post(
            f"/api/v1/review/proposals/{proposal_id}/accept",
            headers=AUTH,
            json={
                "author": "Revisora remota",
                "reason": "Conferido no desenho",
                "adjustments": _element_input(proposal),
                "expected_review_session_id": first_session["review_session_id"],
            },
        )
        assert accepted.status_code == 200, accepted.text
        accepted_payload = _json(accepted)
        assert accepted_payload["decision"] == "ACCEPT"

        stale = first_client.post(
            f"/api/v1/review/proposals/{proposal_id}/reject",
            headers=AUTH,
            json={
                "author": "Segunda revisora",
                "reason": "Sessão antiga",
                "expected_review_session_id": second_session["review_session_id"],
            },
        )
        assert stale.status_code == 409
        assert _json(stale)["code"] == "STALE_STATE"

        refreshed = _json(
            first_client.get(
                f"/api/v1/projects/{project_id}/review-session",
                headers=AUTH,
            )
        )
        current_version = refreshed["project_version"]
        already_decided = first_client.post(
            f"/api/v1/review/proposals/{proposal_id}/reject",
            headers=AUTH,
            json={
                "author": "Revisora remota",
                "reason": "Decisão duplicada",
                "expected_review_session_id": refreshed["review_session_id"],
            },
        )
        assert already_decided.status_code == 409
        assert _json(already_decided)["code"] == "STALE_STATE"

        invalid_catalog = first_client.post(
            f"/api/v1/projects/{project_id}/review/elements",
            headers=AUTH,
            json={
                "author": "Revisora remota",
                "reason": "Teste de catálogo inválido",
                "element": _element_input(proposal, catalog_item_id=str(uuid4())),
                "expected_project_version": current_version,
            },
        )
        assert invalid_catalog.status_code == 422
        assert _json(invalid_catalog)["code"] == "VALIDATION_ERROR"

        cross_project = first_client.post(
            f"/api/v1/projects/{project_id}/review/relations",
            headers=AUTH,
            json={
                "author": "Revisora remota",
                "reason": "Teste de referência externa",
                "source_reference_id": refreshed["references"][0]["reference_id"],
                "target_reference_id": str(foreign_element_id),
                "relation_type": "ASSOCIADO_A",
                "expected_project_version": current_version,
            },
        )
        assert cross_project.status_code == 422
        assert _json(cross_project)["code"] == "VALIDATION_ERROR"

        manual_element = first_client.post(
            f"/api/v1/projects/{project_id}/review/elements",
            headers=AUTH,
            json={
                "author": "Revisora remota",
                "reason": "Elemento ausente na análise",
                "element": _element_input(proposal),
                "expected_project_version": current_version,
            },
        )
        assert manual_element.status_code == 201, manual_element.text
        manual_payload = _json(manual_element)

        manual_relation = first_client.post(
            f"/api/v1/projects/{project_id}/review/relations",
            headers=AUTH,
            json={
                "author": "Revisora remota",
                "reason": "Relação conferida manualmente",
                "source_reference_id": refreshed["references"][0]["reference_id"],
                "target_reference_id": manual_payload["element_id"],
                "relation_type": "ASSOCIADO_A",
                "expected_project_version": manual_payload["project_version"],
            },
        )
        assert manual_relation.status_code == 201, manual_relation.text

    restarted = create_app(settings)
    with TestClient(restarted, raise_server_exceptions=False) as restarted_client:
        reopened = restarted_client.get(
            f"/api/v1/projects/{project_id}/review-session",
            headers=AUTH,
        )
        assert reopened.status_code == 200, reopened.text
        session = _json(reopened)
        stored = next(
            item for item in session["proposals"] if item["proposal_id"] == str(proposal_id)
        )
        assert stored["review_state"] == "ACCEPTED"
        assert manual_payload["element_id"] in {
            item["element_id"] for item in session["confirmed_elements"]
        }
        assert _json(manual_relation)["relation_id"] in {
            item["relation_id"] for item in session["confirmed_relations"]
        }
        audit_by_action: dict[str, list[dict[str, Any]]] = {}
        for item in session["audit"]:
            audit_by_action.setdefault(item["action"], []).append(item)
        accepted_audit = audit_by_action["ACCEPT"][0]
        assert accepted_audit["author"] == "Revisora remota"
        assert accepted_audit["reason"] == "Conferido no desenho"
        assert accepted_audit["occurred_at"]
        assert accepted_audit["previous_values"]
        assert accepted_audit["confirmed_values"]
        assert len(audit_by_action["CREATE_MANUAL"]) == 2


def test_review_session_bounds_raw_vector_content_used_as_navigation_label(
    tmp_path: Path,
) -> None:
    raw_vector_commands = (
        '[["l",' + ",".join(f"[{index}.1,{index}.2]" for index in range(80)) + "]]"
    )
    assert len(raw_vector_commands) > 500
    settings = _settings(tmp_path / "server-data")
    runtime = compose_server_runtime(settings)
    project_id, proposal_id, _foreign = _seed_review(
        runtime,
        evidence_content=raw_vector_commands,
    )
    application = create_app(settings, runtime_factory=lambda _settings: runtime)

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get(
            f"/api/v1/projects/{project_id}/review-session",
            headers=AUTH,
        )

    assert response.status_code == 200, response.text
    payload = _json(response)
    proposal = next(
        item for item in payload["proposals"] if item["proposal_id"] == str(proposal_id)
    )
    label = proposal["evidence"][0]["label"]
    assert label == f"{raw_vector_commands[:499]}…"
    assert len(label) == 500


def test_review_routes_require_authentication(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "server-data")
    runtime = compose_server_runtime(settings)
    project_id, proposal_id, _foreign = _seed_review(runtime)
    application = create_app(settings, runtime_factory=lambda _settings: runtime)
    with TestClient(application) as client:
        assert client.get("/api/v1/review/projects").status_code == 401
        assert client.get(f"/api/v1/projects/{project_id}/review-session").status_code == 401
        assert (
            client.post(f"/api/v1/review/proposals/{proposal_id}/accept", json={}).status_code
            == 401
        )
