"""Oráculos da política E13 por campo, sem usar score bruto como autoridade."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from scripts.reconcile_symbol_benchmark import _observation as benchmark_observation
from scripts.reconcile_symbol_benchmark import _profile as benchmark_profile
from tests.factories import complete_project
from tests.unit.test_topology_compliance import _facts_by_key, _fixture

from zeny_project_handler.application.automatic_promotion import promover_resultado_automatico
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao, SituacaoProjeto
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado


def _proposal(catalog: CatalogoTecnico, project: Projeto) -> PropostaElemento:
    page = project.documentos[0].paginas[0].id
    catalog_item = catalog.itens_ativos(CategoriaElemento.POSTE)[0]
    return PropostaElemento(
        id=uuid4(),
        execucao_id=uuid4(),
        categoria=CategoriaElemento.POSTE,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(uuid4(),),
        geometria=GeometriaDocumento.ponto(page, PontoNormalizado(Decimal("0.8"), Decimal("0.8"))),
        tipo_catalogo_sugerido_id=catalog_item.id,
        codigo_observado=catalog_item.codigo,
        atributos_sugeridos=(
            ("origem_simbolo_ocorrencia_id", "e13-unique-observation"),
            ("simbolo_decisao_e12", "eligible"),
            ("simbolo_ativo_elegivel", True),
            ("simbolo_classe", "POSTE"),
            ("simbolo_identidade_resolvida", True),
            ("simbolo_classe_resolvida", True),
            ("simbolo_situacao_resolvida", True),
            ("simbolo_quantidade_resolvida", True),
            ("simbolo_associacao_resolvida", True),
            ("simbolo_catalogo_resolvido", True),
            ("simbolo_probabilidade_calibrada", Decimal("0.995")),
            ("situacao_validada", True),
            ("quantidade_ativos", 1),
        ),
        confianca=Decimal("0.20"),
    )


def _promote(project: Projeto, catalog: CatalogoTecnico, proposal: PropostaElemento) -> bool:
    result = promover_resultado_automatico(
        project,
        catalog,
        (proposal,),
        (),
        promovido_em=datetime(2026, 9, 24, 12, tzinfo=UTC),
    )
    if result.decisoes:
        assert len(result.decisoes) == 1
        assert result.elementos[0].estado_revisao is EstadoRevisao.CONFIRMADA
        assert len(result.projeto.elementos) == len(project.elementos) + 1
        return True
    assert result.projeto == project
    assert result.elementos == (proposal,)
    return False


def test_exclusive_calibrated_symbol_can_promote_without_second_detector(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    # The proposal carries one E12 occurrence and a low raw score. Promotion
    # uses calibrated eligibility and resolved semantic fields, not a quorum.
    project = complete_project(catalogo_inicial)
    assert _promote(project, catalogo_inicial, _proposal(catalogo_inicial, project))


@pytest.mark.parametrize(
    "unresolved_field",
    (
        "simbolo_identidade_resolvida",
        "simbolo_classe_resolvida",
        "simbolo_situacao_resolvida",
        "simbolo_quantidade_resolvida",
        "simbolo_associacao_resolvida",
        "simbolo_catalogo_resolvido",
    ),
)
def test_catalog_cannot_complete_an_unresolved_symbol_field(
    catalogo_inicial: CatalogoTecnico, unresolved_field: str
) -> None:
    project = complete_project(catalogo_inicial)
    proposal = _proposal(catalogo_inicial, project)
    attrs = dict(proposal.atributos_sugeridos)
    attrs[unresolved_field] = False
    proposal = replace(proposal, atributos_sugeridos=tuple(attrs.items()))
    assert not _promote(project, catalogo_inicial, proposal)


@pytest.mark.parametrize(
    "pending_field",
    (
        "situacao_pendente",
        "quantidade_pendente",
        "associacao_pendente",
        "catalogo_nao_localizado",
    ),
)
def test_explicit_pending_field_blocks_automatic_promotion(
    catalogo_inicial: CatalogoTecnico, pending_field: str
) -> None:
    project = complete_project(catalogo_inicial)
    proposal = _proposal(catalogo_inicial, project)
    attrs = dict(proposal.atributos_sugeridos)
    attrs[pending_field] = True
    proposal = replace(proposal, atributos_sugeridos=tuple(attrs.items()))
    assert not _promote(project, catalogo_inicial, proposal)


@pytest.mark.parametrize("decision", ("review", "not-a-decision"))
def test_detector_agreement_or_raw_confidence_cannot_replace_e12_decision(
    catalogo_inicial: CatalogoTecnico, decision: str
) -> None:
    project = complete_project(catalogo_inicial)
    proposal = _proposal(catalogo_inicial, project)
    attrs = dict(proposal.atributos_sugeridos)
    attrs["simbolo_decisao_e12"] = decision
    attrs["simbolo_observacao_ids"] = '["detector-a", "detector-b"]'
    proposal = replace(proposal, atributos_sugeridos=tuple(attrs.items()), confianca=Decimal(1))
    assert not _promote(project, catalogo_inicial, proposal)


def test_unresolved_reference_identity_and_conflict_never_promote(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    proposal = _proposal(catalogo_inicial, project)
    attrs = dict(proposal.atributos_sugeridos)
    attrs["simbolo_reference_ids"] = '["id-a", "id-b"]'
    attrs["simbolo_identidade_resolvida"] = False
    assert not _promote(
        project, catalogo_inicial, replace(proposal, atributos_sugeridos=tuple(attrs.items()))
    )
    assert not _promote(
        project, catalogo_inicial, replace(proposal, estado_revisao=EstadoRevisao.CONFLITANTE)
    )


def test_informative_or_guy_envelope_cannot_become_cataloged_equipment(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    proposal = _proposal(catalogo_inicial, project)
    attrs = dict(proposal.atributos_sugeridos)
    attrs["simbolo_ativo_elegivel"] = False
    attrs["simbolo_papel"] = "suporte"
    assert not _promote(
        project, catalogo_inicial, replace(proposal, atributos_sugeridos=tuple(attrs.items()))
    )


def test_uncataloged_known_class_remains_a_proposal(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    proposal = _proposal(catalogo_inicial, project)
    uncataloged = replace(proposal, tipo_catalogo_sugerido_id=None)
    assert not _promote(project, catalogo_inicial, uncataloged)


def test_pending_symbol_cannot_create_positive_topology_presence() -> None:
    fixture = _fixture(compatible=True)
    grounding = next(
        item
        for item in fixture.session.propostas
        if isinstance(item, PropostaElemento)
        and dict(item.atributos_sugeridos).get("classe_equipamento") == "ATERRAMENTO"
    )
    pending = replace(
        grounding,
        atributos_sugeridos=(
            ("origem_simbolo_ocorrencia_id", "unresolved-grounding"),
            ("simbolo_classe", "ATERRAMENTO"),
            ("simbolo_decisao_e12", "review"),
            ("simbolo_ativo_elegivel", False),
            ("simbolo_classe_resolvida", False),
            ("classe_equipamento", "ATERRAMENTO"),
            ("reconhecido_por_simbologia", True),
        ),
    )
    fixture = replace(
        fixture,
        session=replace(
            fixture.session,
            propostas=tuple(
                pending if item.id == grounding.id else item for item in fixture.session.propostas
            ),
        ),
    )
    facts = _facts_by_key(fixture)
    assert facts.get("regiao.aterramento_presente") is not True


@pytest.mark.parametrize("situation", ("INSTALAR", "REMOVER"))
def test_benchmark_adapter_preserves_visual_situation_without_validating_convention(
    situation: str,
) -> None:
    profile = benchmark_profile(
        {
            "id": "visual-fixture",
            "version": "1",
            "algorithm_family": "vector",
            "supported_classes": ["TRANSFORMADOR"],
            "supported_layers": ["base"],
            "shared_sources": ["independent-vector"],
        }
    )
    observation = benchmark_observation(
        {
            "id": f"visual-{situation}",
            "document_id": "source.pdf",
            "page": 1,
            "layer": "base",
            "class_id": "TRANSFORMADOR",
            "bbox": [0.1, 0.1, 0.2, 0.2],
            "score": 0.2,
            "situation": situation,
            "provenance": {"legacy_color": "#008000" if situation == "INSTALAR" else "#800000"},
        },
        profile,
        {"source.pdf": "a" * 64},
    )
    attributes = dict(observation.atributos)
    assert observation.situacao is SituacaoProjeto(situation)
    assert attributes["situacao_origem"] == "predicao_benchmark_sem_vigencia_validada"
    assert attributes["cor"] in {"#008000", "#800000"}
    assert "situacao_validada" not in attributes
