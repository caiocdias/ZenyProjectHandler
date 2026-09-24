"""Materialize E13 proposals from frozen E02 predictions without reviewer labels.

This diagnostic runner uses a minimal project shell for each input document.
It cannot resolve documentary support associations absent from E02 predictions.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from scripts.reconcile_symbol_benchmark import _adopted_predictions, _results
from scripts.symbol_benchmark_runner import write_json
from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.application.interpretation_pipeline import (
    ContextoInterpretacao,
    _symbol_proposals,
)
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationPolicy,
    SymbolOccurrence,
    SymbolReconciliation,
    reconcile_symbols,
)
from zeny_project_handler.domain.analysis import ExecucaoAnalise
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.domain.values import CaixaPagina

_NOW = datetime(2026, 9, 24, tzinfo=UTC)
_PAGE_BOX = CaixaPagina(Decimal(0), Decimal(0), Decimal(1), Decimal(1))


def _context(document_id: str, digest: str, pages: tuple[int, ...]) -> ContextoInterpretacao:
    catalog = carregar_catalogo_inicial()
    document_uuid = uuid5(NAMESPACE_URL, f"e13-benchmark-document:{document_id}:{digest}")
    page_records = tuple(
        PaginaDocumento(
            id=uuid5(document_uuid, f"page:{number}"),
            numero=number,
            largura_pontos=Decimal(1),
            altura_pontos=Decimal(1),
            rotacao_graus=0,
            media_box=_PAGE_BOX,
            crop_box=_PAGE_BOX,
        )
        for number in pages
    )
    document = DocumentoProjeto(
        id=document_uuid,
        nome_arquivo=f"{document_uuid}.pdf",
        sha256=digest,
        paginas=page_records,
    )
    project = Projeto(
        id=uuid5(document_uuid, "project"),
        nome=f"Benchmark semântico {document_id}",
        catalogo_versao_id=catalog.id,
        criado_em=_NOW,
        documentos=(document,),
    )
    source = ExecucaoAnalise(
        id=uuid5(document_uuid, "source"),
        projeto_id=project.id,
        metodo="e02-frozen-predictions",
        versao_metodo="1",
        parametros=(),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=_NOW,
        finalizada_em=_NOW,
    )
    return ContextoInterpretacao(
        projeto=project, catalogo=catalog, execucao_extracao=source, evidencias=()
    )


def run(raw: dict[str, Any], excluded_methods: tuple[str, ...]) -> dict[str, Any]:
    adopted = _adopted_predictions(raw, excluded_methods)
    reconciled = reconcile_symbols(_results(adopted), CalibrationPolicy())
    digests = {item["id"]: item["sha256"] for item in raw["documents"]}
    pages: dict[str, set[int]] = defaultdict(set)
    for item in raw["executions"]:
        pages[item["document_id"]].add(item["page"])
    by_document: dict[str, list[SymbolOccurrence]] = defaultdict(list)
    for occurrence in reconciled.occurrences:
        by_document[occurrence.observations[0].fonte.documento_id].append(occurrence)
    records: list[dict[str, object]] = []
    for document_id, digest in sorted(digests.items()):
        page_numbers = tuple(sorted(pages[document_id]))
        if page_numbers != tuple(range(1, len(page_numbers) + 1)):
            raise ValueError(f"Noncontiguous pages for {document_id}")
        context = _context(document_id, digest, page_numbers)
        document_symbols = SymbolReconciliation(
            occurrences=tuple(by_document[document_id]), method_matrix=(), ablations=()
        )
        evidence, proposals, relations = _symbol_proposals(
            document_symbols, context, uuid5(context.projeto.id, "e13-semantic"), ()
        )
        if len(proposals) != len(document_symbols.occurrences):
            raise ValueError(f"E13 lost or duplicated occurrences for {document_id}")
        page_by_id = {
            page.id: page.numero
            for document in context.projeto.documentos
            for page in document.paginas
        }
        for proposal in proposals:
            attributes = dict(proposal.atributos_sugeridos)
            records.append(
                {
                    "document_id": document_id,
                    "document_sha256": digest,
                    "page": page_by_id[proposal.geometria.pagina_id],
                    "layer": attributes.get("simbolo_camada"),
                    "occurrence_id": attributes.get("origem_simbolo_ocorrencia_id"),
                    "proposal_id": str(proposal.id),
                    "category": proposal.categoria.value,
                    "situation": proposal.situacao_projeto.value,
                    "review_state": proposal.estado_revisao.value,
                    "catalog_id": str(proposal.tipo_catalogo_sugerido_id)
                    if proposal.tipo_catalogo_sugerido_id
                    else None,
                    "evidence_ids": [str(value) for value in proposal.evidencia_ids],
                    "bbox": [
                        str(min(point.x for point in proposal.geometria.pontos)),
                        str(min(point.y for point in proposal.geometria.pontos)),
                        str(max(point.x for point in proposal.geometria.pontos)),
                        str(max(point.y for point in proposal.geometria.pontos)),
                    ],
                    "attributes": {
                        key: str(value) if isinstance(value, Decimal) else value
                        for key, value in proposal.atributos_sugeridos
                    },
                }
            )
        if relations:
            raise ValueError("Minimal benchmark context must leave unsupported relations pending")
        if len(evidence) < len({item for proposal in proposals for item in proposal.evidencia_ids}):
            raise ValueError("E13 proposal has no materialized evidence")
    represented = [item["occurrence_id"] for item in records]
    expected = [item.id for item in reconciled.occurrences]
    if len(represented) != len(expected) or set(represented) != set(expected):
        raise ValueError("Semantic projection did not preserve the E12 occurrence union")
    return {
        "schema_version": 1,
        "checkpoint": "e13-semantic-1",
        "input_sha256": sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest(),
        "documents": len(digests),
        "pages": sum(len(items) for items in pages.values()),
        "occurrences": len(expected),
        "proposals": records,
        "limitation": (
            "No documentary evidence in E02 predictions; support association remains pending."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude-method", action="append", default=[])
    args = parser.parse_args()
    raw = json.loads(args.predictions.read_text(encoding="utf-8"))
    result = run(raw, tuple(args.exclude_method))
    write_json(args.output, result)
    print(
        json.dumps(
            {key: result[key] for key in ("documents", "pages", "occurrences")},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
