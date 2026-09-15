"""Endpoint graph and global assignments; consumes evidence, never ground truth."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from itertools import pairwise
from typing import Any

VERSION = "e12a-1"
Point = tuple[float, float]


def points(item: dict[str, Any]) -> list[Point]:
    return [(float(p["x"]), float(p["y"])) for p in item["geometria"]["pontos"]]


def center(item: dict[str, Any]) -> Point:
    coords = points(item)
    return (
        (min(p[0] for p in coords) + max(p[0] for p in coords)) / 2,
        (min(p[1] for p in coords) + max(p[1] for p in coords)) / 2,
    )


def segment_distance(point: Point, a: Point, b: Point) -> float:
    delta = (b[0] - a[0], b[1] - a[1])
    denominator = delta[0] ** 2 + delta[1] ** 2
    if denominator == 0:
        return math.dist(point, a)
    t = max(0.0, min(1.0, sum((point[i] - a[i]) * delta[i] for i in (0, 1)) / denominator))
    return math.dist(point, (a[0] + t * delta[0], a[1] + t * delta[1]))


def minimum_assignment(matrix: list[list[float]]) -> list[int]:
    """Hungarian shortest augmenting paths, rectangular matrix with rows <= columns."""
    n, m = len(matrix), len(matrix[0])
    if n > m or any(len(row) != m for row in matrix):
        raise ValueError("Expected a rectangular matrix with rows <= columns")
    u, v = [0.0] * (n + 1), [0.0] * (m + 1)
    matching, previous = [0] * (m + 1), [0] * (m + 1)
    for row in range(1, n + 1):
        matching[0] = row
        column = 0
        distance, used = [math.inf] * (m + 1), [False] * (m + 1)
        while True:
            used[column] = True
            current, delta, next_column = matching[column], math.inf, 0
            for candidate in range(1, m + 1):
                if used[candidate]:
                    continue
                reduced = matrix[current - 1][candidate - 1] - u[current] - v[candidate]
                if reduced < distance[candidate]:
                    distance[candidate], previous[candidate] = reduced, column
                if distance[candidate] < delta:
                    delta, next_column = distance[candidate], candidate
            for candidate in range(m + 1):
                if used[candidate]:
                    u[matching[candidate]] += delta
                    v[candidate] -= delta
                else:
                    distance[candidate] -= delta
            column = next_column
            if matching[column] == 0:
                break
        while column:
            parent = previous[column]
            matching[column] = matching[parent]
            column = parent
    result = [0] * n
    for column in range(1, m + 1):
        if matching[column]:
            result[matching[column] - 1] = column - 1
    return result


def assign(costs: list[list[float]], abstain: float) -> list[int | None]:
    """Rectangular minimum-cost assignment with one private abstention per row.

    Forbid each winning edge and solve again to expose equally good global optima.
    A tie is abstention, independent of input ordering, never silent authority.
    """
    if not costs:
        return []
    n = len(costs)
    m = len(costs[0])
    if any(len(row) != m for row in costs):
        raise ValueError("Ragged assignment matrix")
    if not m:
        return [None] * n
    matrix = [row + [abstain if i == j else 1e6 for j in range(n)] for i, row in enumerate(costs)]
    columns = minimum_assignment(matrix)
    best = sum(matrix[i][j] for i, j in enumerate(columns))
    result: list[int | None] = [None] * n
    for i, j in enumerate(columns):
        if j >= m or costs[i][j] >= abstain:
            continue
        alternative = [row[:] for row in matrix]
        alternative[i][j] = 1e6
        cc = minimum_assignment(alternative)
        second = sum(alternative[r][c] for r, c in enumerate(cc))
        if second - best > 1e-6:
            result[i] = j
    return result


def endpoint_graph(traces: list[dict[str, Any]], tolerance: float = 0.006) -> dict[str, Any]:
    """Cluster endpoints only, separately per page; interior crossings stay separate."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for trace in sorted(traces, key=lambda value: value["id"]):
        ends = []
        for xy in (trace["points"][0], trace["points"][-1]):
            candidates = [
                (math.dist(xy, node["point"]), i)
                for i, node in enumerate(nodes)
                if node["page"] == trace["page"] and math.dist(xy, node["point"]) <= tolerance
            ]
            if candidates:
                index = min(candidates)[1]
            else:
                index = len(nodes)
                nodes.append({"id": f"node-{index}", "point": xy, "page": trace["page"]})
            ends.append(index)
        if ends[0] != ends[1]:
            edges.append({**trace, "nodes": ends})
    return {"nodes": nodes, "edges": edges}


def run_graph(snapshot: dict[str, Any]) -> dict[str, Any]:
    evidence = snapshot["extraction"]["evidencias"]
    proposals = snapshot["semantic"]["elementos"]
    traces = []
    for ev in evidence:
        if ev["tipo"] != "VETOR" or ev["geometria"]["tipo"] != "POLILINHA":
            continue
        vector_points = points(ev)
        attrs = dict(ev["atributos_extraidos"])
        if (
            math.dist(vector_points[0], vector_points[-1]) < 0.035
            or attrs.get("cor_contorno") == "#FFFFFF"
        ):
            continue
        traces.append({"id": ev["id"], "page": ev["pagina_id"], "points": vector_points})
    graph = endpoint_graph(traces)
    # One graph identity per physical node, not two new identities per conductor.
    nodes = graph["nodes"]
    identifiers: dict[tuple[str, str], dict[str, Any]] = {}
    for ev in evidence:
        text = (ev.get("conteudo_bruto") or "").strip()
        if ev["tipo"] in ("TEXTO", "OCR") and re.fullmatch(r"P\d{1,4}", text):
            identifier_key = (ev["pagina_id"], text)
            identifiers.setdefault(identifier_key, ev)
    labels = list(identifiers.values())
    costs = [
        [math.dist(center(ev), n["point"]) if ev["pagina_id"] == n["page"] else 1e6 for n in nodes]
        for ev in labels
    ]
    for ev, target in zip(labels, assign(costs, 0.055), strict=True):
        if target is not None:
            nodes[target].update(label=ev["conteudo_bruto"], evidence_id=ev["id"])
    associations = []
    supported: dict[str, list[str]] = defaultdict(list)
    for proposal in proposals:
        attrs = dict(proposal["atributos_sugeridos"])
        label = next((e for e in evidence if e["id"] == attrs.get("evidencia_rotulo_id")), proposal)
        xy = center(label)
        page = proposal["geometria"]["pagina_id"]
        cable = proposal["categoria"] == "CABO"
        pool = graph["edges"] if cable else nodes
        distances = [
            (
                min(segment_distance(xy, a, b) for a, b in pairwise(p["points"]))
                if cable
                else math.dist(xy, p["point"])
            )
            if p["page"] == page
            else 1e6
            for p in pool
        ]
        ordered = sorted(range(len(pool)), key=lambda i: distances[i])
        target = None
        if (
            ordered
            and distances[ordered[0]] < (0.055 if cable else 0.10)
            and (len(ordered) == 1 or distances[ordered[1]] - distances[ordered[0]] > 0.002)
        ):
            target = pool[ordered[0]]["id"]
        associations.append({"proposal_id": proposal["id"], "target": target, "cable": cable})
        if cable and target:
            supported[target].append(proposal["id"])
    # Match measurements globally to supported traces. Heights and angles are excluded.
    measured = []
    seen: set[tuple[str, str, int, int]] = set()
    for ev in evidence:
        text = (ev.get("conteudo_bruto") or "").strip()
        match = re.fullmatch(r"(\d{1,4}(?:[.,]\d{1,2})?)\s*[mM]", text)
        if ev["tipo"] not in ("OCR", "TEXTO") or not match:
            continue
        xy = center(ev)
        key = (ev["pagina_id"], match[1], round(xy[0] * 200), round(xy[1] * 200))
        if key not in seen:
            seen.add(key)
            measured.append((ev, float(match[1].replace(",", "."))))
    edges = [e for e in graph["edges"] if e["id"] in supported]
    costs = [
        [
            min(segment_distance(center(ev), a, b) for a, b in pairwise(e["points"]))
            if ev["pagina_id"] == e["page"]
            else 1e6
            for e in edges
        ]
        for ev, _ in measured
    ]
    for (ev, length), target in zip(measured, assign(costs, 0.055), strict=True):
        if target is not None:
            edges[target].update(length=length, length_evidence=ev["id"])
    return {
        "version": VERSION,
        "experimental": True,
        "nodes": nodes,
        "edges": edges,
        "all_graph_edges": graph["edges"],
        "associations": associations,
        "note": "Hypotheses only; no authority, catalog completion or production promotion",
    }
