# mypy: disable-error-code="no-untyped-call"
"""Opt-in visual stroke graph for author-owned grounding and MT controls.

The graph describes ink geometry only. It has no electrical connectivity or
asset semantics. It consumes a complete page, without evaluator regions or
labels, and never modifies the legacy or raster detector's observations.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any, Literal

import pymupdf
from PIL import Image

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

_VERSION = "e09-stroke-graph-2"
_CLASSES = ("ATERRAMENTO", "PARA_RAIOS_MT")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfiguracaoDetectorEstrutural:
    dpi: int = 144
    entrada: Literal["raster", "vetor"] = "raster"
    limite_pixels: int = 4_000_000
    limite_tracos: int = 4096
    limite_expansoes: int = 100_000
    tolerancia_lacuna: int = 2

    def __post_init__(self) -> None:
        if not 72 <= self.dpi <= 300 or self.entrada not in {"raster", "vetor"}:
            raise ValueError("DPI/entrada estrutural inválidos")
        if min(self.limite_pixels, self.limite_tracos, self.limite_expansoes) < 1:
            raise ValueError("Orçamentos estruturais devem ser positivos")
        if not 0 <= self.tolerancia_lacuna <= 8:
            raise ValueError("Tolerância de lacuna deve ficar entre 0 e 8")


@dataclass(frozen=True, slots=True)
class _Stroke:
    # Axis-aligned medial stroke in visual page coordinates.
    axis: Literal["h", "v"]
    line: float
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start

    @property
    def center(self) -> tuple[float, float]:
        middle = (self.start + self.end) / 2
        return (middle, self.line) if self.axis == "h" else (self.line, middle)

    @property
    def endpoints(self) -> tuple[tuple[float, float], tuple[float, float]]:
        if self.axis == "h":
            return (self.start, self.line), (self.end, self.line)
        return (self.line, self.start), (self.line, self.end)


@dataclass(frozen=True, slots=True)
class _Graph:
    strokes: tuple[_Stroke, ...]
    endpoints: int
    junctions: int
    cycles: int


@dataclass(frozen=True, slots=True)
class _Skeleton:
    pixels: int
    endpoints: int
    junctions: int


@dataclass(frozen=True, slots=True)
class _RasterInk:
    binary: bytes
    width: int
    height: int
    factor: float


@dataclass(frozen=True, slots=True)
class _Candidate:
    classe: str
    strokes: tuple[_Stroke, ...]
    gap_penalty: float
    graph: _Graph
    skeleton: _Skeleton | None = None


class _BudgetExceededError(Exception):
    pass


class _Budget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def step(self) -> None:
        self.used += 1
        if self.used > self.limit:
            raise _BudgetExceededError("Limite de expansões do grafo alcançado")


_DEFAULT_CONFIG = ConfiguracaoDetectorEstrutural()


def perfil_simbolos_estruturais(
    configuracao: ConfiguracaoDetectorEstrutural = _DEFAULT_CONFIG,
) -> PerfilMetodoSimbolos:
    """Declare algorithmic family and shared input separately, not independence."""
    shared = (
        "pymupdf:rgb-page-tiles:e08"
        if configuracao.entrada == "raster"
        else "pymupdf:get_drawings:extended"
    )
    return PerfilMetodoSimbolos(
        metodo_id=f"structural-{'raster' if configuracao.entrada == 'raster' else 'vector'}-graph",
        versao=_VERSION,
        familia="grafo-visual-de-tracos",
        dominio_aplicacao="Página base integral; barras ortogonais autorais de aterramento/MT",
        classes_suportadas=_CLASSES,
        camadas_suportadas=("base",),
        fontes_compartilhadas=(shared,),
        perfil_referencia="E02:controles-autorais:gramatica-estrutural-v1",
        parametros=(
            ("dpi", configuracao.dpi),
            ("entrada", configuracao.entrada),
            ("limite_pixels", configuracao.limite_pixels),
            ("limite_tracos", configuracao.limite_tracos),
            ("limite_expansoes", configuracao.limite_expansoes),
            ("tolerancia_lacuna", configuracao.tolerancia_lacuna),
            ("lacuna_raster_antialias_extra_pixel", 1),
            (
                "skeleton_algorithm",
                "zhang-suen-local-v1" if configuracao.entrada == "raster" else None,
            ),
            ("skeleton_crop_pixel_cap", 16_384 if configuracao.entrada == "raster" else None),
            ("pixel_ink_threshold", 220),
            ("score_tipo", "ajuste-de-gramatica-bruto-nao-probabilidade"),
        ),
    )


def _scan_runs(binary: bytes, width: int, height: int, minimum: int, cap: int) -> list[_Stroke]:
    strokes: list[_Stroke] = []
    # Runs are medial-axis proposals, not pixel patches or image correlation.
    for y in range(height):
        row = binary[y * width : (y + 1) * width]
        x = 0
        while x < width:
            if row[x]:
                x += 1
                continue
            start = x
            while x < width and not row[x]:
                x += 1
            if x - start >= minimum:
                strokes.append(_Stroke("h", float(y), float(start), float(x - 1)))
                if len(strokes) > cap:
                    raise _BudgetExceededError("Limite de traços raster alcançado")
    for x in range(width):
        y = 0
        while y < height:
            if binary[y * width + x]:
                y += 1
                continue
            start = y
            while y < height and not binary[y * width + x]:
                y += 1
            if y - start >= minimum:
                strokes.append(_Stroke("v", float(x), float(start), float(y - 1)))
                if len(strokes) > cap:
                    raise _BudgetExceededError("Limite de traços raster alcançado")
    return strokes


def _merge_strokes(
    strokes: list[_Stroke], gap: float, budget: _Budget, *, lateral_tolerance: float = 1.5
) -> tuple[_Stroke, ...]:
    merged: list[_Stroke] = []
    for item in sorted(strokes, key=lambda s: (s.axis, s.line, s.start, s.end)):
        owner = None
        for index in range(len(merged) - 1, -1, -1):
            other = merged[index]
            if item.axis != other.axis:
                break
            if item.line - other.line > lateral_tolerance:
                break
            budget.step()
            overlap = min(item.end, other.end) - max(item.start, other.start)
            close_line = abs(item.line - other.line) <= lateral_tolerance
            collinear_gap = item.start - other.end <= gap
            duplicate = overlap >= min(item.length, other.length) * 0.6
            if close_line and (duplicate or collinear_gap):
                owner = index
                break
        if owner is None:
            merged.append(item)
        else:
            old = merged[owner]
            merged[owner] = _Stroke(
                old.axis,
                (old.line + item.line) / 2 if abs(old.line - item.line) > 0.5 else old.line,
                min(old.start, item.start),
                max(old.end, item.end),
            )
    return tuple(merged)


def _raster_strokes(
    page: Any, config: ConfiguracaoDetectorEstrutural, budget: _Budget
) -> tuple[tuple[_Stroke, ...], str, _RasterInk]:
    factor = config.dpi / 72
    width = math.ceil(float(page.rect.width) * factor)
    height = math.ceil(float(page.rect.height) * factor)
    if width * height > config.limite_pixels:
        raise _BudgetExceededError("Limite de pixels da página alcançado")
    pix = page.get_pixmap(
        matrix=pymupdf.Matrix(factor, factor), colorspace=pymupdf.csGRAY, alpha=False, annots=False
    )
    if pix.width * pix.height > config.limite_pixels:
        raise _BudgetExceededError("Limite de pixels renderizados alcançado")
    raster_hash = sha256(pix.samples).hexdigest()
    with Image.frombytes("L", (pix.width, pix.height), pix.samples) as image:
        binary = image.point(lambda value: 0 if value < 220 else 1).tobytes()
    raw = _scan_runs(binary, pix.width, pix.height, 4, config.limite_tracos * 8)
    merged = _merge_strokes(raw, float(config.tolerancia_lacuna + 1), budget, lateral_tolerance=3.0)
    if len(merged) > config.limite_tracos:
        raise _BudgetExceededError("Limite de traços consolidados alcançado")
    return (
        tuple(
            _Stroke(item.axis, item.line / factor, item.start / factor, item.end / factor)
            for item in merged
        ),
        raster_hash,
        _RasterInk(binary, pix.width, pix.height, factor),
    )


def _vector_strokes(
    page: Any, config: ConfiguracaoDetectorEstrutural, budget: _Budget
) -> tuple[_Stroke, ...]:
    raw: list[_Stroke] = []
    for drawing in page.get_drawings(extended=True):
        if drawing.get("fill") is not None and drawing.get("color") is None:
            continue
        for item in drawing.get("items") or ():
            if item[0] != "l":
                continue
            first = item[1] * page.rotation_matrix
            second = item[2] * page.rotation_matrix
            dx, dy = abs(first.x - second.x), abs(first.y - second.y)
            if dx >= 2 and dy <= max(0.5, dx * 0.05):
                raw.append(
                    _Stroke(
                        "h",
                        (first.y + second.y) / 2,
                        min(first.x, second.x),
                        max(first.x, second.x),
                    )
                )
            elif dy >= 2 and dx <= max(0.5, dy * 0.05):
                raw.append(
                    _Stroke(
                        "v",
                        (first.x + second.x) / 2,
                        min(first.y, second.y),
                        max(first.y, second.y),
                    )
                )
            if len(raw) > config.limite_tracos * 8:
                raise _BudgetExceededError("Limite de primitives vetoriais alcançado")
    merged = _merge_strokes(raw, float(config.tolerancia_lacuna), budget)
    if len(merged) > config.limite_tracos:
        raise _BudgetExceededError("Limite de traços vetoriais alcançado")
    return merged


def _graph(strokes: tuple[_Stroke, ...], tolerance: float, budget: _Budget) -> _Graph:
    # Crossings are visual nodes only. The returned graph is never sent to the
    # electrical topology builder. Endpoints are retained across small gaps.
    neighbors: list[set[int]] = [set() for _ in strokes]
    junctions = 0
    for index, first in enumerate(strokes):
        for next_index in range(index + 1, len(strokes)):
            second = strokes[next_index]
            budget.step()
            if first.axis == second.axis:
                continue
            h, v = (first, second) if first.axis == "h" else (second, first)
            if (
                h.start - tolerance <= v.line <= h.end + tolerance
                and v.start - tolerance <= h.line <= v.end + tolerance
            ):
                neighbors[index].add(next_index)
                neighbors[next_index].add(index)
                junctions += 1
    seen: set[int] = set()
    components = 0
    for index in range(len(strokes)):
        if index in seen:
            continue
        components += 1
        stack = [index]
        seen.add(index)
        while stack:
            for neighbor in neighbors[stack.pop()]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
    cycles = max(0, junctions - len(strokes) + components)
    endpoints = sum(2 for _ in strokes) - sum(min(2, len(n)) for n in neighbors)
    return _Graph(strokes, max(0, endpoints), junctions, cycles)


_NEIGHBOR_OFFSETS = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


def _local_skeleton(strokes: tuple[_Stroke, ...], ink: _RasterInk, budget: _Budget) -> _Skeleton:
    """Thin an algorithm-proposed ink region by two-phase Zhang-Suen deletion.

    The crop comes only from candidate strokes. No benchmark ROI or reviewer
    reference is passed here. The original page bytes remain unchanged.
    """
    xs = [point[0] for stroke in strokes for point in stroke.endpoints]
    ys = [point[1] for stroke in strokes for point in stroke.endpoints]
    x0 = max(0, math.floor(min(xs) * ink.factor) - 2)
    x1 = min(ink.width, math.ceil(max(xs) * ink.factor) + 3)
    y0 = max(0, math.floor(min(ys) * ink.factor) - 2)
    y1 = min(ink.height, math.ceil(max(ys) * ink.factor) + 3)
    if (x1 - x0) * (y1 - y0) > 16_384:
        raise _BudgetExceededError("Limite de pixels do esqueleto local alcançado")
    pixels = {
        (x, y) for y in range(y0, y1) for x in range(x0, x1) if ink.binary[y * ink.width + x] == 0
    }
    if not pixels:
        return _Skeleton(0, 0, 0)
    while True:
        removed_any = False
        for phase in (0, 1):
            remove: set[tuple[int, int]] = set()
            for x, y in pixels:
                budget.step()
                neighbors = [int((x + dx, y + dy) in pixels) for dx, dy in _NEIGHBOR_OFFSETS]
                count = sum(neighbors)
                if not 2 <= count <= 6:
                    continue
                transitions = sum(
                    neighbors[index] == 0 and neighbors[(index + 1) % 8] == 1 for index in range(8)
                )
                if transitions != 1:
                    continue
                n, e, s, w = neighbors[0], neighbors[2], neighbors[4], neighbors[6]
                if phase == 0 and (n * e * s or e * s * w):
                    continue
                if phase == 1 and (n * e * w or n * s * w):
                    continue
                remove.add((x, y))
            if remove:
                pixels.difference_update(remove)
                removed_any = True
        if not removed_any:
            break
    endpoints = junctions = 0
    for x, y in pixels:
        budget.step()
        degree = sum((x + dx, y + dy) in pixels for dx, dy in _NEIGHBOR_OFFSETS)
        endpoints += degree == 1
        junctions += degree >= 3
    return _Skeleton(len(pixels), endpoints, junctions)


def _find_candidates(
    strokes: tuple[_Stroke, ...],
    config: ConfiguracaoDetectorEstrutural,
    budget: _Budget,
    ink: _RasterInk | None = None,
) -> tuple[_Candidate, ...]:
    found: list[_Candidate] = []
    by_axis = {
        axis: sorted((item for item in strokes if item.axis == axis), key=lambda item: item.line)
        for axis in ("h", "v")
    }
    positions = {axis: [item.line for item in values] for axis, values in by_axis.items()}
    # A stem meets the first crossbar. Raster runs may continue beyond that
    # junction when antialiasing merges neighboring row runs; split the visual
    # support there, then verify the real ink skeleton below.
    for stem in strokes:
        if stem.length < 6:
            continue
        bar_axis = "v" if stem.axis == "h" else "h"
        bars = by_axis[bar_axis]
        bar_positions = positions[bar_axis]
        for side in (-1, 1):
            endpoint = stem.start if side < 0 else stem.end
            firsts = []
            first_tolerance = max(1.5, config.tolerancia_lacuna)
            search_radius = max(first_tolerance, min(stem.length * 0.6, 32.0))
            near = bars[
                bisect_left(bar_positions, endpoint - search_radius) : bisect_right(
                    bar_positions, endpoint + search_radius
                )
            ]
            for bar in near:
                budget.step()
                if not 2 <= bar.length <= stem.length * 1.8:
                    continue
                longitudinal = bar.line
                lateral = (bar.start + bar.end) / 2
                lead = (longitudinal - stem.start) if side > 0 else (stem.end - longitudinal)
                tail = (stem.end - longitudinal) if side > 0 else (longitudinal - stem.start)
                lateral_tolerance = 3.0 if ink is not None else max(1.5, bar.length * 0.2)
                if (
                    lead >= max(6.0, bar.length * 0.3)
                    and -first_tolerance <= tail <= max(first_tolerance, bar.length * 1.2)
                    and abs(lateral - stem.line) <= lateral_tolerance
                ):
                    firsts.append(bar)
            for first in firsts:
                trimmed_stem = _Stroke(
                    stem.axis,
                    stem.line,
                    stem.start if side > 0 else first.line,
                    first.line if side > 0 else stem.end,
                )
                if trimmed_stem.length < 6:
                    continue
                ordered = []
                reach = first.length * 2.5 + 1
                local = bars[
                    bisect_left(bar_positions, first.line - reach) : bisect_right(
                        bar_positions, first.line + reach
                    )
                ]
                for bar in local:
                    budget.step()
                    if not 2 <= bar.length <= stem.length * 1.8:
                        continue
                    distance = (bar.line - first.line) * side
                    lateral = (bar.start + bar.end) / 2
                    lateral_tolerance = 3.0 if ink is not None else max(1.5, bar.length * 0.2)
                    if (
                        -1 <= distance <= first.length * 2.5
                        and abs(lateral - stem.line) <= lateral_tolerance
                    ):
                        ordered.append((distance, bar))
                ordered.sort(key=lambda pair: pair[0])
                # Distinct bars must have distinct axis positions. Tiny duplicate
                # strokes are handled in merge, not counted as multiple bars.
                selected: list[tuple[float, _Stroke]] = []
                for distance, bar in ordered:
                    if not selected or distance - selected[-1][0] > max(
                        1, config.tolerancia_lacuna / 2
                    ):
                        selected.append((distance, bar))
                if not selected or selected[0][1] != first or len(selected) not in (3, 4):
                    continue
                gaps = [selected[i + 1][0] - selected[i][0] for i in range(len(selected) - 1)]
                if min(gaps) < max(1.5, first.length * 0.16) or max(gaps) > first.length * 0.8:
                    continue
                if max(gaps) / min(gaps) > 1.8:
                    continue
                lengths = [bar.length for _, bar in selected]
                if not (lengths[0] > lengths[1] * 1.08 and lengths[1] > lengths[2] * 1.08):
                    continue
                if len(lengths) == 4 and not (lengths[2] * 1.15 < lengths[3] <= lengths[1] * 1.3):
                    continue
                if not first.length * 0.3 <= trimmed_stem.length <= first.length * 2.8:
                    continue
                gap_penalty = sum(abs(gap - sum(gaps) / len(gaps)) for gap in gaps) / max(
                    1, sum(gaps)
                )
                support = (trimmed_stem, *(bar for _, bar in selected))
                graph_tolerance = 3.0 if ink is not None else float(config.tolerancia_lacuna)
                graph = _graph(support, graph_tolerance, budget)
                if graph.junctions < 1 or graph.cycles:
                    continue
                skeleton = _local_skeleton(support, ink, budget) if ink is not None else None
                if skeleton is not None and (skeleton.junctions < 1 or skeleton.endpoints < 4):
                    continue
                found.append(
                    _Candidate(
                        "PARA_RAIOS_MT" if len(selected) == 4 else "ATERRAMENTO",
                        support,
                        gap_penalty,
                        graph,
                        skeleton,
                    )
                )
                if len(found) > config.limite_tracos:
                    raise _BudgetExceededError("Limite de candidatos estruturais alcançado")
    # Prefer longer 4-bar MT support to its 3-bar subset; different geometric
    # supports remain independent candidates for the future union stage.
    best: dict[tuple[int, int, int, int], _Candidate] = {}
    for candidate in found:
        xs = [point[0] for stroke in candidate.strokes for point in stroke.endpoints]
        ys = [point[1] for stroke in candidate.strokes for point in stroke.endpoints]
        key = (round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys)))
        current = best.get(key)
        if current is None or (len(candidate.strokes), -candidate.gap_penalty) > (
            len(current.strokes),
            -current.gap_penalty,
        ):
            best[key] = candidate
    return tuple(best.values())


def _geometry(page: Any, candidate: _Candidate) -> GeometriaObservacaoSimbolo:
    xs = [point[0] for stroke in candidate.strokes for point in stroke.endpoints]
    ys = [point[1] for stroke in candidate.strokes for point in stroke.endpoints]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    visual = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    width, height = float(page.rect.width), float(page.rect.height)
    inverse = page.derotation_matrix
    original = tuple(pymupdf.Point(x, y) * inverse for x, y in visual)
    matrix = (
        Decimal(str(width * inverse.a)),
        Decimal(str(width * inverse.b)),
        Decimal(str(height * inverse.c)),
        Decimal(str(height * inverse.d)),
        Decimal(str(inverse.e)),
        Decimal(str(inverse.f)),
    )
    return GeometriaObservacaoSimbolo(
        tipo=TipoGeometria.POLIGONO,
        pontos_originais=tuple((Decimal(str(p.x)), Decimal(str(p.y))) for p in original),
        pontos_normalizados=tuple(
            PontoNormalizado(
                Decimal(str(min(1.0, max(0.0, x / width)))),
                Decimal(str(min(1.0, max(0.0, y / height)))),
            )
            for x, y in visual
        ),
        transformacao=TransformacaoSimbolo(
            normalizada_para_original=matrix,
            sistema_original="pymupdf-page-unrotated:points:top-left",
        ),
        normalizacao_limitada=any(not (0 <= x <= width and 0 <= y <= height) for x, y in visual),
    )


def _raw_score(candidate: _Candidate) -> Decimal:
    # A dense skeleton branch cluster weakens the shape match; this remains a
    # dimensionless grammar score, never a posterior probability.
    skeleton_penalty = (
        min(0.2, 0.01 * max(0, candidate.skeleton.junctions - 3))
        if candidate.skeleton is not None
        else 0.0
    )
    return Decimal(str(max(0.0, 1.0 - candidate.gap_penalty - skeleton_penalty)))


def observar_simbolos_estruturais(
    page: Any,
    *,
    documento_id: str,
    documento_sha256: str,
    pagina_numero: int,
    configuracao: ConfiguracaoDetectorEstrutural = _DEFAULT_CONFIG,
) -> ResultadoMetodoSimbolos:
    """Scan a complete base page and return raw E03 observations plus coverage."""
    width, height = float(page.rect.width), float(page.rect.height)
    if not math.isfinite(width) or not math.isfinite(height) or min(width, height) <= 0:
        raise ValueError("Página deve possuir área positiva finita")
    profile = perfil_simbolos_estruturais(configuracao)
    source = FonteObservacaoSimbolo(
        documento_id=documento_id,
        documento_sha256=documento_sha256,
        pagina_numero=pagina_numero,
        camada="base",
    )
    budget = _Budget(configuracao.limite_expansoes)
    observations: tuple[ObservacaoSimbolo, ...] = ()
    reason = None
    try:
        if configuracao.entrada == "raster":
            strokes, raster_hash, ink = _raster_strokes(page, configuracao, budget)
        else:
            strokes = _vector_strokes(page, configuracao, budget)
            raster_hash = None
            ink = None
        candidates = _find_candidates(strokes, configuracao, budget, ink)
        observations = tuple(
            ObservacaoSimbolo(
                fonte=source,
                metodo_assinatura=profile.assinatura(),
                geometria=_geometry(page, candidate),
                alternativas=(
                    AlternativaClasseSimbolo(
                        classe=candidate.classe,
                        score_bruto=_raw_score(candidate),
                    ),
                ),
                score_bruto=_raw_score(candidate),
                raster_sha256=raster_hash,
                atributos=(
                    ("grafo_extremidades", candidate.graph.endpoints),
                    ("grafo_juncoes_visuais", candidate.graph.junctions),
                    ("grafo_ciclos", candidate.graph.cycles),
                    ("tracos_suporte", len(candidate.strokes)),
                    ("esqueleto_pixels", candidate.skeleton.pixels if candidate.skeleton else None),
                    (
                        "esqueleto_extremidades",
                        candidate.skeleton.endpoints if candidate.skeleton else None,
                    ),
                    (
                        "esqueleto_juncoes",
                        candidate.skeleton.junctions if candidate.skeleton else None,
                    ),
                    ("score_tipo", "ajuste-de-gramatica-bruto-nao-probabilidade"),
                ),
            )
            for candidate in candidates
        )
    except _BudgetExceededError as error:
        reason = str(error)
    coverage = CoberturaMetodoSimbolos(
        fonte=source,
        regiao_normalizada=(
            PontoNormalizado(Decimal(0), Decimal(0)),
            PontoNormalizado(Decimal(1), Decimal(1)),
        ),
        classes_avaliadas=profile.classes_suportadas,
        estado=EstadoMetodoSimbolos.FALHA
        if reason
        else EstadoMetodoSimbolos.CONCLUIDO
        if observations
        else EstadoMetodoSimbolos.NAO_DETECCAO,
        motivo=reason,
    )
    return ResultadoMetodoSimbolos(perfil=profile, coberturas=(coverage,), observacoes=observations)
