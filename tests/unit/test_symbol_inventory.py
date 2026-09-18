"""Portable checks for the E01 documentary inventory, without loading any detector.

The private validator supports only the JSON Schema keywords used by this document.
Unsupported keywords fail explicitly; this is not a general JSON Schema implementation.
Source availability and visual correctness are reviewed separately, never inferred here.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_INVENTORY_PATH = _ROOT / "docs/data/inventario-simbologia-v1.json"
_SCHEMA_PATH = _ROOT / "docs/schemas/inventario-simbologia.schema.json"
_KEYWORDS = {
    "$schema",
    "$id",
    "$defs",
    "$ref",
    "title",
    "description",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "uniqueItems",
    "minLength",
    "pattern",
    "minimum",
    "maximum",
    "enum",
    "const",
}
# Canonical denominator from the independent F02 review (33 sections, 427 visual cells).
# Names are normalized as in the review; ranges include shared boundary pages.
# Source PDF SHA-256: 0e29f0ea81827c7235d0893c383fc993c78378c51e930b8b8228de82d564ce04.
_F02_SECTIONS = (
    (1, "Introdução", 5, 5, 1),
    (2, "Anotações de objetos", 5, 5, 3),
    (3, "Poste", 6, 8, 25),
    (4, "Rota subterrânea", 8, 8, 1),
    (5, "Caixa subterrânea", 9, 10, 13),
    (6, "Câmara", 10, 11, 9),
    (7, "Plataforma", 11, 11, 5),
    (8, "Poste AT", 12, 12, 6),
    (9, "Subestação", 12, 12, 4),
    (10, "Estrutura poste MT", 13, 13, 5),
    (11, "Torre AT", 13, 13, 3),
    (12, "Estrutura poste AT", 14, 14, 3),
    (13, "Estrutura montagem MT/BT", 14, 14, 6),
    (14, "Estai MT", 15, 15, 15),
    (15, "Estai AT", 16, 16, 2),
    (16, "Cabo aéreo", 16, 17, 22),
    (17, "Cabo subterrâneo", 18, 19, 17),
    (18, "Transformador", 19, 21, 27),
    (19, "Conector", 22, 23, 17),
    (20, "Equipamento interrupção", 23, 26, 40),
    (21, "Equipamento proteção", 27, 28, 15),
    (22, "Equipamento regulação", 28, 28, 5),
    (23, "Equipamento associado", 29, 30, 16),
    (24, "Transformador terciário", 30, 30, 2),
    (25, "Transformador de medida", 30, 31, 4),
    (26, "Usina", 31, 31, 1),
    (27, "Iluminação pública", 31, 32, 13),
    (28, "Ponto conexão", 32, 32, 4),
    (29, "Ponto medição", 32, 32, 1),
    (30, "Concentrador primário", 33, 33, 1),
    (31, "Concentrador secundário", 33, 33, 1),
    (32, "Equipamento composto", 33, 38, 51),
    (33, "Desenho rascunhos", 38, 45, 89),
)


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _check_keywords(schema: dict[str, Any]) -> None:
    assert not (schema.keys() - _KEYWORDS), "unsupported schema keyword"
    for group in ("$defs", "properties"):
        for child in schema.get(group, {}).values():
            _check_keywords(child)
    if "items" in schema:
        _check_keywords(schema["items"])
    if "additionalProperties" in schema:
        assert schema["additionalProperties"] is False, "unsupported additionalProperties"


def _is_type(value: Any, name: str) -> bool:
    types = {
        "object": (dict,),
        "array": (list,),
        "string": (str,),
        "integer": (int,),
        "number": (int, float),
        "boolean": (bool,),
        "null": (type(None),),
    }
    assert name in types, f"unsupported schema type: {name}"
    return type(value) in types[name]


def _check_schema(
    value: Any, schema: dict[str, Any], root: dict[str, Any], path: str = "$"
) -> None:
    if "$ref" in schema:
        reference = schema["$ref"]
        assert reference.startswith("#/$defs/"), "only local definition references supported"
        _check_schema(value, root["$defs"][reference.removeprefix("#/$defs/")], root, path)
    if "type" in schema:
        names = schema["type"]
        if isinstance(names, str):
            names = [names]
        assert any(_is_type(value, name) for name in names), f"{path}: type"
    if "const" in schema:
        expected = schema["const"]
        assert type(value) is type(expected) and value == expected, f"{path}: const"
    if "enum" in schema:
        assert any(type(value) is type(item) and value == item for item in schema["enum"]), (
            f"{path}: enum"
        )
    if isinstance(value, dict):
        assert set(schema.get("required", [])) <= value.keys(), f"{path}: required"
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            assert value.keys() <= properties.keys(), f"{path}: additionalProperties"
        for key in value.keys() & properties.keys():
            _check_schema(value[key], properties[key], root, f"{path}.{key}")
    if isinstance(value, list):
        assert len(value) >= schema.get("minItems", 0), f"{path}: minItems"
        if schema.get("uniqueItems"):
            serialized = [json.dumps(item, sort_keys=True) for item in value]
            assert len(serialized) == len(set(serialized)), f"{path}: uniqueItems"
        if "items" in schema:
            for index, item in enumerate(value):
                _check_schema(item, schema["items"], root, f"{path}[{index}]")
    if isinstance(value, str):
        assert len(value) >= schema.get("minLength", 0), f"{path}: minLength"
        if "pattern" in schema:
            assert re.search(schema["pattern"], value), f"{path}: pattern"
    if type(value) in (int, float):
        if "minimum" in schema:
            assert value >= schema["minimum"], f"{path}: minimum"
        if "maximum" in schema:
            assert value <= schema["maximum"], f"{path}: maximum"


def _check_integrity(data: dict[str, Any]) -> None:
    date.fromisoformat(data["reviewed_on"])
    ids = [
        item["id"] for key in ("sources", "profiles", "families", "variants") for item in data[key]
    ]
    assert len(ids) == len(set(ids)), "duplicate entity ID"
    sources = {item["id"]: item for item in data["sources"]}
    profiles = {item["id"]: item for item in data["profiles"]}
    families = {item["id"]: item for item in data["families"]}
    assert {"F01", "F02", "F03", "F04"} <= sources.keys(), "missing reference source"
    for source in sources.values():
        if source["access"] in {"public", "subscription"}:
            parsed = urlparse(source["url"])
            assert parsed.scheme == "https" and parsed.netloc, "invalid source URL"
        if source["pages"] is not None:
            assert source["sha256"] is not None, "PDF without source hash"
        if source["review_status"] != "visual_checked" or source["access"] == "subscription":
            assert source["limitations"], "source limitation missing"
    for profile in profiles.values():
        assert set(profile["source_ids"]) <= sources.keys(), "invalid profile source"
        if profile["review_status"] != "visual_checked":
            assert profile["limitations"], "profile limitation missing"
    for variant in data["variants"]:
        assert variant["family_id"] in families, "invalid variant family"
        assert variant["profile_id"] in profiles, "invalid variant profile"
        profile = profiles[variant["profile_id"]]
        for reference in variant["source_refs"]:
            assert reference["source_id"] in sources, "invalid variant source"
            assert reference["source_id"] in profile["source_ids"], "cross-profile source"
            source = sources[reference["source_id"]]
            page = reference["pdf_page"]
            if source["pages"] is not None and reference["review_status"] != "unverified":
                assert page is not None, "PDF locator page missing"
            if page is not None:
                assert source["pages"] is not None and page <= source["pages"], "source page range"
            if reference["review_status"] == "visual_checked":
                assert source["review_status"] == "visual_checked", "unsupported visual review"
                assert profile["review_status"] == "visual_checked", "unverified profile promoted"
        if variant["function"] == "non_asset":
            assert variant["destination"] in {
                "mechanical_relation",
                "network_context",
                "informative_only",
                "unknown_review",
            }, "non-asset destination"
        if variant["function"] == "composite":
            assert variant["destination"] == "composite_review", "composite destination"
        if variant["function"] == "convention":
            assert variant["destination"] in {
                "document_convention",
                "network_context",
                "informative_only",
                "unknown_review",
            }, "convention destination"
    _check_index(data, families)
    _check_totals(data, profiles, families)


def _check_index(data: dict[str, Any], families: dict[str, Any]) -> None:
    entries = data["f02_index"]
    sections = [entry["section"] for entry in entries]
    assert sorted(sections) == list(range(1, 34)), "F02 index coverage"
    covered: set[str] = set()
    for entry in entries:
        assert entry["pdf_page_start"] <= entry["pdf_page_end"], "F02 index page range"
        assert set(entry["family_ids"]) <= families.keys(), "invalid F02 index family"
        covered.update(entry["family_ids"])
        for family_id in entry["family_ids"]:
            locators = [
                ref
                for variant in data["variants"]
                if variant["family_id"] == family_id
                for ref in variant["source_refs"]
                if ref["source_id"] == "F02"
            ]
            assert locators, "F02 family without variants"
            assert all(
                ref["pdf_page"] is not None
                and entry["pdf_page_start"] <= ref["pdf_page"] <= entry["pdf_page_end"]
                for ref in locators
            ), "F02 family outside index locator"
    f02_families = {
        variant["family_id"]
        for variant in data["variants"]
        if any(ref["source_id"] == "F02" for ref in variant["source_refs"])
    }
    assert f02_families == covered, "unindexed F02 family"


def _check_totals(data: dict[str, Any], profiles: dict[str, Any], families: dict[str, Any]) -> None:
    totals = data["totals"]
    assert totals["families"] == len(families), "family total"
    assert totals["variants"] == len(data["variants"]), "variant total"
    for key, entities, field in (
        ("by_profile", profiles, "profile_id"),
        ("by_family", families, "family_id"),
    ):
        rows = totals[key]
        actual = {row["id"]: row["count"] for row in rows}
        assert len(rows) == len(actual), "duplicate total ID"
        counts = Counter(variant[field] for variant in data["variants"])
        expected = {entity_id: counts[entity_id] for entity_id in entities}
        assert actual == expected, f"{key} totals"
    assert all(row["count"] > 0 for row in totals["by_family"]), "family without variants"


def _check_f02_denominator(data: dict[str, Any]) -> None:
    locators = [
        (reference["pdf_page"], reference["locator"])
        for variant in data["variants"]
        for reference in variant["source_refs"]
        if reference["source_id"] == "F02"
    ]
    assert len(locators) == len(set(locators)), "duplicate F02 locator"
    sections = []
    for entry in sorted(data["f02_index"], key=lambda item: item["section"]):
        count = sum(
            variant["family_id"] in entry["family_ids"]
            and any(ref["source_id"] == "F02" for ref in variant["source_refs"])
            for variant in data["variants"]
        )
        sections.append(
            (
                entry["section"],
                entry["title"],
                entry["pdf_page_start"],
                entry["pdf_page_end"],
                count,
            )
        )
    assert tuple(sections) == _F02_SECTIONS, "canonical F02 index and denominator"
    source = next(item for item in data["sources"] if item["id"] == "F02")
    assert source["sha256"] == (
        "0e29f0ea81827c7235d0893c383fc993c78378c51e930b8b8228de82d564ce04"
    ), "canonical F02 source"


def _validate(data: dict[str, Any]) -> None:
    schema = _read_json(_SCHEMA_PATH)
    _check_keywords(schema)
    _check_schema(data, schema, schema)
    _check_integrity(data)
    _check_f02_denominator(data)


@pytest.fixture
def inventory() -> dict[str, Any]:
    return _read_json(_INVENTORY_PATH)


def test_versioned_inventory_has_valid_schema_and_references(inventory: dict[str, Any]) -> None:
    _validate(inventory)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("schema_version",), "99", "const"),
        (("sources", 0, "sha256"), "not-a-hash", "pattern"),
        (("sources", 0, "url"), "http://example.test", "invalid source URL"),
        (("profiles", 0, "automatic_semantic_equivalence"), True, "const"),
        (("profiles", 0, "source_ids"), ["missing-source"], "invalid profile source"),
        (("variants", 0, "owner"), "", "minLength"),
        (("variants", 0, "world"), "unknown", "enum"),
        (("variants", 0, "operating_state"), "unknown", "enum"),
        (("variants", 0, "situation"), "Existente", "type"),
        (("variants", 0, "source_refs"), [], "minItems"),
        (("variants", 0, "family_id"), "missing-family", "invalid variant family"),
        (("variants", 0, "profile_id"), "missing-profile", "invalid variant profile"),
        (
            ("variants", 0, "source_refs", 0, "source_id"),
            "missing-source",
            "invalid variant source",
        ),
        (("variants", 0, "source_refs", 0, "pdf_page"), True, "type"),
        (("variants", 0, "source_refs", 0, "pdf_page"), 10000, "source page range"),
        (("variants", 0, "source_refs", 0, "review_status"), "approved", "enum"),
        (("totals", "variants"), 0, "minimum"),
        (("totals", "families"), 10000, "family total"),
        (("policies", "silence_is_veto"), True, "const"),
        (("policies", "agreement_is_probability"), True, "const"),
        (("policies", "reviewer_reference_is_inference_input"), True, "const"),
    ],
)
def test_inventory_rejects_invalid_values(
    inventory: dict[str, Any], path: tuple[str | int, ...], value: Any, message: str
) -> None:
    modified = deepcopy(inventory)
    target: Any = modified
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(AssertionError, match=message):
        _validate(modified)


@pytest.mark.parametrize("field", ["owner", "destination", "cardinality", "source_refs"])
def test_inventory_rejects_missing_variant_fields(inventory: dict[str, Any], field: str) -> None:
    del inventory["variants"][0][field]

    with pytest.raises(AssertionError, match="required"):
        _validate(inventory)


def test_inventory_rejects_duplicate_ids_across_entity_types(inventory: dict[str, Any]) -> None:
    inventory["variants"][0]["id"] = inventory["sources"][0]["id"]

    with pytest.raises(AssertionError, match="duplicate entity ID"):
        _validate(inventory)


def test_inventory_rejects_source_from_another_profile(inventory: dict[str, Any]) -> None:
    variant = next(
        item for item in inventory["variants"] if item["profile_id"] == "profile-cemig-eo-r3"
    )
    variant["source_refs"][0]["source_id"] = "F04"

    with pytest.raises(AssertionError, match="cross-profile source"):
        _validate(inventory)


@pytest.mark.parametrize("function", ["non_asset", "composite", "convention"])
def test_inventory_rejects_automatic_asset_destination(
    inventory: dict[str, Any], function: str
) -> None:
    variant = next(item for item in inventory["variants"] if item["function"] == function)
    variant["destination"] = "equipment_review"

    with pytest.raises(AssertionError, match="destination"):
        _validate(inventory)


def test_inventory_rejects_stale_profile_total(inventory: dict[str, Any]) -> None:
    inventory["totals"]["by_profile"][0]["count"] += 1

    with pytest.raises(AssertionError, match="by_profile totals"):
        _validate(inventory)


def test_inventory_rejects_duplicate_total_id(inventory: dict[str, Any]) -> None:
    inventory["totals"]["by_family"].append(deepcopy(inventory["totals"]["by_family"][0]))

    with pytest.raises(AssertionError, match="duplicate total ID"):
        _validate(inventory)


def test_inventory_rejects_missing_f02_index_section(inventory: dict[str, Any]) -> None:
    inventory["f02_index"].pop()

    with pytest.raises(AssertionError, match="F02 index coverage"):
        _validate(inventory)


def test_inventory_rejects_variant_outside_its_f02_section(inventory: dict[str, Any]) -> None:
    variant = next(item for item in inventory["variants"] if item["family_id"] == "family-f02-03")
    variant["source_refs"][0]["pdf_page"] = 9

    with pytest.raises(AssertionError, match="F02 family outside index locator"):
        _validate(inventory)


def test_inventory_rejects_duplicate_source_cell_with_distinct_ids(
    inventory: dict[str, Any],
) -> None:
    variants = [item for item in inventory["variants"] if item["family_id"] == "family-f02-03"]
    variants[1]["source_refs"] = deepcopy(variants[0]["source_refs"])

    with pytest.raises(AssertionError, match="duplicate F02 locator"):
        _validate(inventory)


def test_inventory_rejects_variant_loss_even_with_recalculated_totals(
    inventory: dict[str, Any],
) -> None:
    variant = next(item for item in inventory["variants"] if item["family_id"] == "family-f02-03")
    inventory["variants"].remove(variant)
    inventory["totals"]["variants"] -= 1
    for group, key in (("by_profile", "profile_id"), ("by_family", "family_id")):
        for count in inventory["totals"][group]:
            if count["id"] == variant[key]:
                count["count"] -= 1

    with pytest.raises(AssertionError, match="canonical F02 index and denominator"):
        _validate(inventory)


def test_inventory_rejects_unimplemented_schema_keyword() -> None:
    schema = _read_json(_SCHEMA_PATH)
    schema["$defs"]["variant"]["oneOf"] = []

    with pytest.raises(AssertionError, match="unsupported schema keyword"):
        _check_keywords(schema)
