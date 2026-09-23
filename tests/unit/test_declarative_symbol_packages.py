# mypy: disable-error-code="no-untyped-call"
"""E07: paridade dos pacotes declarativos com o inventário E01.

Os testes de desenho usam apenas PDFs autorais. Uma variante pendente é registrada,
mas nunca conta como uma variante reconhecida pelo runner.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from copy import deepcopy
from importlib import resources
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from scripts.symbol_benchmark_runner import _package_prediction
from tests.fixtures.declarative_symbols.corpus import (
    ENABLED_CASES,
    EnabledCase,
    build_enabled_corpus,
    draw_north_negative,
    draw_symbol,
    negative_kinds,
)

from zeny_project_handler.domain.enums import EstadoMetodoSimbolos

_ROOT = Path(__file__).resolve().parents[2]
_INVENTORY = _ROOT / "docs/data/inventario-simbologia-v1.json"
_PACKAGES = _ROOT / "src/zeny_project_handler/adapters/analysis/symbol_packages"
_SCHEMA = _ROOT / "docs/schemas/pacotes-simbologia.schema.json"

# Denominador independente do registro de pacotes. f02-18 inclui apenas os quatro
# reguladores atribuídos a E07; os outros transformadores continuam em E05.
_FAMILY_COUNTS = {
    "family-f02-03": 25,
    "family-f02-04": 1,
    "family-f02-05": 13,
    "family-f02-06": 9,
    "family-f02-07": 5,
    "family-f02-08": 6,
    "family-f02-09": 4,
    "family-f02-10": 5,
    "family-f02-11": 3,
    "family-f02-12": 3,
    "family-f02-13": 6,
    "family-f02-16": 22,
    "family-f02-17": 17,
    "family-f02-18": 4,
    "family-f02-19": 13,
    "family-f02-20": 40,
    "family-f02-21": 7,
    "family-f02-22": 5,
    "family-f02-23": 16,
    "family-f02-26": 1,
    "family-f02-27": 13,
    "family-f02-28": 4,
    "family-f02-29": 1,
    "family-f02-30": 1,
    "family-f02-31": 1,
    "family-f02-32": 51,
    "family-f02-33": 89,
}

_ENABLED_IDS = tuple(case.variant_id for case in ENABLED_CASES)
_CASE_BY_ID = {case.variant_id: case for case in ENABLED_CASES}


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _inventory_variants() -> dict[str, dict[str, Any]]:
    inventory = _read_json(_INVENTORY)
    selected = {
        variant["id"]: variant
        for variant in inventory["variants"]
        if variant["owner_stage"] == "E07"
    }
    assert len(selected) == 365
    assert Counter(v["family_id"] for v in selected.values()) == _FAMILY_COUNTS
    return selected


def _packages() -> tuple[dict[str, Any], ...]:
    paths = sorted(_PACKAGES.glob("family-f02-*.json"))
    assert len(paths) == 27, "E07 needs one package file per family"
    packages = tuple(_read_json(path) for path in paths)
    for path, package in zip(paths, packages, strict=True):
        assert path.stem == package["family_id"]
    return packages


def test_e07_package_matrix_preserves_all_e01_variants_and_sources() -> None:
    inventory = _inventory_variants()
    packages = _packages()
    assert _SCHEMA.is_file()
    assert _read_json(_SCHEMA)["properties"]["schema_version"]["const"] == 1

    seen: list[str] = []
    for package in packages:
        assert package["schema_version"] == 1
        assert package["family_id"] in _FAMILY_COUNTS
        assert package["profile_id"] == "profile-cemig-eo-r3"
        assert package["source_id"] == "F02"
        assert package["variants"]
        for variant in package["variants"]:
            variant_id = variant["id"]
            seen.append(variant_id)
            assert variant_id in inventory, f"E07 package contains non-E07 variant: {variant_id}"
            original = inventory[variant_id]
            assert original["family_id"] == package["family_id"]
            assert original["profile_id"] == package["profile_id"]
            assert original["source_refs"] == [variant["source_ref"]]
            assert variant["class_code"] == original["class_code"]
            assert variant["destination"] == original["destination"]
            expected_role = (
                "informative"
                if original["destination"] in {"informative_only", "document_convention"}
                else "operational"
            )
            assert variant["role"] == expected_role
            recognition = variant["recognition"]
            assert recognition["status"] in {"enabled", "pending"}
            assert recognition["negative_examples"], variant_id
            assert all(
                isinstance(example, str) and example.strip()
                for example in recognition["negative_examples"]
            ), variant_id
            if recognition["status"] == "enabled":
                assert recognition.get("grammar"), variant_id
                assert "reason" not in recognition, variant_id
            else:
                assert recognition.get("reason", "").strip(), variant_id
                assert "grammar" not in recognition, variant_id

    assert len(seen) == 365
    assert len(set(seen)) == 365, "duplicate variant is not extra coverage"
    assert set(seen) == inventory.keys(), "a pending or missing E01 ID cannot disappear"
    assert Counter(inventory[v]["family_id"] for v in seen) == _FAMILY_COUNTS


def test_enabled_status_is_distinct_from_registered_coverage() -> None:
    packages = _packages()
    all_variants = [variant for package in packages for variant in package["variants"]]
    enabled = {v["id"] for v in all_variants if v["recognition"]["status"] == "enabled"}
    pending = {v["id"] for v in all_variants if v["recognition"]["status"] == "pending"}
    assert enabled
    assert pending
    assert enabled == set(_ENABLED_IDS), "new enabled grammar needs its own positive/negative case"
    assert enabled.isdisjoint(pending)
    assert len(enabled | pending) == 365
    assert all(v["recognition"].get("grammar") for v in all_variants if v["id"] in enabled)
    assert all(not v["recognition"].get("grammar") for v in all_variants if v["id"] in pending)


def test_package_json_files_are_importable_resources() -> None:
    folder = resources.files("zeny_project_handler.adapters.analysis.symbol_packages")
    names = {item.name for item in folder.iterdir() if item.name.endswith(".json")}
    assert names == {f"{family_id}.json" for family_id in _FAMILY_COUNTS}


def test_coverage_audit_reports_missing_variant_even_if_package_loads(tmp_path: Path) -> None:
    from scripts.audit_symbol_packages import audit

    assert audit()["errors"] == []
    shutil.copytree(_PACKAGES, tmp_path / "packages")
    package_path = tmp_path / "packages/family-f02-30.json"
    package = _read_json(package_path)
    package["variants"] = []
    package_path.write_text(json.dumps(package), encoding="utf-8")
    report = audit(package_dir=tmp_path / "packages")
    assert "missing variant: cemig-eo-r3-s30-v001" in report["errors"]
    assert report["complete_recognition"] is False


@pytest.mark.parametrize("field", ["family_id", "source_id", "variants"])
def test_package_schema_rejects_missing_required_fields(tmp_path: Path, field: str) -> None:
    from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes

    package = _packages()[0]
    path = tmp_path / f"{package['family_id']}.json"
    path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    assert len(carregar_pacotes(packages_dir=tmp_path)) == 1
    del package[field]
    path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        carregar_pacotes(packages_dir=tmp_path)


def _one_variant_package(variant_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    for package in _packages():
        for variant in package["variants"]:
            if variant["id"] == variant_id:
                return {**package, "variants": [variant]}, variant
    raise AssertionError(f"variant absent from packages: {variant_id}")


def _author_pdf(path: Path, case: EnabledCase, *, negative: str = "") -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=300, height=300)
        if negative == "north":
            draw_north_negative(page)
        else:
            draw_symbol(page, case, negative=negative)
        document.save(path)


def _observe_page(page: pymupdf.Page, pdf_sha256: str, packages: tuple[dict[str, Any], ...]) -> Any:
    from zeny_project_handler.adapters.analysis.declarative_symbols import observar_pacotes

    return observar_pacotes(
        page,
        documento_id="e07-author-test",
        documento_sha256=pdf_sha256,
        pagina_numero=page.number + 1,
        pacotes=packages,
    )


def _observe(path: Path, packages: tuple[dict[str, Any], ...]) -> Any:
    with pymupdf.open(path) as document:
        return _observe_page(document[0], hashlib.sha256(path.read_bytes()).hexdigest(), packages)


@pytest.mark.parametrize("variant_id", _ENABLED_IDS)
def test_each_enabled_grammar_finds_its_authored_positive(tmp_path: Path, variant_id: str) -> None:
    package, variant = _one_variant_package(variant_id)
    path = tmp_path / "positive.pdf"
    _author_pdf(path, _CASE_BY_ID[variant_id])

    result = _observe(path, (package,))
    assert result.completo
    assert result.perfil.metodo_id == "declarative-vector-packages"
    matching = [
        observation
        for observation in result.observacoes
        if dict(observation.atributos).get("variante_inventario") == variant_id
    ]
    assert len(matching) == 1, variant_id
    observation = matching[0]
    assert observation.fonte.documento_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert observation.score_bruto is None
    assert dict(observation.atributos)["destino"] == variant["destination"]
    assert dict(observation.atributos)["papel"] == variant["role"]


@pytest.mark.parametrize("variant_id", _ENABLED_IDS)
def test_each_enabled_grammar_rejects_authored_near_misses(tmp_path: Path, variant_id: str) -> None:
    package, variant = _one_variant_package(variant_id)
    case = _CASE_BY_ID[variant_id]
    assert variant["recognition"]["grammar"]["kind"] == case.kind
    for index, negative in enumerate(negative_kinds(case)):
        path = tmp_path / f"negative-{index}.pdf"
        _author_pdf(path, case, negative=negative)
        result = _observe(path, (package,))
        assert not any(
            dict(observation.atributos).get("variante_inventario") == variant_id
            for observation in result.observacoes
        ), (variant_id, negative)


def test_enabled_corpus_has_explicit_per_package_positive_and_negative_gates(
    tmp_path: Path,
) -> None:
    from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes

    path = tmp_path / "e07-enabled.pdf"
    reference = build_enabled_corpus(path)
    assert reference["pdf_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert {row["variant_id"] for row in reference["cases"]} == set(_ENABLED_IDS)
    packages = carregar_pacotes()
    assert len(packages) == 27
    counts: Counter[str] = Counter()
    with pymupdf.open(path) as document:
        assert len(document) == reference["pages"] == len(reference["cases"])
        for row in reference["cases"]:
            result = _observe_page(document[row["page"] - 1], reference["pdf_sha256"], packages)
            actual = {dict(item.atributos)["variante_inventario"] for item in result.observacoes}
            assert actual == set(row["expected_variant_ids"]), row
            counts[row["family_id"]] += row["stratum"] == "positive"
    assert counts == Counter(case.family_id for case in ENABLED_CASES)
    alternate_fill_rows = [row for row in reference["cases"] if row["stratum"] == "wrong_fill"]
    assert len(alternate_fill_rows) == 2
    assert all(row["expected_variant_ids"] != [row["variant_id"]] for row in alternate_fill_rows)


def test_new_family_is_loaded_and_observed_only_from_data(tmp_path: Path) -> None:
    from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes

    package, _ = _one_variant_package("cemig-eo-r3-s30-v001")
    custom = json.loads(json.dumps(package))
    custom["family_id"] = "family-custom-01"
    custom["profile_id"] = "profile-author-test"
    custom["source_id"] = "AUTHOR-TEST"
    custom_variant = custom["variants"][0]
    custom_variant["id"] = "author-cp-001"
    custom_variant["class_code"] = "AUTORAL_CP"
    custom_variant["source_ref"] = {
        "source_id": "AUTHOR-TEST",
        "pdf_page": 1,
        "locator": "author drawing 1",
        "review_status": "synthetic_fixture",
    }
    package_path = tmp_path / "family-custom-01.json"
    package_path.write_text(json.dumps(custom), encoding="utf-8")
    loaded = carregar_pacotes(packages_dir=tmp_path)
    assert len(loaded) == 1
    path = tmp_path / "custom-positive.pdf"
    _author_pdf(path, _CASE_BY_ID["cemig-eo-r3-s30-v001"])
    result = _observe(path, loaded)
    assert any(
        dict(observation.atributos).get("variante_inventario") == "author-cp-001"
        for observation in result.observacoes
    )


def test_pending_only_families_are_out_of_domain_even_when_a_frame_matches(
    tmp_path: Path,
) -> None:
    from zeny_project_handler.adapters.analysis.declarative_symbols import perfil_pacotes

    path = tmp_path / "cp.pdf"
    _author_pdf(path, _CASE_BY_ID["cemig-eo-r3-s30-v001"])
    pending_only = [
        package
        for package in _packages()
        if all(v["recognition"]["status"] == "pending" for v in package["variants"])
    ]
    assert len(pending_only) == 17
    for package in pending_only:
        assert perfil_pacotes((package,)).classes_suportadas == ()
        result = _observe(path, (package,))
        assert not result.observacoes, package["family_id"]
        assert result.coberturas[0].estado is EstadoMetodoSimbolos.FORA_DOMINIO


def test_exclusive_and_adjacent_symbols_survive_other_package_silence(tmp_path: Path) -> None:
    cp_package, _ = _one_variant_package("cemig-eo-r3-s30-v001")
    cs_package, _ = _one_variant_package("cemig-eo-r3-s31-v001")
    path = tmp_path / "exclusive.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        page.draw_rect(pymupdf.Rect(60, 110, 108, 158), color=(0, 0, 0), width=1)
        page.insert_text((67, 139), "CP", fontsize=11)
        document.save(path)
    result = _observe(path, (cp_package, cs_package))
    assert [dict(obs.atributos)["variante_inventario"] for obs in result.observacoes] == [
        "cemig-eo-r3-s30-v001"
    ]

    adjacent = tmp_path / "adjacent.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        for x, label in ((60, "CP"), (112, "CS")):
            page.draw_rect(pymupdf.Rect(x, 110, x + 48, 158), color=(0, 0, 0), width=1)
            page.insert_text((x + 7, 139), label, fontsize=11)
        document.save(adjacent)
    result = _observe(adjacent, (cp_package, cs_package))
    assert {dict(obs.atributos)["variante_inventario"] for obs in result.observacoes} == {
        "cemig-eo-r3-s30-v001",
        "cemig-eo-r3-s31-v001",
    }


def test_recognized_informative_symbol_remains_review_only_context(tmp_path: Path) -> None:
    from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes

    package, _ = _one_variant_package("cemig-eo-r3-s30-v001")
    custom = json.loads(json.dumps(package))
    custom["family_id"] = "family-author-north"
    custom["profile_id"] = "profile-author-test"
    custom["source_id"] = "AUTHOR-TEST"
    variant = custom["variants"][0]
    variant["id"] = "author-north-001"
    variant["class_code"] = "NORTE_INFORMATIVO"
    variant["role"] = "informative"
    variant["destination"] = "informative_only"
    variant["source_ref"] = {
        "source_id": "AUTHOR-TEST",
        "pdf_page": 1,
        "locator": "author north marker",
        "review_status": "synthetic_fixture",
    }
    variant["recognition"]["grammar"]["label"] = "N"
    (tmp_path / "family-author-north.json").write_text(json.dumps(custom), encoding="utf-8")
    loaded = carregar_pacotes(packages_dir=tmp_path)
    path = tmp_path / "north-in-frame.pdf"
    _author_pdf(
        path,
        EnabledCase("author-north-001", "family-author-north", "label_in_frame", "rectangle", "N"),
    )
    result = _observe(path, loaded)
    assert len(result.observacoes) == 1
    prediction = _package_prediction(result.observacoes[0], "author-document")
    assert prediction["context"] == "informative"
    assert prediction["review_required"] is True
    assert prediction["quantity"] is None
    assert prediction["association"] is None
    assert prediction["provenance"]["role"] == "informative"


def test_legend_sample_keeps_unknown_context_and_requires_review(tmp_path: Path) -> None:
    cp_package, _ = _one_variant_package("cemig-eo-r3-s30-v001")
    path = tmp_path / "legend-sample.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=300, height=300)
        page.insert_text((40, 60), "LEGENDA", fontsize=12)
        page.draw_rect(pymupdf.Rect(110, 110, 158, 158), color=(0, 0, 0), width=1)
        page.insert_text((116, 139), "CP", fontsize=11)
        document.save(path)
    result = _observe(path, (cp_package,))
    assert len(result.observacoes) == 1
    prediction = _package_prediction(result.observacoes[0], "author-legend")
    assert prediction["provenance"]["reported_context"] == "unknown"
    assert prediction["review_required"] is True
    assert prediction["quantity"] is None
    assert prediction["association"] is None


def test_benchmark_uses_one_package_snapshot_and_reports_configuration_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.symbol_benchmark_runner as runner

    from zeny_project_handler.adapters.analysis import declarative_symbols

    path = tmp_path / "cp.pdf"
    _author_pdf(path, _CASE_BY_ID["cemig-eo-r3-s30-v001"])
    original = declarative_symbols.carregar_pacotes()
    changed = deepcopy(original)
    package = next(p for p in changed if p["family_id"] == "family-f02-30")
    package["variants"][0]["recognition"]["grammar"]["label"] = "ZZ"
    snapshots = iter((original, changed))
    monkeypatch.setattr(declarative_symbols, "carregar_pacotes", lambda: next(snapshots))

    output = tmp_path / "run"
    manifest = runner._run([(path, "author-cp")], output, mode="synthetic", include_packages=True)
    predictions = _read_json(output / "predictions.json")["predictions"]
    assert any(
        row.get("method_id") == "declarative-vector-packages"
        and row["provenance"]["variant_id"] == "cemig-eo-r3-s30-v001"
        for row in predictions
    )
    assert manifest["package_configuration_unchanged"] is False
    assert manifest["completed"] is False
    assert manifest["status"] == "failed"


def test_unknown_fallback_requires_explicit_matching_region_and_has_no_known_class(
    tmp_path: Path,
) -> None:
    from zeny_project_handler.adapters.analysis.declarative_symbols import (
        carregar_pacotes,
        observar_pacotes,
    )

    path = tmp_path / "unmatched-frame.pdf"
    frame = pymupdf.Rect(110, 110, 158, 158)
    with pymupdf.open() as document:
        page = document.new_page(width=300, height=300)
        page.draw_rect(frame, color=(0, 0, 0), width=1)
        document.save(path)
    packages = carregar_pacotes()
    with pymupdf.open(path) as document:
        page = document[0]
        base = observar_pacotes(
            page,
            documento_id="author-unknown",
            documento_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            pagina_numero=1,
            pacotes=packages,
        )
        assert not base.observacoes
        result = observar_pacotes(
            page,
            documento_id="author-unknown",
            documento_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            pagina_numero=1,
            pacotes=packages,
            regioes_desconhecidas=(frame,),
        )
        assert len(result.observacoes) == 1
        unknown = result.observacoes[0]
        assert all(alternative.classe is None for alternative in unknown.alternativas)
        assert dict(unknown.atributos)["papel"] == "unknown"
        assert "variante_inventario" not in dict(unknown.atributos)
        with pytest.raises(ValueError, match="compact closed vector frame"):
            observar_pacotes(
                page,
                documento_id="author-unknown",
                documento_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                pagina_numero=1,
                pacotes=packages,
                regioes_desconhecidas=(pymupdf.Rect(10, 10, 50, 50),),
            )


def test_extended_drawing_clip_without_rect_does_not_crash_or_emit_symbol() -> None:
    from zeny_project_handler.adapters.analysis.declarative_symbols import (
        carregar_pacotes,
        observar_pacotes,
    )

    with pymupdf.open() as document:
        page = document.new_page(width=300, height=300)
        page.draw_oval(pymupdf.Rect(110, 110, 158, 158), color=(0, 0, 0), width=1)
        curve = dict(page.get_drawings(extended=True)[0])
        curve["type"] = "clip"
        curve["rect"] = None

        class ClipPage:
            rect = page.rect

            def get_drawings(self, *, extended: bool) -> list[dict[str, Any]]:
                assert extended
                return [curve]

            def get_text(self, kind: str) -> list[tuple[object, ...]]:
                assert kind == "words"
                return []

        result = observar_pacotes(
            ClipPage(),
            documento_id="author-clip",
            documento_sha256="a" * 64,
            pagina_numero=1,
            pacotes=carregar_pacotes(),
        )
        assert not result.observacoes


def test_extended_drawing_ellipse_without_rect_keeps_valid_match() -> None:
    from zeny_project_handler.adapters.analysis.declarative_symbols import observar_pacotes

    package, _ = _one_variant_package("cemig-eo-r3-s29-v001")
    with pymupdf.open() as document:
        page = document.new_page(width=300, height=300)
        page.draw_oval(pymupdf.Rect(110, 110, 158, 158), color=(0, 0, 0), width=1)
        page.insert_text((116, 139), "M", fontsize=11)

        class NoRectPage:
            rect = page.rect
            rotation_matrix = page.rotation_matrix
            derotation_matrix = page.derotation_matrix

            def get_drawings(self, *, extended: bool) -> list[dict[str, Any]]:
                drawings: list[dict[str, Any]] = page.get_drawings(extended=extended)
                for drawing in drawings:
                    drawing["rect"] = None
                return drawings

            def get_text(self, kind: str) -> Any:
                return page.get_text(kind)

        result = observar_pacotes(
            NoRectPage(),
            documento_id="author-ellipse",
            documento_sha256="b" * 64,
            pagina_numero=1,
            pacotes=(package,),
        )
        assert [dict(item.atributos)["variante_inventario"] for item in result.observacoes] == [
            "cemig-eo-r3-s29-v001"
        ]


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "recognized"), ("negative_examples", []), ("reason", "")],
)
def test_package_schema_rejects_false_or_unverifiable_status(
    tmp_path: Path, field: str, value: object
) -> None:
    from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes

    package = next(
        package
        for package in _packages()
        if any(v["recognition"]["status"] == "pending" for v in package["variants"])
    )
    path = tmp_path / f"{package['family_id']}.json"
    path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    assert len(carregar_pacotes(packages_dir=tmp_path)) == 1
    variant = next(v for v in package["variants"] if v["recognition"]["status"] == "pending")
    variant["recognition"][field] = value
    path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        carregar_pacotes(packages_dir=tmp_path)


@pytest.mark.parametrize("field", ["schema_version", "pdf_page"])
def test_package_loader_rejects_boolean_for_integer_schema_fields(
    tmp_path: Path, field: str
) -> None:
    from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes

    package, _ = _one_variant_package("cemig-eo-r3-s30-v001")
    path = tmp_path / f"{package['family_id']}.json"
    path.write_text(json.dumps(package), encoding="utf-8")
    assert len(carregar_pacotes(packages_dir=tmp_path)) == 1
    if field == "schema_version":
        package[field] = True
    else:
        package["variants"][0]["source_ref"][field] = True
    path.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(ValueError):
        carregar_pacotes(packages_dir=tmp_path)


@pytest.mark.parametrize(
    ("variant_id", "field", "value"),
    [
        ("cemig-eo-r3-s06-v001", "max_aspect", True),
        ("cemig-eo-r3-s06-v001", "empty_interior", False),
        ("cemig-eo-r3-s07-v001", "fill", "unknown"),
        ("cemig-eo-r3-s23-v002", "nested_frame", False),
        ("cemig-eo-r3-s23-v002", "inner_fill", "blue"),
    ],
)
def test_new_grammar_loader_rejects_values_outside_draft202012_schema(
    tmp_path: Path, variant_id: str, field: str, value: object
) -> None:
    from zeny_project_handler.adapters.analysis.declarative_symbols import carregar_pacotes

    package, variant = _one_variant_package(variant_id)
    path = tmp_path / f"{package['family_id']}.json"
    path.write_text(json.dumps(package), encoding="utf-8")
    assert len(carregar_pacotes(packages_dir=tmp_path)) == 1
    variant["recognition"]["grammar"][field] = value
    path.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(ValueError):
        carregar_pacotes(packages_dir=tmp_path)
