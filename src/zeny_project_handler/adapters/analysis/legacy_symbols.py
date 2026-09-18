# mypy: disable-error-code="no-untyped-call"
"""Envelope interno opt-in para o detector legado, sem alterar suas decisões."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

import pymupdf

from zeny_project_handler.domain.enums import EstadoMetodoSimbolos, SituacaoProjeto
from zeny_project_handler.domain.symbols import (
    AlternativaClasseSimbolo,
    CoberturaMetodoSimbolos,
    FonteObservacaoSimbolo,
    GeometriaObservacaoSimbolo,
    ObservacaoSimbolo,
    PerfilMetodoSimbolos,
    PontoOriginalSimbolo,
    PrimitivaObservadaSimbolo,
    ResultadoMetodoSimbolos,
    TransformacaoSimbolo,
)
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.analysis import CandidatoEvidenciaDocumento

from .pymupdf_symbols import (
    _ANGLE_TOLERANCE,
    _MAXIMUM_PRIMITIVE_LENGTH,
    _SYMBOL_CONFIDENCE,
    _SYMBOL_SOURCE,
    _drawing_points,
    _extract_symbolic_equipment,
)


def perfil_simbolos_legados() -> PerfilMetodoSimbolos:
    """Assinatura fixa dos parâmetros realmente executados; score não calibrado."""
    return PerfilMetodoSimbolos(
        metodo_id="pymupdf-symbols-legacy",
        versao="1.18.0:observacoes-1",
        familia="heuristica-geometrica-vetorial-legada",
        dominio_aplicacao="Desenhos vetoriais da base; três assinaturas geométricas legadas",
        classes_suportadas=("ATERRAMENTO", "PARA_RAIOS_MT", "PARA_RAIOS_BT"),
        camadas_suportadas=("base",),
        fontes_compartilhadas=("pymupdf:get_drawings:extended", "heuristicas-simbolos-legadas"),
        perfil_referencia="legado:SIMBOLOGIA.pdf:procedencia-nao-comprovada:v1",
        parametros=(
            ("pymupdf_version", str(pymupdf.VersionBind)),
            ("maximum_primitive_length", Decimal(str(_MAXIMUM_PRIMITIVE_LENGTH))),
            ("angle_tolerance_radians", Decimal(str(_ANGLE_TOLERANCE))),
            ("score_bruto", _SYMBOL_CONFIDENCE),
            ("origem_simbologia", _SYMBOL_SOURCE),
            ("normalizacao", "pymupdf_support._box_geometry:rotacao-e-clipping:v1"),
        ),
    )


def _decimal_points(points: tuple[tuple[float, float], ...]) -> tuple[PontoOriginalSimbolo, ...]:
    return tuple((Decimal(str(x)), Decimal(str(y))) for x, y in points)


def _original_bounds(drawings: tuple[dict[str, Any], ...]) -> Any:
    # Mesma união de Rect do detector; preservar inclusive sua degeneração conhecida.
    bounds = pymupdf.Rect(drawings[0].get("rect") or drawings[0].get("scissor"))
    for drawing in drawings[1:]:
        bounds |= drawing.get("rect") or drawing.get("scissor")
    return bounds


def _geometry(
    page: Any, candidate: CandidatoEvidenciaDocumento, drawings: tuple[dict[str, Any], ...]
) -> GeometriaObservacaoSimbolo:
    bounds = _original_bounds(drawings)
    corners = (bounds.tl, bounds.tr, bounds.br, bounds.bl)
    width, height = float(page.rect.width), float(page.rect.height)
    inverse = page.derotation_matrix
    matrix = (
        Decimal(str(width * inverse.a)),
        Decimal(str(width * inverse.b)),
        Decimal(str(height * inverse.c)),
        Decimal(str(height * inverse.d)),
        Decimal(str(inverse.e)),
        Decimal(str(inverse.f)),
    )
    transformed = tuple(point * page.rotation_matrix for point in corners)
    clipped = any(not (0 <= point.x <= width and 0 <= point.y <= height) for point in transformed)
    return GeometriaObservacaoSimbolo(
        tipo=candidate.geometria.tipo,
        pontos_originais=_decimal_points(tuple((point.x, point.y) for point in corners)),
        pontos_normalizados=candidate.geometria.pontos,
        transformacao=TransformacaoSimbolo(
            normalizada_para_original=matrix,
            sistema_original="pymupdf-page-unrotated:points:top-left",
        ),
        normalizacao_limitada=clipped,
    )


def _observation(
    page: Any,
    candidate: CandidatoEvidenciaDocumento,
    source: FonteObservacaoSimbolo,
    profile: PerfilMetodoSimbolos,
    drawings: tuple[dict[str, Any], ...],
) -> ObservacaoSimbolo:
    attributes = dict(candidate.atributos_extraidos)
    indices = tuple(int(index) for index in str(attributes["vetores_origem"]).split(","))
    originals = tuple(drawings[index] for index in indices)
    primitives = tuple(
        PrimitivaObservadaSimbolo(
            indice=str(index),
            camada=str(drawing["layer"]) if drawing.get("layer") else None,
            pontos_originais=_decimal_points(_drawing_points(tuple(drawing.get("items") or ()))),
        )
        for index, drawing in zip(indices, originals, strict=True)
    )
    score = attributes["confianca"]
    if not isinstance(score, Decimal):
        raise ValueError("Score legado deve permanecer Decimal")
    return ObservacaoSimbolo(
        fonte=source,
        metodo_assinatura=profile.assinatura(),
        geometria=_geometry(page, candidate, originals),
        alternativas=(
            AlternativaClasseSimbolo(
                classe=str(attributes["classe_equipamento"]),
                score_bruto=score,
            ),
        ),
        score_bruto=score,
        primitivas=primitives,
        situacao=SituacaoProjeto(str(attributes["situacao_projeto_forcada"])),
        atributos=candidate.atributos_extraidos,
        chave_legada=candidate.chave_estavel,
        conteudo_bruto=candidate.conteudo_bruto,
    )


def observar_simbolos_legados(
    page: Any,
    *,
    documento_id: str,
    documento_sha256: str,
    pagina_numero: int,
) -> ResultadoMetodoSimbolos:
    """Execute o legado na página base; nenhuma referência visual entra na inferência.

    Fonte SHA é a identidade informada pelo chamador, que deve verificar o arquivo.
    Não aceita perfil customizado ou thresholds que o detector não executaria.
    A cobertura declara a tentativa nas três classes; zero saída não prova ausência.
    """
    if not math.isfinite(float(page.rect.width)) or float(page.rect.width) <= 0:
        raise ValueError("Página deve possuir largura positiva finita")
    if not math.isfinite(float(page.rect.height)) or float(page.rect.height) <= 0:
        raise ValueError("Página deve possuir altura positiva finita")
    profile = perfil_simbolos_legados()
    source = FonteObservacaoSimbolo(
        documento_id=documento_id,
        documento_sha256=documento_sha256,
        pagina_numero=pagina_numero,
        camada="base",
    )
    candidates = _extract_symbolic_equipment(page, pagina_numero)
    drawings = tuple(page.get_drawings(extended=True))
    observations = tuple(
        _observation(page, candidate, source, profile, drawings) for candidate in candidates
    )
    coverage = CoberturaMetodoSimbolos(
        fonte=source,
        regiao_normalizada=(
            PontoNormalizado(Decimal(0), Decimal(0)),
            PontoNormalizado(Decimal(1), Decimal(1)),
        ),
        classes_avaliadas=profile.classes_suportadas,
        estado=EstadoMetodoSimbolos.CONCLUIDO
        if observations
        else EstadoMetodoSimbolos.NAO_DETECCAO,
    )
    return ResultadoMetodoSimbolos(perfil=profile, coberturas=(coverage,), observacoes=observations)
