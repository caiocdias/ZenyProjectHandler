"""Attach explicit, source-bound revision groups before automatic promotion."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import uuid5

from zeny_project_handler.domain.analysis import (
    DecisaoRevisao,
    EvidenciaDocumento,
    PropostaElemento,
    ReferenciaProposta,
)
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao, SituacaoProjeto
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.persistence import UnitOfWorkPort


def preserve_revision_decision(
    work: UnitOfWorkPort,
    proposal: PropostaElemento,
    previous: tuple[PropostaElemento, ...],
) -> PropostaElemento:
    current = revision_data(proposal)
    if current is None:
        return proposal
    for old in previous:
        prior = revision_data(old)
        if prior is None or prior.get("group_id") != current.get("group_id"):
            continue
        decision = work.decisoes_revisao.obter_da_proposta(old.id)
        if not prior.get("decision"):
            continue
        if old.categoria != proposal.categoria or prior.get("base_code") != current.get(
            "base_code"
        ):
            continue
        if dict(old.atributos_sugeridos).get("operacao_revisao_id") != dict(
            proposal.atributos_sugeridos
        ).get("operacao_revisao_id"):
            continue
        # Retain the existing physical element and immutable decision, not a new asset.
        if decision is not None:
            work.propostas.salvar(proposal)
            work.decisoes_revisao.salvar(
                replace(
                    decision,
                    id=uuid5(proposal.id, "decisao-revisao"),
                    proposta_id=proposal.id,
                )
            )
        prior["previous_proposal_id"] = str(old.id)
        return replace(
            proposal,
            estado_revisao=old.estado_revisao,
            geometria=old.geometria,
            codigo_observado=old.codigo_observado,
            tipo_catalogo_sugerido_id=old.tipo_catalogo_sugerido_id,
            situacao_projeto=old.situacao_projeto,
            atributos_sugeridos=tuple(
                sorted(
                    {
                        **dict(proposal.atributos_sugeridos),
                        "revisao_tecnica": json.dumps(prior, ensure_ascii=False),
                        "revisao_tecnica_pendente": False,
                        "revisao_tecnica_decidida": True,
                    }.items()
                )
            ),
        )
    return proposal


def revision_data(proposal: PropostaElemento) -> dict[str, Any] | None:
    value = dict(proposal.atributos_sugeridos).get("revisao_tecnica")
    return json.loads(str(value)) if value else None


def effective_revision_project(
    project: Projeto,
    proposals: tuple[ReferenciaProposta, ...],
    decisions: tuple[DecisaoRevisao, ...],
) -> Projeto:
    """Exclude exact legacy alternatives from the current view, retaining persisted history."""
    current_ids = {item.elemento_confirmado_id for item in decisions}
    excluded = {
        element.id
        for proposal in proposals
        if isinstance(proposal, PropostaElemento)
        if (revision := revision_data(proposal)) is not None
        for element in project.elementos
        if element.id not in current_ids
        and element.categoria == proposal.categoria
        and element.codigo_observado == revision.get("base_code")
        and element.geometria == proposal.geometria
    }
    if not excluded:
        return project
    return replace(
        project,
        elementos=tuple(item for item in project.elementos if item.id not in excluded),
        relacoes_confirmadas=tuple(
            item
            for item in project.relacoes_confirmadas
            if item.origem_id not in excluded and item.destino_id not in excluded
        ),
    )


def attach_revision_conflicts(
    proposals: tuple[PropostaElemento, ...],
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[PropostaElemento, ...]:
    revisions = tuple(
        item for item in evidence if "revisao_tecnica" in dict(item.atributos_extraidos)
    )
    by_id = {item.id: item for item in evidence}
    result = []
    for proposal in proposals:
        source = tuple(by_id[key] for key in proposal.evidencia_ids if key in by_id)
        matches = [
            item
            for item in revisions
            if any(
                _overlap(item, label)
                and (proposal.codigo_observado or "") in (label.conteudo_bruto or "")
                for label in source
            )
        ]
        if not matches:
            result.append(proposal)
            continue
        # Several OCR passes on one label are representations, not additional assets.
        revision = min(matches, key=lambda item: _area(item))
        data = json.loads(str(dict(revision.atributos_extraidos)["revisao_tecnica"]))
        data["evidence_id"] = str(revision.id)
        data["base_code"] = proposal.codigo_observado
        result.append(
            replace(
                proposal,
                estado_revisao=EstadoRevisao.CONFLITANTE,
                evidencia_ids=tuple(dict.fromkeys((*proposal.evidencia_ids, revision.id))),
                atributos_sugeridos=(
                    *proposal.atributos_sugeridos,
                    ("revisao_tecnica_pendente", True),
                    ("revisao_tecnica", json.dumps(data, ensure_ascii=False)),
                ),
                justificativa=(
                    f"{proposal.justificativa or ''} Revisão técnica sobreposta: "
                    f"base {data['base_text']}; "
                    f"visível {data['visible_text'] or 'leitura indisponível'}. "
                    "Autoridade não comprovada; escolha técnica e motivo obrigatórios."
                ),
            )
        )
    return tuple(result)


def append_revision_operations(
    proposals: tuple[PropostaElemento, ...],
) -> tuple[PropostaElemento, ...]:
    """Expose observed structure operations, retaining the base and undecided authority."""
    result = list(proposals)
    for proposal in proposals:
        data = revision_data(proposal)
        if proposal.categoria not in {
            CategoriaElemento.ESTRUTURA_MT,
            CategoriaElemento.ESTRUTURA_BT,
        }:
            continue
        if not data or not data.get("operation_review_pending"):
            continue
        if dict(proposal.atributos_sugeridos).get("operacao_revisao_id"):
            continue
        for color, situation in (
            ("verde", SituacaoProjeto.INSTALAR),
            ("vermelho", SituacaoProjeto.REMOVER),
        ):
            readings = [
                reading
                for reading in data.get("color_readings", [])
                if reading.get("color") == color
                and (color != "vermelho" or reading.get("horizontal_strike") is True)
                and _operation_token(reading.get("text", ""), proposal.codigo_observado)
                and len(reading.get("box", [])) == 4
            ]
            for reading in _distinct_operation_readings(readings):
                box = [Decimal(str(v)) for v in reading["box"]]
                identity = (
                    f"{data['group_id']}:{color}:{reading['annotation_xref']}:"
                    f"{reading['text']}:{box}"
                )
                attrs = dict(proposal.atributos_sugeridos)
                attrs.update(
                    {
                        "operacao_revisao_id": identity,
                        "token_estrutura": reading["text"],
                        "situacao_origem": "leitura_colorida_da_revisao_tecnica",
                    }
                )
                attrs.pop("qualificador_estrutura", None)
                qualifier = re.search(r"\((\d+)\)", reading["text"])
                if qualifier is not None:
                    attrs["qualificador_estrutura"] = qualifier[1]
                result.append(
                    replace(
                        proposal,
                        id=uuid5(proposal.id, identity),
                        situacao_projeto=situation,
                        geometria=GeometriaDocumento.caixa(
                            proposal.geometria.pagina_id,
                            PontoNormalizado(box[0], box[1]),
                            PontoNormalizado(box[2], box[3]),
                        ),
                        atributos_sugeridos=tuple(attrs.items()),
                        justificativa=f"Operação observada em {color}: {reading['text']}. "
                        "Alternativa da camada revisada; autoridade e vigência "
                        "requerem decisão técnica.",
                    )
                )
    return tuple({p.id: p for p in result}.values())


def _distinct_operation_readings(readings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for reading in sorted(readings, key=lambda r: (-len(r["text"]), str(r["box"]))):
        if not any(_same_operation_reading(reading, other) for other in selected):
            selected.append(reading)
    return selected


def _same_operation_reading(reading: dict[str, Any], other: dict[str, Any]) -> bool:
    a, b, c, d = reading["box"]
    e, f, g, h = other["box"]
    return bool(
        reading["annotation_xref"] == other["annotation_xref"]
        and min(c, g) > max(a, e)
        and min(d, h) > max(b, f)
        and (reading["text"] == other["text"] or other["text"].startswith(reading["text"] + "("))
    )


def _operation_token(text: str, code: str | None) -> bool:
    return code is not None and re.fullmatch(re.escape(code) + r"(?:\(\d+\))?", text) is not None


def _bounds(item: EvidenciaDocumento) -> tuple[float, float, float, float]:
    points = item.geometria.pontos
    return (
        float(min(p.x for p in points)),
        float(min(p.y for p in points)),
        float(max(p.x for p in points)),
        float(max(p.y for p in points)),
    )


def _area(item: EvidenciaDocumento) -> float:
    left, top, right, bottom = _bounds(item)
    return (right - left) * (bottom - top)


def _overlap(first: EvidenciaDocumento, second: EvidenciaDocumento) -> bool:
    if first.pagina_id != second.pagina_id:
        return False
    a, b, c, d = _bounds(first)
    e, f, g, h = _bounds(second)
    return min(c, g) > max(a, e) and min(d, h) > max(b, f)
