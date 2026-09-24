"""Opt-in E03 adapter for frozen E11 benchmark predictions.

This module is deliberately outside src/ and is never registered in the
application composition. It only translates an existing E02 output; it does
not run a detector or use reference annotations.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from scripts.experiments.e11_detector import METHOD_ID
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos, TipoGeometria
from zeny_project_handler.domain.symbols import (
    AlternativaClasseSimbolo,
    CoberturaMetodoSimbolos,
    FonteObservacaoSimbolo,
    GeometriaObservacaoSimbolo,
    ObservacaoSimbolo,
    PerfilMetodoSimbolos,
    ResultadoMetodoSimbolos,
    TransformacaoSimbolo,
)
from zeny_project_handler.domain.values import PontoNormalizado

Record = dict[str, Any]


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def result_from_predictions(
    predictions: Record,
    *,
    document_id: str,
    page: int,
    layer: str,
    width_pt: float,
    height_pt: float,
) -> ResultadoMetodoSimbolos:
    """Convert one PDF page/layer and preserve raw score plus source identity."""
    if predictions.get("schema_version") != 1:
        raise ValueError("E02 schema version 1 required")
    methods = [item for item in predictions["methods"] if item["id"] == METHOD_ID]
    if len(methods) != 1:
        raise ValueError("Expected one E11 method")
    documents = [item for item in predictions["documents"] if item["id"] == document_id]
    if len(documents) != 1:
        raise ValueError("Expected one source document")
    runs = [
        item
        for item in predictions["executions"]
        if item["document_id"] == document_id
        and item["page"] == page
        and item["layer"] == layer
        and item["method_id"] == METHOD_ID
    ]
    if len(runs) != 1:
        raise ValueError("Expected one E11 execution for page and layer")
    method, document, run = methods[0], documents[0], runs[0]
    profile = PerfilMetodoSimbolos(
        metodo_id=METHOD_ID,
        versao=str(method["version"]),
        familia=str(method["algorithm_family"]),
        dominio_aplicacao="E11 isolated raster window experiment on PDF base",
        classes_suportadas=tuple(method["supported_classes"]),
        camadas_suportadas=("base",),
        fontes_compartilhadas=tuple(method["shared_sources"]),
        perfil_referencia="E02 author-owned development; no normative equivalence",
        parametros=(("score_kind", "uncalibrated classifier output"),),
        modelo=str(method["model_sha256"]),
    )
    source = FonteObservacaoSimbolo(
        documento_id=document_id,
        documento_sha256=document["sha256"],
        pagina_numero=page,
        camada=layer,
    )
    page_points = (
        PontoNormalizado(Decimal(0), Decimal(0)),
        PontoNormalizado(Decimal(1), Decimal(0)),
        PontoNormalizado(Decimal(1), Decimal(1)),
        PontoNormalizado(Decimal(0), Decimal(1)),
    )
    status = run["status"]
    matching = [
        item
        for item in predictions["predictions"]
        if item["method_id"] == METHOD_ID
        and item["document_id"] == document_id
        and item["page"] == page
        and item["layer"] == layer
    ]
    if status == "not_applicable":
        state = EstadoMetodoSimbolos.FORA_DOMINIO
    elif status == "failed":
        state = EstadoMetodoSimbolos.FALHA
    elif status == "executed":
        state = EstadoMetodoSimbolos.CONCLUIDO if matching else EstadoMetodoSimbolos.NAO_DETECCAO
    else:
        raise ValueError(f"Invalid E02 execution state: {status}")
    coverage = CoberturaMetodoSimbolos(
        fonte=source,
        regiao_normalizada=page_points,
        classes_avaliadas=tuple(method["supported_classes"]) if layer == "base" else (),
        estado=state,
        motivo=run.get("reason")
        or (
            "E11 inference failed"
            if status == "failed"
            else "E11 layer outside experimental domain"
            if status == "not_applicable"
            else None
        ),
    )
    observations = []
    for item in matching:
        x0, y0, x1, y1 = (_decimal(value) for value in item["bbox"])
        if not Decimal(0) <= x0 < x1 <= Decimal(1) or not Decimal(0) <= y0 < y1 <= Decimal(1):
            raise ValueError("Invalid normalized E11 prediction box")
        width, height = _decimal(width_pt), _decimal(height_pt)
        normalized = (
            PontoNormalizado(x0, y0),
            PontoNormalizado(x1, y0),
            PontoNormalizado(x1, y1),
            PontoNormalizado(x0, y1),
        )
        original = (
            (x0 * width, y0 * height),
            (x1 * width, y0 * height),
            (x1 * width, y1 * height),
            (x0 * width, y1 * height),
        )
        geometry = GeometriaObservacaoSimbolo(
            tipo=TipoGeometria.CAIXA,
            pontos_originais=original,
            pontos_normalizados=normalized,
            transformacao=TransformacaoSimbolo(
                normalizada_para_original=(
                    width,
                    Decimal(0),
                    Decimal(0),
                    height,
                    Decimal(0),
                    Decimal(0),
                ),
                sistema_original="rendered-page:points:top-left",
            ),
        )
        score = _decimal(item["score"])
        observations.append(
            ObservacaoSimbolo(
                fonte=source,
                metodo_assinatura=profile.assinatura(),
                geometria=geometry,
                alternativas=(
                    AlternativaClasseSimbolo(classe=item["class_id"], score_bruto=score),
                ),
                score_bruto=score,
                modelo=profile.modelo,
                conteudo_bruto=item["id"],
            )
        )
    if status == "not_applicable" and matching:
        raise ValueError("Out-of-domain execution cannot contain predictions")
    return ResultadoMetodoSimbolos(
        perfil=profile, coberturas=(coverage,), observacoes=tuple(observations)
    )
