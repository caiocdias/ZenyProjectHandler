"""Real tiling/persistence boundaries with a deterministic, optional-runtime-free engine."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar, Never, cast
from uuid import uuid4

from tests.pdf_fixtures import create_analysis_pdf
from tests.unit.test_pymupdf_analyzer import FakeOcr, _request

from zeny_project_handler.adapters.analysis import JsonAnalysisCache, PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.analysis.rapid_evidence import RapidEvidenceExtractor
from zeny_project_handler.adapters.analysis.rapid_ocr import RapidLocalOcr
from zeny_project_handler.application.method_reconciliation import reading_data
from zeny_project_handler.ports.analysis import PaginaRasterOcr, ResultadoAnaliseDocumento


class FakeRapid:
    nome = "fake-rapid"
    versao = "1"
    models: ClassVar[dict[str, str]] = {"model": "a" * 64}

    def __init__(self, *, fail: int = 0, version: str = "1") -> None:
        self.capability = FakeOcr(version=version)._capability
        self.calls: list[dict[str, Any]] = []
        self.count = 0
        self.fail = fail

    def recognize_quads(self, pagina: PaginaRasterOcr) -> list[dict[str, Any]]:
        self.count += 1
        if self.count == self.fail:
            raise RuntimeError("tile unavailable")
        return [
            {
                "quad": [[10, 10], [100, 10], [100, 30], [10, 30]],
                "text": "654321 7654321",
                "confidence": 0.999,
            }
        ]


def test_tiling_failure_retains_other_tiles_and_long_analysis_can_cancel(tmp_path: Path) -> None:
    request = _request(create_analysis_pdf(tmp_path / "tiles.pdf"))
    fake = FakeRapid(fail=2)
    adapter = RapidEvidenceExtractor(lambda: cast(RapidLocalOcr, fake))
    progress = []
    request = replace(request, progresso=lambda n, total, text: progress.append((n, total, text)))
    partial = adapter.extrair(request)
    assert len(partial.candidatos) == 47 and len(partial.diagnosticos) == 1
    assert progress[-1][:2] == (48, 48)
    assert {reading_data(c.atributos_extraidos)["layer"] for c in partial.candidatos} == {  # type: ignore[index]
        "base",
        "appearance",
    }
    fake.count = 0
    cancelled = adapter.extrair(replace(request, cancelado=lambda: fake.count >= 3))
    assert len(cancelled.candidatos) == 2
    assert cancelled.diagnosticos[-1].codigo == "analysis.complementary.cancelled"


def test_cache_roundtrip_keeps_occurrence_identity_but_models_invalidate(tmp_path: Path) -> None:
    request = _request(create_analysis_pdf(tmp_path / "cache.pdf"))
    fake = FakeRapid()
    adapter = RapidEvidenceExtractor(lambda: cast(RapidLocalOcr, fake))
    cache = JsonAnalysisCache(tmp_path / "cache")
    analyzer = PyMuPdfDocumentAnalyzer(cache=cache, complementar=adapter)
    first = analyzer.analisar(request)
    second = analyzer.analisar(replace(request, execucao_id=uuid4()))
    assert second.cache_utilizado and fake.count == 48

    def identities(result: ResultadoAnaliseDocumento) -> list[str]:
        return [
            data["identity"]
            for e in result.evidencias
            if (data := reading_data(e.atributos_extraidos)) is not None
        ]

    assert identities(first) == identities(second)
    changed = FakeRapid(version="2")
    other = PyMuPdfDocumentAnalyzer(
        cache=cache, complementar=RapidEvidenceExtractor(lambda: cast(RapidLocalOcr, changed))
    )
    assert other.assinatura_capacidade != analyzer.assinatura_capacidade
    assert not other.analisar(request).cache_utilizado
    assert changed.count == 48


def test_unavailable_engine_is_explicit_and_retried(tmp_path: Path) -> None:
    def missing() -> Never:
        raise ImportError("optional engine missing")

    request = _request(create_analysis_pdf(tmp_path / "missing.pdf"))
    adapter = RapidEvidenceExtractor(missing)
    result = adapter.extrair(request)
    assert not result.candidatos
    assert result.diagnosticos[0].codigo == "analysis.complementary.unavailable"
