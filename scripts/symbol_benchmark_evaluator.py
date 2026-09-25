"""Independent, detector-free evaluator for the frozen E02 symbol protocol.

All geometry is normalized to the displayed page. Ground truth is used only for
measurement, never for generating the union. This is not a production reconciler.
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from copy import deepcopy
from hashlib import sha256
from typing import Any

Record = dict[str, Any]
PROTOCOL: Record = {
    "id": "symbols-e02-v1",
    "iou_min": 0.5,
    "thin_axis_ratio_max": 0.15,
    "thin_endpoint_distance_max": 0.15,
    "thin_length_ratio_min": 0.70,
    "matching": "maximum cardinality one-to-one; document/page/layer/class",
    "distance_space": "normalized page coordinates; x/y each range [0,1], not PDF points",
    "positive_context": "confirmed operational occurrences",
    "negative_context_attribution": (
        "geometry match or candidate center inside explicit control ROI; diagnostic only"
    ),
    "union": "exact cross-method equivalence; retain within-method duplicates",
    "score": "raw score, not probability; no cross-method thresholding",
    "calibration_min_samples": 30,
    "document_bootstrap_min_ancestors": 5,
    "document_bootstrap_seed": 0,
    "document_bootstrap_repetitions": 500,
}


def _unique(records: list[Record], label: str) -> dict[str, Record]:
    result: dict[str, Record] = {}
    for item in records:
        identity = item.get("id")
        if not isinstance(identity, str) or not identity:
            raise ValueError(f"{label}: missing/non-string id")
        if identity in result:
            raise ValueError(f"{label}: duplicate id {identity}")
        result[identity] = item
    return result


def _finite(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _geometry(item: Record) -> None:
    box = item.get("bbox")
    if not isinstance(box, list | tuple) or len(box) != 4:
        raise ValueError(f"{item['id']}: bbox requires four coordinates")
    if not all(_finite(value) and 0 <= value <= 1 for value in box):
        raise ValueError(f"{item['id']}: bbox must be finite and normalized")
    if box[0] > box[2] or box[1] > box[3] or box[:2] == box[2:]:
        raise ValueError(f"{item['id']}: inverted or point bbox")
    trace = item.get("trace")
    if trace is not None and (
        not isinstance(trace, list | tuple)
        or len(trace) < 2
        or any(
            not isinstance(point, list | tuple)
            or len(point) != 2
            or not all(_finite(value) and 0 <= value <= 1 for value in point)
            for point in trace
        )
    ):
        raise ValueError(f"{item['id']}: invalid trace")


def _validate(reference: Record, outputs: Record, *, allow_reserve: bool = False) -> None:
    if reference.get("schema_version") != 1 or outputs.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    if reference.get("annotation_scope", "complete") != "complete":
        raise ValueError(
            "partial reference cannot produce global FP/recall metrics; "
            "use regional/prediction audit until annotation_scope is complete"
        )
    families = reference.get("families", [])
    if (
        not isinstance(families, list)
        or not all(isinstance(item, str) and item for item in families)
        or len(families) != len(set(families))
    ):
        raise ValueError("families must be unique nonempty strings")
    documents = _unique(reference["documents"], "documents")
    if "documents" in outputs:
        output_documents = _unique(outputs["documents"], "prediction documents")
        if set(output_documents) != set(documents):
            raise ValueError("prediction document inventory differs from reference")
        for document_identity, document in output_documents.items():
            if document.get("sha256") != documents[document_identity].get("sha256"):
                raise ValueError(f"prediction source hash mismatch: {document_identity}")
    methods = _unique(outputs["methods"], "methods")
    occurrences = _unique(reference["occurrences"], "occurrences")
    predictions = _unique(outputs["predictions"], "predictions")
    partitions: dict[tuple[str, str], str] = {}
    pages: dict[str, set[int]] = {}
    splits: set[str] = set()
    for document in documents.values():
        split = document.get("split")
        if split == "reserve" and not allow_reserve:
            raise ValueError("reserve is sealed until E16; evaluation refused")
        if split not in {"development", "calibration", "reserve"}:
            raise ValueError(f"{document['id']}: invalid split")
        splits.add(split)
        for field in ("ancestor_id", "template_family", "sha256"):
            identity = document.get(field)
            if not isinstance(identity, str) or not identity:
                raise ValueError(f"{document['id']}: missing {field}")
            key = field, identity
            if key in partitions and partitions[key] != split:
                raise ValueError(f"partition leakage: {field} {identity}")
            partitions[key] = split
        if not isinstance(document.get("path"), str):
            raise ValueError(f"{document['id']}: missing path")
        page_numbers = []
        for page in document["pages"]:
            number = page["number"]
            if not isinstance(number, int) or isinstance(number, bool) or number < 1:
                raise ValueError("page numbers must be positive integers")
            if not all(_finite(page[key]) and page[key] > 0 for key in ("width_pt", "height_pt")):
                raise ValueError("page dimensions must be positive and finite")
            page_numbers.append(number)
        if len(set(page_numbers)) != len(page_numbers):
            raise ValueError(f"{document['id']}: duplicate page")
        pages[document["id"]] = set(page_numbers)
    if allow_reserve and splits != {"reserve"}:
        raise ValueError("E16 reserve evaluation requires only reserve documents")
    for method in methods.values():
        for field in ("version", "algorithm_family"):
            if not isinstance(method.get(field), str) or not method[field]:
                raise ValueError(f"{method['id']}: missing {field}")
        for field in ("shared_sources", "supported_classes"):
            if not isinstance(method.get(field), list):
                raise ValueError(f"{method['id']}: {field} must be a list")
    for item in (*occurrences.values(), *predictions.values()):
        if item.get("document_id") not in documents:
            raise ValueError(f"{item['id']}: unknown document")
        if item.get("page") not in pages[item["document_id"]]:
            raise ValueError(f"{item['id']}: unknown page")
        if item.get("layer") not in {"base", "annotation"}:
            raise ValueError(f"{item['id']}: unknown layer")
        if item.get("family") not in families or not isinstance(item.get("class_id"), str):
            raise ValueError(f"{item['id']}: unknown family or invalid class")
        if item.get("context", "operational") not in {
            "operational",
            "legend",
            "informative",
            "negative",
        }:
            raise ValueError(f"{item['id']}: unknown context")
        _geometry(item)
        if item.get("quantity") is not None and not _finite(item["quantity"]):
            raise ValueError(f"{item['id']}: non-finite quantity")
    for item in occurrences.values():
        if item.get("evaluability") not in {"confirmed", "ambiguous", "unassessable"}:
            raise ValueError(f"{item['id']}: unknown evaluability")
        if not isinstance(item.get("strata"), list):
            raise ValueError(f"{item['id']}: strata must be a list")
    for item in predictions.values():
        if item.get("method_id") not in methods:
            raise ValueError(f"{item['id']}: unknown method")
        if item.get("score") is not None and not _finite(item["score"]):
            raise ValueError(f"{item['id']}: non-finite score")
        probability = item.get("calibrated_probability")
        if probability is not None and (not _finite(probability) or not 0 <= probability <= 1):
            raise ValueError(f"{item['id']}: invalid calibrated probability")
    executions: set[tuple[Any, ...]] = set()
    for item in outputs.get("executions", []):
        execution_key = tuple(
            item.get(field) for field in ("document_id", "page", "layer", "method_id")
        )
        if (
            execution_key[0] not in documents
            or execution_key[1] not in pages.get(execution_key[0], set())
            or execution_key[2] not in {"base", "annotation"}
            or execution_key[3] not in methods
            or item.get("status") not in {"executed", "not_applicable", "failed"}
        ):
            raise ValueError("invalid execution locator/status")
        if execution_key in executions:
            raise ValueError("duplicate execution")
        executions.add(execution_key)


def _locator(item: Record) -> tuple[Any, ...]:
    return item["document_id"], item["page"], item["layer"]


def _axis(item: Record) -> tuple[tuple[float, float], tuple[float, float]]:
    if item.get("trace"):
        return tuple(item["trace"][0]), tuple(item["trace"][-1])
    x0, y0, x1, y1 = item["bbox"]
    if x1 - x0 >= y1 - y0:
        return (x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)
    return ((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1)


def geometry_match(first: Record, second: Record) -> Record:
    """Return measured geometry and the frozen acceptance criterion, not a score."""
    a, b = first["bbox"], second["bbox"]
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    areas = [(box[2] - box[0]) * (box[3] - box[1]) for box in (a, b)]
    union = sum(areas) - intersection
    iou = intersection / union if union else 0.0
    start_a, end_a = _axis(first)
    start_b, end_b = _axis(second)
    lengths = math.dist(start_a, end_a), math.dist(start_b, end_b)
    longest = max(lengths)
    distance = min(
        max(math.dist(start_a, start_b), math.dist(end_a, end_b)),
        max(math.dist(start_a, end_b), math.dist(end_a, start_b)),
    )
    normalized_distance = distance / longest if longest else None
    length_ratio = min(lengths) / longest if longest else 0.0
    thin = all(
        min(box[2] - box[0], box[3] - box[1])
        <= max(box[2] - box[0], box[3] - box[1]) * PROTOCOL["thin_axis_ratio_max"]
        for box in (a, b)
    )
    thin_ok = (
        thin
        and normalized_distance is not None
        and normalized_distance <= PROTOCOL["thin_endpoint_distance_max"]
        and length_ratio >= PROTOCOL["thin_length_ratio_min"]
    )
    criterion = "iou" if iou >= PROTOCOL["iou_min"] else "thin_endpoints" if thin_ok else None
    return {
        "eligible": criterion is not None,
        "criterion": criterion,
        "iou": iou,
        "endpoint_distance_normalized": normalized_distance,
        "length_ratio": length_ratio,
    }


def _pairs(
    predictions: list[Record], references: list[Record], *, classify: bool = True
) -> tuple[list[Record], dict[str, list[str]]]:
    """Augmenting paths maximize cardinality, avoiding order-dependent greedy misses."""
    edges: dict[str, list[str]] = {}
    details: dict[tuple[str, str], Record] = {}
    ref_index = {item["id"]: item for item in references}
    pred_index = {item["id"]: item for item in predictions}
    for prediction in predictions:
        options = []
        for reference in references:
            if _locator(prediction) != _locator(reference):
                continue
            if classify and prediction["class_id"] != reference["class_id"]:
                continue
            geometry = geometry_match(prediction, reference)
            if geometry["eligible"]:
                details[prediction["id"], reference["id"]] = geometry
                options.append(reference["id"])
        edges[prediction["id"]] = sorted(
            options,
            key=lambda identity: (
                -details[prediction["id"], identity]["iou"],
                details[prediction["id"], identity]["endpoint_distance_normalized"],
                identity,
            ),
        )
    owners: dict[str, str] = {}

    def augment(prediction_id: str, visited: set[str]) -> bool:
        for reference_id in edges[prediction_id]:
            if reference_id in visited:
                continue
            visited.add(reference_id)
            if reference_id not in owners or augment(owners[reference_id], visited):
                owners[reference_id] = prediction_id
                return True
        return False

    for prediction_id in sorted(pred_index):
        augment(prediction_id, set())
    return [
        {
            "reference_id": reference_id,
            "prediction_id": prediction_id,
            "reference": deepcopy(ref_index[reference_id]),
            "prediction": deepcopy(pred_index[prediction_id]),
            "geometry": details[prediction_id, reference_id],
        }
        for reference_id, prediction_id in sorted(owners.items())
    ], edges


def _counts(tp: int, fp: int, fn: int) -> Record:
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def _context_matches(prediction: Record, controls: list[Record]) -> list[Record]:
    """Attribute an existing FP to every explicit context ROI, never create a TP.

    A bad localization (including the legacy degenerate stem box) remains a bad
    localization. Containment only explains which negative control was affected.
    """
    box = prediction["bbox"]
    center_x, center_y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    result = []
    for reference in controls:
        if _locator(prediction) != _locator(reference):
            continue
        geometry = geometry_match(prediction, reference)
        region = reference["bbox"]
        contained = region[0] <= center_x <= region[2] and region[1] <= center_y <= region[3]
        if geometry["eligible"] or contained:
            result.append(
                {
                    "prediction_id": prediction["id"],
                    "reference_id": reference["id"],
                    "prediction": deepcopy(prediction),
                    "reference": deepcopy(reference),
                    "geometry": geometry,
                    "context_only": True,
                    "criterion": "geometry_match"
                    if geometry["eligible"]
                    else "context_center_containment",
                }
            )
    return result


def _measure(predictions: list[Record], occurrences: list[Record]) -> Record:
    candidates = [
        item for item in predictions if item.get("context", "operational") == "operational"
    ]
    positive = [
        item
        for item in occurrences
        if item["evaluability"] == "confirmed" and item["context"] == "operational"
    ]
    uncertain = [item for item in occurrences if item["evaluability"] != "confirmed"]
    negative = [
        item
        for item in occurrences
        if item["evaluability"] == "confirmed" and item["context"] != "operational"
    ]
    matches, edges = _pairs(candidates, positive)
    used_predictions = {item["prediction_id"] for item in matches}
    used_references = {item["reference_id"] for item in matches}
    false_positives, unresolved, duplicates = [], [], []
    for prediction in candidates:
        if prediction["id"] in used_predictions:
            continue
        # A repeated detection of a certain object remains FP even beside an ambiguity.
        if edges[prediction["id"]]:
            duplicate = {
                **deepcopy(prediction),
                "reason": "duplicate",
                "reference_ids": edges[prediction["id"]],
            }
            duplicates.append(duplicate)
            false_positives.append(duplicate)
            continue
        possible, _ = _pairs([prediction], uncertain, classify=False)
        if possible:
            unresolved.append(
                {**deepcopy(prediction), "reason": "uncertain_reference", "matches": possible}
            )
            continue
        context_matches = _context_matches(prediction, negative)
        false_positives.append(
            {
                **deepcopy(prediction),
                "reason": "nonoperational_context" if context_matches else "unmatched",
                "context_matches": context_matches,
            }
        )
    false_negatives = [
        {**deepcopy(item), "reason": "no_matching_prediction"}
        for item in positive
        if item["id"] not in used_references
    ]
    return {
        "micro": _counts(len(matches), len(false_positives), len(false_negatives)),
        "matches": matches,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "duplicates": duplicates,
        "unresolved": unresolved,
        "nonoperational_predictions": [
            deepcopy(item)
            for item in predictions
            if item.get("context", "operational") != "operational"
        ],
    }


def _group_metrics(
    result: Record, values: Iterable[str], selector: Callable[[Record], list[str]]
) -> Record:
    grouped = {}
    for value in sorted(set(values)):
        tp = sum(value in selector(item["reference"]) for item in result["matches"])
        fp = sum(value in selector(item) for item in result["false_positives"])
        fn = sum(value in selector(item) for item in result["false_negatives"])
        grouped[value] = {
            **_counts(tp, fp, fn),
            "reference_count": tp + fn,
            "prediction_count": tp + fp,
        }
    return grouped


def _strata(item: Record) -> list[str]:
    if item.get("strata"):
        return list(item["strata"])
    related = item.get("context_matches", [])
    if related:
        return sorted({value for match in related for value in match["reference"]["strata"]})
    return ["unlabelled_prediction"]


def _semantic(matches: list[Record]) -> Record:
    result = {}
    for field in ("situation", "quantity", "association"):
        eligible = [item for item in matches if item["reference"].get(field) is not None]
        correct = sum(
            item["reference"][field] == item["prediction"].get(field) for item in eligible
        )
        result[field] = {
            "correct": correct,
            "denominator": len(eligible),
            "answered": sum(item["prediction"].get(field) is not None for item in eligible),
            "accuracy": correct / len(eligible) if eligible else None,
        }
    return result


def _confusion(predictions: list[Record], occurrences: list[Record]) -> list[Record]:
    refs = [
        item
        for item in occurrences
        if item["evaluability"] == "confirmed" and item["context"] == "operational"
    ]
    preds = [item for item in predictions if item.get("context", "operational") == "operational"]
    matches, _ = _pairs(preds, refs, classify=False)
    counts = Counter(
        (item["reference"]["class_id"], item["prediction"]["class_id"]) for item in matches
    )
    return [
        {"reference_class": expected, "predicted_class": actual, "count": count}
        for (expected, actual), count in sorted(counts.items())
    ]


def _calibration(predictions: list[Record], result: Record) -> Record:
    resolved = {item["prediction_id"] for item in result["matches"]} | {
        item["id"] for item in result["false_positives"]
    }
    correct = {item["prediction_id"] for item in result["matches"]}
    calibrated = [
        item
        for item in predictions
        if item.get("calibrated_probability") is not None and item["id"] in resolved
    ]
    count = len(calibrated)
    response: Record = {"denominator": count, "brier": None, "ece": None, "reason": None}
    if count < PROTOCOL["calibration_min_samples"]:
        response["reason"] = (
            "insufficient explicitly calibrated samples (minimum 30); raw scores excluded"
        )
        return response
    response["brier"] = (
        sum(
            (item["calibrated_probability"] - int(item["id"] in correct)) ** 2
            for item in calibrated
        )
        / count
    )
    ece = 0.0
    bins = []
    for index in range(10):
        selected = [
            item for item in calibrated if min(9, int(item["calibrated_probability"] * 10)) == index
        ]
        if not selected:
            continue
        probability = sum(item["calibrated_probability"] for item in selected) / len(selected)
        accuracy = sum(item["id"] in correct for item in selected) / len(selected)
        ece += len(selected) / count * abs(probability - accuracy)
        bins.append(
            {
                "bin": index,
                "denominator": len(selected),
                "mean_probability": probability,
                "accuracy": accuracy,
            }
        )
    response.update(ece=ece, bins=bins, reason="descriptive only; no field reliability claim")
    return response


def _curves(predictions: list[Record], occurrences: list[Record]) -> list[Record]:
    values = sorted(
        {item["score"] for item in predictions if item.get("score") is not None}, reverse=True
    )
    curves = []
    for threshold in values:
        selected = [
            item
            for item in predictions
            if item.get("score") is not None and item["score"] >= threshold
        ]
        metrics = _measure(selected, occurrences)["micro"]
        curves.append(
            {
                "raw_score_threshold": threshold,
                **metrics,
                "selected": len(selected),
                "candidate_denominator": len(predictions),
                "coverage": len(selected) / len(predictions) if predictions else None,
                "risk": 1 - metrics["precision"] if metrics["precision"] is not None else None,
            }
        )
    return curves


def _document_intervals(result: Record, documents: list[Record]) -> Record:
    by_document = {}
    clusters: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for document in documents:
        identity = document["id"]
        tp = sum(item["reference"]["document_id"] == identity for item in result["matches"])
        fp = sum(item["document_id"] == identity for item in result["false_positives"])
        fn = sum(item["document_id"] == identity for item in result["false_negatives"])
        by_document[identity] = _counts(tp, fp, fn)
        cluster = clusters[document["ancestor_id"]]
        for index, value in enumerate((tp, fp, fn)):
            cluster[index] += value
    response: Record = {
        "by_document": by_document,
        "independent_ancestor_count": len(clusters),
        "precision_95": None,
        "recall_95": None,
        "reason": "insufficient independent ancestors (minimum 5); no generalization interval",
    }
    if len(clusters) < PROTOCOL["document_bootstrap_min_ancestors"]:
        return response
    generator = random.Random(PROTOCOL["document_bootstrap_seed"])
    observations = list(clusters.values())
    samples: dict[str, list[float]] = {"precision": [], "recall": []}
    for _ in range(PROTOCOL["document_bootstrap_repetitions"]):
        totals = [0, 0, 0]
        for _ in observations:
            observation = generator.choice(observations)
            totals = [old + new for old, new in zip(totals, observation, strict=True)]
        micro = _counts(*totals)
        for field in samples:
            if micro[field] is not None:
                samples[field].append(micro[field])
    for field, values in samples.items():
        values.sort()
        if values:
            response[f"{field}_95"] = [
                values[int((len(values) - 1) * 0.025)],
                values[int((len(values) - 1) * 0.975)],
            ]
    response["reason"] = (
        "descriptive ancestor bootstrap; synthetic correlation and convenience sampling "
        "preclude field generalization"
    )
    return response


def _evaluation(
    predictions: list[Record], reference: Record, classes: set[str], *, curves: bool
) -> Record:
    occurrences = reference["occurrences"]
    result = _measure(predictions, occurrences)
    result["by_family"] = _group_metrics(
        result, reference["families"], lambda item: [item["family"]]
    )
    result["by_class"] = _group_metrics(result, classes, lambda item: [item["class_id"]])
    strata = {value for item in occurrences for value in item["strata"]} | {
        value for item in result["false_positives"] for value in _strata(item)
    }
    result["by_stratum"] = _group_metrics(result, strata, _strata)
    result["macro"] = {}
    for dimension in ("by_family", "by_class"):
        result["macro"][dimension] = {}
        for field in ("precision", "recall"):
            values = [item[field] for item in result[dimension].values() if item[field] is not None]
            result["macro"][dimension][field] = sum(values) / len(values) if values else None
            result["macro"][dimension][f"{field}_denominator"] = len(values)
    pages = sum(len(document["pages"]) for document in reference["documents"])
    result["fp_per_page"] = {
        "value": result["micro"]["fp"] / pages if pages else None,
        "page_denominator": pages,
    }
    result["semantic_accuracy"] = _semantic(result["matches"])
    result["confusion"] = _confusion(predictions, occurrences)
    result["confusion_note"] = (
        "localization-only matched confusion; unmatched predictions and references "
        "remain explicit FP/FN"
    )
    result["review"] = {
        "prediction_denominator": len(predictions),
        "explicit_review_required": sum(
            item.get("review_required") is True for item in predictions
        ),
        "explicit_automatic": sum(item.get("review_required") is False for item in predictions),
        "unspecified": sum("review_required" not in item for item in predictions),
        "unresolved": len(result["unresolved"]),
        "policy": "no promotion policy implemented by E02",
    }
    result["score_curves"] = _curves(predictions, occurrences) if curves else []
    result["score_curves_reason"] = (
        None if curves else "composition scores are not comparable across methods"
    )
    result["calibration"] = _calibration(predictions, result)
    result["calibration_by_class"] = {
        value: _calibration([item for item in predictions if item["class_id"] == value], result)
        for value in sorted(classes)
    }
    result["calibration_by_stratum"] = {
        value: _calibration(
            [
                item
                for item in predictions
                if value in item.get("strata", [])
                or any(
                    error["id"] == item["id"] and value in _strata(error)
                    for error in result["false_positives"]
                )
                or any(
                    match["prediction_id"] == item["id"] and value in match["reference"]["strata"]
                    for match in result["matches"]
                )
            ],
            result,
        )
        for value in sorted(strata)
    }
    result["document_intervals"] = _document_intervals(result, reference["documents"])
    return result


def _exact_key(item: Record) -> tuple[Any, ...]:
    return (
        *_locator(item),
        item["family"],
        item["class_id"],
        tuple(item["bbox"]),
        tuple(tuple(point) for point in item.get("trace", [])),
        item.get("context", "operational"),
        item.get("instance_id"),
    )


def _union(predictions: list[Record]) -> list[Record]:
    groups: dict[tuple[Any, ...], dict[str, list[Record]]] = defaultdict(lambda: defaultdict(list))
    for item in sorted(predictions, key=lambda item: item["id"]):
        groups[_exact_key(item)][item["method_id"]].append(item)
    result = []
    for methods in groups.values():
        for index in range(max(map(len, methods.values()))):
            observations = [
                items[index] for _, items in sorted(methods.items()) if index < len(items)
            ]
            identities = [item["id"] for item in observations]
            item = deepcopy(observations[0])
            item.update(
                id="union:" + sha256("\0".join(identities).encode()).hexdigest()[:24],
                observation_ids=identities,
                method_ids=[observation["method_id"] for observation in observations],
                observations=deepcopy(observations),
            )
            if len(observations) > 1:
                item["score"] = None
                item.pop("calibrated_probability", None)
                for field in ("situation", "quantity", "association"):
                    if any(
                        observation.get(field) != item.get(field) for observation in observations
                    ):
                        item[field] = None
            result.append(item)
    return sorted(result, key=lambda item: item["id"])


def _complementarity(methods: Record) -> Record:
    tp = {
        key: {item["reference_id"] for item in value["matches"]} for key, value in methods.items()
    }
    fp = {
        key: {_exact_key(item) for item in value["false_positives"]}
        for key, value in methods.items()
    }
    by_method = {}
    pairs = []
    for identity, evaluation in methods.items():
        other_tp = set().union(*(value for key, value in tp.items() if key != identity))
        other_fp = set().union(*(value for key, value in fp.items() if key != identity))
        by_method[identity] = {
            "exclusive_tp_reference_ids": sorted(tp[identity] - other_tp),
            "exclusive_fp_prediction_ids": [
                item["id"]
                for item in evaluation["false_positives"]
                if _exact_key(item) not in other_fp
            ],
            "shared_fp_prediction_ids": [
                item["id"] for item in evaluation["false_positives"] if _exact_key(item) in other_fp
            ],
        }
        for other in sorted(methods):
            if other != identity:
                pairs.append(
                    {
                        "a": identity,
                        "b": other,
                        "a_correct_b_missed_reference_ids": sorted(tp[identity] - tp[other]),
                        "shared_tp_reference_ids": sorted(tp[identity] & tp[other]),
                        "shared_fn_reference_ids": sorted(
                            {item["id"] for item in evaluation["false_negatives"]}
                            & {item["id"] for item in methods[other]["false_negatives"]}
                        ),
                        "shared_fp_exact_count": len(fp[identity] & fp[other]),
                    }
                )
    return {
        "by_method": by_method,
        "pairs": pairs,
        "note": "exact-geometry FP equivalence is conservative; agreement is not probability",
    }


def evaluate(reference: Record, outputs: Record, *, allow_reserve: bool = False) -> Record:
    """Evaluate immutable inputs; E16 must explicitly opt in to reserve-only data."""
    _validate(reference, outputs, allow_reserve=allow_reserve)
    classes = (
        {item["class_id"] for item in reference["occurrences"]}
        | {item["class_id"] for item in outputs["predictions"]}
        | {value for method in outputs["methods"] for value in method["supported_classes"]}
    )
    methods = {}
    for method in outputs["methods"]:
        predictions = [item for item in outputs["predictions"] if item["method_id"] == method["id"]]
        result = _evaluation(predictions, reference, classes, curves=True)
        executions = [
            item for item in outputs.get("executions", []) if item["method_id"] == method["id"]
        ]
        expected = sum(len(document["pages"]) * 2 for document in reference["documents"])
        result.update(
            metadata=deepcopy(method),
            executions=deepcopy(executions),
            execution_coverage={
                "expected_page_layers": expected,
                "recorded": len(executions),
                "missing": expected - len(executions),
                "by_status": dict(Counter(item["status"] for item in executions)),
            },
        )
        methods[method["id"]] = result
    union = _union(outputs["predictions"])
    raw = _evaluation(union, reference, classes, curves=False)
    raw["candidates"] = union
    raw["input_observation_count"] = len(outputs["predictions"])
    raw["candidate_count"] = len(union)
    intersection = [item for item in union if len(item["method_ids"]) == len(methods)]
    compositions = {
        "raw_union": raw,
        "filtered_union": {**deepcopy(raw), "alias_of": "raw_union", "policy_implemented": False},
        "final": {**deepcopy(raw), "alias_of": "raw_union", "policy_implemented": False},
        "intersection_control": _evaluation(intersection, reference, classes, curves=False),
        "ablations": {
            identity: _evaluation(
                _union([item for item in outputs["predictions"] if item["method_id"] != identity]),
                reference,
                classes,
                curves=False,
            )
            for identity in methods
        },
    }
    occurrences = reference["occurrences"]
    return {
        "schema_version": 1,
        "reference_annotation_scope": "complete",
        "protocol": deepcopy(PROTOCOL),
        "denominators": {
            "documents": len(reference["documents"]),
            "pages": sum(len(document["pages"]) for document in reference["documents"]),
            "families": len(reference["families"]),
            "occurrences": len(occurrences),
            "confirmed_operational": sum(
                item["evaluability"] == "confirmed" and item["context"] == "operational"
                for item in occurrences
            ),
            "by_context": dict(Counter(item["context"] for item in occurrences)),
            "by_evaluability": dict(Counter(item["evaluability"] for item in occurrences)),
            "by_family": {
                family: {
                    "total": sum(item["family"] == family for item in occurrences),
                    "confirmed_operational": sum(
                        item["family"] == family
                        and item["evaluability"] == "confirmed"
                        and item["context"] == "operational"
                        for item in occurrences
                    ),
                }
                for family in reference["families"]
            },
        },
        "methods": methods,
        "compositions": compositions,
        "complementarity": _complementarity(methods),
        "limitations": [
            "Development/calibration measurements do not establish field generalization.",
            "Unlabelled families have zero denominators, not perfect recall.",
            "Context controls are not active assets; uncertain references remain unresolved.",
            "Exact cross-method equivalence preserves observations; no nearby-object merging.",
            "Filtered/final are aliases; E02 implements no production fusion or promotion.",
            "Intersection is an analytical control and never removes union candidates.",
        ],
    }
