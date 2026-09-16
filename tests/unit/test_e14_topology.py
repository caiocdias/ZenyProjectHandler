from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from scripts.experiments.topology_audit import evaluate
from tests.factories import complete_project
from tests.interpretation_factories import text_evidence, vector_evidence

from zeny_project_handler.adapters.interpretation.span_rules import (
    _endpoint_label,
    _oriented_path,
    _SpanLabel,
    _TracePath,
)
from zeny_project_handler.application.automatic_promotion import promover_resultado_automatico
from zeny_project_handler.application.drawing_continuations import drawing_continuations
from zeny_project_handler.application.physical_spans import projetar_trechos_fisicos
from zeny_project_handler.application.physical_topology import physical_point_id, physical_span_id
from zeny_project_handler.application.spans import detectar_vaos
from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico, TipoCabo
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    ModalidadeTrecho,
    SituacaoProjeto,
    TipoGeometria,
    TipoTrechoRede,
)
from zeny_project_handler.domain.project import Cabo
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado


def cable_proposal(
    catalog: CatalogoTecnico, page: UUID, *, length: str = "36", end_x: str = "0.5"
) -> PropostaElemento:
    cable_type = catalog.itens_ativos(CategoriaElemento.CABO)[0]
    return PropostaElemento(
        id=uuid4(),
        execucao_id=uuid4(),
        categoria=CategoriaElemento.CABO,
        situacao_projeto=SituacaoProjeto.EXISTENTE,
        estado_revisao=EstadoRevisao.PROPOSTA,
        codigo_observado=cable_type.codigo,
        tipo_catalogo_sugerido_id=cable_type.id,
        evidencia_ids=(uuid4(),),
        geometria=GeometriaDocumento.polilinha(
            page,
            (
                PontoNormalizado(Decimal("0.1"), Decimal("0.2")),
                PontoNormalizado(Decimal(end_x), Decimal("0.2")),
            ),
        ),
        atributos_sugeridos=(
            ("evidencia_geometria_id", str(uuid4())),
            ("comprimento_m", Decimal(length)),
        ),
    )


@pytest.mark.parametrize("length", ["14", "36", "83", "100", "80", "57"])
def test_measured_existing_spans_survive_projection_without_classification(
    catalogo_inicial: CatalogoTecnico, length: str
) -> None:
    base = complete_project(catalogo_inicial)
    proposal = cable_proposal(catalogo_inicial, base.ordem_leitura_paginas[0], length=length)
    result = promover_resultado_automatico(
        replace(
            base,
            elementos=(),
            pontos_rede=(),
            relacoes_confirmadas=(),
            terminais=(),
            conexoes_internas=(),
            vinculos_obra=(),
            historico_revisao_manual=(),
        ),
        catalogo_inicial,
        (proposal,),
        (),
        promovido_em=datetime.now(UTC),
    )
    span = detectar_vaos(result.projeto)[0]
    assert span.comprimento_m == Decimal(length)
    assert span.tipo_trecho is TipoTrechoRede.DESCONHECIDO
    assert span.modalidade is ModalidadeTrecho.DESCONHECIDO
    assert span.geometria == proposal.geometria


def test_physical_group_keeps_conductors_and_pending_revision_without_promotion(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    phase = cable_proposal(catalogo_inicial, project.ordem_leitura_paginas[0])
    neutral = replace(phase, id=uuid4(), codigo_observado="N-4", tipo_catalogo_sugerido_id=None)
    projected = projetar_trechos_fisicos(project, (phase, neutral), ())
    assert len(projected) == 1
    assert set(projected[0].propostas) == {phase.id, neutral.id}
    assert not projected[0].cabos
    assert projected[0].comprimento_m == 36
    assert projected[0].tipo is TipoTrechoRede.DESCONHECIDO
    assert projected[0].pendencias
    rejected = replace(neutral, estado_revisao=EstadoRevisao.REJEITADA)
    assert projetar_trechos_fisicos(project, (rejected,), ()) == ()
    other_length = replace(
        neutral,
        atributos_sugeridos=(
            ("evidencia_geometria_id", str(uuid4())),
            ("comprimento_m", Decimal(83)),
        ),
    )
    conflict = projetar_trechos_fisicos(project, (phase, other_length), ())[0]
    assert conflict.comprimento_m is None
    assert "Comprimentos divergentes" in " ".join(conflict.pendencias)


def test_exact_topology_separates_nearby_paths_crossings_pages_and_lengths(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    a = cable_proposal(catalogo_inicial, project.ordem_leitura_paginas[0])
    g = a.geometria
    reversed_geometry = GeometriaDocumento.polilinha(g.pagina_id, tuple(reversed(g.pontos)))
    assert physical_span_id(g) == physical_span_id(reversed_geometry)
    bent = GeometriaDocumento.polilinha(
        g.pagina_id,
        (
            g.pontos[0],
            PontoNormalizado(Decimal("0.3"), Decimal("0.21")),
            g.pontos[-1],
        ),
    )
    b = replace(a, id=uuid4(), geometria=bent)
    assert len(projetar_trechos_fisicos(project, (a, b), ())) == 2
    assert physical_point_id(g.pagina_id, g.pontos[0]) != physical_point_id(uuid4(), g.pontos[0])
    nearby = PontoNormalizado(Decimal("0.100001"), Decimal("0.2"))
    assert physical_point_id(g.pagina_id, nearby) != physical_point_id(g.pagina_id, g.pontos[0])
    crossing = GeometriaDocumento.polilinha(
        g.pagina_id,
        (
            PontoNormalizado(Decimal("0.3"), Decimal("0.1")),
            PontoNormalizado(Decimal("0.3"), Decimal("0.3")),
        ),
    )
    c = replace(a, id=uuid4(), geometria=crossing)
    rows = projetar_trechos_fisicos(project, (a, c), ())
    assert {rows[0].origem_id, rows[0].destino_id}.isdisjoint(
        {rows[1].origem_id, rows[1].destino_id}
    )


def test_electrical_points_share_exact_endpoint_only_in_same_configuration(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    base = complete_project(catalogo_inicial)
    project = replace(
        base,
        elementos=(),
        pontos_rede=(),
        relacoes_confirmadas=(),
        terminais=(),
        conexoes_internas=(),
        vinculos_obra=(),
        historico_revisao_manual=(),
    )
    a = cable_proposal(catalogo_inicial, project.ordem_leitura_paginas[0])
    b = replace(
        a,
        id=uuid4(),
        geometria=GeometriaDocumento.polilinha(
            a.geometria.pagina_id,
            (
                a.geometria.pontos[-1],
                PontoNormalizado(Decimal("0.8"), Decimal("0.2")),
            ),
        ),
    )
    result = promover_resultado_automatico(
        project,
        catalogo_inicial,
        (a, b),
        (),
        promovido_em=datetime.now(UTC),
    )
    assert len(result.projeto.pontos_rede) == 3
    ca, cb = (c for c in result.projeto.elementos if isinstance(c, Cabo))
    assert ca.ponto_destino_id == cb.ponto_origem_id
    again = promover_resultado_automatico(
        result.projeto,
        catalogo_inicial,
        (a, b),
        (),
        promovido_em=datetime.now(UTC),
    )
    assert again.projeto == result.projeto
    assert a.tipo_catalogo_sugerido_id is not None
    first_type = catalogo_inicial.item_por_id(a.tipo_catalogo_sugerido_id)
    assert isinstance(first_type, TipoCabo)
    other_type = next(
        t
        for t in catalogo_inicial.itens_ativos(CategoriaElemento.CABO)
        if isinstance(t, TipoCabo) and t.nivel_tensao_opcao_id != first_type.nivel_tensao_opcao_id
    )
    different = replace(b, id=uuid4(), tipo_catalogo_sugerido_id=other_type.id)
    separate = promover_resultado_automatico(
        project,
        catalogo_inicial,
        (a, different),
        (),
        promovido_em=datetime.now(UTC),
    )
    assert len(separate.projeto.pontos_rede) == 4


def test_explicit_point_labels_orient_reversed_trace_and_abstain_on_ties() -> None:
    page, execution = uuid4(), uuid4()
    p3 = text_evidence(execution_id=execution, page_id=page, key="p3", text="P3", x="0.2", y="0.2")
    p4 = text_evidence(execution_id=execution, page_id=page, key="p4", text="P4", x="0.5", y="0.2")
    geometry = GeometriaDocumento.polilinha(page, (p4.geometria.pontos[0], p3.geometria.pontos[0]))
    path = _TracePath(p3, geometry, (None, None))
    oriented, _ = _oriented_path(path, _SpanLabel("V3-4", p3), (p3, p4))
    assert oriented.pontos[0] == p3.geometria.pontos[0]
    assert oriented.pontos[-1] == p4.geometria.pontos[0]
    ambiguous = replace(p3, id=uuid4(), conteudo_bruto="P9")
    assert _endpoint_label(p3.geometria.pontos[0], page, (p3, ambiguous)) is None


def test_human_adjusted_measurement_overrides_original_proposal(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    base = complete_project(catalogo_inicial)
    project = replace(
        base,
        elementos=(),
        pontos_rede=(),
        relacoes_confirmadas=(),
        terminais=(),
        conexoes_internas=(),
        vinculos_obra=(),
        historico_revisao_manual=(),
    )
    a = cable_proposal(catalogo_inicial, project.ordem_leitura_paginas[0])
    result = promover_resultado_automatico(
        project,
        catalogo_inicial,
        (a,),
        (),
        promovido_em=datetime.now(UTC),
    )
    adjusted = replace(
        result.projeto,
        elementos=tuple(
            replace(c, comprimento_m=Decimal(42), situacao=SituacaoProjeto.ALTERAR)
            if isinstance(c, Cabo)
            else c
            for c in result.projeto.elementos
        ),
    )
    row = projetar_trechos_fisicos(adjusted, result.elementos, result.decisoes)[0]
    assert row.comprimento_m == 42
    assert row.situacoes == (SituacaoProjeto.ALTERAR,)


def continuation_case(
    catalog: CatalogoTecnico,
) -> tuple[tuple[EvidenciaDocumento, ...], PropostaElemento]:
    page, execution = uuid4(), uuid4()
    seed = vector_evidence(
        execution_id=execution, page_id=page, key="seed", points=(("0.3", "0.3"), ("0.5", "0.5"))
    )
    attrs = (
        ("cor_contorno", "#333333"),
        ("espessura", Decimal("0.4")),
        ("tracejado", "[] 0"),
        ("tipo_caminho", "s"),
    )
    seed = replace(seed, atributos_extraidos=attrs)
    continuation = replace(
        seed,
        id=uuid4(),
        geometria=GeometriaDocumento.polilinha(
            page,
            (
                PontoNormalizado(Decimal("0.5"), Decimal("0.5")),
                PontoNormalizado(Decimal("0.9"), Decimal("0.9")),
            ),
        ),
    )
    frame = replace(
        seed,
        id=uuid4(),
        geometria=GeometriaDocumento.caixa(
            page,
            PontoNormalizado(Decimal("0.05"), Decimal("0.05")),
            PontoNormalizado(Decimal("0.95"), Decimal("0.9")),
        ),
        atributos_extraidos=(("cor_preenchimento", "#FFFFFF"), ("operacoes", "re")),
    )
    proposal = replace(
        cable_proposal(catalog, page),
        geometria=seed.geometria,
        atributos_sugeridos=(("evidencia_geometria_id", str(seed.id)),),
    )
    return (seed, continuation, frame), proposal


@pytest.mark.parametrize(
    "invalid",
    [None, "no_frame", "near_anchor", "inside", "dashed", "crossing", "rejected", "other_page"],
)
def test_continuations_require_exact_anchor_style_and_explicit_drawing_window(
    catalogo_inicial: CatalogoTecnico,
    invalid: str | None,
) -> None:
    (seed, continuation, frame), proposal = continuation_case(catalogo_inicial)
    if invalid == "near_anchor":
        continuation = replace(
            continuation,
            geometria=GeometriaDocumento.polilinha(
                seed.pagina_id,
                (
                    PontoNormalizado(Decimal("0.50001"), Decimal("0.5")),
                    continuation.geometria.pontos[-1],
                ),
            ),
        )
    if invalid == "inside":
        continuation = replace(
            continuation,
            geometria=GeometriaDocumento.polilinha(
                seed.pagina_id,
                (
                    continuation.geometria.pontos[0],
                    PontoNormalizado(Decimal("0.89"), Decimal("0.89")),
                ),
            ),
        )
    if invalid == "dashed":
        continuation = replace(
            continuation,
            atributos_extraidos=(
                *((k, v) for k, v in continuation.atributos_extraidos if k != "tracejado"),
                ("tracejado", "[3 3] 0"),
            ),
        )
    if invalid == "crossing":
        continuation = replace(
            continuation,
            geometria=GeometriaDocumento.polilinha(
                seed.pagina_id,
                (
                    continuation.geometria.pontos[0],
                    PontoNormalizado(Decimal("0.05"), Decimal("0.6")),
                ),
            ),
        )
    if invalid == "rejected":
        proposal = replace(proposal, estado_revisao=EstadoRevisao.REJEITADA)
    if invalid == "other_page":
        other_page = uuid4()
        frame = replace(
            frame, pagina_id=other_page, geometria=replace(frame.geometria, pagina_id=other_page)
        )
    evidence = (seed, continuation) if invalid == "no_frame" else (seed, continuation, frame)
    result = drawing_continuations(evidence, (proposal,))
    assert len(result) == (1 if invalid is None else 0)
    if result:
        physical = projetar_trechos_fisicos(
            complete_project(catalogo_inicial), (proposal,), (), evidence
        )
        cut = next(p for p in physical if p.continuidade)
        assert cut.destino_id is None and cut.comprimento_m is None
        assert not cut.cabos and not cut.propostas and cut.evidencias


def test_clipped_label_remains_pending_and_ambiguous_boundary_paths_abstain(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    (seed, continuation, frame), proposal = continuation_case(catalogo_inicial)
    label = replace(
        proposal,
        geometria=GeometriaDocumento(
            pagina_id=seed.pagina_id,
            tipo=TipoGeometria.POLIGONO,
            pontos=(
                PontoNormalizado(Decimal("0.89"), Decimal("0.89")),
                PontoNormalizado(Decimal("0.91"), Decimal("0.91")),
                PontoNormalizado(Decimal("0.909"), Decimal("0.911")),
                PontoNormalizado(Decimal("0.889"), Decimal("0.891")),
            ),
        ),
        atributos_sugeridos=(("associacao_pendente", "tracado"),),
    )
    result = drawing_continuations((continuation, frame), (label,))
    assert len(result) == 1
    duplicate = replace(continuation, id=uuid4())
    assert drawing_continuations((continuation, duplicate, frame), (label,)) == ()
    assert drawing_continuations((continuation, frame), ()) == ()


def test_topology_evaluator_requires_explicit_continuity_and_unsplit_identity() -> None:
    inventory = {
        "items": [
            {"kind": "point", "site": "P1", "center": [0.1, 0.1]},
            {"kind": "point", "site": "P2", "center": [0.5, 0.5]},
            {"id": "v", "kind": "span", "endpoints": ["P1", "P2"], "length": 36},
            {"id": "cut", "kind": "span", "endpoints": ["P2", None], "length": None},
        ]
    }
    first = {
        "id": "a",
        "xy": [[0.1, 0.1], [0.5, 0.5]],
        "nodes": ["n1", "n2"],
        "labels": ["P1", "P2"],
        "length": 36,
    }
    second = {
        "id": "b",
        "xy": [[0.5, 0.5], [0.9, 0.9]],
        "nodes": ["n2", None],
        "labels": ["P2", None],
        "length": None,
        "continuation": True,
    }
    result = evaluate(inventory, [first, second])
    assert result["exact_pairs"] == 1 and result["explicit_continuities"] == 1
    assert result["consistent_physical_points"] == 2
    assert (
        evaluate(inventory, [first, {**second, "continuation": False}])["explicit_continuities"]
        == 0
    )
    assert (
        evaluate(inventory, [first, {**second, "nodes": ["split", None]}])[
            "consistent_physical_points"
        ]
        == 1
    )
