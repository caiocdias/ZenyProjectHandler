from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from zeny_project_handler.application.compliance_callouts import (
    OrigemAncoraCallout,
    ponto_conexao_callout,
    projetar_callouts_conformidade,
)
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
    execution, evidence = _execution(
        (page,),
        fact_geometries=(anchor, anchor, anchor),
        message=("Mensagem sintética longa " * 12).strip(),
    )

    first = projetar_callouts_conformidade(execution, evidencias=evidence, paginas=(page,))
    repeated = projetar_callouts_conformidade(execution, evidencias=evidence, paginas=(page,))

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


def _intersection_area(left: object, right: object) -> Decimal:
    from zeny_project_handler.application.compliance_callouts import RetanguloCallout

    assert isinstance(left, RetanguloCallout)
    assert isinstance(right, RetanguloCallout)
    width = max(Decimal(0), min(left.direita, right.direita) - max(left.esquerda, right.esquerda))
    height = max(Decimal(0), min(left.base, right.base) - max(left.topo, right.topo))
    return width * height


def _on_border(point: PontoNormalizado, rectangle: object) -> bool:
    from zeny_project_handler.application.compliance_callouts import RetanguloCallout

    assert isinstance(rectangle, RetanguloCallout)
    return (
        point.x in {rectangle.esquerda, rectangle.direita}
        and rectangle.topo <= point.y <= rectangle.base
    ) or (
        point.y in {rectangle.topo, rectangle.base}
        and rectangle.esquerda <= point.x <= rectangle.direita
    )
