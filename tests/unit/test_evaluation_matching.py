from __future__ import annotations

from decimal import Decimal

from tests.evaluation_factories import make_criteria

from zeny_project_handler.application.evaluation_matching import (
    associar_elementos,
    relacoes_correspondentes,
    similaridade_geometria,
)
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    SituacaoProjeto,
    TipoGeometria,
)
from zeny_project_handler.domain.evaluation import (
    GeometriaAvaliacao,
    RotuloElementoAvaliacao,
    RotuloRelacaoAvaliacao,
)
from zeny_project_handler.domain.values import PontoNormalizado


def _geometry(
    geometry_type: TipoGeometria,
    *coordinates: tuple[str, str],
    page_number: int = 1,
) -> GeometriaAvaliacao:
    return GeometriaAvaliacao(
        pagina_numero=page_number,
        tipo=geometry_type,
        pontos=tuple(PontoNormalizado(Decimal(x), Decimal(y)) for x, y in coordinates),
    )


def _element(
    element_id: str,
    geometry: GeometriaAvaliacao,
    *,
    category: CategoriaElemento = CategoriaElemento.POSTE,
    situation: SituacaoProjeto = SituacaoProjeto.EXISTENTE,
) -> RotuloElementoAvaliacao:
    return RotuloElementoAvaliacao(
        id=element_id,
        categoria=category,
        situacao=situation,
        geometria=geometry,
    )


def test_geometry_similarity_handles_points_areas_and_incompatible_shapes() -> None:
    criteria = make_criteria()
    point = _geometry(TipoGeometria.PONTO, ("0.10", "0.10"))
    nearby_point = _geometry(TipoGeometria.PONTO, ("0.11", "0.10"))
    distant_point = _geometry(TipoGeometria.PONTO, ("0.50", "0.50"))
    box = _geometry(TipoGeometria.CAIXA, ("0.10", "0.10"), ("0.40", "0.40"))
    overlapping_box = _geometry(
        TipoGeometria.CAIXA,
        ("0.10", "0.10"),
        ("0.35", "0.40"),
    )
    disjoint_box = _geometry(TipoGeometria.CAIXA, ("0.60", "0.60"), ("0.80", "0.80"))

    assert similaridade_geometria(point, nearby_point, criteria) == Decimal("0.5")
    assert similaridade_geometria(point, distant_point, criteria) is None
    assert similaridade_geometria(point, box, criteria) is None
    overlapping_score = similaridade_geometria(box, overlapping_box, criteria)
    assert overlapping_score is not None
    assert overlapping_score >= Decimal("0.5")
    assert similaridade_geometria(box, disjoint_box, criteria) is None


def test_polyline_similarity_is_symmetric_and_respects_tolerance() -> None:
    criteria = make_criteria()
    reference = _geometry(
        TipoGeometria.POLILINHA,
        ("0.10", "0.20"),
        ("0.50", "0.20"),
        ("0.90", "0.20"),
    )
    nearby = _geometry(
        TipoGeometria.POLILINHA,
        ("0.10", "0.21"),
        ("0.90", "0.21"),
    )
    distant = _geometry(
        TipoGeometria.POLILINHA,
        ("0.10", "0.30"),
        ("0.90", "0.30"),
    )

    nearby_score = similaridade_geometria(reference, nearby, criteria)
    assert nearby_score is not None
    assert Decimal("0.49") < nearby_score < Decimal("0.51")
    assert similaridade_geometria(reference, distant, criteria) is None


def test_element_matching_is_one_to_one_deterministic_and_label_aware() -> None:
    geometry = _geometry(TipoGeometria.PONTO, ("0.25", "0.50"))
    wrong_page = _geometry(TipoGeometria.PONTO, ("0.25", "0.50"), page_number=2)
    references = (_element("reference-b", geometry), _element("reference-a", geometry))
    candidates = (
        _element("candidate-y", geometry),
        _element("candidate-x", geometry),
        _element("wrong-page", wrong_page),
        _element("wrong-label", geometry, category=CategoriaElemento.EQUIPAMENTO),
    )

    matches = associar_elementos(references, candidates, make_criteria(), exigir_rotulos=True)

    assert tuple((item.referencia_id, item.candidato_id) for item in matches) == (
        ("reference-a", "candidate-x"),
        ("reference-b", "candidate-y"),
    )
    assert (
        len(
            associar_elementos(
                (references[0],),
                (candidates[-1],),
                make_criteria(),
                exigir_rotulos=False,
            )
        )
        == 1
    )


def test_relation_matching_maps_ids_and_normalizes_undirected_endpoints() -> None:
    undirected_reference = RotuloRelacaoAvaliacao(
        id="reference-undirected",
        origem_id="reference-a",
        destino_id="reference-b",
        tipo_relacao="conecta",
        direcionada=False,
    )
    undirected_candidate = RotuloRelacaoAvaliacao(
        id="candidate-undirected",
        origem_id="candidate-y",
        destino_id="candidate-x",
        tipo_relacao="conecta",
        direcionada=False,
    )
    directed_reference = RotuloRelacaoAvaliacao(
        id="reference-directed",
        origem_id="reference-a",
        destino_id="reference-b",
        tipo_relacao="suporta",
    )
    reversed_candidate = RotuloRelacaoAvaliacao(
        id="candidate-directed",
        origem_id="candidate-y",
        destino_id="candidate-x",
        tipo_relacao="suporta",
    )
    missing_mapping = RotuloRelacaoAvaliacao(
        id="candidate-unmapped",
        origem_id="candidate-x",
        destino_id="candidate-z",
        tipo_relacao="conecta",
        direcionada=False,
    )
    mapping = {"candidate-x": "reference-a", "candidate-y": "reference-b"}

    assert (
        relacoes_correspondentes(
            (undirected_reference,),
            (undirected_candidate, missing_mapping),
            mapping,
        )
        == 1
    )
    assert (
        relacoes_correspondentes(
            (directed_reference,),
            (reversed_candidate,),
            mapping,
        )
        == 0
    )
