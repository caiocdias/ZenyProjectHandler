"""Gere o snapshot canônico da OpenAPI v1."""

from __future__ import annotations

import json
from pathlib import Path

from zeny_project_handler_api_spec import build_openapi_schema

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = PROJECT_ROOT / "docs" / "api" / "openapi-v1.json"


def main() -> int:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    rendered = (
        json.dumps(build_openapi_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    SNAPSHOT.write_text(rendered, encoding="utf-8")
    print(f"OpenAPI v1 gerada em {SNAPSHOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
