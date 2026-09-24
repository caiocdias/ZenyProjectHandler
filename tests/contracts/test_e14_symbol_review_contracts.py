"""E14 additive symbol transport and explicit uncertainty."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from zeny_project_handler_contracts.review import ReviewProposalDto, ReviewSymbolDto


def test_legacy_proposal_without_symbol_still_round_trips() -> None:
    proposal_id, page_id = str(uuid4()), str(uuid4())
    geometry = {"page_id": page_id, "kind": "POINT", "points": [{"x": "0.1", "y": "0.2"}]}
    payload = {
        "proposal_id": proposal_id,
        "category": "EQUIPMENT",
        "situation": "EXISTING",
        "review_state": "PENDING",
        "state_label": "Pendente",
        "situation_label": "Existente",
        "label": "Equipamento",
        "catalog_label": "Não catalogado",
        "detection_summary": "Identificação legada",
        "attributes": {},
        "evidence": [],
        "requires_review": True,
        "overlay": {
            "proposal_id": proposal_id,
            "geometry": geometry,
            "link_geometry": geometry,
            "label": "Equipamento",
            "category": "EQUIPMENT",
            "situation": "EXISTING",
            "situation_label": "Existente",
            "review_state": "PENDING",
        },
    }
    legacy = ReviewProposalDto.model_validate(payload)
    assert legacy.symbol is None
    enriched = ReviewProposalDto.model_validate(
        {**payload, "symbol": {"occurrence_id": "occ-1", "role": "ativo", "status": "exclusive"}}
    )
    assert enriched.symbol is not None
    assert enriched.symbol.effective_situation is None
    assert enriched.symbol.calibrated_probability is None
    assert enriched.symbol.reference_ids == ()
    assert ReviewProposalDto.model_validate_json(enriched.model_dump_json()) == enriched


def test_alternative_identity_is_one_occurrence_without_fabricated_catalog_id() -> None:
    symbol = ReviewSymbolDto.model_validate(
        {
            "occurrence_id": "same-visual-occurrence",
            "role": "desconhecido",
            "status": "conflicting",
            "alternatives": [
                {"symbol_class": "TRANSFORMADOR", "subtype": "A"},
                {"symbol_class": "TRANSFORMADOR", "subtype": "B"},
            ],
        }
    )
    assert len(symbol.alternatives) == 2
    assert symbol.reference_ids == ()
    assert symbol.symbol_class is None
    assert symbol.quantity is None
    assert "catalog_item_id" not in symbol.model_dump()


@pytest.mark.parametrize("invalid", ["majority", "probable", "accepted_by_silence"])
def test_unregistered_symbol_status_is_rejected(invalid: str) -> None:
    with pytest.raises(ValidationError):
        ReviewSymbolDto.model_validate({"occurrence_id": "occ", "role": "ativo", "status": invalid})
