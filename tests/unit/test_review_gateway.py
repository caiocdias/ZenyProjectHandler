from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from zeny_project_handler_client.ui.review_gateway import HttpReviewGateway, ReviewGatewayError
from zeny_project_handler_contracts.base import CorrelationId, ReviewSessionId
from zeny_project_handler_contracts.errors import ErrorCode, ErrorEnvelope
from zeny_project_handler_contracts.review import (
    RejectReviewProposalRequest,
    ReviewProjectSummaryListResponse,
)


def test_review_http_gateway_retries_only_reads_and_decodes_dtos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = ReviewProjectSummaryListResponse.model_validate(
        {
            "items": [
                {
                    "project_id": str(uuid4()),
                    "service_note": "0001234567",
                    "pending_proposal_count": 2,
                    "analyzed_at": datetime(2026, 8, 18, tzinfo=UTC).isoformat(),
                }
            ],
            "page": {"limit": 10, "offset": 3, "total": 1},
        }
    )
    calls: list[tuple[str, str, bytes | None]] = []

    def flaky_read(
        _gateway: HttpReviewGateway,
        method: str,
        path: str,
        *,
        headers: object,
        body: bytes | None,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers
        calls.append((method, path, body))
        if len(calls) == 1:
            raise OSError("queda transitória")
        return 200, {}, payload.model_dump_json().encode("utf-8")

    monkeypatch.setattr(HttpReviewGateway, "_request", flaky_read)
    gateway = HttpReviewGateway("http://127.0.0.1:8765/base", "segredo")

    response = gateway.list_projects(limit=10, offset=3)

    assert response == payload
    assert calls == [
        ("GET", "/api/v1/review/projects?limit=10&offset=3", None),
        ("GET", "/api/v1/review/projects?limit=10&offset=3", None),
    ]


def test_review_http_gateway_does_not_retry_mutations_and_preserves_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def failed_mutation(
        _gateway: HttpReviewGateway,
        method: str,
        path: str,
        *,
        headers: object,
        body: bytes | None,
    ) -> tuple[int, dict[str, str], bytes]:
        del method, path, headers, body
        nonlocal calls
        calls += 1
        raise OSError("conexão encerrada")

    monkeypatch.setattr(HttpReviewGateway, "_request", failed_mutation)
    gateway = HttpReviewGateway("http://127.0.0.1:8765", "segredo")

    with pytest.raises(ReviewGatewayError) as failure:
        gateway.reject(
            uuid4(),
            RejectReviewProposalRequest(
                author="Revisora",
                reason="Símbolo incorreto",
                expected_review_session_id=ReviewSessionId(uuid4()),
            ),
        )

    assert calls == 1
    assert failure.value.code is ErrorCode.INTERNAL_ERROR

    envelope = ErrorEnvelope(
        code=ErrorCode.STALE_STATE,
        message="O projeto mudou; recarregue os dados.",
        correlation_id=CorrelationId(uuid4()),
        details={"current_project_version": 4},
    )
    with pytest.raises(ReviewGatewayError) as stale:
        HttpReviewGateway._model_response(
            409,
            {},
            envelope.model_dump_json().encode("utf-8"),
            ReviewProjectSummaryListResponse,
        )
    assert stale.value.code is ErrorCode.STALE_STATE
    assert stale.value.status_code == 409
    assert stale.value.correlation_id == str(envelope.correlation_id.root)
