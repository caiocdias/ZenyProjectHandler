from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from tests.factories import complete_project
from tests.interpretation_factories import text_evidence, vector_evidence
from tests.unit.test_rule_based_interpreter import _e04_span_change_request
from tests.unit.test_spans import _element_proposal

from zeny_project_handler.adapters.interpretation import InterpretadorRegrasExplicitas
from zeny_project_handler.adapters.interpretation.rule_support import (
    contour_label_situation,
    structure_tokens,
)
from zeny_project_handler.adapters.interpretation.span_rules import _trace_paths
from zeny_project_handler.application.automatic_promotion import (
    _endpoint_poles,
    promover_resultado_automatico,
)
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
    TipoEvidencia,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado


@pytest.mark.parametrize("text", ["CM3(1) U3(2)", "CM3 ( 1 )   U3 (2)"])
def test_separate_qualified_tokens_keep_both_occurrences(text: str) -> None:
    tokens = structure_tokens(text, ("CM3", "U3", "N"))
    assert [(token.code, token.qualifier) for token in tokens] == [("CM3", "1"), ("U3", "2")]
    assert not structure_tokens("XCM3(1) N-(4 CAA) N CM3(X)", ("CM3", "N"))


def test_cable_without_resolved_trace_is_not_promoted(catalogo_inicial: CatalogoTecnico) -> None:
    project = complete_project(catalogo_inicial)
    cable_type = catalogo_inicial.itens_ativos(CategoriaElemento.CABO)[0]
    evidence = text_evidence(
        execution_id=uuid4(),
        page_id=project.documentos[0].paginas[0].id,
        key="unresolved-cable",
        text=cable_type.codigo,
        x="0.5",
        y="0.5",
    )
    proposal = PropostaElemento(
        id=uuid4(),
        execucao_id=uuid4(),
        categoria=CategoriaElemento.CABO,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.CONFLITANTE,
        evidencia_ids=(evidence.id,),
        geometria=evidence.geometria,
        tipo_catalogo_sugerido_id=cable_type.id,
        codigo_observado=cable_type.codigo,
    )
    result = promover_resultado_automatico(
        project,
        catalogo_inicial,
        (proposal,),
        (),
        promovido_em=datetime.now(UTC),
    )
    assert result.projeto == project
    assert result.elementos[0].estado_revisao is EstadoRevisao.CONFLITANTE
    assert not result.decisoes


def test_cable_label_situation_survives_shared_trace(catalogo_inicial: CatalogoTecnico) -> None:
    request, evidence = _e04_span_change_request(catalogo_inicial)
    label = next(
        item
        for item in request.evidencias
        if dict(item.atributos_extraidos).get("motor_ocr") == "tesseract-rotulo-linear-retificado"
    )
    # Remove the supersession evidence: only the label and the shared green path remain.
    selected = tuple(
        replace(item, atributos_extraidos=(("cor", "#000000"),)) if item.id == label.id else item
        for item in request.evidencias
        if item.id not in {evidence["strike"].id, evidence["superseded_length"].id}
    )
    result = InterpretadorRegrasExplicitas(request.registro).interpretar(
        replace(request, evidencias=selected)
    )
    cable = next(
        item
        for item in result.elementos
        if item.categoria is CategoriaElemento.CABO and label.id in item.evidencia_ids
    )
    assert dict(cable.atributos_sugeridos).get("alteracao_cabo") is None
    assert cable.situacao_projeto is SituacaoProjeto.EXISTENTE


@pytest.mark.parametrize(
    "measurement,expected", [("17 m", Decimal(17)), ("H.N.=17m", None), ("Ø17mm", None)]
)
def test_short_trace_needs_anchors_and_preserves_current_measurement(
    catalogo_inicial: CatalogoTecnico,
    measurement: str,
    expected: Decimal | None,
) -> None:
    request, _ = _e04_span_change_request(catalogo_inicial)
    page = request.evidencias[0].pagina_id
    pole_code = catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0].codigo
    cable_code = catalogo_inicial.itens_ativos(CategoriaElemento.CABO)[0].codigo
    evidence = tuple(
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page,
            key=str(index),
            text=text,
            x=x,
            y=y,
            color="#008000",
        )
        for index, (text, x, y) in enumerate(
            (
                (pole_code, "0.20", "0.50"),
                (pole_code, "0.23", "0.50"),
                ("P1", "0.20", "0.49"),
                ("P2", "0.23", "0.49"),
                (cable_code, "0.215", "0.498"),
                (measurement, "0.215", "0.495"),
                ("V1-2", "0.215", "0.490"),
            )
        )
    )
    path = vector_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page,
        key="short-trace",
        points=(("0.20", "0.50"), ("0.23", "0.50")),
        color="#008000",
    )
    circle = replace(
        path,
        id=uuid4(),
        geometria=GeometriaDocumento.caixa(
            page,
            PontoNormalizado(Decimal("0.211"), Decimal("0.491")),
            PontoNormalizado(Decimal("0.219"), Decimal("0.499")),
        ),
        atributos_extraidos=(("cor_contorno", "#800000"), ("operacoes", "c,c,c,c,l")),
    )
    interpreter = InterpretadorRegrasExplicitas(request.registro)
    result = interpreter.interpretar(replace(request, evidencias=(*evidence, path, circle)))
    cable = next(item for item in result.elementos if item.categoria is CategoriaElemento.CABO)
    attrs = dict(cable.atributos_sugeridos)
    assert attrs["identificador_operacional"] == "V1-2"
    assert attrs.get("comprimento_m") == expected
    assert not attrs.get("comprimento_substituido_m")
    assert circle.id not in cable.evidencia_ids
    assert cable.geometria == path.geometria
    negative = interpreter.interpretar(replace(request, evidencias=(*evidence[4:], path)))
    unresolved = next(
        item for item in negative.elementos if item.categoria is CategoriaElemento.CABO
    )
    assert unresolved.estado_revisao is EstadoRevisao.CONFLITANTE
    assert "evidencia_geometria_id" not in dict(unresolved.atributos_sugeridos)


def test_contour_color_requires_contained_glyphs_in_agreement(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    source = text_evidence(
        execution_id=uuid4(), page_id=uuid4(), key="label", text="A-4 CA", x="0.4", y="0.4"
    )
    source = replace(
        source,
        tipo=TipoEvidencia.OCR,
        geometria=GeometriaDocumento.caixa(
            source.pagina_id,
            PontoNormalizado(Decimal("0.4"), Decimal("0.4")),
            PontoNormalizado(Decimal("0.46"), Decimal("0.42")),
        ),
        atributos_extraidos=(("motor_ocr", "tesseract-contornos-vetoriais"),),
    )
    glyphs = tuple(
        replace(
            source,
            id=uuid4(),
            tipo=TipoEvidencia.VETOR,
            geometria=GeometriaDocumento.caixa(
                source.pagina_id,
                PontoNormalizado(Decimal(x), Decimal("0.405")),
                PontoNormalizado(Decimal(x) + Decimal("0.005"), Decimal("0.415")),
            ),
            atributos_extraidos=(("tipo_caminho", "f"), ("cor_preenchimento", color)),
        )
        for x, color in (("0.410", "#000000"), ("0.430", "#000000"), ("0.470", "#008000"))
    )
    found = contour_label_situation(source, glyphs, CategoriaElemento.CABO, catalogo_inicial)
    assert found is not None and found[0] is SituacaoProjeto.EXISTENTE
    assert {item.id for item in found[1]} == {item.id for item in glyphs[:2]}
    conflicting = replace(
        glyphs[1], atributos_extraidos=(("tipo_caminho", "f"), ("cor_preenchimento", "#008000"))
    )
    assert (
        contour_label_situation(
            source, (glyphs[0], conflicting), CategoriaElemento.CABO, catalogo_inicial
        )
        is None
    )


def test_short_trace_uses_resolved_poles_when_identifier_text_is_offset(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    execution, page, evidence_id = uuid4(), uuid4(), uuid4()
    poles = tuple(
        _element_proposal(
            execution,
            evidence_id,
            page,
            category=CategoriaElemento.POSTE,
            catalog_item_id=catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0].id,
            x=x,
            y="0.5",
            attributes=(("identificador_operacional", label),),
        )
        for x, label in (("0.2", "P4"), ("0.23", "P5"))
    )
    path = vector_evidence(
        execution_id=execution,
        page_id=page,
        key="short-resolved",
        points=(("0.2", "0.5"), ("0.23", "0.5")),
    )
    # A elegibilidade usa os dois postes já resolvidos, sem mover rótulos ou inventar pontos.
    assert len(_trace_paths((path,), poles)) == 1
    assert _trace_paths((path,), ()) == ()


@pytest.mark.parametrize("reversed_path", [False, True])
def test_unresolved_endpoint_does_not_take_the_other_endpoint_pole(
    catalogo_inicial: CatalogoTecnico,
    reversed_path: bool,
) -> None:
    execution, page, evidence_id = uuid4(), uuid4(), uuid4()
    pole = _element_proposal(
        execution,
        evidence_id,
        page,
        category=CategoriaElemento.POSTE,
        catalog_item_id=catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0].id,
        x="0.8",
        y="0.5",
        attributes=(("identificador_operacional", "P2"),),
    )
    points = (
        PontoNormalizado(Decimal("0.2"), Decimal("0.5")),
        PontoNormalizado(Decimal("0.8"), Decimal("0.5")),
    )
    labels = ("P1", "P2")
    if reversed_path:
        points = (points[1], points[0])
        labels = (labels[1], labels[0])
    element_id = uuid4()
    found = _endpoint_poles(
        GeometriaDocumento.polilinha(page, points),
        (pole,),
        {pole.id: element_id},
        (None, None),
        dict(zip(("ponto_operacional_origem", "ponto_operacional_destino"), labels, strict=True)),
    )
    assert found == ((element_id, None) if reversed_path else (None, element_id))
