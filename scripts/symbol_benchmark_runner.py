# mypy: disable-error-code="no-untyped-call"
"""Reproducible E02 inference runner; the detector never receives ground truth."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import tracemalloc
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any

import pymupdf

import zeny_project_handler.adapters.analysis.declarative_symbols as declarative_symbols
import zeny_project_handler.adapters.analysis.pymupdf_guys as pymupdf_guys
import zeny_project_handler.adapters.analysis.pymupdf_symbols as pymupdf_symbols
import zeny_project_handler.adapters.analysis.pymupdf_transformers as pymupdf_transformers
import zeny_project_handler.adapters.analysis.raster_symbols as raster_symbols
import zeny_project_handler.adapters.analysis.structural_symbols as structural_symbols
from scripts.symbol_benchmark_evaluator import PROTOCOL, evaluate
from zeny_project_handler.adapters.analysis.pymupdf_analyzer import PyMuPdfDocumentAnalyzer
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos

ROOT = Path(__file__).resolve().parents[1]
METHOD_ID = "legacy-vector-symbols"
TRANSFORMER_METHOD_ID = "transformer-vector-shapes"
GUY_METHOD_ID = "guy-vector-shapes"
PACKAGE_METHOD_ID = "declarative-vector-packages"
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


def transformer_method_metadata() -> Record:
    """Describe the opt-in E05 method separately from the E02 baseline."""
    profile = pymupdf_transformers.perfil_transformadores()
    return {
        "id": TRANSFORMER_METHOD_ID,
        "version": profile.versao,
        "algorithm_family": profile.familia,
        "shared_sources": list(profile.fontes_compartilhadas),
        "supported_classes": list(profile.classes_suportadas),
        "supported_layers": list(profile.camadas_suportadas),
        "source_sha256_lf": _text_sha256(Path(pymupdf_transformers.__file__)),
        "configuration": "E05 visual vector shapes; raw score is not calibrated probability",
        "family_mapping": "per-observation familia_inventario; alternatives retained",
    }


def guy_method_metadata() -> Record:
    """Describe the opt-in E06 mechanical relation method."""
    profile = pymupdf_guys.perfil_estais()
    return {
        "id": GUY_METHOD_ID,
        "version": profile.versao,
        "algorithm_family": profile.familia,
        "shared_sources": list(profile.fontes_compartilhadas),
        "supported_classes": list(profile.classes_suportadas),
        "supported_layers": list(profile.camadas_suportadas),
        "source_sha256_lf": _text_sha256(Path(pymupdf_guys.__file__)),
        "configuration": "E06 vector mechanical relation; no calibrated probability",
        "family_mapping": "per-observation familia_inventario; alternatives retained",
    }


def package_method_metadata(
    packages: tuple[declarative_symbols.Package, ...] | None = None,
) -> Record:
    """Expose only executable E07 classes; pending cells stay in the package audit."""
    packages = declarative_symbols.carregar_pacotes() if packages is None else packages
    profile = declarative_symbols.perfil_pacotes(packages)
    variants = [variant for package in packages for variant in package["variants"]]
    enabled = [item for item in variants if item["recognition"]["status"] == "enabled"]
    return {
        "id": PACKAGE_METHOD_ID,
        "version": profile.versao,
        "algorithm_family": profile.familia,
        "shared_sources": list(profile.fontes_compartilhadas),
        "supported_classes": list(profile.classes_suportadas),
        "supported_layers": list(profile.camadas_suportadas),
        "source_sha256_lf": _text_sha256(Path(declarative_symbols.__file__)),
        "package_sha256": sha256(canonical_json(packages).encode()).hexdigest(),
        "package_count": len(packages),
        "enabled_variant_count": len(enabled),
        "pending_variant_count": len(variants) - len(enabled),
        "configuration": "E07 vector grammars; pending inventory cells are not detections",
        "family_mapping": "per-observation familia_inventario; no asset promotion",
    }


def raster_method_metadata(
    templates: tuple[raster_symbols.TemplateRasterVerificado, ...],
    configuration: raster_symbols.ConfiguracaoDetectorRaster,
) -> list[Record]:
    """Describe the E08 opt-in methods and their common raster/template origin."""
    profiles = raster_symbols.perfis_simbolos_raster(
        templates=templates, configuracao=configuration
    )
    return [
        {
            "id": profile.metodo_id,
            "version": profile.versao,
            "algorithm_family": profile.familia,
            "shared_sources": list(profile.fontes_compartilhadas),
            "supported_classes": list(profile.classes_suportadas),
            "supported_layers": list(profile.camadas_suportadas),
            "source_sha256_lf": _text_sha256(Path(raster_symbols.__file__)),
            "signature": profile.assinatura(),
            "templates": [
                {"id": item.id, "sha256": item.sha256, "source": item.fonte_referencia}
                for item in templates
            ],
            "configuration": {
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in profile.parametros
            },
            "score_kind": (
                "raw generalized Hough votes; not calibrated probability"
                if profile.metodo_id == "raster-hough-generalizado"
                else "raw image similarity; not calibrated probability"
            ),
            "source_limitation": "Bundled template is an author-owned E02 control, not F02 artwork",
        }
        for profile in profiles
    ]


def structural_method_metadata(
    configurations: tuple[structural_symbols.ConfiguracaoDetectorEstrutural, ...],
) -> list[Record]:
    """Describe structural methods and distinguish raster from shared vector input."""
    return [
        {
            "id": profile.metodo_id,
            "version": profile.versao,
            "algorithm_family": profile.familia,
            "shared_sources": list(profile.fontes_compartilhadas),
            "supported_classes": list(profile.classes_suportadas),
            "supported_layers": list(profile.camadas_suportadas),
            "source_sha256_lf": _text_sha256(Path(structural_symbols.__file__)),
            "signature": profile.assinatura(),
            "configuration": {
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in profile.parametros
            },
            "score_kind": "raw graph descriptor fit; not calibrated probability",
            "source_limitation": "Author-owned shape grammar; no F02 equivalence claimed",
        }
        for profile in (
            structural_symbols.perfil_simbolos_estruturais(configuracao=config)
            for config in configurations
        )
    ]


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


def _transformer_prediction(observation: Any, document_id: str) -> Record:
    """Project one E03 observation into the frozen E02 evaluator schema."""
    attributes = dict(observation.atributos)
    points = [
        (float(point.x), float(point.y)) for point in observation.geometria.pontos_normalizados
    ]
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    alternatives = [
        {"class_id": item.classe, "subtype": item.subtipo} for item in observation.alternativas
    ]
    primary = next((item for item in observation.alternativas if item.classe), None)
    if primary is None:
        raise ValueError("Transformer observation has no class alternative")
    reported_context = attributes.get("contexto", "operational")
    if reported_context not in {"operational", "legend", "unknown"}:
        raise ValueError(f"Unknown transformer context: {reported_context}")
    # The E02 evaluator has no unknown-context bucket. Keep a reviewable
    # candidate in its operational denominator rather than silently drop it.
    context = "operational" if reported_context == "unknown" else reported_context
    return {
        "id": f"{document_id}:{observation.id}",
        "method_id": TRANSFORMER_METHOD_ID,
        "document_id": document_id,
        "page": observation.fonte.pagina_numero,
        "layer": observation.fonte.camada,
        "family": attributes["familia_inventario"],
        "class_id": primary.classe,
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
        "score": float(observation.score_bruto) if observation.score_bruto is not None else None,
        "situation": observation.situacao.value if observation.situacao is not None else None,
        "quantity": None,
        "association": None,
        "context": context,
        "review_required": True,
        "provenance": {
            "observation_id": observation.id,
            "variant_graphic": attributes.get("variante_grafica"),
            "possible_references": attributes.get("referencias_possiveis"),
            "possible_families": attributes.get("familias_possiveis"),
            "components": attributes.get("componentes"),
            "cardinality": attributes.get("cardinalidade"),
            "nearby_text": attributes.get("texto_proximo"),
            "text_conflict": attributes.get("conflito_textual"),
            "reported_context": reported_context,
            "alternatives": alternatives,
            "primitive_ids": [item.indice for item in observation.primitivas],
            "score_kind": "raw; not calibrated probability",
        },
    }


def _guy_prediction(observation: Any, document_id: str) -> Record:
    """Keep a mechanical trace and alternatives in the E02 evaluation projection."""
    attributes = dict(observation.atributos)
    points = [
        (float(point.x), float(point.y)) for point in observation.geometria.pontos_normalizados
    ]
    # The E03 polyline is the guy's shaft. The benchmark bbox covers its
    # terminals too, while trace continues to describe the mechanical path.
    a, b, c, d, e, f = map(float, observation.geometria.transformacao.normalizada_para_original)
    determinant = a * d - b * c
    for primitive in observation.primitivas:
        for original_x, original_y in primitive.pontos_originais:
            x, y = float(original_x) - e, float(original_y) - f
            points.append(((d * x - c * y) / determinant, (-b * x + a * y) / determinant))
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    raw_bbox = [min(xs), min(ys), max(xs), max(ys)]
    bounded_bbox = [max(0.0, min(1.0, value)) for value in raw_bbox]
    primary = next((item for item in observation.alternativas if item.classe == "ESTAI"), None)
    if primary is None:
        raise ValueError("Guy observation has no ESTAI alternative")
    reported_context = attributes.get("contexto", "unknown")
    if reported_context not in {"operational", "legend", "unknown"}:
        raise ValueError(f"Unknown guy context: {reported_context}")
    return {
        "id": f"{document_id}:{observation.id}",
        "method_id": GUY_METHOD_ID,
        "document_id": document_id,
        "page": observation.fonte.pagina_numero,
        "layer": observation.fonte.camada,
        "family": attributes["familia_inventario"],
        "class_id": primary.classe,
        "bbox": bounded_bbox,
        "trace": [
            [float(point.x), float(point.y)] for point in observation.geometria.pontos_normalizados
        ],
        "score": float(observation.score_bruto) if observation.score_bruto is not None else None,
        "situation": observation.situacao.value if observation.situacao is not None else None,
        "quantity": None,
        "association": None,
        "context": "operational" if reported_context == "unknown" else reported_context,
        "review_required": True,
        "provenance": {
            "observation_id": observation.id,
            "variant_graphic": attributes.get("variante_grafica"),
            "possible_references": attributes.get("referencias_possiveis"),
            "possible_supports": attributes.get("suportes_possiveis"),
            "components": attributes.get("componentes"),
            "mechanical_link": attributes.get("vinculo"),
            "electrical_connectivity": attributes.get("conectividade_eletrica"),
            "cardinality": attributes.get("cardinalidade"),
            "nearby_text": attributes.get("texto_proximo"),
            "reported_context": reported_context,
            "alternatives": [
                {"class_id": item.classe, "subtype": item.subtipo}
                for item in observation.alternativas
            ],
            "primitive_ids": [item.indice for item in observation.primitivas],
            "raw_component_bbox": raw_bbox,
            "bbox_clipped": bounded_bbox != raw_bbox,
            "score_kind": "raw; not calibrated probability",
        },
    }


def _package_prediction(observation: Any, document_id: str) -> Record:
    """Project one E07 shape without treating informative symbols as equipment."""
    attributes = dict(observation.atributos)
    points = [
        (float(point.x), float(point.y)) for point in observation.geometria.pontos_normalizados
    ]
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    primary = next((item for item in observation.alternativas if item.classe), None)
    if primary is None:
        raise ValueError("Package observation has no class alternative")
    role = attributes["papel"]
    if role not in {"operational", "informative"}:
        raise ValueError(f"Unknown package role: {role}")
    return {
        "id": f"{document_id}:{observation.id}",
        "method_id": PACKAGE_METHOD_ID,
        "document_id": document_id,
        "page": observation.fonte.pagina_numero,
        "layer": observation.fonte.camada,
        "family": attributes["familia_inventario"],
        "class_id": primary.classe,
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
        "score": float(observation.score_bruto) if observation.score_bruto is not None else None,
        "situation": observation.situacao.value if observation.situacao is not None else None,
        "quantity": None,
        "association": None,
        "context": "informative" if role == "informative" else "operational",
        "review_required": True,
        "provenance": {
            "observation_id": observation.id,
            "variant_id": attributes["variante_inventario"],
            "possible_references": attributes["referencias_possiveis"],
            "role": role,
            "destination": attributes["destino"],
            "reported_context": attributes["contexto"],
            "source_reference": attributes["fonte_referencia"],
            "primitive_ids": [item.indice for item in observation.primitivas],
            "score_kind": "raw; not calibrated probability",
        },
    }


def _raster_prediction(observation: Any, document_id: str, method_id: str) -> Record:
    """Project E03 raster evidence into E02 without treating scores as probabilities."""
    attributes = dict(observation.atributos)
    points = [
        (float(point.x), float(point.y)) for point in observation.geometria.pontos_normalizados
    ]
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    primary = next((item for item in observation.alternativas if item.classe), None)
    if primary is None:
        raise ValueError("Raster observation has no class alternative")
    family = CLASS_FAMILY.get(primary.classe)
    if family is None:
        raise ValueError(f"No E01 family mapping for raster class {primary.classe}")
    return {
        "id": f"{document_id}:{observation.id}",
        "method_id": method_id,
        "document_id": document_id,
        "page": observation.fonte.pagina_numero,
        "layer": observation.fonte.camada,
        "family": family,
        "class_id": primary.classe,
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
        "score": float(observation.score_bruto) if observation.score_bruto is not None else None,
        "situation": observation.situacao.value if observation.situacao is not None else None,
        "quantity": None,
        "association": None,
        "context": "operational",
        "review_required": True,
        "provenance": {
            "observation_id": observation.id,
            "template_id": observation.template,
            "raster_sha256": observation.raster_sha256,
            "source_reference": attributes.get("fonte_referencia"),
            "template_sha256": attributes.get("template_sha256"),
            "tile_locations": attributes.get("tiles_concordantes"),
            "correlated_variants": attributes.get("variantes_correlacionadas"),
            "reported_context": "unknown; requires independent review",
            "alternatives": [
                {
                    "class_id": item.classe,
                    "subtype": item.subtipo,
                    "raw_score": float(item.score_bruto) if item.score_bruto is not None else None,
                }
                for item in observation.alternativas
            ],
            "score_kind": (
                "raw generalized Hough votes; not calibrated probability"
                if method_id == "raster-hough-generalizado"
                else "raw image similarity; not calibrated probability"
            ),
        },
    }


def _structural_prediction(observation: Any, document_id: str, method_id: str) -> Record:
    """Project graph evidence without equating raw descriptor fit to confidence."""
    points = [
        (float(point.x), float(point.y)) for point in observation.geometria.pontos_normalizados
    ]
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    primary = next((item for item in observation.alternativas if item.classe), None)
    if primary is None:
        raise ValueError("Structural observation has no class alternative")
    family = CLASS_FAMILY.get(primary.classe)
    if family is None:
        raise ValueError(f"No E01 family mapping for structural class {primary.classe}")
    return {
        "id": f"{document_id}:{observation.id}",
        "method_id": method_id,
        "document_id": document_id,
        "page": observation.fonte.pagina_numero,
        "layer": observation.fonte.camada,
        "family": family,
        "class_id": primary.classe,
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
        "score": float(observation.score_bruto) if observation.score_bruto is not None else None,
        "situation": observation.situacao.value if observation.situacao is not None else None,
        "quantity": None,
        "association": None,
        "context": "operational",
        "review_required": True,
        "provenance": {
            "observation_id": observation.id,
            "raster_sha256": observation.raster_sha256,
            "primitive_ids": [item.indice for item in observation.primitivas],
            "attributes": dict(observation.atributos),
            "alternatives": [
                {
                    "class_id": item.classe,
                    "subtype": item.subtipo,
                    "raw_score": float(item.score_bruto) if item.score_bruto is not None else None,
                }
                for item in observation.alternativas
            ],
            "reported_context": "unknown; requires independent review",
            "score_kind": "raw graph descriptor fit; not calibrated probability",
        },
    }


def infer_pdf(
    source: Path,
    document_id: str,
    *,
    include_transformers: bool = False,
    include_guys: bool = False,
    include_packages: bool = False,
    include_raster: bool = False,
    include_structural: bool = False,
    package_snapshot: tuple[declarative_symbols.Package, ...] | None = None,
    raster_snapshot: tuple[raster_symbols.TemplateRasterVerificado, ...] | None = None,
    raster_configuration: raster_symbols.ConfiguracaoDetectorRaster | None = None,
    structural_configurations: tuple[structural_symbols.ConfiguracaoDetectorEstrutural, ...]
    | None = None,
) -> tuple[Record, list[Record], list[Record]]:
    """Infer all base pages with only source path and opaque document identity.

    No reference, expected class, reviewer ROI or expected count enters this API.
    Page failures are preserved and do not prevent attempting subsequent pages.
    """
    source = source.resolve(strict=True)
    if include_packages and package_snapshot is None:
        package_snapshot = declarative_symbols.carregar_pacotes()
    if include_raster and raster_snapshot is None:
        raster_snapshot = raster_symbols.carregar_templates_raster()
    if include_raster and raster_configuration is None:
        raster_configuration = raster_symbols.ConfiguracaoDetectorRaster()
    if include_structural and structural_configurations is None:
        structural_configurations = (
            structural_symbols.ConfiguracaoDetectorEstrutural(entrada="raster"),
            structural_symbols.ConfiguracaoDetectorEstrutural(entrada="vetor"),
        )
    before = _identity(source)
    started = perf_counter()
    own_tracing = not tracemalloc.is_tracing()
    if own_tracing:
        tracemalloc.start()
    tracemalloc.reset_peak()
    memory_before = tracemalloc.get_traced_memory()[0]
    python_peak_outside_raster = 0
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
                page = None
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
                if include_transformers:
                    transformer_started = perf_counter()
                    transformer_execution: Record = {
                        "document_id": document_id,
                        "page": number,
                        "layer": "base",
                        "method_id": TRANSFORMER_METHOD_ID,
                        "status": "executed",
                        "reason": None,
                    }
                    try:
                        if page is None:
                            raise ValueError("PDF page unavailable to transformer detector")
                        observed = pymupdf_transformers.observar_transformadores(
                            page,
                            documento_id=document_id,
                            documento_sha256=before["sha256"],
                            pagina_numero=number,
                        )
                        transformer_predictions = [
                            _transformer_prediction(item, document_id)
                            for item in observed.observacoes
                        ]
                        predictions.extend(transformer_predictions)
                        transformer_execution["prediction_count"] = len(transformer_predictions)
                        transformer_execution["signature"] = observed.perfil.assinatura()
                    except Exception as error:
                        message = f"{type(error).__name__}: {error}"
                        transformer_execution.update(status="failed", reason=message)
                        page_manifest.update(status="failed", reason=message)
                        manifest["failures"].append(
                            {"page": number, "method_id": TRANSFORMER_METHOD_ID, "reason": message}
                        )
                        manifest["status"] = "failed"
                    transformer_execution["seconds"] = perf_counter() - transformer_started
                    executions.extend(
                        (
                            transformer_execution,
                            {
                                "document_id": document_id,
                                "page": number,
                                "layer": "annotation",
                                "method_id": TRANSFORMER_METHOD_ID,
                                "status": "not_applicable",
                                "reason": "E05 vector detector supports the base layer only",
                            },
                        )
                    )
                if include_guys:
                    guy_started = perf_counter()
                    guy_execution: Record = {
                        "document_id": document_id,
                        "page": number,
                        "layer": "base",
                        "method_id": GUY_METHOD_ID,
                        "status": "executed",
                        "reason": None,
                    }
                    try:
                        if page is None:
                            raise ValueError("PDF page unavailable to guy detector")
                        observed_guys = pymupdf_guys.observar_estais(
                            page,
                            documento_id=document_id,
                            documento_sha256=before["sha256"],
                            pagina_numero=number,
                        )
                        guy_predictions = [
                            _guy_prediction(item, document_id) for item in observed_guys.observacoes
                        ]
                        predictions.extend(guy_predictions)
                        guy_execution["prediction_count"] = len(guy_predictions)
                        guy_execution["signature"] = observed_guys.perfil.assinatura()
                    except Exception as error:
                        message = f"{type(error).__name__}: {error}"
                        guy_execution.update(status="failed", reason=message)
                        page_manifest.update(status="failed", reason=message)
                        manifest["failures"].append(
                            {"page": number, "method_id": GUY_METHOD_ID, "reason": message}
                        )
                        manifest["status"] = "failed"
                    guy_execution["seconds"] = perf_counter() - guy_started
                    executions.extend(
                        (
                            guy_execution,
                            {
                                "document_id": document_id,
                                "page": number,
                                "layer": "annotation",
                                "method_id": GUY_METHOD_ID,
                                "status": "not_applicable",
                                "reason": "E06 vector detector supports the base layer only",
                            },
                        )
                    )
                if include_packages:
                    package_started = perf_counter()
                    package_execution: Record = {
                        "document_id": document_id,
                        "page": number,
                        "layer": "base",
                        "method_id": PACKAGE_METHOD_ID,
                        "status": "executed",
                        "reason": None,
                    }
                    try:
                        if page is None:
                            raise ValueError("PDF page unavailable to package detector")
                        observed_packages = declarative_symbols.observar_pacotes(
                            page,
                            documento_id=document_id,
                            documento_sha256=before["sha256"],
                            pagina_numero=number,
                            pacotes=package_snapshot,
                        )
                        package_predictions = [
                            _package_prediction(item, document_id)
                            for item in observed_packages.observacoes
                        ]
                        predictions.extend(package_predictions)
                        package_execution["prediction_count"] = len(package_predictions)
                        package_execution["signature"] = observed_packages.perfil.assinatura()
                    except Exception as error:
                        message = f"{type(error).__name__}: {error}"
                        package_execution.update(status="failed", reason=message)
                        page_manifest.update(status="failed", reason=message)
                        manifest["failures"].append(
                            {"page": number, "method_id": PACKAGE_METHOD_ID, "reason": message}
                        )
                        manifest["status"] = "failed"
                    package_execution["seconds"] = perf_counter() - package_started
                    executions.extend(
                        (
                            package_execution,
                            {
                                "document_id": document_id,
                                "page": number,
                                "layer": "annotation",
                                "method_id": PACKAGE_METHOD_ID,
                                "status": "not_applicable",
                                "reason": "E07 vector packages support the base layer only",
                            },
                        )
                    )
                if include_raster:
                    raster_started = perf_counter()
                    try:
                        if page is None or raster_snapshot is None or raster_configuration is None:
                            raise ValueError("PDF page or E08 configuration unavailable")
                        if own_tracing:
                            python_peak_outside_raster = max(
                                python_peak_outside_raster, tracemalloc.get_traced_memory()[1]
                            )
                            tracemalloc.stop()
                        try:
                            raster_results = raster_symbols.observar_simbolos_raster(
                                page,
                                documento_id=document_id,
                                documento_sha256=before["sha256"],
                                pagina_numero=number,
                                templates=raster_snapshot,
                                configuracao=raster_configuration,
                            )
                        finally:
                            if own_tracing:
                                tracemalloc.start()
                                tracemalloc.reset_peak()
                        raster_page_predictions: list[Record] = []
                        raster_page_executions: list[Record] = []
                        raster_page_failures: list[Record] = []
                        for result in raster_results:
                            state = result.coberturas[0].estado
                            status = (
                                "failed"
                                if state is EstadoMetodoSimbolos.FALHA
                                else "not_applicable"
                                if state
                                in {
                                    EstadoMetodoSimbolos.INDISPONIVEL,
                                    EstadoMetodoSimbolos.FORA_DOMINIO,
                                    EstadoMetodoSimbolos.ABSTENCAO,
                                }
                                else "executed"
                            )
                            items = [
                                _raster_prediction(item, document_id, result.perfil.metodo_id)
                                for item in result.observacoes
                            ]
                            raster_page_predictions.extend(items)
                            raster_page_executions.extend(
                                (
                                    {
                                        "document_id": document_id,
                                        "page": number,
                                        "layer": "base",
                                        "method_id": result.perfil.metodo_id,
                                        "status": status,
                                        "reason": result.coberturas[0].motivo,
                                        "coverage_state": state.value,
                                        "prediction_count": len(items),
                                        "signature": result.perfil.assinatura(),
                                        "seconds": perf_counter() - raster_started,
                                    },
                                    {
                                        "document_id": document_id,
                                        "page": number,
                                        "layer": "annotation",
                                        "method_id": result.perfil.metodo_id,
                                        "status": "not_applicable",
                                        "reason": "E08 raster supports base layer only",
                                    },
                                )
                            )
                            if status == "failed":
                                raster_page_failures.append(
                                    {
                                        "page": number,
                                        "method_id": result.perfil.metodo_id,
                                        "reason": result.coberturas[0].motivo,
                                    }
                                )
                        predictions.extend(raster_page_predictions)
                        executions.extend(raster_page_executions)
                        if raster_page_failures:
                            page_manifest.update(
                                status="failed", reason=raster_page_failures[0]["reason"]
                            )
                            manifest["failures"].extend(raster_page_failures)
                            manifest["status"] = "failed"
                    except Exception as error:
                        message = f"{type(error).__name__}: {error}"
                        page_manifest.update(status="failed", reason=message)
                        manifest["failures"].append(
                            {"page": number, "method_id": "raster", "reason": message}
                        )
                        manifest["status"] = "failed"
                        for metadata in raster_method_metadata(
                            raster_snapshot or (),
                            raster_configuration or raster_symbols.ConfiguracaoDetectorRaster(),
                        ):
                            executions.extend(
                                (
                                    {
                                        "document_id": document_id,
                                        "page": number,
                                        "layer": "base",
                                        "method_id": metadata["id"],
                                        "status": "failed",
                                        "reason": message,
                                    },
                                    {
                                        "document_id": document_id,
                                        "page": number,
                                        "layer": "annotation",
                                        "method_id": metadata["id"],
                                        "status": "not_applicable",
                                        "reason": "base layer only",
                                    },
                                )
                            )
                if include_structural:
                    for structural_config in structural_configurations or ():
                        structural_started = perf_counter()
                        structural_profile = structural_symbols.perfil_simbolos_estruturais(
                            configuracao=structural_config
                        )
                        structural_execution: Record = {
                            "document_id": document_id,
                            "page": number,
                            "layer": "base",
                            "method_id": structural_profile.metodo_id,
                            "status": "executed",
                            "reason": None,
                            "signature": structural_profile.assinatura(),
                        }
                        try:
                            if page is None:
                                raise ValueError("PDF page unavailable to structural detector")
                            structural_result = structural_symbols.observar_simbolos_estruturais(
                                page,
                                documento_id=document_id,
                                documento_sha256=before["sha256"],
                                pagina_numero=number,
                                configuracao=structural_config,
                            )
                            states = {coverage.estado for coverage in structural_result.coberturas}
                            if EstadoMetodoSimbolos.FALHA in states:
                                structural_execution["status"] = "failed"
                            elif states <= {
                                EstadoMetodoSimbolos.INDISPONIVEL,
                                EstadoMetodoSimbolos.FORA_DOMINIO,
                                EstadoMetodoSimbolos.ABSTENCAO,
                            }:
                                structural_execution["status"] = "not_applicable"
                            structural_execution["coverage_state"] = ",".join(
                                sorted(state.value for state in states)
                            )
                            structural_execution["reason"] = next(
                                (
                                    coverage.motivo
                                    for coverage in structural_result.coberturas
                                    if coverage.motivo
                                ),
                                None,
                            )
                            structural_predictions = [
                                _structural_prediction(
                                    item, document_id, structural_result.perfil.metodo_id
                                )
                                for item in structural_result.observacoes
                            ]
                            predictions.extend(structural_predictions)
                            structural_execution["prediction_count"] = len(structural_predictions)
                            if structural_execution["status"] == "failed":
                                failure = {
                                    "page": number,
                                    "method_id": structural_profile.metodo_id,
                                    "reason": structural_execution["reason"],
                                }
                                manifest["failures"].append(failure)
                                page_manifest.update(status="failed", reason=failure["reason"])
                                manifest["status"] = "failed"
                        except Exception as error:
                            message = f"{type(error).__name__}: {error}"
                            structural_execution.update(status="failed", reason=message)
                            page_manifest.update(status="failed", reason=message)
                            manifest["failures"].append(
                                {
                                    "page": number,
                                    "method_id": structural_profile.metodo_id,
                                    "reason": message,
                                }
                            )
                            manifest["status"] = "failed"
                        structural_execution["seconds"] = perf_counter() - structural_started
                        executions.extend(
                            (
                                structural_execution,
                                {
                                    "document_id": document_id,
                                    "page": number,
                                    "layer": "annotation",
                                    "method_id": structural_profile.metodo_id,
                                    "status": "not_applicable",
                                    "reason": "E09 structural detector supports base layer only",
                                },
                            )
                        )
                manifest["pages"].append(page_manifest)
    except Exception as error:
        manifest["status"] = "failed"
        manifest["failures"].append({"page": None, "reason": f"{type(error).__name__}: {error}"})
    finally:
        current, peak = tracemalloc.get_traced_memory()
        peak = max(peak, python_peak_outside_raster)
        if own_tracing:
            tracemalloc.stop()
        manifest.update(
            seconds=perf_counter() - started,
            memory={
                "python_current_bytes": current,
                "python_peak_bytes": peak,
                "python_current_before_bytes": memory_before,
                "scope": (
                    "tracemalloc Python allocations outside raster scan; raster and native "
                    "MuPDF/RSS excluded when runner owns tracing"
                    if include_raster and own_tracing
                    else "tracemalloc Python allocations; not process RSS/native MuPDF memory"
                ),
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


def _run(
    sources: list[tuple[Path, str]],
    output: Path,
    *,
    mode: str,
    include_transformers: bool = False,
    include_guys: bool = False,
    include_packages: bool = False,
    include_raster: bool = False,
    include_structural: bool = False,
) -> Record:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    protected = {source.resolve() for source, _ in sources}
    if any(
        (output / name).resolve() in protected for name in ("manifest.json", "predictions.json")
    ):
        raise ValueError("Output must not overwrite source PDF")
    package_snapshot = declarative_symbols.carregar_pacotes() if include_packages else None
    raster_snapshot = raster_symbols.carregar_templates_raster() if include_raster else None
    raster_configuration = raster_symbols.ConfiguracaoDetectorRaster() if include_raster else None
    structural_configurations = (
        (
            structural_symbols.ConfiguracaoDetectorEstrutural(
                entrada="raster", dpi=72, limite_pixels=5_000_000
            ),
            structural_symbols.ConfiguracaoDetectorEstrutural(
                entrada="vetor", dpi=72, limite_pixels=5_000_000
            ),
        )
        if include_structural
        else None
    )
    structural_source_hash = (
        _text_sha256(Path(structural_symbols.__file__)) if include_structural else None
    )
    predictions: Record = {
        "schema_version": 1,
        "methods": [
            method_metadata(),
            *([transformer_method_metadata()] if include_transformers else []),
            *([guy_method_metadata()] if include_guys else []),
            *([package_method_metadata(package_snapshot)] if include_packages else []),
            *(
                raster_method_metadata(raster_snapshot, raster_configuration)
                if raster_snapshot is not None and raster_configuration is not None
                else []
            ),
            *(
                structural_method_metadata(structural_configurations)
                if structural_configurations is not None
                else []
            ),
        ],
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
        "limitations": [
            "Methods sharing PyMuPDF vector drawings or raster templates are correlated; "
            "agreement is not probability."
            if include_transformers
            or include_guys
            or include_packages
            or include_raster
            or include_structural
            else "One real visual method only; no independent detector gain claimed."
        ],
    }
    for source, document_id in sources:
        try:
            document, items, executions = (
                infer_pdf(
                    source,
                    document_id,
                    include_transformers=include_transformers,
                    include_guys=include_guys,
                    include_packages=include_packages,
                    include_raster=include_raster,
                    include_structural=include_structural,
                    package_snapshot=package_snapshot,
                    raster_snapshot=raster_snapshot,
                    raster_configuration=raster_configuration,
                    structural_configurations=structural_configurations,
                )
                if include_transformers
                or include_guys
                or include_packages
                or include_raster
                or include_structural
                else infer_pdf(source, document_id)
            )
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
    package_configuration_unchanged = True
    if package_snapshot is not None:
        try:
            package_configuration_unchanged = canonical_json(
                declarative_symbols.carregar_pacotes()
            ) == canonical_json(package_snapshot)
        except (OSError, ValueError):
            package_configuration_unchanged = False
        if not package_configuration_unchanged:
            manifest["failures"] = ["E07 package configuration changed during inference"]
    manifest["package_configuration_unchanged"] = package_configuration_unchanged
    raster_configuration_unchanged = True
    if raster_snapshot is not None:
        try:
            raster_configuration_unchanged = [
                (item.id, item.sha256) for item in raster_symbols.carregar_templates_raster()
            ] == [(item.id, item.sha256) for item in raster_snapshot]
        except (OSError, ValueError):
            raster_configuration_unchanged = False
        if not raster_configuration_unchanged:
            manifest["failures"].append("E08 raster templates changed during inference")
        manifest["raster_configuration_unchanged"] = raster_configuration_unchanged
    structural_configuration_unchanged = (
        structural_source_hash == _text_sha256(Path(structural_symbols.__file__))
        if structural_source_hash is not None
        else True
    )
    if not structural_configuration_unchanged:
        manifest["failures"].append("E09 structural adapter changed during inference")
    if include_structural:
        manifest["structural_configuration_unchanged"] = structural_configuration_unchanged
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
    manifest["completed"] = (
        bool(sources)
        and not manifest["counts"]["documents_failed"]
        and package_configuration_unchanged
        and raster_configuration_unchanged
        and structural_configuration_unchanged
    )
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


def run_examples(
    root: Path,
    output: Path,
    *,
    include_transformers: bool = False,
    include_guys: bool = False,
    include_packages: bool = False,
    include_raster: bool = False,
    include_structural: bool = False,
) -> Record:
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
    manifest = _run(
        named,
        output,
        mode="examples",
        include_transformers=include_transformers,
        include_guys=include_guys,
        include_packages=include_packages,
        include_raster=include_raster,
        include_structural=include_structural,
    )
    manifest["discovery_root"] = str(root)
    manifest["discovery_root_exists"] = root.is_dir()
    manifest["development_only"] = True
    write_json(output / "manifest.json", manifest)
    return manifest


def run_synthetic(
    output: Path,
    *,
    include_transformers: bool = False,
    include_guys: bool = False,
    include_packages: bool = False,
    include_raster: bool = False,
    include_structural: bool = False,
) -> Record:
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
    manifest = _run(
        sources,
        output,
        mode="synthetic-development",
        include_transformers=include_transformers,
        include_guys=include_guys,
        include_packages=include_packages,
        include_raster=include_raster,
        include_structural=include_structural,
    )
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
