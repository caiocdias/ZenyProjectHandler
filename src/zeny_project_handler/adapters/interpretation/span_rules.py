"""Regras geométricas para comprimentos de vãos anotados no desenho."""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from itertools import pairwise

from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.enums import TipoEvidencia
from zeny_project_handler.domain.values import GeometriaDocumento

from .rule_support import center, normalized_text

_MAXIMUM_ANNOTATION_DISTANCE = 0.055
_MINIMUM_ENDPOINT_DISTANCE = 0.035
_LABELED_LENGTH_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:VAO|COMPRIMENTO|COMP|EXTENSAO|L)\.?"
    r"\s*[:=-]?\s*(\d{1,4}(?:[.,]\d{1,2})?)\s*M?(?![A-Z0-9])"
)
_LENGTH_WITH_UNIT_PATTERN = re.compile(
    r"(?<![A-Z0-9.,])(\d{1,4}(?:[.,]\d{1,2})?)"
    r"\s*M(?:ETRO|ETROS)?(?![A-Z0-9])"
)


def detectar_comprimento_anotado(
    geometria_cabo: GeometriaDocumento,
    evidencias: tuple[EvidenciaDocumento, ...],
) -> tuple[Decimal, EvidenciaDocumento] | None:
    """Localize a anotação de comprimento mais próxima da linha do cabo."""
    candidatos: list[tuple[float, int, str, Decimal, EvidenciaDocumento]] = []
    for evidencia in evidencias:
        if (
            evidencia.pagina_id != geometria_cabo.pagina_id
            or evidencia.tipo not in {TipoEvidencia.TEXTO, TipoEvidencia.OCR}
            or not evidencia.conteudo_bruto
        ):
            continue
        comprimento = _comprimento_do_texto(evidencia.conteudo_bruto)
        if comprimento is None:
            continue
        evidence_center = center(evidencia.geometria)
        cable_points = tuple((float(item.x), float(item.y)) for item in geometria_cabo.pontos)
        if (
            len(cable_points) > 1
            and min(
                math.dist(evidence_center, cable_points[0]),
                math.dist(evidence_center, cable_points[-1]),
            )
            < _MINIMUM_ENDPOINT_DISTANCE
        ):
            continue
        distancia, ponto_linha = _distancia_ate_geometria(
            evidence_center,
            geometria_cabo,
        )
        if distancia > _MAXIMUM_ANNOTATION_DISTANCE:
            continue
        texto_acima = int(evidence_center[1] > ponto_linha[1] + 0.015)
        candidatos.append((distancia, texto_acima, str(evidencia.id), comprimento, evidencia))
    if not candidatos:
        return None
    _, _, _, comprimento, evidencia = min(candidatos)
    return comprimento, evidencia


def _comprimento_do_texto(texto: str) -> Decimal | None:
    normalizado = normalized_text(texto)
    correspondencia = _LABELED_LENGTH_PATTERN.search(normalizado)
    if correspondencia is None:
        correspondencia = _LENGTH_WITH_UNIT_PATTERN.search(normalizado)
    if correspondencia is None:
        return None
    try:
        comprimento = Decimal(correspondencia.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    if not Decimal(0) < comprimento <= Decimal(2000):
        return None
    return comprimento


def _distancia_ate_geometria(
    ponto: tuple[float, float],
    geometria: GeometriaDocumento,
) -> tuple[float, tuple[float, float]]:
    pontos = tuple((float(item.x), float(item.y)) for item in geometria.pontos)
    if len(pontos) == 1:
        return math.dist(ponto, pontos[0]), pontos[0]
    return min(
        (_distancia_ate_segmento(ponto, inicio, fim) for inicio, fim in pairwise(pontos)),
        key=lambda item: item[0],
    )


def _distancia_ate_segmento(
    ponto: tuple[float, float],
    inicio: tuple[float, float],
    fim: tuple[float, float],
) -> tuple[float, tuple[float, float]]:
    delta_x = fim[0] - inicio[0]
    delta_y = fim[1] - inicio[1]
    comprimento_quadrado = delta_x * delta_x + delta_y * delta_y
    if comprimento_quadrado == 0:
        return math.dist(ponto, inicio), inicio
    projecao = (
        (ponto[0] - inicio[0]) * delta_x + (ponto[1] - inicio[1]) * delta_y
    ) / comprimento_quadrado
    fator = min(1.0, max(0.0, projecao))
    mais_proximo = (inicio[0] + fator * delta_x, inicio[1] + fator * delta_y)
    return math.dist(ponto, mais_proximo), mais_proximo
