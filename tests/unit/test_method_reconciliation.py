"""Development controls: correlated errors, separate occurrences and technical layers."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

import pytest

from zeny_project_handler.application.method_reconciliation import (
    READING_KEY,
    coordinate_literal,
    reading_data,
    reading_identity,
    reconcile_readings,
)
from zeny_project_handler.domain.analysis import OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.analysis import CandidatoEvidenciaDocumento, GeometriaNormalizada


def candidate(
    text: str, *, auxiliary: bool = False, layer: str = "base", page: int = 1, x: str = "0.1"
) -> CandidatoEvidenciaDocumento:
    return CandidatoEvidenciaDocumento(
        chave_estavel=f"{page}:{x}:{layer}:{text}",
        pagina_numero=page,
        tipo=TipoEvidencia.OCR,
        origem_pdf=OrigemObjetoPdf(),
        conteudo_bruto=None if auxiliary else text,
        geometria=GeometriaNormalizada(
            tipo=TipoGeometria.CAIXA,
            pontos=(
                PontoNormalizado(Decimal(x), Decimal("0.1")),
                PontoNormalizado(Decimal(x) + Decimal("0.1"), Decimal("0.12")),
            ),
        ),
        atributos_extraidos=(
            (
                READING_KEY,
                json.dumps(
                    {
                        "literal": text,
                        "layer": layer,
                        "method": "independent-engine",
                        "raw_score": 0.999,
                    }
                ),
            ),
        )
        if auxiliary
        else (),
    )


@pytest.mark.parametrize(
    ("base", "aux", "resolution"),
    [
        ("654321 7654321", "654321 7654321", "agreement_uncalibrated"),
        ("654321 7654321", "654329 7654321", "conflict_requires_review"),
        ("", "654321 7654321", "complement_requires_review"),
        ("E:654321 N:7654321", "654321 7654321", "agreement_uncalibrated"),
    ],
)
def test_agreement_even_when_both_wrong_never_confirms(
    base: str,
    aux: str,
    resolution: str,
) -> None:
    # Truth is 654320: even two engines agreeing on 654321 are wrong.
    result = reconcile_readings((candidate(base),), (candidate(aux, auxiliary=True),))
    data = reading_data(result[0].atributos_extraidos)
    assert data is not None and data["resolution"] == resolution
    assert data["automatically_confirmed"] is False
    assert data["calibrated_error_rate"] is None
    assert data["requires_review"] is True
    assert result[0].conteudo_bruto is None
    assert data["literal"] == aux


def test_overlaid_revision_and_distinct_occurrences_are_not_votes_or_merged() -> None:
    text = "654321 7654321"
    inputs = (
        candidate(text, auxiliary=True, layer="appearance"),
        candidate(text, auxiliary=True, x="0.7"),
        candidate(text, auxiliary=True, page=2),
    )
    result = reconcile_readings((candidate(text),), inputs)
    data = [reading_data(item.atributos_extraidos) for item in result]
    assert len(result) == 3
    assert data[0] is not None and data[0]["resolution"] == "technical_layer_review"
    assert all(item is not None and item["alternatives"] == [] for item in data)


def test_identity_changes_with_source_layer_model_geometry_or_literal() -> None:
    base = ("source", 1, "base", "model-A", [[0.1, 0.2]], "654321 7654321")
    assert reading_identity(*base) == reading_identity(*base)
    variants = [
        ("new-source", *base[1:]),
        (*base[:2], "appearance", *base[3:]),
        (*base[:3], "model-B", *base[4:]),
        (*base[:4], [[0.2, 0.2]], base[5]),
        (*base[:5], "654329 7654321"),
    ]
    assert len({reading_identity(*args) for args in [base, *variants]}) == 6


def test_scope_does_not_complete_catalog_or_partial_coordinate() -> None:
    for text in ("N3", "TR-3-4?", "65432 7654321", "123456 7654321 7654322"):
        assert not coordinate_literal(text)
        result = reconcile_readings((), (candidate(text, auxiliary=True),))
        data = reading_data(result[0].atributos_extraidos)
        assert data is not None and data["resolution"] == "outside_selected_scope"
    with pytest.raises(ValueError, match="provenance"):
        reconcile_readings((), (replace(candidate("N3"), atributos_extraidos=()),))


@pytest.mark.parametrize(
    "pending", ["reconciliacao_metodos_pendente", "verificacao_metodos_incompleta"]
)
def test_unresolved_method_verification_blocks_catalog_promotion(
    pending: str,
    catalogo_inicial: object,
) -> None:
    from datetime import UTC, datetime
    from typing import cast
    from uuid import uuid4

    from tests.factories import complete_project
    from tests.unit.test_spans import _element_proposal

    from zeny_project_handler.application.automatic_promotion import promover_resultado_automatico
    from zeny_project_handler.domain.catalog import CatalogoTecnico
    from zeny_project_handler.domain.enums import CategoriaElemento

    catalog = cast(CatalogoTecnico, catalogo_inicial)
    project = complete_project(catalog)
    proposal = _element_proposal(
        uuid4(),
        uuid4(),
        project.documentos[0].paginas[0].id,
        category=CategoriaElemento.POSTE,
        catalog_item_id=catalog.itens_ativos(CategoriaElemento.POSTE)[0].id,
        x="0.1",
        y="0.2",
        attributes=((pending, True),),
    )
    promoted = promover_resultado_automatico(
        project, catalog, (proposal,), (), promovido_em=datetime.now(UTC)
    )
    assert not promoted.decisoes and promoted.projeto == project


def test_conflict_reaches_only_proposal_using_that_evidence(catalogo_inicial: object) -> None:
    from typing import cast
    from uuid import uuid4

    from tests.factories import complete_project
    from tests.interpretation_factories import text_evidence
    from tests.unit.test_spans import _element_proposal

    from zeny_project_handler.application.method_reconciliation import attach_method_conflicts
    from zeny_project_handler.domain.catalog import CatalogoTecnico
    from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao

    catalog = cast(CatalogoTecnico, catalogo_inicial)
    project = complete_project(catalog)
    page = project.documentos[0].paginas[0].id
    run = uuid4()
    base = candidate("654321 7654321")
    raw = candidate("654329 7654321", auxiliary=True)
    reconciled = reconcile_readings((base,), (raw,))[0]
    original = text_evidence(
        execution_id=run,
        page_id=page,
        key=base.chave_estavel,
        text=base.conteudo_bruto or "",
        x="0.1",
        y="0.2",
    )
    auxiliary = replace(
        original,
        id=uuid4(),
        conteudo_bruto=None,
        atributos_extraidos=reconciled.atributos_extraidos,
    )
    proposal = _element_proposal(
        run,
        original.id,
        page,
        category=CategoriaElemento.POSTE,
        catalog_item_id=catalog.itens_ativos(CategoriaElemento.POSTE)[0].id,
        x="0.1",
        y="0.2",
        attributes=(),
    )
    unrelated = replace(proposal, id=uuid4(), evidencia_ids=(uuid4(),))
    result = attach_method_conflicts((proposal, unrelated), (original, auxiliary))
    assert result[0].estado_revisao is EstadoRevisao.CONFLITANTE
    assert dict(result[0].atributos_sugeridos)["reconciliacao_metodos_pendente"] is True
    assert auxiliary.id in result[0].evidencia_ids
    assert result[1] == unrelated
