"""Exact drawing identities, separate from electrical voltage/phase points.

Only coincident vector endpoints share a physical identity. Nearby endpoints,
interior crossings and different pages never imply a connection.
"""

from __future__ import annotations

from uuid import UUID, uuid5

from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado


def physical_point_id(page_id: UUID, point: PontoNormalizado) -> UUID:
    return uuid5(page_id, f"physical-point:{point.x.normalize()}:{point.y.normalize()}")


def physical_span_id(geometry: GeometriaDocumento) -> UUID:
    points = tuple(f"{point.x.normalize()}:{point.y.normalize()}" for point in geometry.pontos)
    canonical = min(points, tuple(reversed(points)))
    return uuid5(geometry.pagina_id, "physical-span:" + ";".join(canonical))
