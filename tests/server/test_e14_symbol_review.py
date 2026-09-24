"""E14 HTTP, SQLite reopen and actual XLSX cell regression oracles."""

from __future__ import annotations

import json
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from tests.e14_symbol_review_fixtures import AUTH, SymbolReviewFixture, seed_symbol_review
from tests.server.test_deliverable_exports import _sheet_rows
from zeny_project_handler.adapters.persistence import SqlAlchemyUnitOfWork
from zeny_project_handler_client.ui.review_gateway import HttpReviewGateway
from zeny_project_handler_contracts.enums import ElementCategory
from zeny_project_handler_contracts.exports import (
    CreateDeliverableExportRequest,
    DeliverableExportKind,
)
from zeny_project_handler_contracts.review import ReviewProposalDto, ReviewSessionResponse
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.deliverable_exports import _results_sheets
from zeny_project_handler_server.review_api import ReviewApiService
from zeny_project_handler_server.xlsx_export import write_xlsx

pytestmark = pytest.mark.integration


@pytest.fixture
def symbol_review(tmp_path: Path) -> Iterator[SymbolReviewFixture]:
    fixture = seed_symbol_review(tmp_path / "server")
    try:
        yield fixture
    finally:
        fixture.runtime.close()


def _session(client: TestClient, fixture: SymbolReviewFixture) -> ReviewSessionResponse:
    response = client.get(f"/api/v1/projects/{fixture.project.id}/review-session", headers=AUTH)
    assert response.status_code == 200, response.text
    return ReviewSessionResponse.model_validate(response.json())


def test_union_statuses_source_pages_and_raw_scores_survive_http(
    symbol_review: SymbolReviewFixture,
) -> None:
    fixture = symbol_review
    with TestClient(
        create_app(fixture.settings, runtime_factory=lambda _: fixture.runtime)
    ) as client:
        session = _session(client, fixture)
        assert len(session.proposals) == 6
        assert len(session.confirmed_elements) == len(fixture.project.elementos)
        symbols = [item.symbol for item in session.proposals if item.symbol is not None]
        assert len(symbols) == 6
        assert len({item.occurrence_id for item in symbols}) == 6
        assert {item.status for item in symbols} >= {
            "exclusive",
            "conflicting",
            "unknown",
            "informative",
        }
        conflict = next(item for item in symbols if item.status == "conflicting")
        assert {alt.symbol_class for alt in conflict.alternatives} == {
            "TRANSFORMADOR",
            "PARA_RAIOS",
        }
        assert len(conflict.methods) == 2
        assert conflict.reference_ids == ()
        assert conflict.calibrated_probability is None
        assert any(item.unsupported_family for item in symbols)
        assert any(item.role == "informativo" and not item.unsupported_family for item in symbols)
        page_ids = {page.id for page in fixture.project.documentos[0].paginas}
        assert {item.overlay.geometry.page_id.root for item in session.proposals} == page_ids
        for item in session.proposals:
            assert item.symbol is not None
            assert item.catalog_item_id is None
            assert item.symbol.effective_situation is None
            assert item.situation_label == "Pendente"
            assert item.overlay.situation_label == "Pendente"
            assert item.confidence is None
            assert item.symbol.quantity is None
            assert item.symbol.pending_reasons
            assert item.symbol.methods
            assert all(
                method.raw_score is not None and Decimal(method.raw_score) == Decimal("0.20")
                for method in item.symbol.methods
            )
            assert all(
                method.family is None and method.version is None for method in item.symbol.methods
            )
            assert {method.evidence.page_id for method in item.symbol.methods} == {
                item.overlay.geometry.page_id
            }
            assert all(
                evidence.page_id == item.overlay.geometry.page_id for evidence in item.evidence
            )
        assert _session(client, fixture) == session
        exclusive = next(
            item
            for item in symbols
            if item.symbol_class == "TRANSFORMADOR" and item.status == "exclusive"
        )
        assert any(row.get("state") == "non_detection" for row in exclusive.coverage)
        assert any(row.get("state") == "failure" for row in exclusive.coverage)


def test_rejection_reopens_sqlite_and_xlsx_preserves_one_row_per_occurrence(
    symbol_review: SymbolReviewFixture,
    tmp_path: Path,
) -> None:
    fixture = symbol_review
    with TestClient(
        create_app(fixture.settings, runtime_factory=lambda _: fixture.runtime)
    ) as client:
        initial = _session(client, fixture)
        selected = next(
            item
            for item in initial.proposals
            if item.symbol and item.symbol.status == "conflicting"
        )
        response = client.post(
            f"/api/v1/review/proposals/{selected.proposal_id.root}/reject",
            headers=AUTH,
            json={
                "author": "Revisor E14",
                "reason": "FP conferido no desenho",
                "expected_review_session_id": str(initial.review_session_id.root),
            },
        )
        assert response.status_code == 200, response.text
        decided = _session(client, fixture)
    with TestClient(create_app(fixture.settings)) as reopened_client:
        reopened = _session(reopened_client, fixture)
        assert reopened == decided
        rejected = next(
            item for item in reopened.proposals if item.proposal_id == selected.proposal_id
        )
        assert rejected.review_state.value == "REJECTED"
        assert rejected.symbol == selected.symbol
        assert len(reopened.confirmed_elements) == len(initial.confirmed_elements)
        sheets = _results_sheets(reopened)
        output = write_xlsx(tmp_path / "rejected.xlsx", sheets)
        rows = tuple(
            row
            for index, sheet in enumerate(sheets, 1)
            if sheet.name in {"Símbolos", "Famílias não suportadas"}
            for row in _sheet_rows(output.read_bytes(), index)[1:]
        )
        assert len(rows) == 6
        assert selected.symbol is not None
        selected_rows = [row for row in rows if selected.symbol.occurrence_id in row]
        assert len(selected_rows) == 1
        text = " | ".join(selected_rows[0])
        assert "TRANSFORMADOR" in text and "PARA_RAIOS" in text
        assert "Rejeitada" in text


@pytest.mark.parametrize("symbol_class", ["TRANSFORMADOR", None])
def test_explicit_correction_is_effective_in_reopen_and_export(
    symbol_review: SymbolReviewFixture,
    tmp_path: Path,
    symbol_class: str | None,
) -> None:
    fixture = symbol_review
    with TestClient(
        create_app(fixture.settings, runtime_factory=lambda _: fixture.runtime)
    ) as client:
        initial = _session(client, fixture)
        selected = next(
            item
            for item in initial.proposals
            if item.symbol
            and item.symbol.symbol_class == symbol_class
            and item.symbol.status == ("exclusive" if symbol_class else "unknown")
        )
        catalog = next(
            item for item in initial.catalog_items if item.category is ElementCategory.EQUIPMENT
        )
        geometry = selected.overlay.geometry.model_dump(mode="json")
        geometry["page_id"] = str(fixture.project.documentos[0].paginas[1].id)
        geometry["points"] = [{"x": "0.75", "y": "0.25"}, {"x": "0.80", "y": "0.30"}]
        response = client.post(
            f"/api/v1/review/proposals/{selected.proposal_id.root}/accept",
            headers=AUTH,
            json={
                "author": "Revisor E14",
                "reason": "Catálogo e situação conferidos manualmente",
                "expected_review_session_id": str(initial.review_session_id.root),
                "adjustments": {
                    "category": "EQUIPMENT",
                    "catalog_item_id": str(catalog.catalog_item_id.root),
                    "situation": "REMOVE",
                    "geometry": geometry,
                    "observed_code": "CORRIGIDO-E14",
                    "pole_id": str(
                        next(
                            item.element_id.root
                            for item in initial.confirmed_elements
                            if item.category is ElementCategory.POLE
                        )
                    ),
                },
            },
        )
        assert response.status_code == 200, response.text
        decided = _session(client, fixture)
    with TestClient(create_app(fixture.settings)) as client:
        reopened = _session(client, fixture)
        assert reopened == decided
        corrected = next(
            item for item in reopened.proposals if item.proposal_id == selected.proposal_id
        )
        assert corrected.review_state.value == "ADJUSTED"
        assert corrected.situation.value == "REMOVE"
        assert corrected.symbol is not None and selected.symbol is not None
        assert corrected.symbol.effective_situation == corrected.situation
        assert corrected.catalog_item_id == catalog.catalog_item_id
        assert corrected.overlay.geometry.model_dump(mode="json") == geometry
        assert corrected.symbol.alternatives == selected.symbol.alternatives
        assert corrected.symbol.occurrence_id == selected.symbol.occurrence_id
        assert len(reopened.confirmed_elements) == len(initial.confirmed_elements) + 1
        sheets = _results_sheets(reopened)
        output = write_xlsx(tmp_path / "corrected.xlsx", sheets)
        rows = _sheet_rows(output.read_bytes(), 1)
        row = next(row for row in rows[1:] if str(selected.proposal_id.root) in row)
        assert "A remover" in row and "CORRIGIDO-E14" in row and "2" in row


def test_session_projection_omits_symbol_without_breaking_legacy_consumers(
    symbol_review: SymbolReviewFixture,
) -> None:
    session = ReviewApiService(symbol_review.runtime.core.engine).get_session(
        symbol_review.project.id
    )
    payload = session.model_dump(mode="json")
    for proposal in payload["proposals"]:
        proposal.pop("symbol")
        assert ReviewProposalDto.model_validate(proposal).symbol is None


def test_preexisting_legacy_evidence_keeps_provenance_without_being_overwritten(
    tmp_path: Path,
) -> None:
    fixture = seed_symbol_review(tmp_path / "legacy", legacy_evidence=True)
    try:
        session = ReviewApiService(fixture.runtime.core.engine).get_session(fixture.project.id)
        item = next(
            item
            for item in session.proposals
            if item.symbol
            and item.symbol.symbol_class == "TRANSFORMADOR"
            and item.symbol.status == "exclusive"
        )
        assert item.symbol is not None
        assert len(item.symbol.methods) == 1
        method = item.symbol.methods[0]
        assert method.raw_score is not None and Decimal(method.raw_score) == Decimal("0.20")
        assert method.signature
        assert method.evidence.evidence_id is not None
        with SqlAlchemyUnitOfWork(fixture.runtime.core.engine) as work:
            evidence = work.evidencias.obter(method.evidence.evidence_id.root)
            assert evidence is not None
            assert evidence.metodo == "preserved-legacy-method"
            assert evidence.atributos_extraidos == (("legacy_marker", "preserve-original"),)
    finally:
        fixture.runtime.close()


def test_http_legacy_negotiation_and_client_accepts_additive_nested_fields(
    symbol_review: SymbolReviewFixture,
) -> None:
    fixture = symbol_review
    with TestClient(
        create_app(fixture.settings, runtime_factory=lambda _: fixture.runtime)
    ) as client:
        url = f"/api/v1/projects/{fixture.project.id}/review-session"
        legacy = client.get(url, headers={"Authorization": AUTH["Authorization"]})
        assert legacy.status_code == 200
        assert "symbol_support" not in legacy.json()
        assert all("symbol" not in proposal for proposal in legacy.json()["proposals"])
        current = _session(client, fixture)
        assert current.symbol_support
        assert sum(len(item.pending_reference_ids) for item in current.symbol_support) == 344
        assert sum(len(item.enabled_reference_ids) for item in current.symbol_support) == 21
        payload = current.model_dump(mode="json")
        payload["future_session_field"] = {"enabled": True}
        payload["proposals"][0]["symbol"]["future_symbol_field"] = "additive"
        decoded = HttpReviewGateway._model_response(
            200, {}, json.dumps(payload).encode(), ReviewSessionResponse
        )
        assert decoded == current


@pytest.mark.parametrize("role", ["informativo", "suporte"])
def test_observational_roles_cannot_create_catalog_assets_through_http(
    symbol_review: SymbolReviewFixture,
    role: str,
) -> None:
    fixture = symbol_review
    with TestClient(
        create_app(fixture.settings, runtime_factory=lambda _: fixture.runtime)
    ) as client:
        initial = _session(client, fixture)
        proposal = next(
            item for item in initial.proposals if item.symbol and item.symbol.role == role
        )
        equipment = next(
            item for item in initial.catalog_items if item.category is ElementCategory.EQUIPMENT
        )
        pole = next(
            item for item in initial.confirmed_elements if item.category is ElementCategory.POLE
        )
        response = client.post(
            f"/api/v1/review/proposals/{proposal.proposal_id.root}/accept",
            headers=AUTH,
            json={
                "author": "Revisor E14",
                "reason": "Tentativa de confirmar envelope",
                "expected_review_session_id": str(initial.review_session_id.root),
                "adjustments": {
                    "category": "EQUIPMENT",
                    "catalog_item_id": str(equipment.catalog_item_id.root),
                    "situation": "INSTALL",
                    "geometry": proposal.overlay.geometry.model_dump(mode="json"),
                    "pole_id": str(pole.element_id.root),
                },
            },
        )
        assert response.status_code == 422, response.text
        assert _session(client, fixture) == initial


def test_annotated_pdf_keeps_all_occurrences_and_rotated_page_navigation(
    symbol_review: SymbolReviewFixture,
) -> None:
    fixture = symbol_review
    service = fixture.runtime.portability_api
    assert service is not None
    session = ReviewApiService(fixture.runtime.core.engine).get_session(fixture.project.id)
    metadata = service.create_deliverable_export(
        fixture.project.id,
        CreateDeliverableExportRequest(
            kind=DeliverableExportKind.ANNOTATED_PDF,
            expected_project_version=session.project_version,
        ),
    )
    download = service.get_download(metadata.download_id.root)
    with pymupdf.open(download.path) as pdf:  # type: ignore[no-untyped-call]
        assert len(pdf) == 2
        assert [page.rotation for page in pdf] == [0, 90]
        for index, page in enumerate(pdf):
            proposals = [
                item
                for item in session.proposals
                if item.overlay.geometry.page_id == session.page_order[index]
            ]
            annotations = list(page.annots())
            assert len(annotations) == len(proposals) == 3
            for proposal in proposals:
                assert proposal.symbol is not None
                matching = [
                    a for a in annotations if proposal.symbol.occurrence_id in a.info["content"]
                ]
                assert len(matching) == 1
                annotation = matching[0]
                displayed = annotation.rect * page.rotation_matrix
                points = proposal.overlay.geometry.points
                assert displayed.x0 == pytest.approx(float(points[0].x) * page.rect.width, abs=2)
                assert displayed.y0 == pytest.approx(float(points[0].y) * page.rect.height, abs=2)
                assert "Pendente" in annotation.info["content"]
                if proposal.symbol.status == "conflicting":
                    assert "TRANSFORMADOR" in annotation.info["content"]
                    assert "PARA_RAIOS" in annotation.info["content"]
