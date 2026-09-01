import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]


def test_interpretation_rules_and_schema_are_versioned_json() -> None:
    rules_path = (
        PROJECT_ROOT
        / "src"
        / "zeny_project_handler"
        / "adapters"
        / "interpretation"
        / "data"
        / "regras_interpretacao_v1.json"
    )
    schema_path = PROJECT_ROOT / "docs" / "schemas" / "regras-interpretacao.schema.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert rules["schema_version"] == 1
    assert rules["registry"]["version"] == "1.4.0"
    assert len(rules["recognition_rules"]) == 5
    assert schema["properties"]["schema_version"]["const"] == 1
    assert "zeny_project_handler.adapters.interpretation.data" in pyproject
