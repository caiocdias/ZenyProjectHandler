"""Conservative partial traces at an explicit PDF drawing window.

These are reviewable drawing continuities, never poles, catalogued cables or
electrical connections. A frame alone, an interior crossing or proximity alone
cannot create a candidate.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    TipoEvidencia,
    TipoGeometria,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado


@dataclass(frozen=True, slots=True)
class ContinuidadeDesenho:
    trace: EvidenciaDocumento
    frame: EvidenciaDocumento
    anchor: PropostaElemento
    known_end: PontoNormalizado
    boundary_end: PontoNormalizado


def drawing_continuations(
    evidence: tuple[EvidenciaDocumento, ...], proposals: tuple[PropostaElemento, ...]
) -> tuple[ContinuidadeDesenho, ...]:
    frames = tuple(e for e in evidence if _is_drawing_window(e))
    sources = {str(e.id): e for e in evidence}
    cables = tuple(
        p
        for p in proposals
        if p.categoria is CategoriaElemento.CABO and p.estado_revisao is not EstadoRevisao.REJEITADA
    )
    associated = {dict(p.atributos_sugeridos).get("evidencia_geometria_id") for p in cables}
    result = []
    for trace in evidence:
        if not _is_open_trace(trace) or str(trace.id) in associated:
            continue
        geometry = trace.geometria
        candidates = [
            f
            for f in frames
            if f.pagina_id == trace.pagina_id and _cut_endpoint(geometry, f.geometria) is not None
        ]
        if len(candidates) != 1:
            continue
        frame = candidates[0]
        cut = _cut_endpoint(geometry, frame.geometria)
        assert cut is not None
        known, boundary = cut
        anchors = [
            p
            for p in cables
            if _anchored(trace, known, p, sources) or _clipped_label(trace, frame, p)
        ]
        if not anchors or len({p.situacao_projeto for p in anchors}) != 1:
            continue
        result.append(
            ContinuidadeDesenho(
                trace, frame, min(anchors, key=lambda p: str(p.id)), known, boundary
            )
        )
    counts = Counter(
        c.anchor.id
        for c in result
        if not dict(c.anchor.atributos_sugeridos).get("evidencia_geometria_id")
    )
    return tuple(c for c in result if counts[c.anchor.id] <= 1)


def _is_drawing_window(evidence: EvidenciaDocumento) -> bool:
    geometry = evidence.geometria
    attrs = dict(evidence.atributos_extraidos)
    if evidence.tipo is not TipoEvidencia.VETOR or geometry.tipo is not TipoGeometria.CAIXA:
        return False
    a, b = geometry.pontos
    return bool(
        (b.x - a.x) * (b.y - a.y) >= 0.5
        and attrs.get("cor_preenchimento") == "#FFFFFF"
        and attrs.get("operacoes") == "re"
    )


def _is_open_trace(evidence: EvidenciaDocumento) -> bool:
    attrs = dict(evidence.atributos_extraidos)
    return bool(
        evidence.tipo is TipoEvidencia.VETOR
        and evidence.geometria.tipo is TipoGeometria.POLILINHA
        and len(evidence.geometria.pontos) == 2
        and not attrs.get("fechado")
        and attrs.get("tipo_caminho") == "s"
        and attrs.get("cor_contorno") not in (None, "#FFFFFF")
        and str(attrs.get("tracejado", "")).replace(" ", "") in ("", "[]", "[]0")
    )


def _cut_endpoint(
    geometry: GeometriaDocumento, frame: GeometriaDocumento
) -> tuple[PontoNormalizado, PontoNormalizado] | None:
    a, b = frame.pontos

    def on_boundary(p: PontoNormalizado) -> bool:
        return a.x <= p.x <= b.x and a.y <= p.y <= b.y and (p.x in (a.x, b.x) or p.y in (a.y, b.y))

    p, q = geometry.pontos
    if on_boundary(p) == on_boundary(q):
        return None
    boundary, known = (p, q) if on_boundary(p) else (q, p)
    if not (a.x < known.x < b.x and a.y < known.y < b.y) or _distance(p, q) < 0.05:
        return None
    return known, boundary


def _anchored(
    trace: EvidenciaDocumento,
    known: PontoNormalizado,
    proposal: PropostaElemento,
    sources: dict[str, EvidenciaDocumento],
) -> bool:
    attrs = dict(proposal.atributos_sugeridos)
    source = sources.get(str(attrs.get("evidencia_geometria_id")))
    if source is None or attrs.get("associacao_pendente") or source.pagina_id != trace.pagina_id:
        return False
    geometry = proposal.geometria
    if known not in (geometry.pontos[0], geometry.pontos[-1]):
        return False
    own, other = dict(trace.atributos_extraidos), dict(source.atributos_extraidos)
    return (
        all(own.get(k) == other.get(k) for k in ("cor_contorno", "espessura", "tracejado"))
        and _angle_difference(geometry, trace.geometria) <= 5
    )


def _clipped_label(
    trace: EvidenciaDocumento,
    frame: EvidenciaDocumento,
    proposal: PropostaElemento,
) -> bool:
    attrs = dict(proposal.atributos_sugeridos)
    geometry = proposal.geometria
    if (
        geometry.pagina_id != trace.pagina_id
        or attrs.get("associacao_pendente") != "tracado"
        or geometry.tipo is not TipoGeometria.POLIGONO
    ):
        return False
    a, b = frame.geometria.pontos
    xs, ys = [p.x for p in geometry.pontos], [p.y for p in geometry.pontos]
    clipped = (
        min(xs) <= a.x <= max(xs)
        or min(xs) <= b.x <= max(xs)
        or min(ys) <= a.y <= max(ys)
        or min(ys) <= b.y <= max(ys)
    )
    if not clipped or _angle_difference(geometry, trace.geometria) > 5:
        return False
    # The clipped text itself touches the candidate boundary endpoint; no remote label lookup.
    return min(_distance(p, q) for p in geometry.pontos for q in trace.geometria.pontos) <= 0.02


def _distance(a: PontoNormalizado, b: PontoNormalizado) -> float:
    return math.hypot(float(a.x - b.x), float(a.y - b.y))


def _angle_difference(a: GeometriaDocumento, b: GeometriaDocumento) -> float:
    def angle(g: GeometriaDocumento) -> float:
        pairs = tuple(zip(g.pontos, (*g.pontos[1:], g.pontos[0]), strict=True))
        p, q = max(pairs, key=lambda pair: _distance(*pair))
        return math.degrees(math.atan2(float(q.y - p.y), float(q.x - p.x))) % 180

    delta = abs(angle(a) - angle(b))
    return min(delta, 180 - delta)
