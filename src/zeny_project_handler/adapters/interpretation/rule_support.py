"""Operações puras compartilhadas pelas regras explícitas."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.catalog import AssinaturaSimbologia, CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, SituacaoProjeto, TipoEvidencia
from zeny_project_handler.domain.values import GeometriaDocumento


def normalized_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    translation: dict[str | int, str | int | None] = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00d7": "X",
        "_": " ",
    }
    normalized = without_accents.upper().translate(str.maketrans(translation))
    normalized = re.sub(r"\s*([-/,()])\s*", r"\1", normalized)
    return " ".join(normalized.split())


def contains_code(text: str, code: str) -> bool:
    normalized_code = normalized_text(code)
    if len(normalized_code) < 2:
        return False
    pattern = rf"(?<![A-Z0-9]){re.escape(normalized_code)}(?![A-Z0-9])"
    return re.search(pattern, normalized_text(text)) is not None


@dataclass(frozen=True, slots=True)
class StructureToken:
    """Token de estrutura catalogada preservando sua ocorrência no texto normalizado."""

    code: str
    qualifier: str | None
    start: int
    end: int
    observed: str


def structure_tokens(text: str, codes: tuple[str, ...]) -> tuple[StructureToken, ...]:
    """Reconheça estruturas; código unitário exige qualificador numérico explícito."""
    normalized = normalized_text(text)
    normalized_codes = tuple(
        sorted(
            {normalized_text(code) for code in codes if normalized_text(code)},
            key=lambda code: (-len(code), code),
        )
    )
    qualified_alternatives = "|".join(re.escape(code) for code in normalized_codes)
    plain_alternatives = "|".join(re.escape(code) for code in normalized_codes if len(code) >= 2)
    if not qualified_alternatives:
        return ()
    qualified = rf"(?P<qualified_code>{qualified_alternatives})\((?P<qualifier>\d{{1,4}})\)"
    plain = rf"(?P<plain_code>{plain_alternatives})" if plain_alternatives else r"(?!)"
    pattern = re.compile(rf"(?<![A-Z0-9])(?:{qualified}|{plain})(?![A-Z0-9(])")
    tokens = []
    for match in pattern.finditer(normalized):
        code = match.group("qualified_code") or match.group("plain_code")
        tokens.append(
            StructureToken(
                code=code,
                qualifier=match.group("qualifier"),
                start=match.start(),
                end=match.end(),
                observed=match.group(0),
            )
        )
    return tuple(tokens)


def center(geometry: GeometriaDocumento) -> tuple[float, float]:
    x_values = [float(point.x) for point in geometry.pontos]
    y_values = [float(point.y) for point in geometry.pontos]
    return (min(x_values) + max(x_values)) / 2, (min(y_values) + max(y_values)) / 2


def point_distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def geometry_distance(first: GeometriaDocumento, second: GeometriaDocumento) -> float:
    if first.pagina_id != second.pagina_id:
        return math.inf
    return point_distance(center(first), center(second))


def _color_values(evidence: EvidenciaDocumento) -> tuple[str, ...]:
    attributes = dict(evidence.atributos_extraidos)
    return tuple(
        str(attributes[key]).upper()
        for key in ("cor", "cor_contorno", "cor_preenchimento")
        if attributes.get(key) not in {None, "", "None"}
    )


def _rgb(value: str) -> tuple[int, int, int] | None:
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        return None
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


def _signature_matches(color: str, signature: AssinaturaSimbologia) -> bool:
    observed = _rgb(color)
    expected = _rgb(signature.cor)
    if observed is None or expected is None:
        return False
    return max(abs(left - right) for left, right in zip(observed, expected, strict=True)) <= (
        signature.tolerancia_cor
    )


def situation_from_evidence(
    evidence: EvidenciaDocumento,
    category: CategoriaElemento,
    catalog: CatalogoTecnico,
) -> SituacaoProjeto | None:
    signatures = sorted(
        catalog.assinaturas_simbologia,
        key=lambda item: item.prioridade,
        reverse=True,
    )
    for signature in signatures:
        if signature.categoria_elemento not in {None, category}:
            continue
        if any(_signature_matches(color, signature) for color in _color_values(evidence)):
            return signature.situacao_projeto
    return None


def project_situation_override(
    source: EvidenciaDocumento,
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[SituacaoProjeto, EvidenciaDocumento | None] | None:
    """Aplique marcações explícitas do desenho antes da inferência por cor."""
    bubbles = tuple(
        item
        for item in evidence
        if item.pagina_id == source.pagina_id
        and _is_installation_bubble(item)
        and _geometry_center_is_inside(source.geometria, item.geometria)
    )
    if bubbles:
        bubble = min(bubbles, key=lambda item: _geometry_area(item.geometria))
        return SituacaoProjeto.INSTALAR, bubble
    forced = dict(source.atributos_extraidos).get("situacao_projeto_forcada")
    try:
        situation = SituacaoProjeto(str(forced)) if forced is not None else None
    except ValueError:
        situation = None
    return (situation, None) if situation is not None else None


def _is_installation_bubble(evidence: EvidenciaDocumento) -> bool:
    if evidence.tipo is not TipoEvidencia.VETOR:
        return False
    attributes = dict(evidence.atributos_extraidos)
    operations = {
        operation.strip()
        for operation in str(attributes.get("operacoes") or "").split(",")
        if operation.strip()
    }
    if operations not in ({"qu"}, {"re"}):
        return False
    colors = tuple(
        color
        for color in _color_values(evidence)
        if (rgb := _rgb(color)) is not None
        and 96 <= rgb[0] <= 160
        and rgb[1] <= 32
        and rgb[2] <= 32
    )
    if not colors:
        return False
    left, top, right, bottom = _geometry_bounds(evidence.geometria)
    width = right - left
    height = bottom - top
    return min(width, height) >= 0.0005 and max(width, height) <= 0.20


def _geometry_bounds(geometry: GeometriaDocumento) -> tuple[float, float, float, float]:
    x_values = [float(point.x) for point in geometry.pontos]
    y_values = [float(point.y) for point in geometry.pontos]
    return min(x_values), min(y_values), max(x_values), max(y_values)


def _geometry_area(geometry: GeometriaDocumento) -> float:
    left, top, right, bottom = _geometry_bounds(geometry)
    return (right - left) * (bottom - top)


def _geometry_center_is_inside(
    source: GeometriaDocumento,
    container: GeometriaDocumento,
) -> bool:
    source_x, source_y = center(source)
    left, top, right, bottom = _geometry_bounds(container)
    tolerance = 0.001
    return (
        left - tolerance <= source_x <= right + tolerance
        and top - tolerance <= source_y <= bottom + tolerance
    )


def nearest_context_evidence(
    source: EvidenciaDocumento,
    evidence: tuple[EvidenciaDocumento, ...],
    maximum_distance: Decimal,
) -> EvidenciaDocumento | None:
    candidates = (
        item
        for item in evidence
        if item.tipo in {TipoEvidencia.VETOR, TipoEvidencia.IMAGEM}
        and item.pagina_id == source.pagina_id
    )
    nearest = min(
        candidates,
        key=lambda item: geometry_distance(source.geometria, item.geometria),
        default=None,
    )
    if nearest is None:
        return None
    return (
        nearest
        if geometry_distance(source.geometria, nearest.geometria) <= float(maximum_distance)
        else None
    )
