from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from tests.factories import complete_project
from tests.interpretation_factories import text_evidence

from zeny_project_handler.application.analysis_regions import classificar_pontos_de_entrega
from zeny_project_handler.application.automatic_promotion import (
    promover_resultado_automatico,
)
from zeny_project_handler.application.spans import VaoDetectado, detectar_vaos
from zeny_project_handler.domain.analysis import PropostaElemento, PropostaRelacao
from zeny_project_handler.domain.catalog import CatalogoTecnico, ExtraAttributes
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    ModalidadeTrecho,
    OrigemComprimentoVao,
    SituacaoProjeto,
    TipoPontoRede,
    TipoTrechoRede,
)
from zeny_project_handler.domain.project import (
    Cabo,
    Equipamento,
    EstruturaMt,
    Poste,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado


def test_existing_informed_cable_is_exposed_as_a_span(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)

    spans = detectar_vaos(project)

    assert len(spans) == 1
    cable = next(item for item in project.elementos if isinstance(item, Cabo))
    assert spans[0].ponto_origem_id == cable.ponto_origem_id
    assert spans[0].ponto_destino_id == cable.ponto_destino_id
    assert spans[0].tipo_trecho is TipoTrechoRede.DESCONHECIDO
    assert spans[0].modalidade is ModalidadeTrecho.DESCONHECIDO
    assert spans[0].comprimento_m == Decimal("31.5")
    assert spans[0].origem_comprimento is OrigemComprimentoVao.INFORMADO


def test_altered_cable_is_exposed_as_altered_span(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    project = replace(
        project,
        elementos=tuple(
            replace(item, situacao=SituacaoProjeto.ALTERAR) if isinstance(item, Cabo) else item
            for item in project.elementos
        ),
    )

    spans = detectar_vaos(project)

    assert len(spans) == 1
    assert spans[0].situacao is SituacaoProjeto.ALTERAR


def test_identified_span_is_kept_when_one_endpoint_has_no_classified_pole(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    cable = next(item for item in project.elementos if isinstance(item, Cabo))
    destination = next(point for point in project.pontos_rede if point.id == cable.ponto_destino_id)
    project = replace(
        project,
        elementos=tuple(
            replace(item, identificador_operacional="V1-2") if item.id == cable.id else item
            for item in project.elementos
        ),
        pontos_rede=tuple(
            replace(point, poste_id=None, tipo=TipoPontoRede.CONEXAO)
            if point.id == destination.id
            else point
            for point in project.pontos_rede
        ),
    )

    spans = detectar_vaos(project)

    assert len(spans) == 1
    assert spans[0].poste_origem_id is not None
    assert spans[0].poste_destino_id is None
    assert spans[0].ponto_destino_id == destination.id
    assert spans[0].tipo_trecho is TipoTrechoRede.DESCONHECIDO


def test_unidentified_cable_without_both_classified_poles_is_not_a_span(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    cable = next(item for item in project.elementos if isinstance(item, Cabo))
    destination = next(point for point in project.pontos_rede if point.id == cable.ponto_destino_id)
    project = replace(
        project,
        pontos_rede=tuple(
            replace(point, poste_id=None, tipo=TipoPontoRede.CONEXAO)
            if point.id == destination.id
            else point
            for point in project.pontos_rede
        ),
    )

    assert detectar_vaos(project) == ()


def test_span_without_informed_length_keeps_unknown_measurement(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    project = replace(
        project,
        elementos=tuple(
            replace(item, comprimento_m=None, origem_comprimento=None, geometria=None)
            if isinstance(item, Cabo)
            else item
            for item in project.elementos
        ),
    )

    span = detectar_vaos(project)[0]

    assert span.comprimento_m is None
    assert span.origem_comprimento is None
    assert span.geometria is None


def test_detected_span_validates_endpoints_and_length_metadata() -> None:
    cable_id = uuid4()
    pole_id = uuid4()

    with pytest.raises(ValueError, match="distintos"):
        VaoDetectado(
            id=uuid4(),
            cabo_id=cable_id,
            ponto_origem_id=uuid4(),
            ponto_destino_id=uuid4(),
            poste_origem_id=pole_id,
            poste_destino_id=pole_id,
            situacao=SituacaoProjeto.EXISTENTE,
            geometria=None,
        )
    with pytest.raises(ValueError, match="Origem do comprimento"):
        VaoDetectado(
            id=uuid4(),
            cabo_id=cable_id,
            ponto_origem_id=uuid4(),
            ponto_destino_id=uuid4(),
            poste_origem_id=None,
            poste_destino_id=None,
            situacao=SituacaoProjeto.EXISTENTE,
            geometria=None,
            origem_comprimento=OrigemComprimentoVao.INFORMADO,
        )
    with pytest.raises(ValueError, match="positivo"):
        VaoDetectado(
            id=uuid4(),
            cabo_id=cable_id,
            ponto_origem_id=uuid4(),
            ponto_destino_id=uuid4(),
            poste_origem_id=None,
            poste_destino_id=None,
            situacao=SituacaoProjeto.EXISTENTE,
            geometria=None,
            comprimento_m=Decimal(0),
        )


@pytest.mark.parametrize(
    ("cable_attributes", "situation", "expected_length", "expected_source"),
    (
        (
            (),
            SituacaoProjeto.INSTALAR,
            Decimal("50.00"),
            OrigemComprimentoVao.COORDENADAS,
        ),
        (
            (
                ("comprimento_m", Decimal("42.5")),
                ("comprimento_origem", "anotacao_desenho"),
            ),
            SituacaoProjeto.INSTALAR,
            Decimal("42.5"),
            OrigemComprimentoVao.ANOTACAO_DESENHO,
        ),
        (
            (
                ("comprimento_m", Decimal("269")),
                ("comprimento_origem", "anotacao_desenho"),
                ("comprimento_substituido_m", Decimal("321")),
                ("alteracao_cabo", "REDUCAO_COMPRIMENTO"),
            ),
            SituacaoProjeto.ALTERAR,
            Decimal("269"),
            OrigemComprimentoVao.ANOTACAO_DESENHO,
        ),
    ),
)
def test_automatic_analysis_materializes_span_length(
    catalogo_inicial: CatalogoTecnico,
    cable_attributes: ExtraAttributes,
    situation: SituacaoProjeto,
    expected_length: Decimal,
    expected_source: OrigemComprimentoVao,
) -> None:
    base = complete_project(catalogo_inicial)
    project = replace(
        base,
        elementos=(),
        pontos_rede=(),
        terminais=(),
        conexoes_internas=(),
        vinculos_obra=(),
        relacoes_confirmadas=(),
        historico_revisao_manual=(),
    )
    execution_id = uuid4()
    evidence_id = uuid4()
    page_id = project.ordem_leitura_paginas[0]
    pole_type_id = catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0].id
    cable_type_id = catalogo_inicial.itens_ativos(CategoriaElemento.CABO)[0].id
    first_pole = _element_proposal(
        execution_id,
        evidence_id,
        page_id,
        category=CategoriaElemento.POSTE,
        catalog_item_id=pole_type_id,
        x="0.20",
        y="0.40",
        attributes=(("coordenada_leste", 100), ("coordenada_norte", 200)),
    )
    second_pole = _element_proposal(
        execution_id,
        evidence_id,
        page_id,
        category=CategoriaElemento.POSTE,
        catalog_item_id=pole_type_id,
        x="0.80",
        y="0.40",
        attributes=(("coordenada_leste", 130), ("coordenada_norte", 240)),
    )
    cable = PropostaElemento(
        id=uuid4(),
        execucao_id=execution_id,
        categoria=CategoriaElemento.CABO,
        situacao_projeto=situation,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(evidence_id,),
        geometria=GeometriaDocumento.polilinha(
            page_id,
            (
                PontoNormalizado(Decimal("0.20"), Decimal("0.40")),
                PontoNormalizado(Decimal("0.80"), Decimal("0.40")),
            ),
        ),
        tipo_catalogo_sugerido_id=cable_type_id,
        atributos_sugeridos=cable_attributes,
        confianca=Decimal("0.90"),
    )
    relations = tuple(
        PropostaRelacao(
            id=uuid4(),
            execucao_id=execution_id,
            origem_referencia_id=cable.id,
            destino_referencia_id=pole.id,
            tipo_relacao="CONECTA",
            evidencia_ids=(evidence_id,),
            confianca=Decimal("0.80"),
        )
        for pole in (first_pole, second_pole)
    )

    promoted = promover_resultado_automatico(
        project,
        catalogo_inicial,
        (first_pole, second_pole, cable),
        relations,
        promovido_em=datetime(2026, 7, 23, 12, tzinfo=UTC),
    )

    confirmed_cable = next(item for item in promoted.projeto.elementos if isinstance(item, Cabo))
    spans = detectar_vaos(promoted.projeto)
    assert confirmed_cable.comprimento_m == expected_length
    assert confirmed_cable.origem_comprimento is expected_source
    assert confirmed_cable.situacao is situation
    assert confirmed_cable.tipo_trecho is TipoTrechoRede.REDE_DISTRIBUICAO
    assert confirmed_cable.modalidade is ModalidadeTrecho.DESCONHECIDO
    assert len(spans) == 1
    assert spans[0].cabo_id == confirmed_cable.id
    assert spans[0].comprimento_m == expected_length
    assert spans[0].origem_comprimento is expected_source
    assert spans[0].situacao is situation
    assert spans[0].tipo_trecho is TipoTrechoRede.REDE_DISTRIBUICAO
    assert spans[0].modalidade is ModalidadeTrecho.DESCONHECIDO


@pytest.mark.parametrize("delivery_label", ("P1", "P5"))
def test_automatic_promotion_separates_delivery_from_nearby_real_pole_and_is_idempotent(
    catalogo_inicial: CatalogoTecnico,
    delivery_label: str,
) -> None:
    base = complete_project(catalogo_inicial)
    project = replace(
        base,
        elementos=(),
        pontos_rede=(),
        terminais=(),
        conexoes_internas=(),
        vinculos_obra=(),
        relacoes_confirmadas=(),
        historico_revisao_manual=(),
    )
    execution_id = uuid4()
    page_id = project.ordem_leitura_paginas[0]
    real_anchor = text_evidence(
        execution_id=execution_id,
        page_id=page_id,
        key=f"{delivery_label}-real-anchor",
        text="P2",
        x="0.20",
        y="0.40",
    )
    delivery_anchor = text_evidence(
        execution_id=execution_id,
        page_id=page_id,
        key=f"{delivery_label}-delivery-anchor",
        text=delivery_label,
        x="0.80",
        y="0.40",
    )
    standard_marker = text_evidence(
        execution_id=execution_id,
        page_id=page_id,
        key=f"{delivery_label}-standard-marker",
        text="PADRÃO",
        x="0.82",
        y="0.40",
    )
    pole_type_id = catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0].id
    cable_type_id = catalogo_inicial.itens_ativos(CategoriaElemento.CABO)[0].id
    structure_type_id = catalogo_inicial.itens_ativos(CategoriaElemento.ESTRUTURA_MT)[0].id
    equipment_type_id = catalogo_inicial.itens_ativos(CategoriaElemento.EQUIPAMENTO)[0].id
    real_pole = _element_proposal(
        execution_id,
        real_anchor.id,
        page_id,
        category=CategoriaElemento.POSTE,
        catalog_item_id=pole_type_id,
        x="0.20",
        y="0.40",
        attributes=(("identificador_operacional", "P2"),),
    )
    delivery_symbol = _element_proposal(
        execution_id,
        delivery_anchor.id,
        page_id,
        category=CategoriaElemento.POSTE,
        catalog_item_id=pole_type_id,
        x="0.80",
        y="0.40",
        attributes=(("identificador_operacional", delivery_label),),
    )
    structure = _element_proposal(
        execution_id,
        real_anchor.id,
        page_id,
        category=CategoriaElemento.ESTRUTURA_MT,
        catalog_item_id=structure_type_id,
        x="0.21",
        y="0.40",
        attributes=(("identificador_operacional", "P2"),),
    )
    equipment = _element_proposal(
        execution_id,
        real_anchor.id,
        page_id,
        category=CategoriaElemento.EQUIPAMENTO,
        catalog_item_id=equipment_type_id,
        x="0.22",
        y="0.40",
        attributes=(("identificador_operacional", "P2"),),
    )
    cable = PropostaElemento(
        id=uuid4(),
        execucao_id=execution_id,
        categoria=CategoriaElemento.CABO,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(real_anchor.id, delivery_anchor.id),
        geometria=GeometriaDocumento.polilinha(
            page_id,
            (
                PontoNormalizado(Decimal("0.20"), Decimal("0.40")),
                PontoNormalizado(Decimal("0.80"), Decimal("0.40")),
            ),
        ),
        tipo_catalogo_sugerido_id=cable_type_id,
        atributos_sugeridos=(
            ("geometria_cabo_origem", "vetor_associado_geometricamente"),
            ("ponto_operacional_origem", "P2"),
            ("ponto_operacional_destino", delivery_label),
        ),
        confianca=Decimal("0.90"),
    )
    proposals = classificar_pontos_de_entrega(
        (real_pole, delivery_symbol, structure, equipment, cable),
        (real_anchor, delivery_anchor, standard_marker),
    )
    classified_delivery = next(item for item in proposals if item.id == delivery_symbol.id)
    classified_cable = next(item for item in proposals if item.id == cable.id)
    assert dict(classified_delivery.atributos_sugeridos)["tipo_ponto_rede"] == "ENTREGA"
    assert dict(classified_cable.atributos_sugeridos)["tipo_ponto_operacional_destino"] == "ENTREGA"

    relations = (
        _relation_proposal(execution_id, structure.id, delivery_symbol.id, "INSTALADA_EM"),
        _relation_proposal(execution_id, equipment.id, delivery_symbol.id, "INSTALADO_EM"),
        _relation_proposal(execution_id, cable.id, real_pole.id, "CONECTA"),
        _relation_proposal(execution_id, cable.id, delivery_symbol.id, "CONECTA"),
    )
    promoted = promover_resultado_automatico(
        project,
        catalogo_inicial,
        proposals,
        relations,
        promovido_em=datetime(2026, 9, 1, 23, tzinfo=UTC),
    )
    repeated = promover_resultado_automatico(
        promoted.projeto,
        catalogo_inicial,
        proposals,
        relations,
        promovido_em=datetime(2026, 9, 1, 23, tzinfo=UTC),
    )

    assert repeated.projeto == promoted.projeto
    poles = tuple(item for item in promoted.projeto.elementos if isinstance(item, Poste))
    assert len(poles) == 1
    assert poles[0].identificador_operacional == "P2"
    assert all(item.identificador_operacional != delivery_label for item in poles)
    delivery_point = next(
        point for point in promoted.projeto.pontos_rede if point.tipo is TipoPontoRede.ENTREGA
    )
    assert delivery_point.poste_id is None
    assert delivery_label in delivery_point.nome
    confirmed_cable = next(item for item in promoted.projeto.elementos if isinstance(item, Cabo))
    assert confirmed_cable.tipo_trecho is TipoTrechoRede.RAMAL_CONEXAO
    assert confirmed_cable.modalidade is ModalidadeTrecho.DESCONHECIDO
    assert {
        item.poste_id
        for item in promoted.projeto.elementos
        if isinstance(item, (EstruturaMt, Equipamento))
    } == {poles[0].id}
    assert all(
        relation.destino_id != delivery_point.id
        for relation in promoted.projeto.relacoes_confirmadas
        if relation.tipo_relacao in {"INSTALADA_EM", "INSTALADO_EM"}
    )
    span = detectar_vaos(promoted.projeto)[0]
    assert span.ponto_destino_id == delivery_point.id
    assert span.poste_destino_id is None
    assert span.tipo_trecho is TipoTrechoRede.RAMAL_CONEXAO


def test_e09_delivery_marker_uses_nearest_point_label_not_sprawling_region(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    execution_id = uuid4()
    page_id = project.ordem_leitura_paginas[0]
    delivery_anchor = text_evidence(
        execution_id=execution_id,
        page_id=page_id,
        key="e09-delivery-anchor",
        text="P1",
        x="0.38",
        y="0.32",
    )
    network_anchor = text_evidence(
        execution_id=execution_id,
        page_id=page_id,
        key="e09-network-anchor",
        text="P2",
        x="0.57",
        y="0.23",
    )
    standard_marker = text_evidence(
        execution_id=execution_id,
        page_id=page_id,
        key="e09-standard-marker",
        text="PADRÃO",
        x="0.38",
        y="0.34",
    )
    pole_type_id = catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0].id
    cable_type_id = catalogo_inicial.itens_ativos(CategoriaElemento.CABO)[0].id
    delivery_symbol = _element_proposal(
        execution_id,
        delivery_anchor.id,
        page_id,
        category=CategoriaElemento.POSTE,
        catalog_item_id=pole_type_id,
        x="0.43",
        y="0.28",
        attributes=(("identificador_operacional", "P1"),),
    )
    network_pole = replace(
        _element_proposal(
            execution_id,
            network_anchor.id,
            page_id,
            category=CategoriaElemento.POSTE,
            catalog_item_id=pole_type_id,
            x="0.57",
            y="0.23",
            attributes=(("identificador_operacional", "P2"),),
        ),
        geometria=GeometriaDocumento.caixa(
            page_id,
            PontoNormalizado(Decimal("0.42"), Decimal("0.21")),
            PontoNormalizado(Decimal("0.67"), Decimal("0.37")),
        ),
    )
    cable = PropostaElemento(
        id=uuid4(),
        execucao_id=execution_id,
        categoria=CategoriaElemento.CABO,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(delivery_anchor.id, network_anchor.id),
        geometria=GeometriaDocumento.polilinha(
            page_id,
            (
                PontoNormalizado(Decimal("0.43"), Decimal("0.28")),
                PontoNormalizado(Decimal("0.57"), Decimal("0.23")),
            ),
        ),
        tipo_catalogo_sugerido_id=cable_type_id,
        atributos_sugeridos=(
            ("geometria_cabo_origem", "vetor_associado_geometricamente"),
            ("ponto_operacional_origem", "P1"),
            ("ponto_operacional_destino", "P2"),
        ),
        confianca=Decimal("0.90"),
    )

    proposals = classificar_pontos_de_entrega(
        (delivery_symbol, network_pole, cable),
        (delivery_anchor, network_anchor, standard_marker),
    )

    classified_delivery = next(item for item in proposals if item.id == delivery_symbol.id)
    classified_network = next(item for item in proposals if item.id == network_pole.id)
    classified_cable = next(item for item in proposals if item.id == cable.id)
    assert dict(classified_delivery.atributos_sugeridos)["tipo_ponto_rede"] == "ENTREGA"
    assert "tipo_ponto_rede" not in dict(classified_network.atributos_sugeridos)
    assert dict(classified_cable.atributos_sugeridos)["tipo_ponto_operacional_origem"] == "ENTREGA"


def test_automatic_promotion_keeps_unproved_endpoint_unknown(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    base = complete_project(catalogo_inicial)
    project = replace(
        base,
        elementos=(),
        pontos_rede=(),
        terminais=(),
        conexoes_internas=(),
        vinculos_obra=(),
        relacoes_confirmadas=(),
        historico_revisao_manual=(),
    )
    execution_id = uuid4()
    evidence_id = uuid4()
    page_id = project.ordem_leitura_paginas[0]
    real_pole = _element_proposal(
        execution_id,
        evidence_id,
        page_id,
        category=CategoriaElemento.POSTE,
        catalog_item_id=catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0].id,
        x="0.20",
        y="0.40",
        attributes=(("identificador_operacional", "P2"),),
    )
    cable = PropostaElemento(
        id=uuid4(),
        execucao_id=execution_id,
        categoria=CategoriaElemento.CABO,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(evidence_id,),
        geometria=GeometriaDocumento.polilinha(
            page_id,
            (
                PontoNormalizado(Decimal("0.20"), Decimal("0.40")),
                PontoNormalizado(Decimal("0.80"), Decimal("0.40")),
            ),
        ),
        tipo_catalogo_sugerido_id=catalogo_inicial.itens_ativos(CategoriaElemento.CABO)[0].id,
        atributos_sugeridos=(
            ("geometria_cabo_origem", "vetor_associado_geometricamente"),
            ("identificador_operacional", "V2-9"),
            ("ponto_operacional_origem", "P2"),
            ("ponto_operacional_destino", "P9"),
        ),
        confianca=Decimal("0.90"),
    )
    promoted = promover_resultado_automatico(
        project,
        catalogo_inicial,
        (real_pole, cable),
        (_relation_proposal(execution_id, cable.id, real_pole.id, "CONECTA"),),
        promovido_em=datetime(2026, 9, 1, 23, tzinfo=UTC),
    )

    confirmed_cable = next(item for item in promoted.projeto.elementos if isinstance(item, Cabo))
    destination = next(
        point
        for point in promoted.projeto.pontos_rede
        if point.id == confirmed_cable.ponto_destino_id
    )
    assert destination.tipo is TipoPontoRede.CONEXAO
    assert destination.poste_id is None
    assert confirmed_cable.tipo_trecho is TipoTrechoRede.DESCONHECIDO
    span = detectar_vaos(promoted.projeto)[0]
    assert span.ponto_destino_id == destination.id
    assert span.tipo_trecho is TipoTrechoRede.DESCONHECIDO


def _relation_proposal(
    execution_id: UUID,
    origin_id: UUID,
    destination_id: UUID,
    relation_type: str,
) -> PropostaRelacao:
    return PropostaRelacao(
        id=uuid4(),
        execucao_id=execution_id,
        origem_referencia_id=origin_id,
        destino_referencia_id=destination_id,
        tipo_relacao=relation_type,
        evidencia_ids=(uuid4(),),
        confianca=Decimal("0.80"),
    )


def _element_proposal(
    execution_id: UUID,
    evidence_id: UUID,
    page_id: UUID,
    *,
    category: CategoriaElemento,
    catalog_item_id: UUID,
    x: str,
    y: str,
    attributes: ExtraAttributes,
) -> PropostaElemento:
    return PropostaElemento(
        id=uuid4(),
        execucao_id=execution_id,
        categoria=category,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(evidence_id,),
        geometria=GeometriaDocumento.ponto(
            page_id,
            PontoNormalizado(Decimal(x), Decimal(y)),
        ),
        tipo_catalogo_sugerido_id=catalog_item_id,
        atributos_sugeridos=attributes,
        confianca=Decimal("0.90"),
    )
