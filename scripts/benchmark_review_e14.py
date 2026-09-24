"""Project frozen detector outputs through persisted review and real deliverable writers.

This local diagnostic takes no reviewer labels. It does not execute detection or
claim visual approval. Source identity and complete recursive coverage are required.
Use a new output directory for each checkpoint; existing databases are refused.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4, uuid5

from scripts.benchmark_semantic_e13 import _context
from scripts.reconcile_symbol_benchmark import _adopted_predictions, _results
from scripts.symbol_benchmark_runner import write_json
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import SqlAlchemyUnitOfWork
from zeny_project_handler.application.interpretation_pipeline import (
    SYMBOL_SEMANTICS_VERSION,
    _symbol_proposals,
)
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationPolicy,
    SymbolReconciliation,
    reconcile_symbols,
)
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler_contracts.exports import (
    CreateDeliverableExportRequest,
    DeliverableExportKind,
)
from zeny_project_handler_server.composition import compose_server_runtime
from zeny_project_handler_server.config import ServerSettings


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _checkpoint_code() -> dict[str, str]:
    project = Path(__file__).resolve().parents[1]
    paths = (
        "scripts/benchmark_review_e14.py",
        "scripts/reconcile_symbol_benchmark.py",
        "src/zeny_project_handler/application/interpretation_pipeline.py",
        "src/zeny_project_handler/application/human_review.py",
        "src/zeny_project_handler/application/symbol_reconciliation.py",
        "src/zeny_project_handler_contracts/review.py",
        "src/zeny_project_handler_server/review_api.py",
        "src/zeny_project_handler_server/symbol_review.py",
        "src/zeny_project_handler_server/symbol_support.py",
        "src/zeny_project_handler_server/deliverable_exports.py",
        "src/zeny_project_handler_server/xlsx_export.py",
    )
    return {str(path): _digest(project / path) for path in paths}


def run(predictions: Path, manifest_path: Path, root: Path, output: Path) -> dict[str, Any]:
    code = _checkpoint_code()
    raw = json.loads(predictions.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("completed"):
        raise ValueError("Cannot reuse an incomplete inference checkpoint")
    discovered = {path.resolve() for path in root.rglob("*") if path.suffix.lower() == ".pdf"}
    recorded = {Path(item["path"]).resolve() for item in manifest["documents"]}
    if not discovered or discovered != recorded:
        raise ValueError("Recursive PDF coverage differs from the frozen manifest")
    prediction_hashes = {item["id"]: item["sha256"] for item in raw["documents"]}
    if set(prediction_hashes) != {item["id"] for item in manifest["documents"]}:
        raise ValueError("Prediction documents differ from the frozen manifest")
    for item in manifest["documents"]:
        source = Path(item["path"])
        if (
            not item["source_unchanged"]
            or source.stat().st_size != item["source_before"]["bytes"]
            or _digest(source) != item["source_before"]["sha256"]
            or prediction_hashes.get(item["id"]) != item["source_before"]["sha256"]
        ):
            raise ValueError(f"Source identity changed: {source}")
    data_directory = output / "server"
    if data_directory.exists():
        raise ValueError("Use a fresh checkpoint output; no existing server data is overwritten")
    output.mkdir(parents=True, exist_ok=True)
    excluded = ("structural-raster-graph", "structural-vector-graph")
    symbols = reconcile_symbols(_results(_adopted_predictions(raw, excluded)), CalibrationPolicy())
    runtime = compose_server_runtime(
        ServerSettings(
            password=f"e14-local-diagnostic-{uuid4()}",
            market_sqlserver_connection_string="Server=localhost;Database=e14-unused",
            data_directory=data_directory,
        )
    )
    documents = []
    try:
        assert runtime.review_api is not None
        assert runtime.portability_api is not None
        for index, entry in enumerate(manifest["documents"], start=1):
            source = Path(entry["path"]).resolve()
            context = _context(
                entry["id"],
                entry["source_before"]["sha256"],
                tuple(range(1, entry["page_count"] + 1)),
            )
            inspection = PyMuPdfReader().inspecionar(
                source, documento_id=context.projeto.documentos[0].id
            )
            if len(inspection.documento.paginas) != entry["page_count"]:
                raise ValueError("Page count differs from frozen predictions")
            document = replace(
                inspection.documento,
                paginas=tuple(
                    replace(page, id=old.id)
                    for page, old in zip(
                        inspection.documento.paginas,
                        context.projeto.documentos[0].paginas,
                        strict=True,
                    )
                ),
            )
            context = replace(
                context,
                projeto=replace(
                    context.projeto,
                    nome=f"{index:010d}",
                    documentos=(document,),
                    ordem_leitura_paginas=tuple(page.id for page in document.paginas),
                ),
            )
            occurrences = tuple(
                item
                for item in symbols.occurrences
                if item.observations[0].fonte.documento_id == entry["id"]
            )
            occurrence_ids = {item.id for item in occurrences}
            subset = SymbolReconciliation(
                occurrences=occurrences,
                method_matrix=tuple(
                    row for row in symbols.method_matrix if row.occurrence_id in occurrence_ids
                ),
                ablations=(),
            )
            execution_id = uuid5(context.projeto.id, SYMBOL_SEMANTICS_VERSION)
            evidence, proposals, relations = _symbol_proposals(subset, context, execution_id, ())
            assert context.execucao_extracao.finalizada_em is not None
            execution = replace(
                context.execucao_extracao,
                id=execution_id,
                metodo="e14-frozen-review-projection",
                versao_metodo=SYMBOL_SEMANTICS_VERSION,
                parametros=(("execucao_extracao_id", str(context.execucao_extracao.id)),),
                iniciada_em=context.execucao_extracao.iniciada_em + timedelta(seconds=1),
                finalizada_em=context.execucao_extracao.finalizada_em + timedelta(seconds=1),
            )
            with SqlAlchemyUnitOfWork(runtime.core.engine) as work:
                work.projetos.salvar(context.projeto)
                work.fontes_pdf.salvar(
                    ReferenciaFontePdf(
                        documento_id=document.id,
                        projeto_id=context.projeto.id,
                        caminho_canonico=source,
                        sha256=document.sha256,
                        tamanho_bytes=source.stat().st_size,
                        modificado_em_ns=source.stat().st_mtime_ns,
                    )
                )
                work.execucoes_analise.salvar(context.execucao_extracao)
                work.execucoes_analise.salvar(execution)
                for item in evidence:
                    work.evidencias.salvar(item)
                for proposal in proposals:
                    work.propostas.salvar(proposal)
                for relation in relations:
                    work.propostas.salvar(relation)
                work.commit()
            session = runtime.review_api.get_semantic_session(context.projeto.id)
            folder = output / f"document-{index:02d}"
            folder.mkdir()
            session_path = folder / "review-session.json"
            session_path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
            exports = []
            for kind, filename in (
                (DeliverableExportKind.RESULTS_XLSX, "results.xlsx"),
                (DeliverableExportKind.ANNOTATED_PDF, "review.pdf"),
            ):
                metadata = runtime.portability_api.create_deliverable_export(
                    context.projeto.id,
                    CreateDeliverableExportRequest(
                        kind=kind,
                        expected_project_version=session.project_version,
                    ),
                )
                download = runtime.portability_api.get_download(metadata.download_id.root)
                destination = folder / filename
                shutil.copyfile(download.path, destination)
                exports.append(
                    {"kind": kind.value, "path": str(destination), "sha256": _digest(destination)}
                )
            reopened = runtime.review_api.get_semantic_session(context.projeto.id)
            if reopened != session:
                raise ValueError("Export changed the review session")
            if _digest(source) != document.sha256:
                raise ValueError("Source PDF changed during projection/export")
            documents.append(
                {
                    "document_id": entry["id"],
                    "source": str(source),
                    "sha256": document.sha256,
                    "page_count": len(document.paginas),
                    "project_id": str(context.projeto.id),
                    "page_ids": [str(page.id) for page in document.paginas],
                    "proposals": len(session.proposals),
                    "session": str(session_path),
                    "session_sha256": _digest(session_path),
                    "exports": exports,
                }
            )
    finally:
        runtime.close()
    if _checkpoint_code() != code:
        raise ValueError("Review/export code changed during the checkpoint run")
    result = {
        "code_sha256": code,
        "checkpoint": SYMBOL_SEMANTICS_VERSION,
        "inference": "reused-frozen-output",
        "predictions_sha256": _digest(predictions),
        "manifest_sha256": _digest(manifest_path),
        "excluded_methods": excluded,
        "documents": documents,
        "pages": sum(item["page_count"] for item in documents),
        "proposals": sum(item["proposals"] for item in documents),
        "limitations": [
            "Minimal documentary context; support remains pending",
            "Visual inspection is separate; this runner does not approve images",
        ],
    }
    write_json(output / "manifest.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("examples"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.predictions, args.manifest, args.root, args.output)
    print(
        json.dumps(
            {
                "documents": len(result["documents"]),
                "pages": result["pages"],
                "proposals": result["proposals"],
            }
        )
    )


if __name__ == "__main__":
    main()
