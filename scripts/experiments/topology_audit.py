"""Evaluate topology against a separate inventory; never consumed by production.

Pairs require a bijection, correct names at their actual endpoints and the exact
observed length (including None). Counts or nearby labels alone are insufficient.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from scripts.experiments.global_graph import points, run_graph, segment_distance


def paths(snapshot: dict[str, Any], method: str) -> list[dict[str, Any]]:
    sample = snapshot["ocr"]
    pages = {p["id"]: p["numero"] for d in sample["project"]["documentos"] for p in d["paginas"]}
    if method == "graph":
        graph = run_graph(sample)
        return [
            {
                "id": edge["id"],
                "page": pages[edge["page"]],
                "xy": [edge["points"][0], edge["points"][-1]],
                "nodes": [graph["nodes"][n]["id"] for n in edge["nodes"]],
                "labels": [graph["nodes"][n].get("label") for n in edge["nodes"]],
                "length": edge.get("length"),
            }
            for edge in graph["edges"]
        ]
    if method == "physical":
        return [
            {
                "id": p["span_id"],
                "page": pages[p["geometry"]["page_id"]],
                "xy": [
                    (float(g["x"]), float(g["y"]))
                    for g in (p["geometry"]["points"][0], p["geometry"]["points"][-1])
                ],
                "nodes": [p["start_point_id"], p["end_point_id"]],
                "labels": [p["start_label"], p["end_label"]],
                "continuation": p.get("continuation", False),
                "length": float(p["length"]) if p["length"] is not None else None,
            }
            for p in sample["results"]["physical_spans"]
        ]
    return [
        {
            "id": p["id"],
            "page": pages[p["geometria"]["pagina_id"]],
            "xy": [points(p)[0], points(p)[-1]],
            "nodes": [p["id"] + "-origin", p["id"] + "-destination"],
            "labels": [
                dict(p["atributos_sugeridos"]).get("ponto_operacional_" + s)
                for s in ("origem", "destino")
            ],
            "length": float(value)
            if (value := dict(p["atributos_sugeridos"]).get("comprimento_m")) is not None
            else None,
        }
        for p in sample["semantic"]["elementos"]
        if p["categoria"] == "CABO" and dict(p["atributos_sugeridos"]).get("evidencia_geometria_id")
    ]


def evaluate(inventory: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    physical = {i["site"]: i["center"] for i in inventory["items"] if i["kind"] == "point"}
    nodes: dict[str, set[str]] = defaultdict(set)
    reverse_nodes: dict[str, set[str]] = defaultdict(set)
    rows = []
    used = set()
    for reference in (i for i in inventory["items"] if i["kind"] == "span"):
        ends = reference["endpoints"]
        matches = []
        # A finite endpoint near U2 does not prove a continuation beyond the sheet.
        if None not in ends:
            for path in candidates:
                if path.get("page", 1) != reference.get("page", 1):
                    continue
                for order in ((0, 1), (1, 0)):
                    if not all(
                        math.dist(physical[k], path["xy"][j]) <= 0.02
                        for k, j in zip(ends, order, strict=True)
                    ):
                        continue
                    names = all(
                        path["labels"][j] == k
                        for k, j in zip(ends, order, strict=True)
                        if k.startswith("P")
                    )
                    matches.append(
                        {
                            "id": path["id"],
                            "names": names,
                            "length": path["length"] == reference["length"],
                        }
                    )
                    used.add(path["id"])
                    for k, j in zip(ends, order, strict=True):
                        nodes[k].add(path["nodes"][j])
                        reverse_nodes[path["nodes"][j]].add(k)
                    break
        continuity = False
        if None in ends:
            known = next(k for k in ends if k is not None)
            for path in candidates:
                if (
                    path.get("continuation")
                    and path.get("page", 1) == reference.get("page", 1)
                    and (
                        "center" not in reference
                        or segment_distance(tuple(reference["center"]), *path["xy"]) <= 0.02
                    )
                    and path["nodes"][1] is None
                    and math.dist(physical[known], path["xy"][0]) <= 0.02
                    and path["length"] is None
                ):
                    continuity = True
                    matches.append({"id": path["id"], "names": True, "length": True})
                    nodes[known].add(path["nodes"][0])
                    reverse_nodes[path["nodes"][0]].add(known)
                    used.add(path["id"])
        rows.append(
            {
                "id": reference["id"],
                "endpoints": ends,
                "expected_length": reference["length"],
                "matches": matches,
                "exact_pair": None not in ends and any(m["names"] and m["length"] for m in matches),
                "continuity_explicit": continuity,
            }
        )
    consistent = {
        k: list(ids)
        for k, ids in nodes.items()
        if len(ids) == 1 and all(len(reverse_nodes[n]) == 1 for n in ids)
    }
    return {
        "rows": rows,
        "visible_pairs": sum(bool(r["matches"]) and None not in r["endpoints"] for r in rows),
        "exact_pairs": sum(r["exact_pair"] for r in rows),
        "exact_lengths": sum(r["exact_pair"] and r["expected_length"] is not None for r in rows),
        "points_covered": len(nodes),
        "consistent_physical_points": len(consistent),
        "physical_identity_map": {k: sorted(v) for k, v in nodes.items()},
        "duplicate_paths": sum(max(0, len(r["matches"]) - 1) for r in rows),
        "unmatched_paths": [p["id"] for p in candidates if p["id"] not in used],
        "explicit_continuities": sum(r["continuity_explicit"] for r in rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    def load(path: Path) -> dict[str, Any]:
        return dict(json.loads(path.read_text(encoding="utf-8")))

    baseline, current, inventory = load(args.baseline), load(args.current), load(args.reference)
    assert baseline["source_sha256"] == current["source_sha256"]
    assert current["source_unchanged"] and baseline["source_unchanged"]
    result = {
        "reference_rows": len(inventory["items"]),
        "reconciliation": inventory["items"],
        "metrics": {
            name: evaluate(inventory, paths(s, method))
            for name, s, method in (
                ("E13", baseline, "legacy"),
                ("E12A_on_E13", baseline, "graph"),
                ("E14", current, "physical"),
                ("E12A_on_E14", current, "graph"),
            )
        },
        "limits": "Off-page continuities require explicit representation; "
        "not inferred from a nearby endpoint. "
        "Legacy proposals have conductor identities, not physical identities. No time ranking.",
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                k: {a: b for a, b in v.items() if isinstance(b, int)}
                for k, v in result["metrics"].items()
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
