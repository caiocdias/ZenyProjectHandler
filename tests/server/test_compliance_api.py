from __future__ import annotations

import json
from base64 import b64encode
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from zeny_project_handler.adapters.compliance import (
    carregar_registro_conformidade_inicial,
    registro_conformidade_e_avisos_de_dict,
)
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.composition import compose_server_runtime
from zeny_project_handler_server.config import ServerSettings

PASSWORD = "senha segura para conformidade remota"
AUTH = {"Authorization": f"Bearer {PASSWORD}"}


def _settings(data_directory: Path) -> ServerSettings:
    return ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=data_directory,
    )


def _custom_registry_payload() -> bytes:
    payload = deepcopy(carregar_registro_conformidade_inicial().para_dict())
    metadata = payload["registry"]
    rules = payload["rules"]
    assert isinstance(metadata, dict) and isinstance(rules, list)
    metadata["id"] = str(uuid4())
    metadata["version"] = "fixture-server-stage7"
    added = deepcopy(rules[0])
    assert isinstance(added, dict)
    added["id"] = "fixture.server.regra-adicional"
    added["title"] = "Regra adicional do servidor"
    rules[:] = [added]
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def test_remote_registry_preserves_41_rule_baseline_round_trip_and_confirmed_restart(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "server-data")
    runtime = compose_server_runtime(settings)
    application = create_app(settings, runtime_factory=lambda _settings: runtime)

    with TestClient(application) as client:
        active = client.get("/api/v1/rules/active", headers=AUTH)
        assert active.status_code == 200, active.text
        baseline = active.json()
        assert baseline["rule_count"] == baseline["active_rule_count"] == 41
        assert len(baseline["rules"]) == len(baseline["details"]) == 41
        assert len({item["rule_id"] for item in baseline["rules"]}) == 41
        assert {item["rule_number"] for item in baseline["rules"]} == set(range(1, 42))

        download = client.get("/api/v1/rules/active/download", headers=AUTH)
        assert download.status_code == 200
        assert download.headers["content-disposition"] == (
            'attachment; filename="regras-conformidade.json"'
        )
        expected_digest = b64encode(sha256(download.content).digest()).decode("ascii")
        assert download.headers["digest"] == f"sha-256={expected_digest}"
        assert str(settings.data_directory) not in download.text
        decoded = json.loads(download.content)
        registry, warnings = registro_conformidade_e_avisos_de_dict(decoded)
        assert warnings == ()
        assert registry.assinatura() == baseline["sha256"]
        assert len(registry.regras) == 41

        content = _custom_registry_payload()
        preflight = client.post(
            "/api/v1/rules/import-preflights",
            headers={**AUTH, "Idempotency-Key": "stage7-cancelled-preflight"},
            files={"file": ("rules.json", content, "application/json")},
        )
        assert preflight.status_code == 201, preflight.text
        prepared = preflight.json()
        assert prepared["disposition"] == "CONFIRMATION_REQUIRED"
        assert prepared["added_rule_ids"] == ["fixture.server.regra-adicional"]
        assert len(prepared["preserved_rule_ids"]) == 41

        unchanged = client.get("/api/v1/rules/active", headers=AUTH).json()
        assert unchanged["revision"] == baseline["revision"]
        assert unchanged["sha256"] == baseline["sha256"]
        assert unchanged["rule_count"] == 41

        confirmed = client.post(
            "/api/v1/rules/imports",
            headers=AUTH,
            json={
                "preflight_id": prepared["preflight_id"],
                "fingerprint": prepared["fingerprint"],
                "expected_active_revision": prepared["current_revision"],
                "confirmed": True,
            },
        )
        assert confirmed.status_code == 201, confirmed.text
        assert confirmed.json()["active_rule_count"] == 42

        imported = client.get("/api/v1/rules/active", headers=AUTH).json()
        imported_numbers = {item["rule_id"]: item["rule_number"] for item in imported["rules"]}
        baseline_numbers = {item["rule_id"]: item["rule_number"] for item in baseline["rules"]}
        assert imported["rule_count"] == imported["active_rule_count"] == 42
        assert imported_numbers["fixture.server.regra-adicional"] == 42
        assert all(
            imported_numbers[rule_id] == number for rule_id, number in baseline_numbers.items()
        )

    reopened_runtime = compose_server_runtime(settings)
    reopened_app = create_app(
        settings,
        runtime_factory=lambda _settings: reopened_runtime,
    )
    with TestClient(reopened_app) as client:
        reopened = client.get("/api/v1/rules/active", headers=AUTH)
        assert reopened.status_code == 200
        assert reopened.json()["revision"] == "fixture-server-stage7"
        assert reopened.json()["rule_count"] == 42
