from __future__ import annotations

import re
from pathlib import Path

from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial

_SUMMARY_ROW = re.compile(
    r"^\| Regra (?P<number>\d+) \| `(?P<id>[^`]+)` \| .*? \| "
    r"(?P<state>ATIVA|INATIVA) \|",
    re.MULTILINE,
)


def test_versioned_catalog_has_registry_id_order_and_activation_parity() -> None:
    registry = carregar_registro_conformidade_inicial()
    catalog_path = Path(__file__).parents[2] / "docs" / "catalogo-regras-conformidade.md"
    catalog = catalog_path.read_text(encoding="utf-8")
    rows = [
        (int(match["number"]), match["id"], match["state"] == "ATIVA")
        for match in _SUMMARY_ROW.finditer(catalog)
    ]
    expected = [
        (number, rule.id, rule.ativa) for number, rule in enumerate(registry.regras, start=1)
    ]

    assert rows == expected
    for rule in registry.regras:
        assert catalog.count(f"`{rule.id}`") == 1
