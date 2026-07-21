from __future__ import annotations

from decimal import Decimal

from tests.evaluation_factories import (
    make_annotation,
    make_criteria,
    make_element,
    make_relation,
)

from zeny_project_handler.application.evaluation_metrics import (
    calcular_metricas_semanticas,
    medir_divergencia_anotadores,
)
from zeny_project_handler.domain.enums import CategoriaElemento, PapelAnotacao, SituacaoProjeto


def test_metrics_match_elements_and_relations_with_independent_ids() -> None:
    references = (
        make_element(),
        make_element(element_id="equipamento-001", category=CategoriaElemento.EQUIPAMENTO),
    )
    candidates = (
        make_element(element_id="predito-poste", x="0.251"),
        make_element(
            element_id="predito-equipamento",
            category=CategoriaElemento.EQUIPAMENTO,
            x="0.251",
        ),
    )
    category_metrics, relation_metrics = calcular_metricas_semanticas(
        references,
        (make_relation(),),
        candidates,
        (
            make_relation(
                relation_id="relacao-predita",
                source_id="predito-poste",
                target_id="predito-equipamento",
            ),
        ),
        make_criteria(),
    )

    by_category = {item.categoria: item.contagem for item in category_metrics}
    assert by_category[CategoriaElemento.POSTE].precisao == Decimal(1)
    assert by_category[CategoriaElemento.EQUIPAMENTO].recall == Decimal(1)
    assert relation_metrics.verdadeiros_positivos == 1


def test_double_annotation_quantifies_label_disagreement() -> None:
    primary = make_annotation(
        role=PapelAnotacao.PRIMARIA,
        annotator_id="anotador-01",
        elements=(make_element(),),
    )
    secondary = make_annotation(
        role=PapelAnotacao.SECUNDARIA,
        annotator_id="anotador-02",
        elements=(make_element(element_id="poste-sec", situation=SituacaoProjeto.INSTALAR),),
    )

    result = medir_divergencia_anotadores(primary, secondary, make_criteria())

    assert result.elementos_correspondentes == 1
    assert result.divergencias_situacao == 1
    assert result.taxa_divergencia == Decimal(1)
