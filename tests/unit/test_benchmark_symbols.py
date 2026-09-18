from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from scripts.symbol_benchmark_evaluator import PROTOCOL, evaluate
from tests.symbol_benchmark_fixtures import (
    FAMILIES,
    FIXTURE_ROOT,
    ROOT,
    build_corpus,
    portable_reference,
    sha256,
    source_sha256,
)

Record = dict[str, Any]


def _occurrence(identity: str = "r1", **fields: Any) -> Record:
    return {
        "id": identity,
        "document_id": "doc",
        "page": 1,
        "layer": "base",
        "family": "family-f02-19",
        "class_id": "ATERRAMENTO",
        "bbox": [0.1, 0.1, 0.3, 0.3],
        "context": "operational",
        "evaluability": "confirmed",
        "situation": "EXISTENTE",
        "quantity": 1,
        "association": "support-1",
        "strata": ["oracle"],
        **fields,
    }


def _reference(*occurrences: Record) -> Record:
    return {
        "schema_version": 1,
        "families": list(FAMILIES),
        "documents": [
            {
                "id": "doc",
                "sha256": "1" * 64,
                "path": "oracle.pdf",
                "split": "development",
                "ancestor_id": "author-1",
                "template_family": "drawing-1",
                "pages": [
                    {"number": number, "width_pt": 400, "height_pt": 300} for number in (1, 2)
                ],
            }
        ],
        "occurrences": list(occurrences),
    }


def _prediction(identity: str, occurrence: Record | None = None, **fields: Any) -> Record:
    source = copy.deepcopy(occurrence or _occurrence())
    source.pop("evaluability", None)
    source.pop("strata", None)
    source.update(id=identity, method_id="A", score=0.88)
    source.update(fields)
    return source


def _outputs(*predictions: Record, methods: tuple[str, ...] = ("A",)) -> Record:
    return {
        "schema_version": 1,
        "methods": [
            {
                "id": method,
                "version": "oracle-v1",
                "algorithm_family": f"oracle-{method}",
                "shared_sources": [],
                "supported_classes": ["ATERRAMENTO", "ABSENT_CLASS"],
            }
            for method in methods
        ],
        "predictions": list(predictions),
        "executions": [],
    }


def _micro(result: Record) -> tuple[int, int, int]:
    micro = result["micro"]
    return micro["tp"], micro["fp"], micro["fn"]


def test_duplicates_are_false_positives_and_never_inflate_true_positives() -> None:
    report = evaluate(_reference(_occurrence()), _outputs(_prediction("p1"), _prediction("p2")))
    result = report["methods"]["A"]
    assert _micro(result) == (1, 1, 0)
    assert len(result["duplicates"]) == 1
    duplicate = result["duplicates"][0]
    assert duplicate["document_id"] == "doc"
    assert duplicate["page"] == 1
    assert duplicate["layer"] == "base"
    assert duplicate["bbox"] == [0.1, 0.1, 0.3, 0.3]


def test_union_recovers_exclusives_even_when_intersection_is_empty() -> None:
    first = _occurrence("left")
    second = _occurrence("right", bbox=[0.6, 0.6, 0.8, 0.8])
    report = evaluate(
        _reference(first, second),
        _outputs(
            _prediction("a", first), _prediction("b", second, method_id="B"), methods=("A", "B")
        ),
    )
    assert _micro(report["methods"]["A"]) == (1, 0, 1)
    assert _micro(report["methods"]["B"]) == (1, 0, 1)
    for composition in ("raw_union", "filtered_union", "final"):
        assert _micro(report["compositions"][composition]) == (2, 0, 0)
    assert _micro(report["compositions"]["intersection_control"]) == (0, 0, 2)
    assert report["complementarity"]["by_method"]["A"]["exclusive_tp_reference_ids"] == ["left"]
    assert any(
        pair["a"] == "A"
        and pair["b"] == "B"
        and pair["a_correct_b_missed_reference_ids"] == ["left"]
        for pair in report["complementarity"]["pairs"]
    )
    assert _micro(report["compositions"]["ablations"]["A"]) == (1, 0, 1)
    assert report["compositions"]["final"]["policy_implemented"] is False


def test_cross_method_equivalence_preserves_observations_and_intramethod_duplicates() -> None:
    report = evaluate(
        _reference(_occurrence()),
        _outputs(
            _prediction("a1"),
            _prediction("a2"),
            _prediction("b1", method_id="B"),
            methods=("A", "B"),
        ),
    )
    union = report["compositions"]["raw_union"]
    assert _micro(union) == (1, 1, 0)
    assert union["input_observation_count"] == 3
    assert union["candidate_count"] == 2
    assert sorted(
        observation for item in union["candidates"] for observation in item["observation_ids"]
    ) == ["a1", "a2", "b1"]
    shared = next(item for item in union["candidates"] if len(item["observations"]) == 2)
    assert shared["score"] is None
    assert "calibrated_probability" not in shared


@pytest.mark.parametrize("locator", [{"page": 2}, {"layer": "annotation"}])
def test_equal_geometry_on_another_page_or_layer_is_not_a_match(locator: Record) -> None:
    ref = _reference(_occurrence())
    prediction = _prediction("elsewhere", **locator)
    result = evaluate(ref, _outputs(prediction))["methods"]["A"]
    assert _micro(result) == (0, 1, 1)
    assert result["false_positives"][0]["id"] == "elsewhere"
    assert result["false_negatives"][0]["id"] == "r1"
    assert result["false_negatives"][0]["bbox"] == ref["occurrences"][0]["bbox"]


def test_neighbors_with_overlapping_boxes_are_distinct_union_candidates() -> None:
    left = _occurrence("left", bbox=[0.1, 0.1, 0.4, 0.4])
    right = _occurrence("right", bbox=[0.3, 0.1, 0.6, 0.4])
    report = evaluate(
        _reference(left, right),
        _outputs(
            _prediction("a", left), _prediction("b", right, method_id="B"), methods=("A", "B")
        ),
    )
    union = report["compositions"]["raw_union"]
    assert _micro(union) == (2, 0, 0)
    assert union["candidate_count"] == 2


def test_maximum_matching_handles_case_where_greedy_loses_a_true_positive() -> None:
    left = _occurrence("left", bbox=[0.1, 0.1, 0.3, 0.3])
    right = _occurrence("right", bbox=[0.2, 0.1, 0.4, 0.3])
    broad = _prediction("a-broad", bbox=[0.15, 0.1, 0.35, 0.3])
    narrow = _prediction("b-narrow", left)
    result = evaluate(_reference(left, right), _outputs(broad, narrow))["methods"]["A"]
    assert _micro(result) == (2, 0, 0)
    assert {(pair["prediction_id"], pair["reference_id"]) for pair in result["matches"]} == {
        ("a-broad", "right"),
        ("b-narrow", "left"),
    }


def test_absent_classes_and_families_have_null_recall_with_zero_denominators() -> None:
    report = evaluate(_reference(_occurrence()), _outputs())
    result = report["methods"]["A"]
    assert len(result["by_family"]) == 33
    assert result["by_family"]["family-f02-01"]["recall"] is None
    assert result["by_family"]["family-f02-01"]["reference_count"] == 0
    assert result["by_class"]["ABSENT_CLASS"]["recall"] is None
    assert result["micro"]["precision"] is None
    assert report["denominators"]["confirmed_operational"] == 1
    assert result["fp_per_page"] == {"value": 0, "page_denominator": 2}


def test_thin_symbols_match_by_endpoints_when_iou_is_zero() -> None:
    thin = _occurrence(bbox=[0.1, 0.2, 0.7, 0.202], trace=[[0.1, 0.201], [0.7, 0.201]])
    prediction = _prediction(
        "thin", thin, bbox=[0.1, 0.21, 0.7, 0.212], trace=[[0.7, 0.211], [0.1, 0.211]]
    )
    result = evaluate(_reference(thin), _outputs(prediction))["methods"]["A"]
    assert _micro(result) == (1, 0, 0)
    geometry = result["matches"][0]["geometry"]
    assert geometry["iou"] == 0
    assert geometry["criterion"] == "thin_endpoints"
    assert geometry["endpoint_distance_normalized"] == pytest.approx(1 / 60)


@pytest.mark.parametrize("box", [[0.1, 0.4, 0.7, 0.402], [0.1, 0.21, 0.4, 0.212]])
def test_thin_symbols_outside_distance_or_length_tolerance_remain_errors(box: list[float]) -> None:
    thin = _occurrence(bbox=[0.1, 0.2, 0.7, 0.202])
    result = evaluate(_reference(thin), _outputs(_prediction("bad", thin, bbox=box)))["methods"][
        "A"
    ]
    assert _micro(result) == (0, 1, 1)


def test_context_controls_and_ambiguities_do_not_enter_certain_positive_denominator() -> None:
    occurrences = [
        _occurrence("positive"),
        _occurrence("legend", bbox=[0.4, 0.1, 0.5, 0.2], context="legend"),
        _occurrence("negative", bbox=[0.6, 0.1, 0.7, 0.2], context="negative"),
        _occurrence("ambiguous", bbox=[0.1, 0.6, 0.2, 0.7], evaluability="ambiguous"),
        _occurrence("unassessable", bbox=[0.4, 0.6, 0.5, 0.7], evaluability="unassessable"),
    ]
    outputs = _outputs(
        *[_prediction(f"p-{item['id']}", item, context="operational") for item in occurrences]
    )
    report = evaluate(_reference(*occurrences), outputs)
    result = report["methods"]["A"]
    assert report["denominators"]["confirmed_operational"] == 1
    assert _micro(result) == (1, 2, 0)
    assert {item["id"] for item in result["unresolved"]} == {"p-ambiguous", "p-unassessable"}
    assert all(item["reason"] == "nonoperational_context" for item in result["false_positives"])


def test_ambiguous_overlap_cannot_steal_confirmed_match_or_hide_duplicate() -> None:
    report = evaluate(
        _reference(_occurrence(), _occurrence("uncertain", evaluability="ambiguous")),
        _outputs(_prediction("p1"), _prediction("p2")),
    )
    result = report["methods"]["A"]
    assert _micro(result) == (1, 1, 0)
    assert result["matches"][0]["reference_id"] == "r1"
    assert result["unresolved"] == []


def test_wrong_class_records_confusion_and_locatable_fp_fn() -> None:
    result = evaluate(
        _reference(_occurrence()),
        _outputs(_prediction("wrong-class", class_id="PARA_RAIOS_MT", family="family-f02-21")),
    )["methods"]["A"]
    assert _micro(result) == (0, 1, 1)
    assert result["confusion"] == [
        {"reference_class": "ATERRAMENTO", "predicted_class": "PARA_RAIOS_MT", "count": 1}
    ]


def test_semantic_metrics_keep_separate_denominators_and_raw_score_is_not_probability() -> None:
    result = evaluate(
        _reference(_occurrence()),
        _outputs(
            _prediction("correct-shape", situation=None, quantity=3, association="support-other")
        ),
    )["methods"]["A"]
    assert _micro(result) == (1, 0, 0)
    for field in ("situation", "quantity", "association"):
        assert result["semantic_accuracy"][field]["denominator"] == 1
        assert result["semantic_accuracy"][field]["correct"] == 0
    assert result["calibration"]["denominator"] == 0
    assert result["calibration"]["brier"] is None
    assert result["calibration"]["ece"] is None
    assert result["document_intervals"]["recall_95"] is None
    assert result["score_curves"][0]["raw_score_threshold"] == 0.88


@pytest.mark.parametrize(
    "field,value",
    [
        ("document_id", "missing"),
        ("page", 99),
        ("layer", "unknown"),
        ("family", "missing"),
        ("method_id", "missing"),
        ("bbox", [0.1, float("nan"), 0.3, 0.3]),
        ("bbox", [0.1, 0.1, float("inf"), 0.3]),
        ("bbox", [0.3, 0.1, 0.1, 0.3]),
        ("score", float("nan")),
        ("trace", [[0.1, 0.1], [float("inf"), 0.3]]),
    ],
)
def test_invalid_prediction_inputs_are_rejected(field: str, value: Any) -> None:
    prediction = _prediction("invalid")
    prediction[field] = value
    with pytest.raises(ValueError):
        evaluate(_reference(_occurrence()), _outputs(prediction))


@pytest.mark.parametrize("collection", ["documents", "occurrences", "methods", "predictions"])
def test_duplicate_ids_are_rejected(collection: str) -> None:
    reference, outputs = _reference(_occurrence()), _outputs(_prediction("p1"))
    target = reference if collection in reference else outputs
    target[collection].append(copy.deepcopy(target[collection][0]))
    with pytest.raises(ValueError, match="duplicate"):
        evaluate(reference, outputs)


@pytest.mark.parametrize("field", ["ancestor_id", "template_family", "sha256"])
def test_partition_leakage_is_rejected_by_ancestry_template_and_content(field: str) -> None:
    reference = _reference(_occurrence())
    original = reference["documents"][0]
    second = {
        **copy.deepcopy(original),
        "id": "second",
        "split": "calibration",
        "ancestor_id": "other-ancestor",
        "template_family": "other-template",
        "sha256": "2" * 64,
    }
    second[field] = original[field]
    reference["documents"].append(second)
    with pytest.raises(ValueError, match="partition leakage"):
        evaluate(reference, _outputs())


def test_reference_and_outputs_are_not_mutated() -> None:
    reference, outputs = _reference(_occurrence()), _outputs(_prediction("p1"))
    before = copy.deepcopy((reference, outputs))
    evaluate(reference, outputs)
    assert (reference, outputs) == before


def test_fixture_generation_is_deterministic_self_contained_and_portable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert not Path("examples").exists()
    first = build_corpus(tmp_path / "first")
    second = build_corpus(tmp_path / "second")
    assert portable_reference(first) == portable_reference(second)
    assert len(first["families"]) == 33
    assert len(first["documents"]) == 4
    assert sum(len(item["pages"]) for item in first["documents"]) == 6
    strata = {tag for item in first["occurrences"] for tag in item["strata"]}
    assert {
        "scale_rotation",
        "color",
        "raster",
        "fragmentation",
        "overlap",
        "annotation",
        "neighbors",
        "critical_legend",
        "critical_glyph",
        "critical_table",
        "critical_fence",
    } <= strata
    assert all(Path(item["path"]).is_relative_to(tmp_path) for item in first["documents"])
    assert all(sha256(Path(item["path"])) == item["sha256"] for item in first["documents"])


def test_development_and_calibration_share_no_ancestor_template_or_pdf(tmp_path: Path) -> None:
    development = build_corpus(tmp_path / "development")
    calibration = build_corpus(tmp_path / "calibration", split="calibration")
    for field in ("ancestor_id", "template_family", "sha256"):
        assert {item[field] for item in development["documents"]}.isdisjoint(
            {item[field] for item in calibration["documents"]}
        )
    report = evaluate(
        {
            **development,
            "documents": development["documents"] + calibration["documents"],
            "occurrences": development["occurrences"] + calibration["occurrences"],
        },
        _outputs(),
    )
    assert report["denominators"]["documents"] == 6


def test_reserve_cannot_be_materialized_or_evaluated_in_e02(tmp_path: Path) -> None:
    output = tmp_path / "reserve"
    with pytest.raises(ValueError, match="sealed"):
        build_corpus(output, split="reserve")
    assert not output.exists()
    reference = _reference(_occurrence())
    reference["documents"][0]["split"] = "reserve"
    with pytest.raises(ValueError, match="sealed"):
        evaluate(reference, _outputs())


def test_fixture_and_evaluator_do_not_import_detectors_or_private_data() -> None:
    for relative in ("tests/symbol_benchmark_fixtures.py", "scripts/symbol_benchmark_evaluator.py"):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        modules.extend(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not any(module and module.startswith("zeny_project_handler") for module in modules)


def test_versioned_partition_manifest_and_opaque_reserve_hashes_are_intact() -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["generator_sha256"] == source_sha256(
        ROOT / "tests/symbol_benchmark_fixtures.py"
    )
    assert {item["split"] for item in manifest["partitions"]} == {
        "development",
        "calibration",
        "reserve",
    }
    ancestry: dict[str, str] = {}
    templates: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for partition in manifest["partitions"]:
        for document in partition["documents"]:
            for collection, key in (
                (ancestry, "ancestor_id"),
                (templates, "template_family"),
                (hashes, "sha256"),
            ):
                assert (
                    collection.setdefault(document[key], partition["split"]) == partition["split"]
                )
    # Do not list, decompress or parse the sealed archive: only the opaque bytes are hashed.
    sealed = manifest["reserve"]
    assert (
        hashlib.sha256((FIXTURE_ROOT / sealed["path"]).read_bytes()).hexdigest() == sealed["sha256"]
    )
    assert sealed["evaluation_status"] == "sealed_until_E16"
    assert sealed["visual_review"] == "not_performed"


def test_prediction_artifact_source_hash_must_match_reference_when_declared() -> None:
    reference = _reference(_occurrence())
    outputs = _outputs(_prediction("p1"))
    outputs["documents"] = [{"id": "doc", "sha256": "2" * 64}]
    with pytest.raises(ValueError, match="hash"):
        evaluate(reference, outputs)
    outputs["documents"][0]["sha256"] = "1" * 64
    assert _micro(evaluate(reference, outputs)["methods"]["A"]) == (1, 0, 0)


def test_degenerate_false_positive_inside_legend_is_attributed_without_becoming_tp() -> None:
    legend = _occurrence("legend", context="legend", strata=["critical_legend"])
    overlapping = _occurrence("informative", context="informative", strata=["informative"])
    prediction = _prediction("stem", bbox=[0.15, 0.2, 0.25, 0.2])
    result = evaluate(_reference(legend, overlapping), _outputs(prediction))["methods"]["A"]
    assert _micro(result) == (0, 1, 0)
    assert result["by_stratum"]["critical_legend"]["fp"] == 1
    assert result["false_positives"][0]["bbox"] == prediction["bbox"]
    matches = result["false_positives"][0]["context_matches"]
    assert {item["reference_id"] for item in matches} == {"legend", "informative"}
    assert all(item["context_only"] for item in matches)
    assert all(item["criterion"] == "context_center_containment" for item in matches)
    assert all(item["geometry"]["iou"] == 0 for item in matches)
    assert all(item["geometry"]["eligible"] is False for item in matches)


def test_partial_reference_cannot_produce_global_precision_or_recall() -> None:
    reference = _reference(_occurrence())
    reference["annotation_scope"] = "partial"
    with pytest.raises(ValueError, match="complete"):
        evaluate(reference, _outputs(_prediction("p1")))
    reference["annotation_scope"] = "complete"
    assert _micro(evaluate(reference, _outputs(_prediction("p1")))["methods"]["A"]) == (1, 0, 0)


def test_public_reference_hashes_match_generated_pdfs_and_frozen_protocol(tmp_path: Path) -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    protocol_bytes = (
        json.dumps(PROTOCOL, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()
    assert hashlib.sha256(protocol_bytes).hexdigest() == manifest["protocol_sha256"]
    for partition in manifest["partitions"]:
        if partition["split"] == "reserve":
            continue
        reference_path = FIXTURE_ROOT / partition["reference_path"]
        assert sha256(reference_path) == partition["reference_sha256"]
        expected = json.loads(reference_path.read_text(encoding="utf-8"))
        generated = build_corpus(tmp_path / partition["split"], split=partition["split"])
        assert portable_reference(generated) == expected


def test_runner_recurses_all_pages_and_keeps_equal_content_paths_distinct(tmp_path: Path) -> None:
    from scripts.symbol_benchmark_runner import run_examples

    corpus = build_corpus(tmp_path / "corpus")
    original = Path(corpus["documents"][0]["path"]).read_bytes()
    root = tmp_path / "examples"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (root / "copy.pdf").write_bytes(original)
    (nested / "copy.PDF").write_bytes(original)
    manifest = run_examples(root, tmp_path / "run")
    assert manifest["completed"] is True
    assert manifest["counts"]["pdfs"] == 2
    assert manifest["counts"]["pages_discovered"] == 4
    assert manifest["counts"]["pages_attempted"] == 4
    assert len({item["id"] for item in manifest["documents"]}) == 2
    assert len({item["source_before"]["sha256"] for item in manifest["documents"]}) == 1
    assert all(item["source_unchanged"] for item in manifest["documents"])
    assert "not performed" in manifest["visual_review"]


def test_runner_records_unreadable_source_and_continues_other_pdfs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import symbol_benchmark_runner as runner

    corpus = build_corpus(tmp_path / "corpus")
    original = Path(corpus["documents"][0]["path"]).read_bytes()
    root = tmp_path / "examples"
    root.mkdir()
    (root / "a-denied.pdf").write_bytes(original)
    (root / "b-valid.pdf").write_bytes(original)
    original_hash = runner.file_sha256

    def hash_with_denied_source(path: Path) -> str:
        if path.name == "a-denied.pdf":
            raise PermissionError("injected source read failure")
        return original_hash(path)

    monkeypatch.setattr(runner, "file_sha256", hash_with_denied_source)
    manifest = runner.run_examples(root, tmp_path / "run")
    assert manifest["completed"] is False
    assert manifest["counts"]["pdfs"] == 2
    assert manifest["counts"]["documents_failed"] == 1
    assert manifest["counts"]["pages_attempted"] == 2
    assert [item["status"] for item in manifest["documents"]] == ["failed", "executed"]
    assert "PermissionError" in manifest["documents"][0]["failures"][0]["reason"]


def test_runner_page_failure_preserves_manifest_and_attempts_following_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import symbol_benchmark_runner as runner

    from zeny_project_handler.adapters.analysis import pymupdf_symbols

    corpus = build_corpus(tmp_path / "corpus")
    source = Path(corpus["documents"][0]["path"])
    attempted: list[int] = []

    def detector_with_page_failure(page: Any, number: int) -> tuple[Any, ...]:
        attempted.append(number)
        if number == 1:
            raise RuntimeError("injected detector failure")
        return ()

    monkeypatch.setattr(pymupdf_symbols, "_extract_symbolic_equipment", detector_with_page_failure)
    document, predictions, executions = runner.infer_pdf(source, "opaque-id")
    assert attempted == [1, 2]
    assert predictions == []
    assert document["status"] == "failed"
    assert document["source_unchanged"] is True
    assert [page["status"] for page in document["pages"]] == ["failed", "executed"]
    assert [item["status"] for item in executions if item["layer"] == "base"] == [
        "failed",
        "executed",
    ]


def test_empty_examples_are_explicit_and_do_not_claim_completion(tmp_path: Path) -> None:
    from scripts.symbol_benchmark_runner import run_examples

    manifest = run_examples(tmp_path / "absent", tmp_path / "run")
    assert manifest["status"] == "no_examples"
    assert manifest["completed"] is False
    assert manifest["discovery_root_exists"] is False
    assert manifest["counts"]["pdfs"] == 0
    assert manifest["counts"]["pages_attempted"] == 0


def test_synthetic_runner_reads_reference_only_after_predictions_are_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import symbol_benchmark_runner as runner

    monkeypatch.chdir(tmp_path)
    assert not Path("examples").exists()
    output = tmp_path / "synthetic-run"
    original_read = Path.read_text
    original_infer = runner.infer_pdf
    inference_inputs: list[tuple[Path, str]] = []
    reference_read_after_inference: list[int] = []

    def infer_only_pdf_and_id(
        source: Path, document_id: str
    ) -> tuple[Record, list[Record], list[Record]]:
        # The callable intentionally has no channel for GT, expected classes or ROIs.
        assert source.suffix == ".pdf"
        inference_inputs.append((source, document_id))
        return original_infer(source, document_id)

    def audited_read(path: Path, *args: Any, **kwargs: Any) -> str:
        if path == output / "reference.json":
            assert len(inference_inputs) == 4
            predictions = json.loads(original_read(output / "predictions.json", encoding="utf-8"))
            assert len(predictions["executions"]) == 12
            reference_read_after_inference.append(len(inference_inputs))
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(runner, "infer_pdf", infer_only_pdf_and_id)
    monkeypatch.setattr(Path, "read_text", audited_read)
    result = runner.run_synthetic(output)
    assert reference_read_after_inference
    assert result["manifest"]["completed"] is True
    assert result["report"]["denominators"]["families"] == 33
    assert result["report"]["denominators"]["pages"] == 6
    assert len(inference_inputs) == 4
