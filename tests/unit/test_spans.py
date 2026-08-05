from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from tests.factories import complete_project

from zeny_project_handler.application.automatic_promotion import (
    promover_resultado_automatico,
)
from zeny_project_handler.application.spans import VaoDetectado, detectar_vaos
from zeny_project_handler.domain.analysis import PropostaElemento, PropostaRelacao
from zeny_project_handler.domain.catalog import CatalogoTecnico, ExtraAttributes
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    OrigemComprimentoVao,
    SituacaoProjeto,
    TipoPontoRede,
)
from zeny_project_handler.domain.project import Cabo
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado


def test_existing_informed_cable_is_exposed_as_a_span(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)

    spans = detectar_vaos(project)

    assert len(spans) == 1
    assert spans[0].comprimento_m == Decimal("31.5")
    assert spans[0].origem_comprimento is OrigemComprimentoVao.INFORMADO


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
            poste_origem_id=pole_id,
            poste_destino_id=pole_id,
            situacao=SituacaoProjeto.EXISTENTE,
            geometria=None,
        )
    with pytest.raises(ValueError, match="Origem do comprimento"):
        VaoDetectado(
            id=uuid4(),
            cabo_id=cable_id,
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
            poste_origem_id=None,
            poste_destino_id=None,
            situacao=SituacaoProjeto.EXISTENTE,
            geometria=None,
            comprimento_m=Decimal(0),
        )


@pytest.mark.parametrize(
    ("cable_attributes", "expected_length", "expected_source"),
    (
        ((), Decimal("50.00"), OrigemComprimentoVao.COORDENADAS),
        (
            (
                ("comprimento_m", Decimal("42.5")),
                ("comprimento_origem", "anotacao_desenho"),
            ),
            Decimal("42.5"),
            OrigemComprimentoVao.ANOTACAO_DESENHO,
        ),
    ),
)
def test_automatic_analysis_materializes_span_length(
    catalogo_inicial: CatalogoTecnico,
    cable_attributes: ExtraAttributes,
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
    assert len(spans) == 1
    assert spans[0].cabo_id == confirmed_cable.id
    assert spans[0].comprimento_m == expected_length
    assert spans[0].origem_comprimento is expected_source


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
