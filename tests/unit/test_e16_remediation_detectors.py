# mypy: disable-error-code="no-untyped-call"
"""Public author-owned controls for E16 detector remediation.

The sealed reserve is never read by this module.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf
from tests.symbol_benchmark_fixtures import build_corpus

from zeny_project_handler.adapters.analysis.raster_symbols import (
    carregar_templates_raster,
    observar_simbolos_raster,
)
from zeny_project_handler.domain.symbols import ObservacaoSimbolo


def _bbox(observation: ObservacaoSimbolo) -> tuple[float, float, float, float]:
    points = observation.geometria.pontos_normalizados
    return (
        min(float(point.x) for point in points),
        min(float(point.y) for point in points),
        max(float(point.x) for point in points),
        max(float(point.y) for point in points),
    )


def _iou(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    overlap = max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0, min(left[3], right[3]) - max(left[1], right[1])
    )
    area_left = (left[2] - left[0]) * (left[3] - left[1])
    area_right = (right[2] - right[0]) * (right[3] - right[1])
    return overlap / (area_left + area_right - overlap)


def test_default_templates_recover_public_raster_bt_and_transformer(
    tmp_path: Path,
) -> None:
    corpus = build_corpus(tmp_path, split="development")
    source = tmp_path / "dev-raster.pdf"
    targets = {
        row["class_id"]: row["bbox"]
        for row in corpus["occurrences"]
        if row["document_id"] == "dev-raster"
        and row["class_id"] in {"PARA_RAIOS_BT", "TRANSFORMADOR"}
    }
    assert set(targets) == {"PARA_RAIOS_BT", "TRANSFORMADOR"}
    templates = carregar_templates_raster()
    assert {template.classe for template in templates} >= set(targets)
    with pymupdf.open(source) as document:
        page = document[0]
        assert not page.get_drawings()
        result = observar_simbolos_raster(
            page,
            documento_id="dev-raster",
            documento_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            pagina_numero=1,
            templates=templates,
        )
    observations = result[0].observacoes
    for class_code, target in targets.items():
        matches = [
            observation
            for observation in observations
            if observation.alternativas[0].classe == class_code
            and _iou(_bbox(observation), tuple(target)) >= 0.5
        ]
        assert len(matches) == 1, class_code
        assert matches[0].score_bruto is not None
