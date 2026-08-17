"""Aplicação FastAPI somente para produzir a OpenAPI v1 revisável."""

from zeny_project_handler_api_spec.app import app, build_openapi_schema

__all__ = ["app", "build_openapi_schema"]
