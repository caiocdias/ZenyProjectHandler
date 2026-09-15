"""Evaluate neural readings through the same interpreter, without promotion/persistence."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from scripts.benchmark_network_pdf import json_value
from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.domain.analysis import (
    ArtefatoExtraido,
    EvidenciaDocumento,
    OrigemObjetoPdf,
)
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria, TipoOrigemPdf
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.interpretation import SolicitacaoInterpretacao


def decode_evidence(row: dict[str, Any]) -> EvidenciaDocumento:
    origin = dict(row["origem_pdf"])
    origin["tipo"] = TipoOrigemPdf(origin["tipo"])
    return EvidenciaDocumento(
        id=UUID(row["id"]),
        execucao_id=UUID(row["execucao_id"]),
        pagina_id=UUID(row["pagina_id"]),
        tipo=TipoEvidencia(row["tipo"]),
        geometria=GeometriaDocumento(
            pagina_id=UUID(row["pagina_id"]),
            tipo=TipoGeometria(row["geometria"]["tipo"]),
            pontos=tuple(
                PontoNormalizado(x=Decimal(p["x"]), y=Decimal(p["y"]))
                for p in row["geometria"]["pontos"]
            ),
        ),
        metodo=row["metodo"],
        versao_metodo=row["versao_metodo"],
        parametros=tuple(tuple(p) for p in row["parametros"]),
        conteudo_bruto=row["conteudo_bruto"],
        criada_em=datetime.fromisoformat(row["criada_em"]),
        origem_pdf=OrigemObjetoPdf(**origin),
        artefato=ArtefatoExtraido(**row["artefato"]) if row.get("artefato") else None,
        atributos_extraidos=tuple(tuple(p) for p in row["atributos_extraidos"]),
    )


def interpret(snapshot: dict[str, Any], rapid: dict[str, Any]) -> dict[str, Any]:
    if not rapid["completed"] or snapshot["source_sha256"] != rapid["source"]["sha256"]:
        raise ValueError("Incomplete OCR or mismatched source")
    native = snapshot["native"]
    evidence = [decode_evidence(row) for row in native["extraction"]["evidencias"]]
    project_id = UUID(native["project"]["id"])
    execution_id = uuid5(project_id, "experimental-rapid-interpretation-e12a-1")
    extraction_id = uuid5(project_id, "experimental-rapid-evidence-e12a-1")
    page_ids = {
        p["numero"]: UUID(p["id"]) for d in native["project"]["documentos"] for p in d["paginas"]
    }
    for row in rapid["readings"]:
        # Visible annotation readings remain a sidecar pending E11/E12B reconciliation.
        if row["annotations"]:
            continue
        page_id = page_ids[row["page"]]
        evidence.append(
            EvidenciaDocumento(
                id=uuid5(extraction_id, row["id"]),
                execucao_id=extraction_id,
                pagina_id=page_id,
                tipo=TipoEvidencia.OCR,
                geometria=GeometriaDocumento(
                    pagina_id=page_id,
                    tipo=TipoGeometria.POLIGONO,
                    pontos=tuple(
                        PontoNormalizado(x=Decimal(str(x)), y=Decimal(str(y)))
                        for x, y in row["quad"]
                    ),
                ),
                metodo="experimental-rapidocr-db-svtr",
                versao_metodo="e12a-1",
                parametros=(),
                conteudo_bruto=row["text"],
                criada_em=datetime.now(UTC),
                atributos_extraidos=(
                    ("motor_ocr", "experimental-rapidocr-db-svtr"),
                    ("confianca", Decimal(str(row["confidence"]))),
                    ("tile_id", row["tile"]),
                ),
            )
        )
    result = InterpretadorRegrasExplicitas(carregar_registro_regras_inicial()).interpretar(
        SolicitacaoInterpretacao(
            projeto_id=project_id,
            execucao_id=execution_id,
            execucao_extracao_id=extraction_id,
            catalogo=carregar_catalogo_inicial(),
            evidencias=tuple(evidence),
            registro=carregar_registro_regras_inicial(),
        )
    )
    return {
        "source_sha256": snapshot["source_sha256"],
        "experimental": True,
        "completed": not result.diagnosticos,
        "production_promotions": 0,
        "ocr": {
            "extraction": {"evidencias": evidence},
            "semantic": {
                "elementos": result.elementos,
                "relacoes": result.relacoes,
                "diagnosticos": result.diagnosticos,
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--readings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in (args.snapshot.resolve(), args.readings.resolve()):
        raise ValueError("Output cannot overwrite evidence inputs")
    result = interpret(
        json.loads(args.snapshot.read_text(encoding="utf-8")),
        json.loads(args.readings.read_text(encoding="utf-8")),
    )
    args.output.write_text(
        json.dumps(result, default=json_value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not result["completed"]:
        raise RuntimeError("Interpreter diagnostics recorded; experiment incomplete")
    print(
        f"Neural interpreter: {len(result['ocr']['semantic']['elementos'])} proposals, no promotion"
    )


if __name__ == "__main__":
    main()
