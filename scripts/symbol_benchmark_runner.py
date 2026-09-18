# mypy: disable-error-code="no-untyped-call"
"""Reproducible E02 inference runner; the detector never receives ground truth."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import tracemalloc
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any

import pymupdf

from scripts.symbol_benchmark_evaluator import PROTOCOL, evaluate
from zeny_project_handler.adapters.analysis import pymupdf_symbols
from zeny_project_handler.adapters.analysis.pymupdf_analyzer import PyMuPdfDocumentAnalyzer

ROOT = Path(__file__).resolve().parents[1]
METHOD_ID = "legacy-vector-symbols"
CLASS_FAMILY = {
    "ATERRAMENTO": "family-f02-19",
    "PARA_RAIOS_MT": "family-f02-21",
    "PARA_RAIOS_BT": "family-f02-21",
}
Record = dict[str, Any]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value), encoding="utf-8", newline="\n")


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _text_sha256(path: Path) -> str:
    return sha256(path.read_text(encoding="utf-8").replace("\r\n", "\n").encode()).hexdigest()


def method_metadata() -> Record:
    module = Path(pymupdf_symbols.__file__)
    return {
        "id": METHOD_ID,
        "version": PyMuPdfDocumentAnalyzer.versao,
        "algorithm_family": "legacy-vector-geometry",
        "shared_sources": ["pymupdf.get_drawings", "legacy SIMBOLOGIA.pdf provenance unverified"],
        "supported_classes": list(CLASS_FAMILY),
        "supported_layers": ["base"],
        "source_sha256_lf": _text_sha256(module),
        "configuration": "unmodified legacy defaults; raw constant score 0.88",
        "family_mapping": CLASS_FAMILY,
        "mapping_limitation": "benchmark taxonomy mapping, not normative equivalence",
    }


def _environment() -> Record:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pymupdf": pymupdf.VersionBind,
        "runner_sha256_lf": _text_sha256(Path(__file__)),
        "evaluator_sha256_lf": _text_sha256(
            Path(__file__).with_name("symbol_benchmark_evaluator.py")
        ),
        "protocol_sha256": sha256(canonical_json(PROTOCOL).encode()).hexdigest(),
        "memory_scope": (
            "tracemalloc Python allocations; excludes native MuPDF/RSS; per-document reset peak"
        ),
    }


def _identity(source: Path) -> Record:
    info = source.stat()
    return {"bytes": info.st_size, "mtime_ns": info.st_mtime_ns, "sha256": file_sha256(source)}


def _prediction(candidate: Any, document_id: str) -> Record:
    attributes = dict(candidate.atributos_extraidos)
    points = [(float(point.x), float(point.y)) for point in candidate.geometria.pontos]
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    class_id = str(attributes["classe_equipamento"])
    return {
        "id": f"{document_id}:{candidate.chave_estavel}",
        "method_id": METHOD_ID,
        "document_id": document_id,
        "page": candidate.pagina_numero,
        "layer": "base",
        "family": CLASS_FAMILY[class_id],
        "class_id": class_id,
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
        "score": float(attributes["confianca"]),
        "situation": attributes.get("situacao_projeto_forcada"),
        "quantity": None,
        "association": None,
        "context": "operational",
        "review_required": True,
        "provenance": {
            "stable_key": candidate.chave_estavel,
            "primitive_ids": str(attributes.get("vetores_origem", "")).split(","),
            "geometry_type": candidate.geometria.tipo.value,
            "original_normalized_points": points,
            "legacy_color": attributes.get("cor"),
            "legacy_symbol_source": attributes.get("origem_simbologia"),
            "score_kind": "raw constant; not calibrated probability",
        },
    }


def infer_pdf(source: Path, document_id: str) -> tuple[Record, list[Record], list[Record]]:
    """Infer all base pages with only source path and opaque document identity.

    No reference, expected class, reviewer ROI or expected count enters this API.
    Page failures are preserved and do not prevent attempting subsequent pages.
    """
    source = source.resolve(strict=True)
    before = _identity(source)
    started = perf_counter()
    own_tracing = not tracemalloc.is_tracing()
    if own_tracing:
        tracemalloc.start()
    tracemalloc.reset_peak()
    memory_before = tracemalloc.get_traced_memory()[0]
    manifest: Record = {
        "id": document_id,
        "path": str(source),
        "split": "development",
        "source_before": before,
        "pages": [],
        "status": "executed",
        "failures": [],
    }
    predictions: list[Record] = []
    executions: list[Record] = []
    try:
        with pymupdf.open(source) as document:
            if document.needs_pass:
                raise ValueError("encrypted PDF needs password; no page silently skipped")
            manifest["page_count"] = len(document)
            for number in range(1, len(document) + 1):
                page_started = perf_counter()
                page_manifest: Record = {"number": number, "status": "executed"}
                base: Record = {
                    "document_id": document_id,
                    "page": number,
                    "layer": "base",
                    "method_id": METHOD_ID,
                    "status": "executed",
                    "reason": None,
                }
                try:
                    page = document[number - 1]
                    page_manifest.update(
                        width_pt=float(page.rect.width),
                        height_pt=float(page.rect.height),
                        rotation=int(page.rotation),
                        annotation_count=len(tuple(page.annots() or ())),
                    )
                    extracted = pymupdf_symbols._extract_symbolic_equipment(page, number)
                    page_predictions = [_prediction(item, document_id) for item in extracted]
                    predictions.extend(page_predictions)
                    base["prediction_count"] = len(page_predictions)
                except Exception as error:
                    message = f"{type(error).__name__}: {error}"
                    base.update(status="failed", reason=message)
                    page_manifest.update(status="failed", reason=message)
                    manifest["failures"].append({"page": number, "reason": message})
                    manifest["status"] = "failed"
                base["seconds"] = perf_counter() - page_started
                executions.extend(
                    (
                        base,
                        {
                            "document_id": document_id,
                            "page": number,
                            "layer": "annotation",
                            "method_id": METHOD_ID,
                            "status": "not_applicable",
                            "reason": "legacy vector detector has base-layer scope only",
                        },
                    )
                )
                manifest["pages"].append(page_manifest)
    except Exception as error:
        manifest["status"] = "failed"
        manifest["failures"].append({"page": None, "reason": f"{type(error).__name__}: {error}"})
    finally:
        current, peak = tracemalloc.get_traced_memory()
        if own_tracing:
            tracemalloc.stop()
        manifest.update(
            seconds=perf_counter() - started,
            memory={
                "python_current_bytes": current,
                "python_peak_bytes": peak,
                "python_current_before_bytes": memory_before,
                "scope": "tracemalloc Python allocations; not process RSS/native MuPDF memory",
            },
        )
        try:
            after = _identity(source)
            manifest.update(source_after=after, source_unchanged=before == after)
        except OSError as error:
            manifest.update(source_after=None, source_unchanged=False)
            manifest["failures"].append({"page": None, "reason": str(error)})
        if not manifest["source_unchanged"]:
            manifest["status"] = "failed"
            manifest["failures"].append({"page": None, "reason": "source identity changed"})
    return manifest, predictions, executions


def _run(sources: list[tuple[Path, str]], output: Path, *, mode: str) -> Record:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    protected = {source.resolve() for source, _ in sources}
    if any(
        (output / name).resolve() in protected for name in ("manifest.json", "predictions.json")
    ):
        raise ValueError("Output must not overwrite source PDF")
    predictions: Record = {
        "schema_version": 1,
        "methods": [method_metadata()],
        "documents": [],
        "predictions": [],
        "executions": [],
    }
    manifest: Record = {
        "schema_version": 1,
        "mode": mode,
        "environment": _environment(),
        "documents": [],
        "completed": False,
        "visual_review": "not performed by runner; independent image review required",
        "reference_access": "inference accepts only PDF path and opaque document id",
        "limitations": ["One real visual method only; no independent detector gain claimed."],
    }
    for source, document_id in sources:
        try:
            document, items, executions = infer_pdf(source, document_id)
        except OSError as error:
            # A removed/unreadable file can fail before opening or hashing. Preserve
            # the failed inventory entry and still attempt every subsequent source.
            document = {
                "id": document_id,
                "path": str(source),
                "split": "development",
                "source_before": None,
                "source_after": None,
                "source_unchanged": None,
                "status": "failed",
                "pages": [],
                "page_count": None,
                "failures": [{"page": None, "reason": f"{type(error).__name__}: {error}"}],
            }
            items, executions = [], []
        manifest["documents"].append(document)
        predictions["documents"].append(
            {
                "id": document_id,
                "sha256": (document.get("source_before") or {}).get("sha256"),
            }
        )
        predictions["predictions"].extend(items)
        predictions["executions"].extend(executions)
        write_json(output / "predictions.json", predictions)
        write_json(output / "manifest.json", manifest)
    manifest["counts"] = {
        "pdfs": len(sources),
        "pages_discovered": sum(item.get("page_count") or 0 for item in manifest["documents"]),
        "documents_unknown_page_count": sum(
            item.get("page_count") is None for item in manifest["documents"]
        ),
        "pages_attempted": sum(len(item["pages"]) for item in manifest["documents"]),
        "pages_failed": sum(
            page["status"] == "failed" for item in manifest["documents"] for page in item["pages"]
        ),
        "documents_failed": sum(item["status"] == "failed" for item in manifest["documents"]),
        "predictions": len(predictions["predictions"]),
    }
    manifest["completed"] = bool(sources) and not manifest["counts"]["documents_failed"]
    manifest["status"] = (
        "completed_inference" if manifest["completed"] else "failed" if sources else "no_examples"
    )
    write_json(output / "predictions.json", predictions)
    manifest["predictions_sha256"] = file_sha256(output / "predictions.json")
    # This hash excludes timing and machine paths, suitable for repeatability checks.
    manifest["observations_sha256"] = sha256(
        canonical_json(predictions["predictions"]).encode()
    ).hexdigest()
    write_json(output / "manifest.json", manifest)
    return manifest


def run_examples(root: Path, output: Path) -> Record:
    """Discover every recursive PDF, including .PDF, without collapsing equal copies."""
    root = root.resolve()
    sources = (
        sorted(
            (
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.casefold() == ".pdf"
            ),
            key=lambda path: path.relative_to(root).as_posix().casefold(),
        )
        if root.is_dir()
        else []
    )
    named = [(path, "example:" + path.relative_to(root).as_posix()) for path in sources]
    manifest = _run(named, output, mode="examples")
    manifest["discovery_root"] = str(root)
    manifest["discovery_root_exists"] = root.is_dir()
    manifest["development_only"] = True
    write_json(output / "manifest.json", manifest)
    return manifest


def run_synthetic(output: Path) -> Record:
    """Materialize fixtures in a separate process; load labels only after inference."""
    output = output.resolve()
    corpus = output / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    reference_path = output / "reference.json"
    # Fixture construction knows labels. Inference runs after that process has exited,
    # discovers PDFs from disk and persists predictions before reading this JSON.
    construction = (
        "import sys; from pathlib import Path; "
        "from tests.symbol_benchmark_fixtures import build_corpus, portable_reference; "
        "from scripts.symbol_benchmark_runner import write_json; "
        "write_json(Path(sys.argv[2]), portable_reference(build_corpus(Path(sys.argv[1]))))"
    )
    subprocess.run(
        [sys.executable, "-c", construction, str(corpus), str(reference_path)], check=True, cwd=ROOT
    )
    sources = [(path, path.stem) for path in sorted(corpus.glob("*.pdf"))]
    manifest = _run(sources, output, mode="synthetic-development")
    # Deliberate phase boundary. The original prediction artifact already exists.
    predictions = json.loads((output / "predictions.json").read_text(encoding="utf-8"))
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    expected = {document["id"]: document for document in reference["documents"]}
    actual = {document["id"]: document for document in manifest["documents"]}
    if set(expected) != set(actual):
        raise ValueError("Generated PDF inventory differs from the frozen reference")
    for identity, document in expected.items():
        source_before = actual[identity]["source_before"]
        if source_before is None or document["sha256"] != source_before["sha256"]:
            raise ValueError(f"Generated PDF hash mismatch: {identity}")
    report = evaluate(reference, predictions)
    write_json(output / "report.json", report)
    manifest.update(
        reference_sha256=file_sha256(reference_path),
        report_sha256=file_sha256(output / "report.json"),
        protocol=PROTOCOL,
        reference_access=(
            "fixture builder separate process; reference loaded after predictions.json persisted"
        ),
    )
    write_json(output / "manifest.json", manifest)
    return {"manifest": manifest, "report": report}


def evaluate_files(reference: Path, predictions: Path, output: Path) -> Record:
    if output.resolve() in {reference.resolve(), predictions.resolve()}:
        raise ValueError("Report must not overwrite reference or predictions")
    report = evaluate(
        json.loads(reference.read_text(encoding="utf-8")),
        json.loads(predictions.read_text(encoding="utf-8")),
    )
    write_json(output, report)
    return report
