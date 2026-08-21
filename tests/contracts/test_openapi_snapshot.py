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
    assert len(operations) == 52


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
