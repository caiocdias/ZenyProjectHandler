"""Reference-only scoring, deliberately separate from all candidate inference."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from scripts.experiments.global_graph import center, minimum_assignment, points

CATEGORIES = {"pole": "POSTE", "mt": "ESTRUTURA_MT", "bt": "ESTRUTURA_BT", "cable": "CABO"}


def normal(text: str | None) -> str:
    # Whitespace/case only: retain digits, accents, punctuation and qualifiers.
    return re.sub(r"\s+", "", text or "").upper()


def box_distance(xy: list[float], coords: list[Any]) -> float:
    return math.hypot(
        max(min(p[0] for p in coords) - xy[0], 0, xy[0] - max(p[0] for p in coords)),
        max(min(p[1] for p in coords) - xy[1], 0, xy[1] - max(p[1] for p in coords)),
    )


def readings(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"id": e["id"], "text": e["conteudo_bruto"], "quad": points(e), "annotations": False}
        for e in snapshot["ocr"]["extraction"]["evidencias"]
        if e["tipo"] in ("OCR", "TEXTO") and e.get("conteudo_bruto")
    ]


def literal_links(item: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    expected = normal(item.get("code"))
    nearby = [e for e in candidates if box_distance(item["center"], e["quad"]) <= 0.012]
    exact = []
    if expected:
        # Substring must have lexical boundaries: N4 must not match N40 or N4(1).
        pattern = rf"(?<![A-Z0-9]){re.escape(expected)}(?![A-Z0-9(])"
        exact = [e["id"] for e in nearby if re.search(pattern, normal(e["text"]))]
    return {"exact_literal_candidates": exact, "nearby": [e["id"] for e in nearby]}


def proposal_code(proposal: dict[str, Any]) -> str:
    attrs = dict(proposal["atributos_sugeridos"])
    return str(attrs.get("token_estrutura") or proposal["codigo_observado"])


def label_geometry(proposal: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    attrs = dict(proposal["atributos_sugeridos"])
    if proposal["categoria"] == "CABO":
        return cast(dict[str, Any], evidence.get(str(attrs.get("evidencia_rotulo_id")), proposal))
    return proposal


def operational(
    inventory: dict[str, Any], snapshot: dict[str, Any], graph: dict[str, Any] | None = None
) -> dict[str, Any]:
    refs = [i for i in inventory["items"] if i["kind"] in CATEGORIES and i["eligible"]]
    proposals = snapshot["ocr"]["semantic"]["elementos"]
    evidence = {e["id"]: e for e in snapshot["ocr"]["extraction"]["evidencias"]}
    costs = []
    for item in refs:
        row = []
        for p in proposals:
            geometry = label_geometry(p, evidence)
            distance = box_distance(item["center"], points(geometry))
            eligible = p["categoria"] == CATEGORIES[item["kind"]] and distance < 0.025
            row.append(
                distance
                + math.dist(item["center"], center(geometry)) * 0.05
                + (0 if normal(proposal_code(p)) == normal(item["code"]) else 0.03)
                if eligible
                else 1e6
            )
        costs.append(row + [0.1] * len(refs))
    matches = minimum_assignment(costs)
    associations = {a["proposal_id"]: a for a in graph["associations"]} if graph else {}
    nodes = {n["id"]: n for n in graph["nodes"]} if graph else {}
    edges = {e["id"]: e for e in graph["edges"]} if graph else {}
    physical = {i["site"]: i for i in inventory["items"] if i["kind"] == "point"}
    rows: list[dict[str, Any]] = []
    used = set()
    for item, match in zip(refs, matches, strict=True):
        p = proposals[match] if match < len(proposals) and costs[len(rows)][match] < 0.1 else None
        record: dict[str, Any] = {
            "id": item["id"],
            "class": item["kind"],
            "expected_code": item["code"],
            "expected_site": item["site"],
            "code": False,
            "situation": False,
            "association": False,
        }
        if p:
            used.add(p["id"])
            attrs = dict(p["atributos_sugeridos"])
            record.update(
                proposal_id=p["id"],
                observed_code=proposal_code(p),
                observed_site=attrs.get("identificador_operacional"),
                code=normal(proposal_code(p)) == normal(item["code"]),
                situation=p["situacao_projeto"] == item["situation"],
            )
            if graph:
                target = associations.get(p["id"], {}).get("target")
                record["graph_target"] = target
                if item["kind"] != "cable" and target in nodes:
                    expected = physical[item["site"]]["center"]
                    record["association"] = math.dist(expected, nodes[target]["point"]) <= 0.02
                elif target in edges:
                    # Exact trace geometry must agree with the already localized cable.
                    observed = edges[target]["points"]
                    baseline = points(p)
                    record["association"] = (
                        min(
                            max(
                                math.dist(observed[0], baseline[0]),
                                math.dist(observed[-1], baseline[-1]),
                            ),
                            max(
                                math.dist(observed[-1], baseline[0]),
                                math.dist(observed[0], baseline[-1]),
                            ),
                        )
                        <= 0.02
                    )
            elif item["kind"] != "cable" or item["site"].startswith("V"):
                record["association"] = attrs.get("identificador_operacional") == item["site"]
            else:
                # Unnumbered traces are evaluated by their geometry, not invented labels.
                span = next(i for i in inventory["items"] if i["id"] == item["site"])
                known = [physical[e]["center"] for e in span.get("endpoints", []) if e in physical]
                record["association"] = bool(known) and all(
                    min(math.dist(xy, pt) for pt in (points(p)[0], points(p)[-1])) <= 0.02
                    for xy in known
                )
        record["joint"] = all(record[k] for k in ("code", "situation", "association"))
        rows.append(record)
    summary = {}
    for kind in CATEGORIES:
        group = [r for r in rows if r["class"] == kind]
        tp = sum(r["joint"] for r in group)
        # Extra predictions near scored occurrences are duplicates/FP. Revisions, equipment
        # and clipped sources are separate strata, never silently counted as core truth.
        extra = [
            p
            for p in proposals
            if p["id"] not in used
            and p["categoria"] == CATEGORIES[kind]
            and any(
                box_distance(i["center"], points(label_geometry(p, evidence))) <= 0.012
                and normal(proposal_code(p)) == normal(i["code"])
                for i in refs
                if i["kind"] == kind
            )
        ]
        fp = sum(
            "proposal_id" in r
            and not r["joint"]
            and (graph is None or r.get("graph_target") is not None)
            for r in group
        ) + len(extra)
        summary[kind] = {
            "tp": tp,
            "fn": len(group) - tp,
            "fp": fp,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / len(group),
            "duplicates": [p["id"] for p in extra],
        }
    return {
        "rows": rows,
        "classes": summary,
        "scope": "29 core occurrences; other output strata retained separately",
    }


def topology(
    inventory: dict[str, Any], snapshot: dict[str, Any], graph: dict[str, Any] | None = None
) -> dict[str, Any]:
    physical = {i["site"]: i["center"] for i in inventory["items"] if i["kind"] == "point"}
    paths = []
    if graph:
        for edge in graph["edges"]:
            nodes = [graph["nodes"][n] for n in edge["nodes"]]
            paths.append(
                {
                    "id": edge["id"],
                    "xy": edge["points"],
                    "labels": [n.get("label") for n in nodes],
                    "node_ids": [n["id"] for n in nodes],
                    "length": edge.get("length"),
                }
            )
    else:
        for p in snapshot["ocr"]["semantic"]["elementos"]:
            if p["categoria"] != "CABO" or p["geometria"]["tipo"] != "POLILINHA":
                continue
            a = dict(p["atributos_sugeridos"])
            paths.append(
                {
                    "id": p["id"],
                    "xy": points(p),
                    "labels": [
                        a.get("ponto_operacional_origem"),
                        a.get("ponto_operacional_destino"),
                    ],
                    "length": float(a["comprimento_m"]) if a.get("comprimento_m") else None,
                }
            )
    rows = []
    for item in (i for i in inventory["items"] if i["kind"] == "span"):
        known = [p for p in item["endpoints"] if p is not None]
        matches = []
        for path in paths:
            ends = [path["xy"][0], path["xy"][-1]]
            if all(min(math.dist(physical[k], p) for p in ends) <= 0.02 for k in known):
                names_correct = all(
                    path["labels"][min(range(2), key=lambda j: math.dist(physical[k], ends[j]))]
                    == k
                    for k in known
                    if k.startswith("P")
                )
                matches.append(
                    {
                        "id": path["id"],
                        "names_correct": names_correct,
                        "length_correct": path["length"] == item["length"],
                        "observed_length": path["length"],
                    }
                )
        rows.append(
            {
                "id": item["id"],
                "endpoints": item["endpoints"],
                "expected_length": item["length"],
                "matches": matches,
                "geometry_pair": len(known) == 2 and bool(matches),
                "names_and_geometry": len(known) == 2 and any(m["names_correct"] for m in matches),
                "length_correct": item["length"] is not None
                and any(m["length_correct"] for m in matches),
                "continuity_explicit": False,
            }
        )
    return {
        "rows": rows,
        "visible_pairs": sum(r["geometry_pair"] for r in rows),
        "names_and_geometry": sum(r["names_and_geometry"] for r in rows),
        "lengths": sum(r["length_correct"] for r in rows),
        "explicit_continuities": 0,
        "limits": "Geometry/name matches do not certify shared physical identity or class; "
        "off-page continuation is not implemented by these candidates",
    }


def compare(root: Path, reference: Path) -> dict[str, Any]:
    inventory = json.loads(reference.read_text(encoding="utf-8-sig"))
    original = json.loads((root / "original.json").read_text(encoding="utf-8"))
    vertical = json.loads((root / "vertical.json").read_text(encoding="utf-8"))
    rapid = json.loads((root / "rapid.json").read_text(encoding="utf-8"))
    neural = json.loads((root / "rapid-semantic.json").read_text(encoding="utf-8"))
    graph = json.loads((root / "graph.json").read_text(encoding="utf-8"))
    assert original["source_sha256"] == vertical["source_sha256"] == rapid["source"]["sha256"]
    assert (
        original["source_unchanged"] and vertical["source_unchanged"] and rapid["source_unchanged"]
    )
    assert rapid["completed"] and graph["completed"]
    assert neural["completed"] and neural["source_sha256"] == original["source_sha256"]
    variants = {
        "original": readings(original),
        "vertical": readings(vertical),
        "rapid": [r for r in rapid["readings"] if not r["annotations"]],
    }
    rows = [
        {
            "id": i["id"],
            "kind": i["kind"],
            "reference": i,
            "methods": {
                name: literal_links(i, candidates) for name, candidates in variants.items()
            },
        }
        for i in inventory["items"]
    ]
    metric_rows = [r for r in rows if r["kind"] in CATEGORIES and r["reference"]["eligible"]]
    # Literal coverage is not operational precision; qualifiers/association scored above.
    coverage = {
        name: dict(
            Counter(
                r["kind"] for r in metric_rows if r["methods"][name]["exact_literal_candidates"]
            )
        )
        for name in variants
    }
    patterns = Counter(
        "/".join(name for name in variants if not r["methods"][name]["exact_literal_candidates"])
        or "none"
        for r in metric_rows
    )
    operations = {
        "original": operational(inventory, original),
        "vertical": operational(inventory, vertical),
        "rapid": operational(inventory, neural),
        "graph": operational(inventory, vertical, graph),
    }
    topologies = {
        "original": topology(inventory, original),
        "vertical": topology(inventory, vertical),
        "rapid": topology(inventory, neural),
        "graph": topology(inventory, vertical, graph),
    }
    operational_patterns = Counter(
        "/".join(name for name, result in operations.items() if not result["rows"][i]["joint"])
        or "none"
        for i in range(len(operations["original"]["rows"]))
    )
    return {
        "schema": 1,
        "reference_sha256": sha256(reference.read_bytes()).hexdigest(),
        "source_sha256": original["source_sha256"],
        "rows": rows,
        "core_literal_coverage": coverage,
        "core_literal_failure_patterns": dict(patterns),
        "operational": operations,
        "operational_failure_patterns": dict(operational_patterns),
        "topology": topologies,
        "limitations": [
            "Literal links are candidates, not whole-item TP or document recall",
            "Graph cable association uses baseline geometry; inspect endpoint metrics separately",
            "OCR produces no operational situation, authority or automatic confirmation",
            "All 139 reference rows retained; no blind evaluation performed",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.runs, args.reference)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "coverage": result["core_literal_coverage"],
                "correlated": result["core_literal_failure_patterns"],
                "operational": {k: v["classes"] for k, v in result["operational"].items()},
            }
        )
    )


if __name__ == "__main__":
    main()
