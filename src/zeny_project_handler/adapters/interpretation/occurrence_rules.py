"""Consolidação de leituras, sem usar o traçado como identidade de um condutor."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao, TipoGeometria
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado


def token_geometry(
    geometry: GeometriaDocumento, start: int, end: int, size: int
) -> GeometriaDocumento:
    """Localize a token along the OCR baseline; retain source evidence and token offsets."""
    points = geometry.pontos
    if geometry.tipo is TipoGeometria.POLIGONO and len(points) == 4:
        a, b, c, d = points
    elif geometry.tipo is TipoGeometria.CAIXA:
        a, c = points
        if c.x - a.x >= c.y - a.y:
            b, d = PontoNormalizado(c.x, a.y), PontoNormalizado(a.x, c.y)
        else:
            b, d = PontoNormalizado(a.x, c.y), PontoNormalizado(c.x, a.y)
    else:
        return geometry

    def at(first: PontoNormalizado, last: PontoNormalizado, index: int) -> PontoNormalizado:
        ratio = Decimal(index) / size
        return PontoNormalizado(
            first.x + (last.x - first.x) * ratio, first.y + (last.y - first.y) * ratio
        )

    return GeometriaDocumento(
        pagina_id=geometry.pagina_id,
        tipo=TipoGeometria.POLIGONO,
        pontos=(at(a, b, start), at(a, b, end), at(d, c, end), at(d, c, start)),
    )


def overlapping_labels(
    first: GeometriaDocumento, second: GeometriaDocumento, *, whole: bool = True
) -> bool:
    if first.pagina_id != second.pagina_id:
        return False
    boxes = [
        (
            min(float(p.x) for p in g.pontos),
            min(float(p.y) for p in g.pontos),
            max(float(p.x) for p in g.pontos),
            max(float(p.y) for p in g.pontos),
        )
        for g in (first, second)
    ]
    a, b = boxes
    areas = [(c - x) * (d - y) for x, y, c, d in boxes]
    if min(areas) <= 0:
        return first == second
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    if whole:
        return intersection / max(areas) >= 0.75
    return intersection / min(areas) >= 0.80 and min(areas) / max(areas) >= 0.35


def deduplicate_cable_readings(
    proposals: tuple[PropostaElemento, ...],
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[PropostaElemento, ...]:
    by_id = {str(item.id): item for item in evidence}
    groups: list[list[PropostaElemento]] = []

    def same(first: PropostaElemento, second: PropostaElemento) -> bool:
        a, b = dict(first.atributos_sugeridos), dict(second.atributos_sugeridos)
        if first.categoria is not CategoriaElemento.CABO or second.categoria != first.categoria:
            return False
        if (first.tipo_catalogo_sugerido_id, first.codigo_observado, first.situacao_projeto) != (
            second.tipo_catalogo_sugerido_id,
            second.codigo_observado,
            second.situacao_projeto,
        ):
            return False
        # A common path alone cannot distinguish parallel, physically different cables.
        keys = ("evidencia_geometria_id", "identificador_operacional", "comprimento_m")
        if not a.get(keys[0]) or any(a.get(key) != b.get(key) for key in keys):
            return False
        labels = [by_id.get(str(attrs.get("evidencia_rotulo_id"))) for attrs in (a, b)]
        left, right = labels
        return (
            left is not None
            and right is not None
            and left.origem_pdf == right.origem_pdf
            and overlapping_labels(left.geometria, right.geometria)
        )

    for proposal in sorted(proposals, key=lambda item: str(item.id)):
        group = next((g for g in groups if all(same(proposal, p) for p in g)), None)
        if group is None:
            groups.append([proposal])
        else:
            group.append(proposal)
    result = []
    for group in groups:
        selected = group[0]
        if len(group) > 1:
            attrs = dict(selected.atributos_sugeridos)
            attrs["leituras_consolidadas"] = json.dumps([str(p.id) for p in group])
            selected = replace(
                selected,
                estado_revisao=(
                    EstadoRevisao.CONFLITANTE
                    if any(p.estado_revisao is EstadoRevisao.CONFLITANTE for p in group)
                    else selected.estado_revisao
                ),
                evidencia_ids=tuple(sorted({e for p in group for e in p.evidencia_ids}, key=str)),
                atributos_sugeridos=tuple(attrs.items()),
            )
        result.append(selected)
    return tuple(result)
