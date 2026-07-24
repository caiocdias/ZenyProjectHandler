"""Regras geométricas para comprimentos de vãos anotados no desenho."""

from __future__ import annotations

import math
import re
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from itertools import pairwise

from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    TipoEvidencia,
    TipoGeometria,
)
from zeny_project_handler.domain.values import GeometriaDocumento

from .rule_support import center, normalized_text, point_distance, situation_from_evidence

_MAXIMUM_ANNOTATION_DISTANCE = 0.055
_MINIMUM_ENDPOINT_DISTANCE = 0.035
_MINIMUM_CABLE_PATH_LENGTH = 0.06
_MAXIMUM_PATH_ENDPOINT_DISTANCE = 0.10
_MAXIMUM_CABLE_LABEL_DISTANCE = 0.045
_LABELED_LENGTH_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:VAO|COMPRIMENTO|COMP|EXTENSAO|L)\.?"
    r"\s*[:=-]?\s*(\d{1,4}(?:[.,]\d{1,2})?)\s*M?(?![A-Z0-9])"
)
_LENGTH_WITH_UNIT_PATTERN = re.compile(
    r"(?<![A-Z0-9.,])(\d{1,4}(?:[.,]\d{1,2})?)"
    r"\s*M(?:ETRO|ETROS)?(?![A-Z0-9])"
)


def associar_tracados_de_cabos(
    propostas: tuple[PropostaElemento, ...],
    evidencias: tuple[EvidenciaDocumento, ...],
    catalogo: CatalogoTecnico,
) -> tuple[PropostaElemento, ...]:
    """Associe cada rótulo de cabo ao traçado sólido que liga dois postes."""
    postes = tuple(
        proposta for proposta in propostas if proposta.categoria is CategoriaElemento.POSTE
    )
    cabos = tuple(
        proposta for proposta in propostas if proposta.categoria is CategoriaElemento.CABO
    )
    caminhos = tuple(
        evidencia for evidencia in evidencias if _liga_dois_postes(evidencia, postes, catalogo)
    )
    combinacoes = sorted(
        (
            distancia,
            str(cabo.id),
            str(caminho.id),
            cabo,
            caminho,
        )
        for cabo in cabos
        for caminho in caminhos
        if cabo.geometria.pagina_id == caminho.pagina_id
        and cabo.situacao_projeto
        is situation_from_evidence(caminho, CategoriaElemento.CABO, catalogo)
        if (
            distancia := _distancia_ate_geometria(
                center(cabo.geometria),
                caminho.geometria,
            )[0]
        )
        <= _MAXIMUM_CABLE_LABEL_DISTANCE
    )
    caminhos_usados = set()
    cabos_atualizados: dict[object, PropostaElemento] = {}
    for _, _, _, cabo, caminho in combinacoes:
        if cabo.id in cabos_atualizados or caminho.id in caminhos_usados:
            continue
        cabos_atualizados[cabo.id] = _com_tracado(cabo, caminho, evidencias)
        caminhos_usados.add(caminho.id)
    return tuple(cabos_atualizados.get(proposta.id, proposta) for proposta in propostas)


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


def _liga_dois_postes(
    evidencia: EvidenciaDocumento,
    postes: tuple[PropostaElemento, ...],
    catalogo: CatalogoTecnico,
) -> bool:
    geometria = evidencia.geometria
    atributos = dict(evidencia.atributos_extraidos)
    if (
        evidencia.tipo is not TipoEvidencia.VETOR
        or geometria.tipo is not TipoGeometria.POLILINHA
        or len(geometria.pontos) < 2
        or bool(atributos.get("fechado", False))
        or not _tracado_solido(atributos.get("tracejado"))
        or _comprimento_geometria(geometria) < _MINIMUM_CABLE_PATH_LENGTH
    ):
        return False
    situacao = situation_from_evidence(evidencia, CategoriaElemento.CABO, catalogo)
    if situacao is None:
        return False
    candidatos = tuple(
        poste
        for poste in postes
        if poste.geometria.pagina_id == evidencia.pagina_id and poste.situacao_projeto is situacao
    )
    associados = []
    for extremidade in (geometria.pontos[0], geometria.pontos[-1]):
        coordenada = (float(extremidade.x), float(extremidade.y))
        mais_proximo = min(
            candidatos,
            key=lambda poste: point_distance(coordenada, center(poste.geometria)),
            default=None,
        )
        if (
            mais_proximo is None
            or point_distance(coordenada, center(mais_proximo.geometria))
            > _MAXIMUM_PATH_ENDPOINT_DISTANCE
        ):
            return False
        associados.append(mais_proximo.id)
    return len(set(associados)) == 2


def _tracado_solido(valor: object) -> bool:
    tracejado = re.sub(r"\s+", "", str(valor or "")).casefold()
    return tracejado in {"", "[]", "[]0"}


def _comprimento_geometria(geometria: GeometriaDocumento) -> float:
    pontos = tuple((float(item.x), float(item.y)) for item in geometria.pontos)
    return sum(math.dist(inicio, fim) for inicio, fim in pairwise(pontos))


def _com_tracado(
    cabo: PropostaElemento,
    caminho: EvidenciaDocumento,
    evidencias: tuple[EvidenciaDocumento, ...],
) -> PropostaElemento:
    atributos = dict(cabo.atributos_sugeridos)
    atributos.update(
        {
            "geometria_cabo_origem": "vetor_ligando_postes",
            "evidencia_geometria_id": str(caminho.id),
        }
    )
    evidencia_ids = {*cabo.evidencia_ids, caminho.id}
    comprimento = detectar_comprimento_anotado(caminho.geometria, evidencias)
    if comprimento is not None:
        valor, evidencia = comprimento
        atributos.update(
            {
                "comprimento_m": valor,
                "comprimento_origem": "anotacao_desenho",
                "evidencia_comprimento_id": str(evidencia.id),
            }
        )
        evidencia_ids.add(evidencia.id)
    return replace(
        cabo,
        geometria=caminho.geometria,
        evidencia_ids=tuple(sorted(evidencia_ids, key=str)),
        atributos_sugeridos=tuple(atributos.items()),
        justificativa=(
            f"{cabo.justificativa or ''} "
            "O traçado vetorial sólido liga dois postes da mesma situação do cabo."
        ).strip(),
    )


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
