from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from zeny_project_handler.application import compliance_callouts as callout_layout
from zeny_project_handler.application.compliance_callouts import (
    CalloutConformidade,
    OrigemAncoraCallout,
    RetanguloCallout,
    ponto_conexao_callout,
    projetar_callouts_conformidade,
)
from zeny_project_handler.application.visual_occupancy import MapaOcupacaoVisual
from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.compliance import (
    AchadoConformidade,
    AlvoConformidade,
    AvaliacaoCondicaoConformidade,
    ExecucaoConformidade,
    FatoConformidade,
    FonteNormativa,
    GrupoCondicaoConformidade,
    OperadorCondicao,
    QuantificadorCondicao,
    ResultadoCondicaoConformidade,
    ResultadoConformidade,
    SeveridadeConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.documents import PaginaDocumento
from zeny_project_handler.domain.enums import TipoEvidencia
from zeny_project_handler.domain.values import (
    CaixaPagina,
    GeometriaDocumento,
    PontoNormalizado,
)


@pytest.mark.parametrize(
    ("width", "height"),
    ((Decimal("595"), Decimal("842")), (Decimal("1191"), Decimal("842"))),
)
def test_projection_is_contained_wrapped_deterministic_and_reduces_collisions(
    width: Decimal,
    height: Decimal,
) -> None:
    page = _page("layout", width=width, height=height)
    anchor = GeometriaDocumento.ponto(page.id, _point("0.5", "0.5"))
    message = ("Mensagem sintética longa " * 12).strip()
    execution, evidence = _execution(
        (page,),
        fact_geometries=(anchor, anchor, anchor),
        message=message,
    )
    presentation = {item.id: f"{item.titulo}: {message}" for item in execution.achados}

    first = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(page,),
        textos_apresentacao=presentation,
    )
    repeated = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(page,),
        textos_apresentacao=presentation,
    )

    assert first == repeated
    assert len(first) == 3
    assert len({item.caixa_sugerida for item in first}) == 3
    assert all("\n" in item.texto for item in first)
    assert all(
        Decimal(0) <= item.caixa_sugerida.esquerda < item.caixa_sugerida.direita <= Decimal(1)
        and Decimal(0) <= item.caixa_sugerida.topo < item.caixa_sugerida.base <= Decimal(1)
        for item in first
    )
    assert all(
        _intersection_area(left.caixa_sugerida, right.caixa_sugerida) == 0
        for index, left in enumerate(first)
        for right in first[index + 1 :]
    )


def test_projection_uses_only_the_supplied_presentation_text() -> None:
    page = _page("friendly-text", width=Decimal("595"), height=Decimal("842"))
    geometry = GeometriaDocumento.ponto(page.id, _point("0.5", "0.5"))
    execution, evidence = _execution((page,), fact_geometries=(geometry,))
    finding = execution.achados[0]
    friendly = "Chave fusível — Poste P2. Observado: Não. Esperado: Sim."

    projected = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(page,),
        textos_apresentacao={finding.id: friendly},
    )

    assert projected[0].texto.replace("\n", " ") == friendly
    assert finding.mensagem not in projected[0].texto


@pytest.mark.parametrize("count", (2, 5, 10))
def test_dense_page_has_no_overlaps_stays_contained_and_is_repeatable(count: int) -> None:
    page = _page("dense", width=Decimal("595"), height=Decimal("842"))
    geometries = tuple(
        GeometriaDocumento.ponto(
            page.id,
            PontoNormalizado(
                Decimal("0.46") + Decimal(index % 2) * Decimal("0.08"),
                Decimal("0.44") + Decimal(index // 2) * Decimal("0.025"),
            ),
        )
        for index in range(count)
    )
    execution, evidence = _execution((page,), fact_geometries=geometries)
    presentation = {
        item.id: (f"Divergência {index}: valor observado incompatível com o requisito sintético.")
        for index, item in enumerate(execution.achados)
    }

    first = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(page,),
        textos_apresentacao=presentation,
    )
    repeated = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(page,),
        textos_apresentacao=presentation,
    )

    assert first == repeated
    assert len(first) == count
    _assert_valid_layout(first)
    assert all(item.tamanho_fonte_pontos >= Decimal("9") for item in first)


def test_dense_long_text_uses_predefined_smaller_geometry_without_clipping() -> None:
    page = _page("dense-long", width=Decimal("595"), height=Decimal("842"))
    anchor = GeometriaDocumento.ponto(page.id, _point("0.50", "0.50"))
    execution, evidence = _execution(
        (page,),
        fact_geometries=tuple(anchor for _index in range(10)),
    )
    presentation = {
        item.id: f"Divergência {index}: " + "texto sintético longo " * 14
        for index, item in enumerate(execution.achados)
    }

    projected = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(page,),
        textos_apresentacao=presentation,
    )

    _assert_valid_layout(projected)
    assert all(item.tamanho_fonte_pontos < Decimal("10.5") for item in projected)
    for item in projected:
        box_height = item.caixa_sugerida.altura * page.altura_pontos
        required_height = max(
            Decimal("36"),
            Decimal("18")
            + Decimal(len(item.texto.splitlines())) * item.tamanho_fonte_pontos * Decimal("1.28"),
        )
        assert box_height + Decimal("0.001") >= required_height


@pytest.mark.parametrize(
    ("width", "height"),
    (
        (Decimal("595"), Decimal("842")),
        (Decimal("842"), Decimal("595")),
        (Decimal("842"), Decimal("1191")),
        (Decimal("1191"), Decimal("842")),
    ),
)
def test_a4_a3_portrait_landscape_support_edges_long_text_and_occupied_areas(
    width: Decimal,
    height: Decimal,
) -> None:
    page = _page(f"formats-{width}-{height}", width=width, height=height)
    points = (
        _point("0.015", "0.50"),
        _point("0.985", "0.50"),
        _point("0.50", "0.015"),
        _point("0.50", "0.985"),
    )
    geometries = tuple(GeometriaDocumento.ponto(page.id, point) for point in points)
    occupied = tuple(
        GeometriaDocumento.caixa(
            page.id,
            PontoNormalizado(
                max(Decimal(0), point.x - Decimal("0.04")),
                max(Decimal(0), point.y - Decimal("0.025")),
            ),
            PontoNormalizado(
                min(Decimal(1), point.x + Decimal("0.04")),
                min(Decimal(1), point.y + Decimal("0.025")),
            ),
        )
        for point in points
    )
    execution, evidence = _execution(
        (page,),
        fact_geometries=geometries,
        evidence_geometries=occupied,
    )
    presentation = {
        item.id: (
            "Texto curto."
            if index % 2 == 0
            else "Texto longo de divergência que precisa permanecer totalmente legível na caixa. "
            * 3
        )
        for index, item in enumerate(execution.achados)
    }

    projected = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(page,),
        textos_apresentacao=presentation,
    )

    assert len(projected) == 4
    _assert_valid_layout(projected)
    assert {item.ancoras[0].ponto for item in projected} == set(points)


def test_projection_orders_findings_spatially_instead_of_by_uuid_or_input_order() -> None:
    page = _page("spatial-order", width=Decimal("595"), height=Decimal("842"))
    points = (_point("0.80", "0.80"), _point("0.70", "0.20"), _point("0.20", "0.20"))
    execution, evidence = _execution(
        (page,),
        fact_geometries=tuple(GeometriaDocumento.ponto(page.id, point) for point in points),
    )
    reversed_execution = replace(
        execution,
        fatos=tuple(reversed(execution.fatos)),
        achados=tuple(reversed(execution.achados)),
    )

    first = projetar_callouts_conformidade(execution, evidencias=evidence, paginas=(page,))
    repeated = projetar_callouts_conformidade(
        reversed_execution,
        evidencias=evidence,
        paginas=(page,),
    )

    assert first == repeated
    assert tuple(item.ancoras[0].ponto for item in first) == (
        _point("0.20", "0.20"),
        _point("0.70", "0.20"),
        _point("0.80", "0.80"),
    )


def test_point_target_p2_is_the_only_traceable_location_and_receives_arrow() -> None:
    page = _page("p2", width=Decimal("595"), height=Decimal("842"))
    p2 = GeometriaDocumento.ponto(page.id, _point("0.73", "0.41"))
    execution, evidence = _execution(
        (page,),
        fact_geometries=(None,),
        target_geometry=p2,
    )
    execution = replace(
        execution,
        alvos=(replace(execution.alvos[0], rotulo="P2"),),
    )

    projected = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(page,),
    )

    assert len(projected) == 1
    assert projected[0].pagina_id == page.id
    assert projected[0].ancoras[0].origem is OrigemAncoraCallout.ALVO
    assert projected[0].ancoras[0].ponto == p2.pontos[0]
    assert ponto_conexao_callout(projected[0].caixa_sugerida, p2.pontos[0]) != p2.pontos[0]


def test_named_point_target_uses_p2_region_instead_of_auxiliary_fact_geometry() -> None:
    page = _page("p2-region", width=Decimal("595"), height=Decimal("842"))
    auxiliary_symbol = GeometriaDocumento.ponto(page.id, _point("0.15", "0.20"))
    p2_region = GeometriaDocumento.caixa(
        page.id,
        _point("0.64", "0.36"),
        _point("0.76", "0.48"),
    )
    execution, evidence = _execution(
        (page,),
        fact_geometries=(auxiliary_symbol,),
        target_geometry=p2_region,
    )
    execution = replace(
        execution,
        alvos=(replace(execution.alvos[0], rotulo="P2"),),
    )

    projected = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(page,),
    )

    assert projected[0].ancoras[0].origem is OrigemAncoraCallout.ALVO
    assert projected[0].ancoras[0].geometria == p2_region
    assert projected[0].ancoras[0].ponto == _point("0.70", "0.42")


def test_specific_decisive_point_is_not_hidden_by_broad_decisive_region() -> None:
    page = _page("specific-point", width=Decimal("595"), height=Decimal("842"))
    broad = GeometriaDocumento.caixa(
        page.id,
        _point("0.10", "0.10"),
        _point("0.90", "0.90"),
    )
    p2 = GeometriaDocumento.ponto(page.id, _point("0.25", "0.35"))
    execution, evidence = _execution((page,), fact_geometries=(broad, p2))
    finding = replace(
        execution.achados[0],
        fato_ids=tuple(item.id for item in execution.fatos),
        avaliacoes_condicoes=(
            replace(
                execution.achados[0].avaliacoes_condicoes[0],
                fato_ids=tuple(item.id for item in execution.fatos),
            ),
        ),
    )
    execution = replace(execution, achados=(finding,))

    projected = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(page,),
    )

    assert tuple(item.ponto for item in projected[0].ancoras) == (p2.pontos[0],)


def test_projection_prioritizes_decisive_facts_and_keeps_only_the_selected_page() -> None:
    first_page = _page("primeira", width=Decimal("595"), height=Decimal("842"))
    second_page = _page("segunda", width=Decimal("842"), height=Decimal("595"), number=2)
    first_geometry = GeometriaDocumento.ponto(first_page.id, _point("0.25", "0.30"))
    second_anchor = GeometriaDocumento.ponto(first_page.id, _point("0.30", "0.35"))
    other_page = GeometriaDocumento.ponto(second_page.id, _point("0.70", "0.70"))
    target_geometry = GeometriaDocumento.ponto(second_page.id, _point("0.90", "0.90"))
    execution, evidence = _execution(
        (first_page, second_page),
        fact_geometries=(first_geometry, second_anchor, other_page),
        target_geometry=target_geometry,
    )
    combined_finding = replace(
        execution.achados[0],
        fato_ids=tuple(item.id for item in execution.fatos),
        avaliacoes_condicoes=(
            replace(
                execution.achados[0].avaliacoes_condicoes[0],
                fato_ids=tuple(item.id for item in execution.fatos),
            ),
        ),
    )
    execution = replace(execution, achados=(combined_finding,))

    projected = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(first_page, second_page),
    )

    assert len(projected) == 1
    assert projected[0].pagina_id == first_page.id
    assert tuple(item.ponto for item in projected[0].ancoras) == (
        first_geometry.pontos[0],
        second_anchor.pontos[0],
    )
    assert all(item.origem is OrigemAncoraCallout.FATO for item in projected[0].ancoras)


def test_projection_falls_back_to_referenced_evidence_then_target_and_omits_unlocated() -> None:
    page = _page("fallback", width=Decimal("842"), height=Decimal("595"))
    evidence_geometry = GeometriaDocumento.caixa(
        page.id,
        _point("0.10", "0.20"),
        _point("0.20", "0.30"),
    )
    target_geometry = GeometriaDocumento.ponto(page.id, _point("0.80", "0.70"))
    with_evidence, evidence = _execution(
        (page,),
        fact_geometries=(None,),
        evidence_geometries=(evidence_geometry,),
        target_geometry=target_geometry,
    )
    evidence_projection = projetar_callouts_conformidade(
        with_evidence,
        evidencias=evidence,
        paginas=(page,),
    )
    assert evidence_projection[0].ancoras[0].origem is OrigemAncoraCallout.EVIDENCIA
    assert evidence_projection[0].ancoras[0].ponto == _point("0.15", "0.25")

    with_target, _unused = _execution(
        (page,),
        fact_geometries=(None,),
        target_geometry=target_geometry,
    )
    target_projection = projetar_callouts_conformidade(
        with_target,
        evidencias=(),
        paginas=(page,),
    )
    assert target_projection[0].ancoras[0].origem is OrigemAncoraCallout.ALVO

    unlocated, _unused = _execution((page,), fact_geometries=(None,))
    assert projetar_callouts_conformidade(unlocated, evidencias=(), paginas=(page,)) == ()


def test_projection_ignores_context_fact_geometry_before_decisive_fact_evidence() -> None:
    context_page = _page("contexto", width=Decimal("595"), height=Decimal("842"))
    decisive_page = _page(
        "decisiva",
        width=Decimal("842"),
        height=Decimal("595"),
        number=2,
    )
    context_geometry = GeometriaDocumento.ponto(context_page.id, _point("0.20", "0.20"))
    evidence_geometry = GeometriaDocumento.ponto(decisive_page.id, _point("0.65", "0.55"))
    execution, evidence = _execution(
        (context_page, decisive_page),
        fact_geometries=(None,),
        evidence_geometries=(evidence_geometry,),
    )
    decisive_fact = execution.fatos[0]
    context_fact = replace(
        decisive_fact,
        id=_id("context-fact"),
        chave="fixture.contexto",
        geometria=context_geometry,
        evidencia_ids=(),
    )
    finding = replace(
        execution.achados[0],
        fato_ids=(context_fact.id, decisive_fact.id),
    )
    execution = replace(execution, fatos=(context_fact, decisive_fact), achados=(finding,))

    projected = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(context_page, decisive_page),
    )

    assert projected[0].pagina_id == decisive_page.id
    assert projected[0].ancoras[0].origem is OrigemAncoraCallout.EVIDENCIA


def test_connector_starts_on_box_border_for_outside_and_colliding_anchor() -> None:
    page = _page("connector", width=Decimal("595"), height=Decimal("842"))
    geometry = GeometriaDocumento.ponto(page.id, _point("0.5", "0.5"))
    execution, evidence = _execution((page,), fact_geometries=(geometry,))
    callout = projetar_callouts_conformidade(execution, evidencias=evidence, paginas=(page,))[0]

    outside = ponto_conexao_callout(callout.caixa_sugerida, callout.ancoras[0].ponto)
    assert _on_border(outside, callout.caixa_sugerida)

    center = PontoNormalizado(
        (callout.caixa_sugerida.esquerda + callout.caixa_sugerida.direita) / 2,
        (callout.caixa_sugerida.topo + callout.caixa_sugerida.base) / 2,
    )
    inside = ponto_conexao_callout(callout.caixa_sugerida, center)
    assert _on_border(inside, callout.caixa_sugerida)


def test_projection_moves_box_away_from_known_pdf_content() -> None:
    page = _page("content-aware", width=Decimal("595"), height=Decimal("842"))
    anchor = GeometriaDocumento.ponto(page.id, _point("0.5", "0.5"))
    execution, evidence = _execution((page,), fact_geometries=(anchor,))
    baseline = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(page,),
    )[0]
    blocked = baseline.caixa_sugerida
    blocking_geometry = GeometriaDocumento.caixa(
        page.id,
        PontoNormalizado(blocked.esquerda, blocked.topo),
        PontoNormalizado(blocked.direita, blocked.base),
    )
    blocking_evidence = EvidenciaDocumento(
        id=_id("blocking-content"),
        execucao_id=_id("semantic-execution"),
        pagina_id=page.id,
        tipo=TipoEvidencia.TEXTO,
        geometria=blocking_geometry,
        metodo="fixture-callout",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto="conteúdo importante da folha",
        criada_em=datetime(2026, 8, 12, 12, tzinfo=UTC),
    )

    moved = projetar_callouts_conformidade(
        execution,
        evidencias=(*evidence, blocking_evidence),
        paginas=(page,),
    )[0]

    assert moved.caixa_sugerida != blocked
    assert _intersection_area(moved.caixa_sugerida, blocked) == 0


def test_visual_layout_falls_back_without_losing_previously_localized_callouts() -> None:
    page = _page("visual-fallback", width=Decimal("595"), height=Decimal("842"))
    anchor = GeometriaDocumento.ponto(page.id, _point("0.5", "0.5"))
    execution, evidence = _execution(
        (page,),
        fact_geometries=(anchor, anchor),
    )
    baseline = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(page,),
    )
    fully_occupied = MapaOcupacaoVisual(
        pagina_id=page.id,
        largura_pixels=100,
        altura_pixels=100,
        colunas=1,
        linhas=1,
        lado_celula_pixels=100,
        celulas_ocupadas=b"\x01",
    )

    projected = projetar_callouts_conformidade(
        execution,
        evidencias=evidence,
        paginas=(page,),
        mapas_ocupacao_visual={page.id: fully_occupied},
    )

    assert projected == baseline


def test_collision_score_prefers_less_important_area_over_fewer_obstacles() -> None:
    rectangle = callout_layout._RetanguloPontos
    over_one_large_region = rectangle(0.0, 0.0, 10.0, 10.0)
    over_two_tiny_regions = rectangle(20.0, 0.0, 30.0, 10.0)
    over_target = rectangle(40.0, 0.0, 50.0, 10.0)
    target = rectangle(40.0, 0.0, 50.0, 10.0)
    important_content = (
        rectangle(0.0, 0.0, 9.0, 10.0),
        rectangle(20.0, 0.0, 21.0, 1.0),
        rectangle(29.0, 9.0, 30.0, 10.0),
    )
    occupied = (rectangle(0.0, 0.0, 10.0, 10.0),)
    candidates = (over_one_large_region, over_two_tiny_regions, over_target)

    _index, selected = min(
        enumerate(candidates),
        key=lambda pair: (
            callout_layout._collision_score(
                pair[1],
                target,
                occupied,
                important_content,
            ),
            pair[0],
        ),
    )

    assert selected is over_two_tiny_regions
    assert callout_layout._intersection_area(selected, target) == 0
    assert all(callout_layout._intersection_area(selected, item) == 0 for item in occupied)


def _execution(
    pages: tuple[PaginaDocumento, ...],
    *,
    fact_geometries: tuple[GeometriaDocumento | None, ...],
    evidence_geometries: tuple[GeometriaDocumento | None, ...] = (),
    target_geometry: GeometriaDocumento | None = None,
    message: str = "Valor observado não atende ao requisito sintético.",
) -> tuple[ExecucaoConformidade, tuple[EvidenciaDocumento, ...]]:
    project_id = _id("project")
    target_id = _id("target")
    target = AlvoConformidade(
        id=target_id,
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="Região sintética",
        pagina_id=target_geometry.pagina_id if target_geometry is not None else None,
        geometria=target_geometry,
    )
    facts: list[FatoConformidade] = []
    findings: list[AchadoConformidade] = []
    evidences: list[EvidenciaDocumento] = []
    source_execution_id = _id("semantic-execution")
    for index, geometry in enumerate(fact_geometries):
        evidence_geometry = evidence_geometries[index] if index < len(evidence_geometries) else None
        evidence_id = _id(f"evidence-{index}")
        if evidence_geometry is not None:
            evidences.append(
                EvidenciaDocumento(
                    id=evidence_id,
                    execucao_id=source_execution_id,
                    pagina_id=evidence_geometry.pagina_id,
                    tipo=TipoEvidencia.TEXTO,
                    geometria=evidence_geometry,
                    metodo="fixture-callout",
                    versao_metodo="1",
                    parametros=(),
                    conteudo_bruto="evidência rastreável",
                    criada_em=datetime(2026, 8, 12, 12, tzinfo=UTC),
                )
            )
        fact_id = _id(f"fact-{index}")
        facts.append(
            FatoConformidade(
                id=fact_id,
                alvo_id=target_id,
                chave="fixture.valor",
                valor=f"observado-{index}",
                origem="fixture sintética rastreável",
                evidencia_ids=(evidence_id,) if evidence_geometry is not None else (),
                geometria=geometry,
            )
        )
        evaluation = AvaliacaoCondicaoConformidade(
            grupo=GrupoCondicaoConformidade.REQUISITO,
            indice=0,
            chave_fato="fixture.valor",
            operador=OperadorCondicao.IGUAL,
            quantificador=QuantificadorCondicao.TODOS,
            valores_esperados=("esperado",),
            valores_observados=(f"observado-{index}",),
            fato_ids=(fact_id,),
            resultado=ResultadoCondicaoConformidade.NAO_ATENDE,
        )
        findings.append(
            AchadoConformidade(
                id=_id(f"finding-{index}"),
                regra_id=f"fixture.regra-{index}",
                alvo_id=target_id,
                resultado=ResultadoConformidade.DIVERGENCIA,
                severidade=SeveridadeConformidade.ERRO,
                titulo=f"Divergência sintética {index}",
                mensagem=message,
                fonte=FonteNormativa(
                    documento="Norma sintética",
                    revisao="1",
                    item="1.1",
                ),
                versao_regras="fixture-1",
                evidencia_ids=(evidence_id,) if evidence_geometry is not None else (),
                fato_ids=(fact_id,),
                avaliacoes_condicoes=(evaluation,),
            )
        )
    execution = ExecucaoConformidade(
        id=_id("compliance-execution"),
        projeto_id=project_id,
        execucoes_semanticas_ids=(source_execution_id,),
        revisao_regras_id=_id("revision"),
        registro_regras_id=_id("registry"),
        versao_regras="fixture-1",
        assinatura_regras="a" * 64,
        assinatura_sessao="b" * 64,
        versao_metodo="1",
        executada_em=datetime(2026, 8, 12, 12, tzinfo=UTC),
        alvos=(target,),
        fatos=tuple(facts),
        achados=tuple(findings),
        itens_documentais=(),
    )
    assert {item.geometria.pagina_id for item in facts if item.geometria is not None} <= {
        item.id for item in pages
    }
    return execution, tuple(evidences)


def _page(name: str, *, width: Decimal, height: Decimal, number: int = 1) -> PaginaDocumento:
    return PaginaDocumento(
        id=_id(f"page-{name}"),
        numero=number,
        largura_pontos=width,
        altura_pontos=height,
        rotacao_graus=0,
        media_box=CaixaPagina(Decimal(0), Decimal(0), width, height),
        crop_box=CaixaPagina(Decimal(0), Decimal(0), width, height),
    )


def _point(x: str, y: str) -> PontoNormalizado:
    return PontoNormalizado(Decimal(x), Decimal(y))


def _id(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"compliance-callout:{value}")


def _assert_valid_layout(callouts: tuple[CalloutConformidade, ...]) -> None:
    assert all(
        Decimal(0) <= item.caixa_sugerida.esquerda < item.caixa_sugerida.direita <= Decimal(1)
        and Decimal(0) <= item.caixa_sugerida.topo < item.caixa_sugerida.base <= Decimal(1)
        for item in callouts
    )
    assert all(
        _intersection_area(left.caixa_sugerida, right.caixa_sugerida) == 0
        for index, left in enumerate(callouts)
        for right in callouts[index + 1 :]
    )


def _intersection_area(left: object, right: object) -> Decimal:
    assert isinstance(left, RetanguloCallout)
    assert isinstance(right, RetanguloCallout)
    width = max(Decimal(0), min(left.direita, right.direita) - max(left.esquerda, right.esquerda))
    height = max(Decimal(0), min(left.base, right.base) - max(left.topo, right.topo))
    return width * height


def _on_border(point: PontoNormalizado, rectangle: object) -> bool:
    assert isinstance(rectangle, RetanguloCallout)
    return (
        point.x in {rectangle.esquerda, rectangle.direita}
        and rectangle.topo <= point.y <= rectangle.base
    ) or (
        point.y in {rectangle.topo, rectangle.base}
        and rectangle.esquerda <= point.x <= rectangle.direita
    )
