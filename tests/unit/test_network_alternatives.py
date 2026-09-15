"""Public synthetic controls; no private PDF, optional models or reserved E10 cases."""

from __future__ import annotations

import json
from itertools import permutations
from pathlib import Path
from random import Random
from typing import Any

import pytest
from scripts.benchmark_network_pdf import benchmark
from scripts.experiments.compare import literal_links
from scripts.experiments.global_graph import (
    assign,
    endpoint_graph,
    minimum_assignment,
    run_graph,
    segment_distance,
)
from scripts.experiments.interpret_rapid import interpret
from scripts.experiments.rapid_ocr import RapidLocalOcr, map_quad
from tests.pdf_fixtures import create_network_benchmark_pdf

from zeny_project_handler.ports.analysis import PaginaRasterOcr


def test_assignment_optimizes_globally_and_abstains_on_global_ties() -> None:
    # Greedy consumes column 0 for row 0, forcing row 1 into a bad assignment.
    assert assign([[1, 2], [1.1, 100]], 50) == [1, 0]
    assert assign([[1, 1], [1, 1]], 50) == [None, None]
    assert assign([[100]], 2) == [None]
    assert assign([[], []], 2) == [None, None]
    assert assign([], 2) == []
    with pytest.raises(ValueError, match="Ragged"):
        assign([[1], [1, 2]], 2)


def test_assignment_matches_exhaustive_optimum_on_small_matrices() -> None:
    random = Random(51237)  # Development seed, unrelated to E10 H01/H02/H03.
    for n in range(1, 5):
        for _ in range(12):
            matrix = [[random.uniform(-2, 10) for _ in range(n + 1)] for _ in range(n)]
            result = minimum_assignment(matrix)
            observed = sum(matrix[i][j] for i, j in enumerate(result))
            expected = min(
                sum(matrix[i][j] for i, j in enumerate(p)) for p in permutations(range(n + 1), n)
            )
            assert observed == pytest.approx(expected)


def test_graph_shares_endpoints_but_not_crossings_or_pages() -> None:
    traces = [
        {"id": "a", "page": "1", "points": [(0.1, 0.5), (0.9, 0.5)]},
        {"id": "b", "page": "1", "points": [(0.5, 0.1), (0.5, 0.9)]},
        {"id": "c", "page": "1", "points": [(0.9, 0.501), (0.99, 0.7)]},
        {"id": "d", "page": "2", "points": [(0.1, 0.5), (0.9, 0.5)]},
    ]
    graph = endpoint_graph(traces)
    assert len(graph["nodes"]) == 7
    assert graph == endpoint_graph(list(reversed(traces)))
    assert graph["edges"][0]["nodes"][1] == graph["edges"][2]["nodes"][0]
    assert not set(graph["edges"][0]["nodes"]) & set(graph["edges"][1]["nodes"])


def ev(key: str, xy: list[tuple[float, float]], text: str, vector: bool = False) -> dict[str, Any]:
    return {
        "id": key,
        "pagina_id": "page",
        "tipo": "VETOR" if vector else "OCR",
        "geometria": {
            "pagina_id": "page",
            "tipo": "POLILINHA" if vector else "CAIXA",
            "pontos": [{"x": x, "y": y} for x, y in xy],
        },
        "atributos_extraidos": [],
        "conteudo_bruto": text,
    }


def test_graph_associates_length_and_rejects_height_and_empty_context() -> None:
    trace = ev("line", [(0.1, 0.5), (0.9, 0.5)], "", True)
    label = ev("label", [(0.4, 0.51), (0.6, 0.52)], "ABC-2 CAA")
    pole = ev("p1", [(0.1, 0.48), (0.11, 0.49)], "P1")
    measure = ev("measure", [(0.4, 0.52), (0.45, 0.53)], "42m")
    height = ev("height", [(0.4, 0.499), (0.45, 0.50)], "ALTURA 12m")
    proposal = {
        **label,
        "categoria": "CABO",
        "atributos_sugeridos": [["evidencia_rotulo_id", "label"]],
    }
    snapshot = {
        "extraction": {"evidencias": [trace, label, pole, measure, height]},
        "semantic": {"elementos": [proposal]},
    }
    result = run_graph(snapshot)
    assert result["edges"][0]["length"] == 42
    assert result["edges"][0]["length_evidence"] == "measure"
    assert result["nodes"][0]["label"] == "P1"
    assert result["associations"][0]["target"] == "line"
    snapshot["semantic"]["elementos"] = []
    assert run_graph(snapshot)["edges"] == []


def test_coordinate_mapping_uses_pixel_origin_and_keeps_polygon() -> None:
    quad: list[list[float]] = [[0, 0], [100, 2], [98, 40], [1, 39]]
    mapped = map_quad(quad, raster_origin=(201, 301), scale=2, page_size=(400, 600))
    assert len(mapped) == 4
    assert mapped[0] == pytest.approx([201 / 800, 301 / 1200])
    assert mapped[2] == pytest.approx([299 / 800, 341 / 1200])
    assert segment_distance((0.5, 1), (0, 0), (1, 0)) == 1
    assert segment_distance((1, 0), (0, 0), (0, 0)) == 1


def test_literal_scoring_does_not_complete_or_merge_codes() -> None:
    item = {"code": "N4", "center": [0.5, 0.5]}
    candidates = [{"id": "wrong", "text": "N40 N4(1)", "quad": [[0.49, 0.49], [0.51, 0.51]]}]
    assert literal_links(item, candidates)["exact_literal_candidates"] == []
    candidates[0]["text"] = "N4"
    assert literal_links(item, candidates)["exact_literal_candidates"] == ["wrong"]
    item["center"] = [0.1, 0.1]
    assert literal_links(item, candidates)["exact_literal_candidates"] == []


def test_ocr_rejects_invalid_memory_before_calling_optional_engine() -> None:
    engine = object.__new__(RapidLocalOcr)
    for width, height, stride, data in ((3000, 3000, 9000, b""), (2, 2, 3, b"123456")):
        page = PaginaRasterOcr(
            pagina_numero=1,
            largura_pixels=width,
            altura_pixels=height,
            stride=stride,
            dados_rgb=data,
            dpi=600,
        )
        with pytest.raises(ValueError):
            engine.recognize_quads(page)


def test_neural_interpretation_keeps_geometry_without_promoting_visible_revision(
    tmp_path: Path,
) -> None:
    source = create_network_benchmark_pdf(tmp_path / "synthetic.pdf")
    report = tmp_path / "native.json"
    benchmark(source, report, tmp_path, native_only=True)
    snapshot = json.loads(report.read_text(encoding="utf-8"))
    reading = {
        "id": "base",
        "page": 1,
        "annotations": False,
        "tile": "test",
        "text": "N3(2)",
        "confidence": 0.99,
        "quad": [[0.20, 0.30], [0.25, 0.31], [0.24, 0.35], [0.19, 0.34]],
    }
    rapid = {
        "completed": True,
        "source": {"sha256": snapshot["source_sha256"]},
        "readings": [
            reading,
            {**reading, "id": "visible", "annotations": True, "text": "REVISAO NAO APROVADA"},
        ],
    }
    result = interpret(snapshot, rapid)
    assert result["completed"] and result["production_promotions"] == 0
    extracted = [
        e
        for e in result["ocr"]["extraction"]["evidencias"]
        if e.metodo == "experimental-rapidocr-db-svtr"
    ]
    assert len(extracted) == 1
    assert extracted[0].conteudo_bruto == "N3(2)"
    assert len(extracted[0].geometria.pontos) == 4
    assert dict(extracted[0].atributos_extraidos)["tile_id"] == "test"
    rapid["completed"] = False
    with pytest.raises(ValueError, match="Incomplete"):
        interpret(snapshot, rapid)
