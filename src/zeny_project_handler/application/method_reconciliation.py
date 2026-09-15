"""Reconcile documentary hypotheses without treating agreement as calibrated evidence."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from hashlib import sha256
from typing import Any
from uuid import uuid5

from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.enums import EstadoRevisao, TipoOrigemPdf
from zeny_project_handler.ports.analysis import CandidatoEvidenciaDocumento

COMPOSITION_VERSION = "documentary-coordinate-review-1"
READING_KEY = "leitura_metodo"
_NUMBER = re.compile(r"(?<!\d)\d{6,8}(?!\d)")


def coordinate_literal(text: str) -> bool:
    numbers = [int(match.group()) for match in _NUMBER.finditer(text)]
    return (
        sum(100_000 <= n <= 999_999 for n in numbers) == 1
        and sum(1_000_000 <= n <= 10_000_000 for n in numbers) == 1
        and len(numbers) == 2
    )


def reading_data(attributes: object) -> dict[str, Any] | None:
    if not isinstance(attributes, (tuple, list)):
        return None
    value = dict(attributes).get(READING_KEY)
    return json.loads(str(value)) if value else None


def reconcile_readings(
    base: tuple[CandidatoEvidenciaDocumento, ...],
    auxiliary: tuple[CandidatoEvidenciaDocumento, ...],
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    result = []
    for candidate in auxiliary:
        data = reading_data(candidate.atributos_extraidos)
        if data is None:
            raise ValueError("Complementary reading must carry provenance")
        selected = coordinate_literal(data["literal"])
        # Overlap only locates alternatives; it never merges physical objects.
        matches = (
            [
                item
                for item in base
                if data["layer"] == "base"
                and item.pagina_numero == candidate.pagina_numero
                and item.origem_pdf.tipo
                in {
                    TipoOrigemPdf.CONTEUDO_PAGINA,
                    TipoOrigemPdf.FORM_XOBJECT,
                }
                and item.conteudo_bruto
                and coordinate_literal(item.conteudo_bruto)
                and _overlaps(candidate, item)
            ]
            if selected
            else []
        )
        status = "outside_selected_scope"
        if selected:
            if data["layer"] != "base":
                status = "technical_layer_review"
            elif not matches:
                status = "complement_requires_review"
            elif all(
                coordinate_value(item.conteudo_bruto or "") == coordinate_value(data["literal"])
                for item in matches
            ):
                status = "agreement_uncalibrated"
            else:
                status = "conflict_requires_review"
        alternatives = [
            {
                "evidence_key": item.chave_estavel,
                "literal": item.conteudo_bruto,
                "method": str(dict(item.atributos_extraidos).get("motor_ocr", item.tipo.value)),
                "layer": "base",
                "geometry": [[str(p.x), str(p.y)] for p in item.geometria.pontos],
            }
            for item in matches
        ]
        data.update(
            composition=COMPOSITION_VERSION,
            selected=selected,
            resolution=status,
            alternatives=alternatives,
            requires_review=selected,
            automatically_confirmed=False,
            calibrated_error_rate=None,
        )
        # Unreviewed literals cannot enter old semantic consumers implicitly.
        result.append(
            replace(
                candidate,
                conteudo_bruto=None,
                atributos_extraidos=(
                    *[(k, v) for k, v in candidate.atributos_extraidos if k != READING_KEY],
                    (READING_KEY, json.dumps(data, ensure_ascii=False, sort_keys=True)),
                ),
            )
        )
    return tuple(result)


def reading_identity(
    source: str, page: int, layer: str, signature: str, quad: list[list[float]], literal: str
) -> str:
    # No execution UUID or fuzzy geometry: decisions cannot migrate to a neighbour.
    payload = [source, page, layer, signature, quad, literal]
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def coordinate_value(text: str) -> tuple[int, ...]:
    """Compare observed digits; surrounding label punctuation is not a disagreement."""
    return tuple(sorted(int(m.group()) for m in _NUMBER.finditer(text)))


def attach_method_conflicts(
    proposals: tuple[PropostaElemento, ...],
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[PropostaElemento, ...]:
    conflicts = []
    for item in evidence:
        data = reading_data(item.atributos_extraidos)
        if data is not None and data.get("resolution") == "conflict_requires_review":
            references = {uuid5(item.execucao_id, a["evidence_key"]) for a in data["alternatives"]}
            conflicts.append((item, data, references))
    result = []
    for proposal in proposals:
        matches = [
            (item, data)
            for item, data, references in conflicts
            if references.intersection(proposal.evidencia_ids)
        ]
        if not matches:
            result.append(proposal)
            continue
        result.append(
            replace(
                proposal,
                estado_revisao=EstadoRevisao.CONFLITANTE,
                evidencia_ids=tuple(
                    sorted({*proposal.evidencia_ids, *(item.id for item, _ in matches)}, key=str)
                ),
                atributos_sugeridos=tuple(
                    sorted(
                        {
                            **dict(proposal.atributos_sugeridos),
                            "reconciliacao_metodos_pendente": True,
                            "reconciliacao_metodos": json.dumps(
                                [data for _, data in matches], ensure_ascii=False
                            ),
                        }.items()
                    )
                ),
                justificativa=f"{proposal.justificativa or ''} "
                "Coordenada com leituras divergentes; "
                "conferir as alternativas antes de aceitar a proposta.",
            )
        )
    return tuple(result)


def _overlaps(first: CandidatoEvidenciaDocumento, second: CandidatoEvidenciaDocumento) -> bool:
    def bounds(item: CandidatoEvidenciaDocumento) -> tuple[float, float, float, float]:
        xs = [float(p.x) for p in item.geometria.pontos]
        ys = [float(p.y) for p in item.geometria.pontos]
        return min(xs), min(ys), max(xs), max(ys)

    a, b = bounds(first), bounds(second)
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return smaller > 0 and intersection / smaller >= 0.8
