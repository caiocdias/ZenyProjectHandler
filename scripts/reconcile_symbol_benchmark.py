"""Apply the E12 symbol reconciler to frozen E02 predictions.

The optional reference is opened only after the composition artifact is written.
No reviewer annotation or benchmark label enters reconciliation.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.symbol_benchmark_evaluator import _evaluation, evaluate
from scripts.symbol_benchmark_runner import write_json
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationPolicy,
    reconcile_symbols,
)
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos, SituacaoProjeto, TipoGeometria
from zeny_project_handler.domain.symbols import (
    AlternativaClasseSimbolo,
    CoberturaMetodoSimbolos,
    FonteObservacaoSimbolo,
    GeometriaObservacaoSimbolo,
    ObservacaoSimbolo,
    PerfilMetodoSimbolos,
    PrimitivaObservadaSimbolo,
    ResultadoMetodoSimbolos,
    TransformacaoSimbolo,
)
from zeny_project_handler.domain.values import PontoNormalizado

Record = dict[str, Any]
_PAGE = (
    PontoNormalizado(Decimal(0), Decimal(0)),
    PontoNormalizado(Decimal(1), Decimal(1)),
)
_IDENTITY = TransformacaoSimbolo(
    normalizada_para_original=(
        Decimal(1),
        Decimal(0),
        Decimal(0),
        Decimal(1),
        Decimal(0),
        Decimal(0),
    ),
    sistema_original="benchmark-normalized-bbox",
)


def _profile(method: Record) -> PerfilMetodoSimbolos:
    return PerfilMetodoSimbolos(
        metodo_id=method["id"],
        versao=method["version"],
        familia=method["algorithm_family"],
        dominio_aplicacao="benchmark-frozen-predictions",
        classes_suportadas=tuple(method["supported_classes"]),
        camadas_suportadas=tuple(method.get("supported_layers", ("base",))),
        fontes_compartilhadas=tuple(method["shared_sources"]),
        perfil_referencia="e02-e12-development-calibration",
    )


def _source(prediction: Record, digests: dict[str, str]) -> FonteObservacaoSimbolo:
    return FonteObservacaoSimbolo(
        documento_id=prediction["document_id"],
        documento_sha256=digests[prediction["document_id"]],
        pagina_numero=prediction["page"],
        camada=prediction["layer"],
    )


def _observation(
    prediction: Record, profile: PerfilMetodoSimbolos, digests: dict[str, str]
) -> ObservacaoSimbolo:
    x0, y0, x1, y1 = (Decimal(str(value)) for value in prediction["bbox"])
    box = ((x0, y0), (x1, y1))
    provenance = prediction.get("provenance") or {}
    alternatives = provenance.get("alternatives") or [
        {"class_id": prediction["class_id"], "subtype": None}
    ]
    primitive_ids = tuple(str(item) for item in provenance.get("primitive_ids", ()) if str(item))
    attributes = [
        ("contexto", provenance.get("reported_context") or prediction.get("context", "unknown")),
        ("estrato", "default"),
    ]
    raw_situation = prediction.get("situation")
    observed_situation: SituacaoProjeto | None = None
    if raw_situation is not None:
        try:
            observed_situation = SituacaoProjeto(str(raw_situation))
        except ValueError:
            attributes.append(("situacao_evidencia", f"valor_bruto:{raw_situation}"))
        else:
            attributes.append(("situacao_origem", "predicao_benchmark_sem_vigencia_validada"))
    legacy_color = provenance.get("legacy_color")
    if isinstance(legacy_color, str) and legacy_color:
        attributes.append(("cor", legacy_color))
    for source_key, target_key in (
        ("variant_id", "variante_inventario"),
        ("possible_references", "referencias_possiveis"),
        ("role", "papel"),
    ):
        value = provenance.get(source_key)
        if value is not None:
            attributes.append(
                (
                    target_key,
                    json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value,
                )
            )
    return ObservacaoSimbolo(
        fonte=_source(prediction, digests),
        metodo_assinatura=profile.assinatura(),
        geometria=GeometriaObservacaoSimbolo(
            tipo=TipoGeometria.CAIXA,
            pontos_originais=box,
            pontos_normalizados=(PontoNormalizado(x0, y0), PontoNormalizado(x1, y1)),
            transformacao=_IDENTITY,
        ),
        alternativas=tuple(
            AlternativaClasseSimbolo(classe=item.get("class_id"), subtipo=item.get("subtype"))
            for item in alternatives
        ),
        score_bruto=Decimal(str(prediction["score"]))
        if prediction.get("score") is not None
        else None,
        primitivas=tuple(
            PrimitivaObservadaSimbolo(indice=item, camada=None, pontos_originais=box)
            for item in primitive_ids
        ),
        situacao=observed_situation,
        atributos=tuple(attributes),
        chave_legada=prediction["id"],
    )


def _results(raw: Record) -> tuple[ResultadoMetodoSimbolos, ...]:
    digests = {document["id"]: document["sha256"] for document in raw["documents"]}
    profiles = {method["id"]: _profile(method) for method in raw["methods"]}
    by_method: dict[str, list[Record]] = defaultdict(list)
    for prediction in raw["predictions"]:
        by_method[prediction["method_id"]].append(prediction)
    executions: dict[str, list[Record]] = defaultdict(list)
    for execution in raw["executions"]:
        executions[execution["method_id"]].append(execution)
    results = []
    for method_id, profile in profiles.items():
        observations = tuple(_observation(item, profile, digests) for item in by_method[method_id])
        coverages = []
        for execution in executions[method_id]:
            if execution["layer"] not in profile.camadas_suportadas:
                continue
            source = _source(execution, digests)
            own = tuple(observation for observation in observations if observation.fonte == source)
            status = execution["status"]
            state = EstadoMetodoSimbolos.CONCLUIDO if own else EstadoMetodoSimbolos.NAO_DETECCAO
            if execution.get("coverage_state"):
                state = EstadoMetodoSimbolos(execution["coverage_state"])
            elif status == "failed":
                state = EstadoMetodoSimbolos.FALHA
            elif status == "not_applicable":
                state = EstadoMetodoSimbolos.FORA_DOMINIO
            coverages.append(
                CoberturaMetodoSimbolos(
                    fonte=source,
                    regiao_normalizada=_PAGE,
                    classes_avaliadas=profile.classes_suportadas,
                    estado=state,
                    motivo=execution.get("reason") or "benchmark execution state"
                    if state
                    not in {EstadoMetodoSimbolos.CONCLUIDO, EstadoMetodoSimbolos.NAO_DETECCAO}
                    else None,
                )
            )
        if not coverages:
            raise ValueError(f"No covered pages for method {method_id}")
        results.append(
            ResultadoMetodoSimbolos(
                perfil=profile, coberturas=tuple(coverages), observacoes=observations
            )
        )
    return tuple(results)


def compose(raw: Record, excluded_methods: tuple[str, ...] = ()) -> Record:
    unknown = set(excluded_methods) - {item["id"] for item in raw["methods"]}
    if unknown:
        raise ValueError(f"Unknown excluded methods: {sorted(unknown)}")
    adopted = _adopted_predictions(raw, excluded_methods)
    results = _results(adopted)
    reconciliation = reconcile_symbols(results, CalibrationPolicy())
    by_observation = {
        observation.id: prediction
        for result in results
        for observation in result.observacoes
        for prediction in adopted["predictions"]
        if observation.chave_legada == prediction["id"]
    }
    method_ids = {result.perfil.assinatura(): result.perfil.metodo_id for result in results}
    candidates = []
    for occurrence in reconciliation.occurrences:
        selected = next(
            observation
            for observation in occurrence.observations
            if observation.geometria == occurrence.geometry
        )
        source = by_observation[selected.id]
        classes = sorted({item.classe for item in occurrence.alternatives if item.classe})
        families = sorted({by_observation[item.id]["family"] for item in occurrence.observations})
        candidate = {
            **source,
            "id": "e12:" + occurrence.id,
            "class_id": classes[0] if len(classes) == 1 else None,
            "family": families[0] if len(families) == 1 else None,
            "observation_ids": [by_observation[item.id]["id"] for item in occurrence.observations],
            "method_ids": [method_ids[item] for item in occurrence.support],
            "alternatives": [
                {"class_id": item.classe, "subtype": item.subtipo}
                for item in occurrence.alternatives
            ],
            "reference_ids": list(occurrence.reference_ids),
            "score": None,
            "raw_scores": [
                {
                    "method_id": method_ids[signature],
                    "score": float(score) if score is not None else None,
                }
                for signature, score in occurrence.raw_scores
            ],
            "calibrated_probability": (
                float(occurrence.calibrated_probability)
                if occurrence.calibrated_probability is not None
                else None
            ),
            "decision": occurrence.decision,
            "reasons": list(occurrence.reasons),
            "review_required": occurrence.decision != "eligible",
        }
        candidates.append(candidate)
    input_ids = {item["id"] for item in adopted["predictions"]}
    represented = [item for candidate in candidates for item in candidate["observation_ids"]]
    if len(represented) != len(input_ids) or set(represented) != input_ids:
        raise ValueError("Composition dropped or duplicated detector observations")
    return {
        "schema_version": 1,
        "composition_version": "symbol-reconciliation-e12-1",
        "methods": adopted["methods"],
        "excluded_experimental_methods": sorted(excluded_methods),
        "documents": raw["documents"],
        "input_observations": len(adopted["predictions"]),
        "candidates": candidates,
        "method_matrix": [
            {
                "occurrence_id": "e12:" + row.occurrence_id,
                "method_id": method_ids[row.method_signature],
                "state": row.state,
                "classes": list(row.classes),
            }
            for row in reconciliation.method_matrix
        ],
        "ablations": [
            {
                "method_id": method_ids[item.method_signature],
                "candidate_count": len(item.occurrences),
                "lost_occurrence_ids": ["e12:" + value for value in item.lost_occurrence_ids],
                "eligible_before": item.eligible_before,
                "eligible_after": item.eligible_after,
            }
            for item in reconciliation.ablations
        ],
        "calibration": {
            "minimum_samples": 30,
            "promotion_probability": "0.99",
            "entries": [],
            "reason": "calibration partition has four positives; no per-method/class/stratum fit",
        },
    }


def _adopted_predictions(raw: Record, excluded_methods: tuple[str, ...]) -> Record:
    return {
        **raw,
        "methods": [item for item in raw["methods"] if item["id"] not in excluded_methods],
        "predictions": [
            item for item in raw["predictions"] if item["method_id"] not in excluded_methods
        ],
        "executions": [
            item for item in raw["executions"] if item["method_id"] not in excluded_methods
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--exclude-method", action="append", default=[])
    args = parser.parse_args()
    raw = json.loads(args.predictions.read_text(encoding="utf-8"))
    composition = compose(raw, tuple(args.exclude_method))
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "composition.json", composition)
    summary: Record = {
        "observations": composition["input_observations"],
        "occurrences": len(composition["candidates"]),
        "ambiguous": sum(item["class_id"] is None for item in composition["candidates"]),
    }
    if args.reference is not None:
        reference = json.loads(args.reference.read_text(encoding="utf-8"))
        baseline = evaluate(reference, raw)
        adopted_baseline = evaluate(
            reference, _adopted_predictions(raw, tuple(args.exclude_method))
        )
        exact = [
            item
            for item in composition["candidates"]
            if item["class_id"] is not None and item["family"] is not None
        ]
        classes = {item["class_id"] for item in reference["occurrences"]} | {
            item["class_id"] for item in exact
        }
        final = _evaluation(exact, reference, classes, curves=False)
        report = {
            "denominators": baseline["denominators"],
            "methods": {key: value["micro"] for key, value in baseline["methods"].items()},
            "raw_union": baseline["compositions"]["raw_union"]["micro"],
            "adopted_raw_union": adopted_baseline["compositions"]["raw_union"]["micro"],
            "final_exact_class": final["micro"],
            "final_excluded_ambiguous": len(composition["candidates"]) - len(exact),
            "ablations": {
                key: value["micro"] for key, value in baseline["compositions"]["ablations"].items()
            },
            "adopted_ablations": {
                key: value["micro"]
                for key, value in adopted_baseline["compositions"]["ablations"].items()
            },
            "note": (
                "Exact-class metric excludes unresolved class/family alternatives; "
                "all remain in composition.json."
            ),
        }
        write_json(args.output / "evaluation.json", report)
        summary["micro"] = report["final_exact_class"]
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
