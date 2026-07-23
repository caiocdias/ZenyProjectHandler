"""Detecção determinística de pares de coordenadas em evidências textuais."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.enums import TipoEvidencia
from zeny_project_handler.domain.values import GeometriaDocumento

_COORDINATE_NUMBER_PATTERN = re.compile(r"(?<!\d)\d{6,8}(?!\d)")


@dataclass(frozen=True, slots=True)
class ParCoordenadaDetectado:
    leste: int
    norte: int
    geometria_leste: GeometriaDocumento
    geometria_norte: GeometriaDocumento
    evidencia_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class _NumeroCoordenada:
    valor: int
    evidencia_id: UUID
    geometria: GeometriaDocumento
    ordem_no_fragmento: int

    @property
    def chave(self) -> tuple[UUID, int]:
        return self.evidencia_id, self.ordem_no_fragmento


def detectar_pares_coordenadas(
    evidencias: tuple[EvidenciaDocumento, ...],
    *,
    distancia_maxima: float,
    distancia_geometrias: Callable[[GeometriaDocumento, GeometriaDocumento], float],
) -> tuple[ParCoordenadaDetectado, ...]:
    """Pareie leste/norte uma única vez, priorizando o mesmo fragmento e a proximidade."""
    if distancia_maxima < 0:
        raise ValueError("Distância máxima de coordenadas não pode ser negativa")
    numeros = tuple(
        _NumeroCoordenada(
            valor=int(match.group()),
            evidencia_id=evidencia.id,
            geometria=evidencia.geometria,
            ordem_no_fragmento=ordem,
        )
        for evidencia in evidencias
        if evidencia.tipo in {TipoEvidencia.TEXTO, TipoEvidencia.OCR} and evidencia.conteudo_bruto
        for ordem, match in enumerate(_COORDINATE_NUMBER_PATTERN.finditer(evidencia.conteudo_bruto))
    )
    lestes = tuple(item for item in numeros if 100_000 <= item.valor <= 999_999)
    nortes = tuple(item for item in numeros if 1_000_000 <= item.valor <= 10_000_000)
    arestas: list[
        tuple[
            tuple[int, int, float, str, int, str, int],
            _NumeroCoordenada,
            _NumeroCoordenada,
        ]
    ] = []
    for leste in lestes:
        for norte in nortes:
            if leste.geometria.pagina_id != norte.geometria.pagina_id:
                continue
            distancia = distancia_geometrias(leste.geometria, norte.geometria)
            if distancia > distancia_maxima:
                continue
            mesmo_fragmento = leste.evidencia_id == norte.evidencia_id
            prioridade = (
                0 if mesmo_fragmento else 1,
                (
                    abs(leste.ordem_no_fragmento - norte.ordem_no_fragmento)
                    if mesmo_fragmento
                    else 0
                ),
                distancia,
                str(leste.evidencia_id),
                leste.ordem_no_fragmento,
                str(norte.evidencia_id),
                norte.ordem_no_fragmento,
            )
            arestas.append((prioridade, leste, norte))

    lestes_usados: set[tuple[UUID, int]] = set()
    nortes_usados: set[tuple[UUID, int]] = set()
    pares: list[ParCoordenadaDetectado] = []
    for _prioridade, leste, norte in sorted(arestas, key=lambda item: item[0]):
        if leste.chave in lestes_usados or norte.chave in nortes_usados:
            continue
        lestes_usados.add(leste.chave)
        nortes_usados.add(norte.chave)
        pares.append(
            ParCoordenadaDetectado(
                leste=leste.valor,
                norte=norte.valor,
                geometria_leste=leste.geometria,
                geometria_norte=norte.geometria,
                evidencia_ids=tuple(dict.fromkeys((leste.evidencia_id, norte.evidencia_id))),
            )
        )
    return tuple(pares)
