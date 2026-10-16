"""Union of symbol observations with explicit coverage and calibrated decisions.

The result retains every detector observation.  Matching locates a physical
occurrence; it never turns agreement, silence, or a raw detector score into a
probability.  Calibration entries must come from an independent calibration
partition and describe one method, class, and stratum.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from zeny_project_handler.domain.enums import EstadoMetodoSimbolos, TipoGeometria
from zeny_project_handler.domain.symbols import (
    AlternativaClasseSimbolo,
    FonteObservacaoSimbolo,
    GeometriaObservacaoSimbolo,
    ObservacaoSimbolo,
    ResultadoMetodoSimbolos,
)
from zeny_project_handler.domain.values import PontoNormalizado

# Box of the whole physical support (e.g. the stem down to the pole) reported by
# the legacy vector detector apart from the pictogram box, in original coordinates.
_SUPPORT_BOUNDS_KEY = "simbolo_limites_suporte"

Decision = Literal["review", "eligible"]
MatrixState = Literal[
    "support",
    "conflict",
    "non_detection",
    "abstention",
    "failure",
    "not_applicable",
    "uncovered",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class CalibrationEntry:
    method_signature: str
    class_code: str
    stratum: str
    probability: Decimal
    sample_size: int

    def __post_init__(self) -> None:
        if not self.method_signature or not self.class_code or not self.stratum:
            raise ValueError("Calibration key must be complete")
        if not self.probability.is_finite() or not Decimal(0) <= self.probability <= Decimal(1):
            raise ValueError("Calibrated probability must be between zero and one")
        if self.sample_size < 0:
            raise ValueError("Calibration sample size cannot be negative")


@dataclass(frozen=True, slots=True, kw_only=True)
class CalibrationPolicy:
    entries: tuple[CalibrationEntry, ...] = ()
    minimum_samples: int = 30
    promotion_probability: Decimal = Decimal("0.99")

    def __post_init__(self) -> None:
        if self.minimum_samples < 1:
            raise ValueError("Minimum calibration sample count must be positive")
        if not self.promotion_probability.is_finite() or not (
            Decimal(0) <= self.promotion_probability <= Decimal(1)
        ):
            raise ValueError("Promotion probability must be between zero and one")
        keys = [(e.method_signature, e.class_code, e.stratum) for e in self.entries]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate calibration key")
        object.__setattr__(self, "entries", tuple(self.entries))


@dataclass(frozen=True, slots=True, kw_only=True)
class SymbolOccurrence:
    id: str
    observations: tuple[ObservacaoSimbolo, ...]
    alternatives: tuple[AlternativaClasseSimbolo, ...]
    reference_ids: tuple[str, ...]
    geometry: GeometriaObservacaoSimbolo
    raw_scores: tuple[tuple[str, Decimal | None], ...]
    calibrated_probability: Decimal | None
    probability_source: str | None
    support: tuple[str, ...]
    decision: Decision
    reasons: tuple[str, ...]
    # Physical extent linking the symbol to its support (e.g. the stem down to the
    # pole) when a detector reports it apart from the symbol box; association only.
    support_geometry: GeometriaObservacaoSimbolo | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class MethodMatrixRow:
    occurrence_id: str
    method_signature: str
    state: MatrixState
    classes: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class MethodAblation:
    method_signature: str
    occurrences: tuple[SymbolOccurrence, ...]
    lost_occurrence_ids: tuple[str, ...]
    eligible_before: int
    eligible_after: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SymbolReconciliation:
    occurrences: tuple[SymbolOccurrence, ...]
    method_matrix: tuple[MethodMatrixRow, ...]
    ablations: tuple[MethodAblation, ...]


def reconcile_symbols(
    results: tuple[ResultadoMetodoSimbolos, ...], calibration: CalibrationPolicy
) -> SymbolReconciliation:
    """Return the immutable union and each method's leave-one-out contribution."""
    signatures = [result.perfil.assinatura() for result in results]
    if len(set(signatures)) != len(signatures):
        raise ValueError("Each method/configuration can appear only once")
    ordered = tuple(sorted(results, key=lambda result: result.perfil.assinatura()))
    occurrences, matrix = _compose(ordered, calibration)
    ablations = []
    for result in ordered:
        signature = result.perfil.assinatura()
        remaining, _ = _compose(
            tuple(item for item in ordered if item.perfil.assinatura() != signature),
            calibration,
        )
        remaining_ids = {obs.id for occurrence in remaining for obs in occurrence.observations}
        lost = tuple(
            occurrence.id
            for occurrence in occurrences
            if not any(obs.id in remaining_ids for obs in occurrence.observations)
        )
        ablations.append(
            MethodAblation(
                method_signature=signature,
                occurrences=remaining,
                lost_occurrence_ids=lost,
                eligible_before=sum(o.decision == "eligible" for o in occurrences),
                eligible_after=sum(o.decision == "eligible" for o in remaining),
            )
        )
    return SymbolReconciliation(
        occurrences=occurrences, method_matrix=matrix, ablations=tuple(ablations)
    )


def _compose(
    results: tuple[ResultadoMetodoSimbolos, ...], calibration: CalibrationPolicy
) -> tuple[tuple[SymbolOccurrence, ...], tuple[MethodMatrixRow, ...]]:
    observations = sorted(
        (observation for result in results for observation in result.observacoes),
        key=lambda observation: observation.id,
    )
    groups: list[list[ObservacaoSimbolo]] = []
    for observation in observations:
        candidates = [
            group
            for group in groups
            if all(_same_occurrence(observation, member) for member in group)
        ]
        # Several plausible groups mean a neighbour is ambiguous.  Preserve it
        # as its own occurrence rather than bridging two distinct objects.
        if len(candidates) == 1:
            candidates[0].append(observation)
        else:
            groups.append([observation])
    occurrences = tuple(
        sorted((_occurrence(group, calibration) for group in groups), key=lambda o: o.id)
    )
    matrix = tuple(
        _matrix_row(occurrence, result) for occurrence in occurrences for result in results
    )
    return occurrences, matrix


def _source_key(observation: ObservacaoSimbolo) -> tuple[str, str, int, str, str]:
    source = observation.fonte
    # PDF object indices are detector provenance, not a shared physical ID.
    # A vector and raster detector can point to different source objects for
    # the same drawing.  Geometry/primitives still have to confirm the match.
    context = "legenda" if _is_legend_context(observation) else "desenho"
    return (
        source.documento_id,
        source.documento_sha256,
        source.pagina_numero,
        source.camada,
        context,
    )


def _bounds(observation: ObservacaoSimbolo) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    xs = [point.x for point in observation.geometria.pontos_normalizados]
    ys = [point.y for point in observation.geometria.pontos_normalizados]
    return min(xs), min(ys), max(xs), max(ys)


def _same_occurrence(first: ObservacaoSimbolo, second: ObservacaoSimbolo) -> bool:
    if _source_key(first) != _source_key(second):
        return False
    first_primitives = {(p.indice, p.camada) for p in first.primitivas}
    second_primitives = {(p.indice, p.camada) for p in second.primitivas}
    if first_primitives and second_primitives:
        shared_primitives = first_primitives & second_primitives
        first_shapes = {(p.camada, p.pontos_originais) for p in first.primitivas}
        second_shapes = {(p.camada, p.pontos_originais) for p in second.primitivas}
        shared_shapes = first_shapes & second_shapes
        if not shared_primitives and not shared_shapes:
            return False
        if len(shared_primitives) * 2 < min(len(first_primitives), len(second_primitives)) and len(
            shared_shapes
        ) * 2 < min(len(first_shapes), len(second_shapes)):
            return False
    a, b = _bounds(first), _bounds(second)
    aw, ah, bw, bh = a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1]
    scale = min(max(aw, ah), max(bw, bh))
    center_distance = max(
        abs((a[0] + a[2] - b[0] - b[2]) / 2),
        abs((a[1] + a[3] - b[1] - b[3]) / 2),
    )
    if center_distance > max(Decimal("0.001"), scale * Decimal("0.10")):
        return False
    if any(
        abs(x - y) > max(Decimal("0.001"), scale * Decimal("0.20")) for x, y in ((aw, bw), (ah, bh))
    ):
        return False
    area_a, area_b = aw * ah, bw * bh
    if area_a == 0 or area_b == 0:
        # Thin strokes have zero box area; compare their endpoints instead.
        return all(abs(x - y) <= Decimal("0.002") for x, y in zip(a, b, strict=True))
    intersection = max(Decimal(0), min(a[2], b[2]) - max(a[0], b[0])) * max(
        Decimal(0), min(a[3], b[3]) - max(a[1], b[1])
    )
    iou = intersection / (area_a + area_b - intersection)
    threshold = Decimal("0.80") if first_primitives and second_primitives else Decimal("0.92")
    return iou >= threshold


def _attributes(observation: ObservacaoSimbolo) -> dict[str, object]:
    return dict(observation.atributos)


def _is_legend_context(observation: ObservacaoSimbolo) -> bool:
    return str(_attributes(observation).get("contexto", "")).strip().casefold() in {
        "legenda",
        "legend",
    }


def _reference_ids(observations: tuple[ObservacaoSimbolo, ...]) -> tuple[tuple[str, ...], bool]:
    """Read documented E07/E05 references without treating a class as an ID."""
    found: set[str] = set()
    invalid = False
    for observation in observations:
        attributes = _attributes(observation)
        for key in ("variante_inventario", "referencias_possiveis"):
            if key not in attributes:
                continue
            raw = attributes[key]
            if not isinstance(raw, str) or not raw.strip():
                invalid = True
                continue
            value = raw.strip()
            if key == "referencias_possiveis" and value.startswith(("[", '"')):
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    invalid = True
                    continue
                if isinstance(parsed, list):
                    values = parsed
                elif isinstance(parsed, str):
                    values = [parsed]
                else:
                    invalid = True
                    continue
            else:
                values = [value]
            if not values or any(not isinstance(item, str) or not item.strip() for item in values):
                invalid = True
                continue
            found.update(item.strip() for item in values)
    return tuple(sorted(found)), invalid


def _occurrence(
    observations: list[ObservacaoSimbolo], calibration: CalibrationPolicy
) -> SymbolOccurrence:
    ordered = tuple(sorted(observations, key=lambda observation: observation.id))
    occurrence_id = sha256("|".join(obs.id for obs in ordered).encode()).hexdigest()
    alternatives = tuple(
        sorted(
            {alternative for obs in ordered for alternative in obs.alternativas},
            key=lambda alt: (alt.classe or "", alt.subtipo or "", str(alt.score_bruto)),
        )
    )
    identities = {(alt.classe, alt.subtipo) for alt in alternatives}
    reference_ids, invalid_references = _reference_ids(ordered)
    support = tuple(sorted({obs.metodo_assinatura for obs in ordered}))
    raw_scores = tuple((obs.metodo_assinatura, obs.score_bruto) for obs in ordered)
    # Preserve one actual geometry.  Primitive count and unclipped coordinates
    # select provenance quality; detector scores never weight geometry.
    by_quality = sorted(
        ordered,
        key=lambda obs: (
            obs.geometria.normalizacao_limitada,
            -len(obs.primitivas),
            obs.id,
        ),
    )
    selected = by_quality[0]
    support_geometry = next(
        (geometry for obs in by_quality if (geometry := _support_geometry(obs)) is not None),
        None,
    )
    reasons = _observation_reasons(ordered, identities, reference_ids, invalid_references)
    probability: Decimal | None = None
    probability_source: str | None = None
    if len(identities) == 1:
        class_code = next(iter(identities))[0]
        if class_code is not None:
            calibrated = _calibrated_probability(ordered, class_code, calibration)
            if calibrated is not None:
                probability_source, probability = calibrated
            else:
                reasons.append("insufficient_calibration")
    if probability is not None and probability < calibration.promotion_probability:
        reasons.append("below_promotion_probability")
    decision: Decision = "eligible" if probability is not None and not reasons else "review"
    return SymbolOccurrence(
        id=occurrence_id,
        observations=ordered,
        alternatives=alternatives,
        reference_ids=reference_ids,
        geometry=selected.geometria,
        raw_scores=raw_scores,
        calibrated_probability=probability,
        probability_source=probability_source,
        support=support,
        decision=decision,
        reasons=tuple(reasons),
        support_geometry=support_geometry,
    )


def _support_bounds(observation: ObservacaoSimbolo) -> tuple[Decimal, ...] | None:
    """Read the detector's ``[x0, y0, x1, y1]`` support box, in original coordinates."""
    raw = _attributes(observation).get(_SUPPORT_BOUNDS_KEY)
    if not isinstance(raw, str):
        return None
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if (
        not isinstance(values, list)
        or len(values) != 4
        or not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in values)
    ):
        return None
    bounds = tuple(Decimal(str(item)) for item in values)
    if (
        not all(item.is_finite() for item in bounds)
        or bounds[0] > bounds[2]
        or bounds[1] > bounds[3]
    ):
        return None
    return bounds


def _support_geometry(observation: ObservacaoSimbolo) -> GeometriaObservacaoSimbolo | None:
    """Normalize the support box with the observation's own declared transformation."""
    bounds = _support_bounds(observation)
    if bounds is None:
        return None
    x0, y0, x1, y1 = bounds
    corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    transformation = observation.geometria.transformacao
    a, b, c, d, e, f = transformation.normalizada_para_original
    determinant = a * d - c * b
    # original = (nx * a + ny * c + e, nx * b + ny * d + f); invert the affine map.
    raw = tuple(
        (
            (d * (x - e) - c * (y - f)) / determinant,
            (a * (y - f) - b * (x - e)) / determinant,
        )
        for x, y in corners
    )
    clipped = any(not (0 <= value <= 1) for point in raw for value in point)
    xs = [min(Decimal(1), max(Decimal(0), x)) for x, _ in raw]
    ys = [min(Decimal(1), max(Decimal(0), y)) for _, y in raw]
    lower = PontoNormalizado(min(xs), min(ys))
    upper = PontoNormalizado(max(xs), max(ys))
    kind = (
        TipoGeometria.PONTO
        if lower == upper
        else TipoGeometria.POLILINHA
        if lower.x == upper.x or lower.y == upper.y
        else TipoGeometria.CAIXA
    )
    return GeometriaObservacaoSimbolo(
        tipo=kind,
        pontos_originais=corners,
        pontos_normalizados=(lower,) if lower == upper else (lower, upper),
        transformacao=transformation,
        normalizacao_limitada=observation.geometria.normalizacao_limitada or clipped,
    )


def _observation_reasons(
    ordered: tuple[ObservacaoSimbolo, ...],
    identities: set[tuple[str | None, str | None]],
    reference_ids: tuple[str, ...],
    invalid_references: bool,
) -> list[str]:
    """Return review reasons that depend only on the grouped observations."""
    reasons: list[str] = []
    if len(identities) != 1 or next(iter(identities))[0] is None:
        reasons.append("ambiguous_class_or_id")
    if len(reference_ids) > 1:
        reasons.append("ambiguous_reference_id")
    if invalid_references:
        reasons.append("invalid_reference_id")
    if any(_is_legend_context(obs) for obs in ordered):
        reasons.append("legend_reference")
    if any(
        str(_attributes(obs).get("papel", "")).strip().casefold() == "informative"
        for obs in ordered
    ):
        reasons.append("informative_context")
    if any(str(_attributes(obs).get("status", "")).lower() == "pending" for obs in ordered):
        reasons.append("pending_variant")
    situations = {obs.situacao for obs in ordered if obs.situacao is not None}
    if len(situations) > 1:
        reasons.append("situation_conflict")
    for key in ("potencia", "potencia_kva"):
        values = {str(_attributes(obs)[key]) for obs in ordered if key in _attributes(obs)}
        if len(values) > 1:
            reasons.append("attribute_conflict:" + key)
    return reasons


def _calibration_entry(
    observation: ObservacaoSimbolo, class_code: str, calibration: CalibrationPolicy
) -> CalibrationEntry | None:
    stratum = str(_attributes(observation).get("estrato", "default"))
    return next(
        (
            entry
            for entry in calibration.entries
            if entry.method_signature == observation.metodo_assinatura
            and entry.class_code == class_code
            and entry.stratum == stratum
            and entry.sample_size >= calibration.minimum_samples
        ),
        None,
    )


def _calibrated_probability(
    ordered: tuple[ObservacaoSimbolo, ...], class_code: str, calibration: CalibrationPolicy
) -> tuple[str, Decimal] | None:
    """Return the selected calibration source and probability, if any cell is valid."""
    valid: list[tuple[int, str, Decimal]] = []
    for obs in ordered:
        entry = _calibration_entry(obs, class_code, calibration)
        if entry is not None:
            valid.append((entry.sample_size, obs.metodo_assinatura, entry.probability))
    if not valid:
        return None
    # Select the most sampled calibration cell, with a stable
    # signature tie-break.  This priority is fixed before seeing
    # a candidate's scores or the methods that agree with it;
    # choosing the largest probability here would bias promotion.
    _, probability_source, probability = sorted(valid, key=lambda item: (-item[0], item[1]))[0]
    return probability_source, probability


def _matrix_row(occurrence: SymbolOccurrence, result: ResultadoMetodoSimbolos) -> MethodMatrixRow:
    signature = result.perfil.assinatura()
    own = tuple(obs for obs in occurrence.observations if obs.metodo_assinatura == signature)
    classes = tuple(sorted({alt.classe for obs in own for alt in obs.alternativas if alt.classe}))
    state: MatrixState
    if own:
        all_classes = {alt.classe for alt in occurrence.alternatives if alt.classe}
        state = "conflict" if len(all_classes) > 1 and set(classes) != all_classes else "support"
    else:
        state = _absent_method_state(occurrence, result)
    return MethodMatrixRow(
        occurrence_id=occurrence.id,
        method_signature=signature,
        state=state,
        classes=classes,
    )


def _absent_method_state(
    occurrence: SymbolOccurrence, result: ResultadoMetodoSimbolos
) -> MatrixState:
    """Classify a method that has no observation in the occurrence by its coverage."""
    candidate_classes = {alt.classe for alt in occurrence.alternatives if alt.classe}
    if (
        candidate_classes and not candidate_classes & set(result.perfil.classes_suportadas)
    ) or occurrence.observations[0].fonte.camada not in result.perfil.camadas_suportadas:
        return "not_applicable"
    return _coverage_state(_applicable_coverage_states(occurrence, result, candidate_classes))


def _same_coverage_source(coverage: FonteObservacaoSimbolo, source: FonteObservacaoSimbolo) -> bool:
    return (
        coverage.documento_id == source.documento_id
        and coverage.documento_sha256 == source.documento_sha256
        and coverage.pagina_numero == source.pagina_numero
        and coverage.camada == source.camada
    )


def _applicable_coverage_states(
    occurrence: SymbolOccurrence,
    result: ResultadoMetodoSimbolos,
    candidate_classes: set[str],
) -> list[EstadoMetodoSimbolos]:
    bounds = _bounds(occurrence.observations[0])
    center = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
    source = occurrence.observations[0].fonte
    applicable: list[EstadoMetodoSimbolos] = []
    for coverage in result.coberturas:
        if not _same_coverage_source(coverage.fonte, source):
            continue
        if candidate_classes and not candidate_classes & set(coverage.classes_avaliadas):
            continue
        xs = [point.x for point in coverage.regiao_normalizada]
        ys = [point.y for point in coverage.regiao_normalizada]
        if min(xs) <= center[0] <= max(xs) and min(ys) <= center[1] <= max(ys):
            applicable.append(coverage.estado)
    return applicable


def _coverage_state(applicable: list[EstadoMetodoSimbolos]) -> MatrixState:
    if not applicable:
        return "uncovered"
    if any(item is EstadoMetodoSimbolos.FALHA for item in applicable):
        return "failure"
    if any(item is EstadoMetodoSimbolos.NAO_DETECCAO for item in applicable):
        return "non_detection"
    if any(item is EstadoMetodoSimbolos.INDISPONIVEL for item in applicable):
        return "failure"
    if any(item is EstadoMetodoSimbolos.CONCLUIDO for item in applicable):
        return "abstention"
    if all(item is EstadoMetodoSimbolos.FORA_DOMINIO for item in applicable):
        return "not_applicable"
    return "abstention"
