from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock
from uuid import UUID, uuid4, uuid5

import pytest
from scripts.benchmark_network_pdf import json_value
from scripts.experiments.compare import context_association
from tests.factories import complete_project
from tests.interpretation_factories import text_evidence

from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.interpretation.occurrence_rules import deduplicate_cable_readings
from zeny_project_handler.application.analysis_regions import agrupar_regioes_da_analise
from zeny_project_handler.application.automatic_promotion import promover_resultado_automatico
from zeny_project_handler.application.method_reconciliation import attach_method_conflicts
from zeny_project_handler.application.technical_revisions import (
    append_revision_operations,
    preserve_revision_decision,
)
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao, SituacaoProjeto
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.interpretation import SolicitacaoInterpretacao


def _box(page: UUID, x: str, y: str, width: str = "0.02") -> GeometriaDocumento:
    return GeometriaDocumento.caixa(
        page,
        PontoNormalizado(Decimal(x), Decimal(y)),
        PontoNormalizado(Decimal(x) + Decimal(width), Decimal(y) + Decimal("0.006")),
    )


def _request(
    catalog: CatalogoTecnico, rows: tuple[tuple[str, str, str], ...]
) -> SolicitacaoInterpretacao:
    execution, page = uuid4(), uuid4()
    evidence = tuple(
        replace(
            text_evidence(
                execution_id=execution,
                page_id=page,
                key=str(i),
                text=text,
                x=x,
                y=y,
            ),
            geometria=_box(page, x, y),
        )
        for i, (text, x, y) in enumerate(rows)
    )
    return SolicitacaoInterpretacao(
        projeto_id=uuid4(),
        execucao_id=uuid4(),
        execucao_extracao_id=execution,
        catalogo=catalog,
        evidencias=evidence,
        registro=carregar_registro_regras_inicial(),
    )


@pytest.mark.parametrize("difference", ["none", "label", "trace", "situation", "page", "code"])
def test_duplicate_reading_requires_same_label_trace_code_page_and_situation(
    catalogo_inicial: CatalogoTecnico,
    difference: str,
) -> None:
    request = _request(catalogo_inicial, (("N-(1N5)", "0.3", "0.4"),))
    first = request.evidencias[0]
    second = replace(first, id=uuid4())
    if difference == "label":
        second = replace(second, geometria=_box(first.pagina_id, "0.325", "0.4"))
    if difference == "page":
        page = uuid4()
        second = replace(second, pagina_id=page, geometria=_box(page, "0.3", "0.4"))
    proposals = tuple(
        PropostaElemento(
            id=uuid4(),
            execucao_id=request.execucao_id,
            categoria=CategoriaElemento.CABO,
            estado_revisao=EstadoRevisao.PROPOSTA,
            situacao_projeto=SituacaoProjeto.INSTALAR,
            evidencia_ids=(e.id,),
            geometria=e.geometria,
            codigo_observado="N-(1N5)",
            atributos_sugeridos=(
                ("evidencia_rotulo_id", str(e.id)),
                ("evidencia_geometria_id", "shared-trace"),
                ("comprimento_m", "100"),
                ("identificador_operacional", "V2-3"),
            ),
        )
        for e in (first, second)
    )
    a, b = proposals
    if difference == "trace":
        b = replace(
            b,
            atributos_sugeridos=tuple(
                {**dict(b.atributos_sugeridos), "evidencia_geometria_id": "parallel-trace"}.items()
            ),
        )
    if difference == "situation":
        b = replace(b, situacao_projeto=SituacaoProjeto.REMOVER)
    if difference == "code":
        b = replace(b, codigo_observado="ABC-2 CAA")
    result = deduplicate_cable_readings((a, b), (first, second))
    assert len(result) == (1 if difference == "none" else 2)
    assert result == deduplicate_cable_readings((b, a), (second, first))
    if difference == "none":
        assert set(result[0].evidencia_ids) == {first.id, second.id}
        assert set(
            json.loads(str(dict(result[0].atributos_sugeridos)["leituras_consolidadas"]))
        ) == {str(a.id), str(b.id)}
        conflicted_label = uuid5(first.execucao_id, "disagreed-reading")
        source = replace(second, id=conflicted_label)
        b = replace(
            b,
            evidencia_ids=(source.id,),
            atributos_sugeridos=tuple(
                {**dict(b.atributos_sugeridos), "evidencia_rotulo_id": str(source.id)}.items()
            ),
        )
        auxiliary = replace(
            second,
            id=uuid4(),
            conteudo_bruto=None,
            atributos_extraidos=(
                (
                    "leitura_metodo",
                    json.dumps(
                        {
                            "resolution": "conflict_requires_review",
                            "alternatives": [{"evidence_key": "disagreed-reading"}],
                        }
                    ),
                ),
            ),
        )
        merged = deduplicate_cable_readings((a, b), (first, source))
        checked = attach_method_conflicts(merged, (first, source, auxiliary))
        assert len(checked) == 1
        assert dict(checked[0].atributos_sugeridos)["reconciliacao_metodos_pendente"]
        assert auxiliary.id in checked[0].evidencia_ids


def test_unnumbered_context_keeps_own_assets_and_regions_without_p5(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(
        catalogo_inicial,
        (
            ("P5", "0.6", "0.65"),
            ("11-600", "0.6", "0.67"),
            ("N2-10-300", "0.62", "0.56"),
            ("S3R", "0.62", "0.57"),
            ("100A-10kA-1H", "0.62", "0.53"),
        ),
    )
    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)
    contextual = [
        p for p in result.elementos if dict(p.atributos_sugeridos).get("contexto_ponto_id")
    ]
    assert {p.categoria for p in contextual} == {
        CategoriaElemento.POSTE,
        CategoriaElemento.ESTRUTURA_MT,
        CategoriaElemento.ESTRUTURA_BT,
        CategoriaElemento.EQUIPAMENTO,
    }
    assert all("identificador_operacional" not in dict(p.atributos_sugeridos) for p in contextual)
    context_ids = {p.id for p in contextual}
    assert all(
        r.destino_referencia_id in context_ids
        for r in result.relacoes
        if r.origem_referencia_id in context_ids
    )
    regions = agrupar_regioes_da_analise(
        (*result.elementos, *result.relacoes), request.evidencias, ()
    )
    local = [r for r in regions if context_ids.intersection(r.elemento_ids)]
    assert len(local) == 1 and local[0].rotulo_ponto is None
    assert set(local[0].elemento_ids) == context_ids


def test_repeated_n3_tokens_and_close_disjoint_physical_labels_survive(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(
        catalogo_inicial,
        (
            ("P1", "0.3", "0.3"),
            ("N3(1)N3(1)", "0.3", "0.32"),
            ("N3(1)", "0.3", "0.32"),
            ("N3(1)", "0.321", "0.32"),
        ),
    )
    evidence = list(request.evidencias)
    evidence[1] = replace(
        evidence[1], geometria=_box(evidence[1].pagina_id, "0.3", "0.32", "0.042")
    )
    result = InterpretadorRegrasExplicitas(request.registro).interpretar(
        replace(request, evidencias=tuple(evidence))
    )
    assert len(result.elementos) == 2
    assert all(
        dict(p.atributos_sugeridos)["qualificador_estrutura"] == "1" for p in result.elementos
    )
    assert result.elementos[0].geometria != result.elementos[1].geometria


@pytest.mark.parametrize("literal", ["TR-3-45", "TR-1-25", "N-4"])
def test_uncataloged_literal_is_represented_without_inventing_model(
    catalogo_inicial: CatalogoTecnico,
    literal: str,
) -> None:
    request = _request(catalogo_inicial, (("P2", "0.3", "0.3"), (literal, "0.3", "0.32")))
    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)
    assert len(result.elementos) == 1
    p = result.elementos[0]
    assert p.codigo_observado == literal and p.tipo_catalogo_sugerido_id is None
    assert dict(p.atributos_sugeridos)["catalogo_nao_localizado"]
    assert request.evidencias[1].id in p.evidencia_ids
    if literal.startswith("TR"):
        assert dict(p.atributos_sugeridos)["capacidade_observada_kva"] == int(
            literal.split("-")[-1]
        )


@pytest.mark.parametrize("literal", ["XTR-3-45", "TR-3-45X", "TR-3-", "N-4/", "N-40X"])
def test_incomplete_or_embedded_literal_is_not_completed(
    catalogo_inicial: CatalogoTecnico, literal: str
) -> None:
    request = _request(catalogo_inicial, (("P2", "0.3", "0.3"), (literal, "0.3", "0.32")))
    assert not InterpretadorRegrasExplicitas(request.registro).interpretar(request).elementos


def _revision_proposal(catalog: CatalogoTecnico) -> PropostaElemento:
    request = _request(catalog, (("P1", "0.3", "0.3"), ("N4(1)", "0.3", "0.32")))
    proposal = InterpretadorRegrasExplicitas(request.registro).interpretar(request).elementos[0]
    data = {
        "group_id": "synthetic-revision",
        "base_code": "N4",
        "decision": None,
        "operation_review_pending": True,
        "color_readings": [
            {
                "text": "N4(1)",
                "color": color,
                "horizontal_strike": strike,
                "box": [0.3, y, 0.32, y + 0.006],
                "annotation_xref": 7,
            }
            for color, strike, y in (("verde", False, 0.33), ("vermelho", True, 0.32))
        ],
    }
    return replace(
        proposal,
        estado_revisao=EstadoRevisao.CONFLITANTE,
        atributos_sugeridos=(
            *proposal.atributos_sugeridos,
            ("revisao_tecnica_pendente", True),
            ("revisao_tecnica", json.dumps(data)),
        ),
    )


def test_revision_operations_are_distinct_reviewable_and_never_auto_promoted(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    base = _revision_proposal(catalogo_inicial)
    proposals = append_revision_operations((base,))
    assert len(proposals) == 3 and len({p.id for p in proposals}) == 3
    assert {p.situacao_projeto for p in proposals} == {
        SituacaoProjeto.EXISTENTE,
        SituacaoProjeto.INSTALAR,
        SituacaoProjeto.REMOVER,
    }
    assert proposals == append_revision_operations((base,))
    assert proposals == append_revision_operations(proposals)
    project = complete_project(catalogo_inicial)
    promotion = promover_resultado_automatico(
        project, catalogo_inicial, proposals, (), promovido_em=datetime.now(UTC)
    )
    assert promotion.projeto == project and not promotion.decisoes
    installed, removed = proposals[1:]
    data = json.loads(str(dict(installed.atributos_sugeridos)["revisao_tecnica"]))
    data["decision"] = "visible"
    installed = replace(
        installed,
        atributos_sugeridos=tuple(
            {**dict(installed.atributos_sugeridos), "revisao_tecnica": json.dumps(data)}.items()
        ),
    )
    work = Mock()
    work.decisoes_revisao.obter_da_proposta.return_value = None
    assert preserve_revision_decision(work, removed, (installed,)) == removed
    assert preserve_revision_decision(work, base, (installed,)) == base
    assert dict(preserve_revision_decision(work, proposals[1], (installed,)).atributos_sugeridos)[
        "revisao_tecnica_decidida"
    ]


def test_context_comparison_requires_matching_source(catalogo_inicial: CatalogoTecnico) -> None:
    request = _request(catalogo_inicial, (("N2-10-300", "0.6", "0.5"), ("S3R", "0.6", "0.51")))
    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)
    proposals = json.loads(json.dumps(result.elementos, default=json_value))
    evidence = {
        str(e.id): json.loads(json.dumps(e, default=json_value)) for e in request.evidencias
    }
    pole = next(p for p in proposals if p["categoria"] == "POSTE")
    bt = next(p for p in proposals if p["categoria"] == "ESTRUTURA_BT")
    reference = {"kind": "bt", "site": "unnumbered"}
    refs = [
        {
            "kind": "pole",
            "site": "unnumbered",
            "center": [0.61, 0.503],
            "code": "10-300",
            "situation": "EXISTENTE",
        }
    ]
    assert context_association(reference, bt, proposals, evidence, refs)
    assert not context_association(
        reference, {**bt, "evidencia_ids": []}, proposals, evidence, refs
    )
    assert not context_association(reference, bt, [bt], evidence, refs)
    pole["atributos_sugeridos"] = [["contexto_ponto_id", "another-source"]]
    assert not context_association(reference, bt, proposals, evidence, refs)


def test_revision_preserves_disjoint_operations_and_qualifier_conflicts(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    base = _revision_proposal(catalogo_inicial)
    attrs = dict(base.atributos_sugeridos)
    data = json.loads(str(attrs["revisao_tecnica"]))
    original = data["color_readings"][0]
    data["color_readings"].extend(
        [
            dict(original),
            {**original, "box": [0.4, 0.33, 0.42, 0.336]},
            {**original, "text": "N4(2)"},
        ]
    )
    attrs["revisao_tecnica"] = json.dumps(data)
    result = append_revision_operations((replace(base, atributos_sugeridos=tuple(attrs.items())),))
    installed = [p for p in result if p.situacao_projeto is SituacaoProjeto.INSTALAR]
    assert len(installed) == 3 and len({p.id for p in installed}) == 3
    assert {dict(p.atributos_sugeridos)["qualificador_estrutura"] for p in installed} == {"1", "2"}
    assert all(dict(p.atributos_sugeridos)["revisao_tecnica_pendente"] for p in installed)
