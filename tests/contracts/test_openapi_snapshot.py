"""Snapshot e invariantes transversais da OpenAPI v1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zeny_project_handler_api_spec import build_openapi_schema
from zeny_project_handler_contracts import API_VERSION

PROJECT_ROOT = Path(__file__).parents[2]
SNAPSHOT = PROJECT_ROOT / "docs" / "api" / "openapi-v1.json"
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})


def _operations(schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (path, method, operation)
        for path, path_item in schema["paths"].items()
        for method, operation in path_item.items()
        if method in HTTP_METHODS
    ]


def test_openapi_v1_matches_reviewed_snapshot() -> None:
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert build_openapi_schema() == expected


def test_openapi_covers_every_minimum_group_and_expected_operation() -> None:
    schema = build_openapi_schema()
    operations = _operations(schema)
    tags = {tag for _, _, operation in operations for tag in operation["tags"]}
    assert {
        "session",
        "projects",
        "documents",
        "viewer",
        "jobs",
        "analysis",
        "review",
        "documentation",
        "compliance",
        "rules",
        "portability",
        "backup",
        "photos",
    } <= tags
    assert schema["info"]["version"] == API_VERSION
    assert schema["openapi"].startswith("3.1.")
    assert API_VERSION == "1.3.0"
    assert len(operations) == 56


def test_review_contract_exposes_closed_span_type_change_and_endpoint_points() -> None:
    schemas = build_openapi_schema()["components"]["schemas"]
    span = schemas["DetectedSpanDto"]
    overlay = schemas["ReviewOverlayDto"]

    assert schemas["ElementSituation"]["enum"] == ["EXISTING", "INSTALL", "REMOVE", "CHANGE"]
    assert schemas["SpanType"]["enum"] == [
        "DISTRIBUTION_NETWORK",
        "CONNECTION_BRANCH",
        "UNKNOWN",
    ]
    assert {
        "start_point_id",
        "end_point_id",
        "span_type",
        "span_type_label",
    } <= set(span["required"])
    assert "situation_label" in overlay["required"]


def test_every_business_operation_is_bearer_protected() -> None:
    schema = build_openapi_schema()
    for path, _, operation in _operations(schema):
        if path == "/health/live":
            assert "security" not in operation
        else:
            assert path.startswith("/api/v1/")
            assert operation["security"] == [{"BearerAuth": []}]


def test_mutations_expose_error_envelope_idempotency_and_job_semantics() -> None:
    schema = build_openapi_schema()
    operations = _operations(schema)
    for path, method, operation in operations:
        responses = operation["responses"]
        if path != "/health/live":
            assert responses["401"]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ErrorEnvelope"
            }
        if method == "post" and ("jobs" in operation["tags"] or path.endswith("/document-uploads")):
            header_names = {parameter["name"] for parameter in operation.get("parameters", [])}
            assert "Idempotency-Key" in header_names or path.endswith("/cancel")
        if operation["operationId"].startswith(("createAnalysisJob", "createComplianceJob")):
            assert "202" in responses


def test_uploads_and_binary_responses_are_streaming_contracts() -> None:
    schema = build_openapi_schema()
    upload_paths = (
        "/api/v1/projects/{project_id}/document-uploads",
        "/api/v1/viewer-sessions",
        "/api/v1/rules/import-preflights",
        "/api/v1/project-import-preflights",
        "/api/v1/backup-restore-preflights",
        "/api/v1/projects/{project_id}/elements/{element_id}/photos",
    )
    for path in upload_paths:
        operation = schema["paths"][path]["post"]
        assert "multipart/form-data" in operation["requestBody"]["content"]
        assert "Idempotency-Key" in {parameter["name"] for parameter in operation["parameters"]}

    preview = schema["paths"]["/api/v1/viewer-pages/{page_id}/preview"]["get"]["responses"]["200"]
    assert "image/png" in preview["content"]
    assert {"X-Zeny-Page-Id", "X-Zeny-Pixel-Width", "X-Zeny-Pixel-Height"} <= set(
        preview["headers"]
    )
    download = schema["paths"]["/api/v1/downloads/{download_id}"]["get"]["responses"]["200"]
    assert "application/octet-stream" in download["content"]


def test_public_schemas_never_expose_file_paths() -> None:
    schemas = build_openapi_schema()["components"]["schemas"]
    violations = {
        schema_name: sorted(
            field_name
            for field_name in schema.get("properties", {})
            if "path" in field_name.casefold() or "destination" in field_name.casefold()
        )
        for schema_name, schema in schemas.items()
    }
    assert not {key: value for key, value in violations.items() if value}


def test_service_code_operations_are_additive_versioned_and_strict() -> None:
    schema = build_openapi_schema()
    route = schema["paths"]["/api/v1/projects/{project_id}/service-codes"]
    schemas = schema["components"]["schemas"]

    assert set(route) == {"get", "put"}
    assert route["get"]["operationId"] == "getProjectServiceCodes"
    assert route["put"]["operationId"] == "replaceProjectServiceCodes"
    assert route["put"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ReplaceProjectServiceCodesRequest"
    }
    assert (
        schemas["ReplaceProjectServiceCodesRequest"]["properties"]["service_codes"]["items"][
            "pattern"
        ]
        == "^[0-9]{4}$"
    )
    assert "service_codes" not in schemas["ProjectDetailDto"]["properties"]
    assert set(schemas["UpdateProjectRequest"]["properties"]) == {
        "service_note",
        "expected_project_version",
    }


def test_exact_service_note_operation_and_project_conflict_are_additive() -> None:
    schema = build_openapi_schema()
    operation = schema["paths"]["/api/v1/projects/by-service-note/{service_note}"]["get"]
    parameter = next(item for item in operation["parameters"] if item["name"] == "service_note")

    assert operation["operationId"] == "findProjectByServiceNote"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProjectDetailResponse"
    }
    assert parameter["in"] == "path"
    assert parameter["required"] is True
    assert parameter["schema"]["pattern"] == "^[0-9]{10}$"
    assert "PROJECT_ALREADY_EXISTS" in schema["components"]["schemas"]["ErrorCode"]["enum"]


def test_gmax_operation_exposes_closed_read_model() -> None:
    schema = build_openapi_schema()
    operation = schema["paths"]["/api/v1/projects/{project_id}/gmax"]["get"]
    schemas = schema["components"]["schemas"]

    assert operation["operationId"] == "getProjectGmax"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GmaxSummaryResponse"
    }
    assert schemas["GmaxHeaderState"]["enum"] == ["NOT_FOUND", "MATCH", "MISMATCH"]
    assert schemas["GmaxSnapshotState"]["enum"] == [
        "NEVER_EXECUTED",
        "CURRENT",
        "STALE",
        "BLOCKED_NS_MISMATCH",
    ]
    checks_schema = schemas["GmaxSummaryResponse"]["properties"]["checks"]
    assert checks_schema["minItems"] == checks_schema["maxItems"] == 2
    expected_query_states = [
        "NOT_EXECUTED",
        "NOT_EXECUTED_NO_TRIGGER",
        "NOT_EXECUTED_NO_SERVICE_CODES",
    ]
    for check_name, check_type in (
        ("GmaxImpact", "IMPACTO_AMBIENTAL"),
        ("GmaxServitude", "SERVIDAO"),
    ):
        executed = schemas[f"{check_name}ExecutedCheckDto"]
        not_executed = schemas[f"{check_name}NotExecutedCheckDto"]
        assert executed["properties"]["check_type"]["const"] == check_type
        assert not_executed["properties"]["check_type"]["const"] == check_type
        assert executed["properties"]["query_state"]["const"] == "EXECUTED"
        assert executed["properties"]["row_found"]["type"] == "boolean"
        assert not_executed["properties"]["query_state"]["enum"] == expected_query_states
        assert not_executed["properties"]["row_found"]["type"] == "null"
