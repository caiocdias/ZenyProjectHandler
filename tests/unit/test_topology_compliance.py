from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.application.analysis_regions import RegiaoAnalise
from zeny_project_handler.application.compliance_evaluation import avaliar_regras_conformidade
from zeny_project_handler.application.compliance_fact_providers import ContextoProvedorFatos
from zeny_project_handler.application.human_review import SessaoRevisao
from zeny_project_handler.application.topology_compliance import (
    _deflection_angle,
    _deflection_angles,
    _is_neutral_cable,
    prover_fatos_topologicos,
)
from zeny_project_handler.domain.analysis import (
    DecisaoRevisao,
    EvidenciaDocumento,
    ExecucaoAnalise,
    PropostaElemento,
)
from zeny_project_handler.domain.catalog import (
    JsonPrimitive,
    TipoCabo,
    TipoEquipamento,
    TipoEstruturaBt,
    TipoEstruturaMt,
    TipoPoste,
)
from zeny_project_handler.domain.compliance import (
    AlvoConformidade,
    ResultadoConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    NivelRede,
    SituacaoProjeto,
    TipoDecisaoRevisao,
    TipoEvidencia,
    TipoPontoRede,
    TipoTrechoRede,
)
from zeny_project_handler.domain.market import Mercado
from zeny_project_handler.domain.project import (
    Cabo,
    Equipamento,
    EstruturaBt,
    EstruturaMt,
    PontoRede,
    Poste,
    Projeto,
)
from zeny_project_handler.domain.values import CaixaPagina, GeometriaDocumento, PontoNormalizado

_NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)


def _point(x: float, y: float) -> PontoNormalizado:
    return PontoNormalizado(Decimal(str(x)), Decimal(str(y)))


def _cable(angle_degrees: float) -> SimpleNamespace:
    radians = math.radians(angle_degrees)
    end = _point(0.5 + 0.25 * math.cos(radians), 0.5 + 0.25 * math.sin(radians))
    return SimpleNamespace(geometria=GeometriaDocumento.polilinha(uuid4(), (_point(0.5, 0.5), end)))


@pytest.mark.parametrize("deflection", [0, 20, 45])
def test_deflection_angle_uses_zero_for_alignment(deflection: int) -> None:
    page_id = uuid4()
    pole = GeometriaDocumento.ponto(page_id, _point(0.5, 0.5))
    cables = (_cable(0), _cable(180 - deflection))

    assert _deflection_angle(pole, cables) == Decimal(deflection)


def test_branch_angles_are_independent_of_cable_order() -> None:
    page_id = uuid4()
    pole = GeometriaDocumento.ponto(page_id, _point(0.5, 0.5))
    cables = (_cable(0), _cable(150), _cable(210))

    assert _deflection_angles(pole, cables) == _deflection_angles(
        pole,
        tuple(reversed(cables)),
    )


@pytest.mark.parametrize(("compatible", "expected"), ((True, False), (False, True)))
def test_structure_cable_pair_is_evaluated_against_catalog(
    compatible: bool,
    expected: bool,
) -> None:
    fixture = _fixture(compatible=compatible)

    produced_facts = prover_fatos_topologicos(
        ContextoProvedorFatos(fixture.session, (fixture.target,), Mercado.URBANO)
    )
    facts = {fact.chave: fact.valor for fact in produced_facts}
    findings = avaliar_regras_conformidade(
        carregar_registro_conformidade_inicial(),
        (fixture.target,),
        produced_facts,
    )
    finding = next(
        item for item in findings if item.regra_id == "catalogo.compatibilidade.estrutura-cabo"
    )

    assert facts["regiao.estrutura_cabo_avaliada"] is True
    assert facts["regiao.estrutura_cabo_incompativel"] is expected
    assert finding.resultado is (
        ResultadoConformidade.DIVERGENCIA if expected else ResultadoConformidade.CONFORME
    )


@pytest.mark.parametrize(
    "segment_type",
    (TipoTrechoRede.RAMAL_CONEXAO, TipoTrechoRede.DESCONHECIDO),
)
def test_non_network_cable_is_not_supported_by_structure_compatibility_matrix(
    segment_type: TipoTrechoRede,
) -> None:
    fixture = _fixture(compatible=True)
    session = fixture.session
    structure = next(
        item for item in session.projeto.elementos if isinstance(item, (EstruturaMt, EstruturaBt))
    )
    incompatible = next(
        item
        for item in session.catalogo.itens_ativos(CategoriaElemento.CABO)
        if isinstance(item, TipoCabo)
        and (structure.tipo_catalogo_id, item.id)
        not in {
            (entry.tipo_estrutura_id, entry.tipo_cabo_id)
            for entry in session.catalogo.compatibilidades
        }
    )
    origin = next(point for point in session.projeto.pontos_rede if point.nome == "P1-A")
    extra_points: tuple[PontoRede, ...] = ()
    if segment_type is TipoTrechoRede.RAMAL_CONEXAO:
        destination = PontoRede(
            id=_id("unsupported-service-drop-point"),
            poste_id=None,
            nome="Padrão do cliente",
            nivel_rede=origin.nivel_rede,
            nivel_tensao_opcao_id=origin.nivel_tensao_opcao_id,
            configuracao_fases_opcao_id=origin.configuracao_fases_opcao_id,
            tipo=TipoPontoRede.ENTREGA,
            geometria=_geometry_point(session.projeto.documentos[0].paginas[0].id, 0.5, 0.1),
        )
        extra_points = (destination,)
    else:
        destination = next(point for point in session.projeto.pontos_rede if point.nome == "P2")
    unsupported = Cabo(
        id=_id(f"unsupported-{segment_type.value}"),
        tipo_catalogo_id=incompatible.id,
        situacao=SituacaoProjeto.INSTALAR,
        geometria=_line(session.projeto.documentos[0].paginas[0].id, (0.5, 0.5), (0.5, 0.1)),
        ponto_origem_id=origin.id,
        ponto_destino_id=destination.id,
        tipo_trecho=segment_type,
    )
    fixture = replace(
        fixture,
        session=replace(
            session,
            projeto=replace(
                session.projeto,
                elementos=(*session.projeto.elementos, unsupported),
                pontos_rede=(*session.projeto.pontos_rede, *extra_points),
            ),
        ),
    )

    facts = _facts_by_key(fixture)

    assert facts["regiao.estrutura_cabo_avaliada"] is True
    assert facts["regiao.estrutura_cabo_incompativel"] is False


def test_installed_post_equipment_post_and_symbol_facts_are_published() -> None:
    fixture = _fixture(compatible=True)
    post_type = fixture.post_type

    facts = _facts_by_key(fixture)

    assert facts["regiao.poste_instalar_altura_m"] == post_type.altura_m
    assert facts["regiao.poste_instalar_resistencia_dan"] == post_type.resistencia_dan
    assert facts["regiao.poste_instalar_formato"] == fixture.post_format
    assert facts["regiao.poste_equipamento_instalar_altura_m"] == post_type.altura_m
    assert facts["regiao.poste_equipamento_instalar_resistencia_dan"] == (post_type.resistencia_dan)
    assert facts["regiao.transformador_instalar"] is True
    assert facts["regiao.chave_fusivel_presente"] is True
    assert facts["regiao.para_raios_mt_presente"] is True
    assert facts["regiao.transformador_para_raios_mt_presente"] is True
    assert facts["regiao.para_raios_mt_requisito_presente"] is False
    assert facts["regiao.para_raios_bt_presente"] is True
    assert facts["regiao.aterramento_presente"] is True


def test_transformer_protection_must_be_on_the_transformer_pole() -> None:
    fixture = _fixture(compatible=True)
    page_id = fixture.session.projeto.documentos[0].paginas[0].id
    moved = tuple(
        replace(item, geometria=_geometry_point(page_id, 0.1, 0.5))
        if isinstance(item, PropostaElemento)
        and dict(item.atributos_sugeridos).get("classe_equipamento") == "PARA_RAIOS_MT"
        else item
        for item in fixture.session.propostas
    )
    fixture = replace(fixture, session=replace(fixture.session, propostas=moved))

    facts = _facts_by_key(fixture)

    assert facts["regiao.transformador_para_raios_mt_presente"] is False
    assert facts["regiao.para_raios_mt_presente"] is False


def test_missing_fuse_fact_keeps_specific_p2_post_geometry_instead_of_region() -> None:
    fixture = _fixture(compatible=True)
    session = fixture.session
    fuse = next(
        item
        for item in session.propostas
        if isinstance(item, PropostaElemento)
        and dict(item.atributos_sugeridos).get("classe_equipamento") == "CHAVE FUSIVEL"
    )
    proposals = tuple(item for item in session.propostas if item.id != fuse.id)
    region = replace(
        session.regioes[0],
        elemento_ids=tuple(item for item in session.regioes[0].elemento_ids if item != fuse.id),
        rotulo_ponto="P2",
    )
    target = replace(fixture.target, rotulo="P2")
    fixture = replace(
        fixture,
        session=replace(session, propostas=proposals, regioes=(region,)),
        target=target,
    )

    facts = prover_fatos_topologicos(
        ContextoProvedorFatos(fixture.session, (fixture.target,), Mercado.URBANO)
    )
    fuse_fact = next(item for item in facts if item.chave == "regiao.chave_fusivel_presente")
    transformer = next(item for item in session.projeto.elementos if isinstance(item, Equipamento))
    post = next(
        item
        for item in session.projeto.elementos
        if isinstance(item, Poste) and item.id == transformer.poste_id
    )

    assert fuse_fact.valor is False
    assert fuse_fact.geometria == post.geometria
    assert fuse_fact.geometria != fixture.target.geometria


def test_transformer_and_line_end_protection_are_correlated_separately() -> None:
    fixture = _fixture(compatible=True)
    session = fixture.session
    transformer = next(item for item in session.projeto.elementos if isinstance(item, Equipamento))
    outer_pole = next(
        item
        for item in session.projeto.elementos
        if isinstance(item, Poste) and item.id != transformer.poste_id
    )
    evidence = session.evidencias[0]
    proposal = _proposal(
        "outer-pole-proposal",
        session.execucoes[0].id,
        CategoriaElemento.POSTE,
        outer_pole.geometria,
        evidence.id,
        outer_pole.tipo_catalogo_id,
    )
    decision = _decision(proposal.id, outer_pole.id)
    region = replace(
        session.regioes[0],
        elemento_ids=(*session.regioes[0].elemento_ids, proposal.id),
    )
    fixture = replace(
        fixture,
        session=replace(
            session,
            propostas=(*session.propostas, proposal),
            decisoes=(*session.decisoes, decision),
            regioes=(region,),
        ),
    )

    facts = _facts_by_key(fixture)

    assert facts["regiao.transformador_para_raios_mt_presente"] is True
    assert facts["regiao.para_raios_mt_requisito_presente"] is False
    assert facts["regiao.para_raios_mt_presente"] is False


def test_neutral_cable_recognizes_bare_and_multiplexed_catalog_codes() -> None:
    catalog = carregar_catalogo_inicial()
    cables = {
        item.codigo: item
        for item in catalog.itens_ativos(CategoriaElemento.CABO)
        if isinstance(item, TipoCabo)
    }

    assert _is_neutral_cable(cables["N- (1N5)"])
    assert _is_neutral_cable(cables["AN-16(16)"])
    assert _is_neutral_cable(cables["ABCN-35(70)"])


def test_rejected_symbol_does_not_satisfy_topological_rule() -> None:
    fixture = _fixture(compatible=True)
    rejected = tuple(
        replace(item, estado_revisao=EstadoRevisao.REJEITADA)
        if isinstance(item, PropostaElemento)
        and dict(item.atributos_sugeridos).get("classe_equipamento") == "ATERRAMENTO"
        else item
        for item in fixture.session.propostas
    )
    fixture = replace(fixture, session=replace(fixture.session, propostas=rejected))

    facts = _facts_by_key(fixture)

    assert facts["regiao.aterramento_presente"] is False


def test_plain_text_equipment_label_does_not_count_as_symbol() -> None:
    fixture = _fixture(compatible=True)
    proposals = tuple(
        replace(
            item,
            atributos_sugeridos=tuple(
                attribute
                for attribute in item.atributos_sugeridos
                if attribute[0] != "reconhecido_por_simbologia"
            ),
        )
        if isinstance(item, PropostaElemento)
        and dict(item.atributos_sugeridos).get("classe_equipamento") == "ATERRAMENTO"
        else item
        for item in fixture.session.propostas
    )
    fixture = replace(fixture, session=replace(fixture.session, propostas=proposals))

    facts = _facts_by_key(fixture)

    assert facts["regiao.aterramento_presente"] is False


def test_unconfirmed_cable_geometry_makes_topology_incomplete_without_inference() -> None:
    fixture = _fixture(compatible=True)
    cable_ids = {item.id for item in fixture.session.projeto.elementos if isinstance(item, Cabo)}
    session = replace(
        fixture.session,
        projeto=replace(
            fixture.session.projeto,
            elementos=tuple(
                item for item in fixture.session.projeto.elementos if item.id not in cable_ids
            ),
        ),
        decisoes=tuple(
            decision
            for decision in fixture.session.decisoes
            if decision.elemento_confirmado_id not in cable_ids
        ),
    )
    fallback_fixture = replace(fixture, session=session)

    produced_facts = prover_fatos_topologicos(
        ContextoProvedorFatos(
            fallback_fixture.session,
            (fallback_fixture.target,),
            Mercado.URBANO,
        )
    )
    facts = {fact.chave: fact.valor for fact in produced_facts}

    assert facts["regiao.topologia_mt_avaliavel"] is False
    assert facts["regiao.componente_mt_completo"] is False
    assert "conexao.angulo_graus" not in facts
    assert "regiao.fim_rede" not in facts
    assert "regiao.transicao_rede" not in facts
    assert "regiao.para_raios_mt_requerido" not in facts
    assert "regiao.estrutura_cabo_avaliada" not in facts


def test_geometric_cable_cannot_complete_confirmed_topology_for_mt_transition() -> None:
    fixture = _fixture(compatible=True)
    session = fixture.session
    option_codes = {
        option.id: option.codigo
        for group in session.catalogo.grupos_opcao
        for option in group.opcoes
    }
    mt_cables = tuple(
        item
        for item in session.catalogo.itens_ativos(CategoriaElemento.CABO)
        if isinstance(item, TipoCabo) and option_codes[item.nivel_tensao_opcao_id] == "MT"
    )
    conventional = next(
        item
        for item in mt_cables
        if option_codes[item.tecnologia_rede_opcao_id].startswith("CONVENCIONAL")
    )
    protected = next(
        item for item in mt_cables if option_codes[item.tecnologia_rede_opcao_id] == "PROTEGIDA"
    )
    confirmed_cable_ids = {item.id for item in session.projeto.elementos if isinstance(item, Cabo)}
    project = replace(
        session.projeto,
        elementos=tuple(
            replace(item, tipo_catalogo_id=conventional.id) if isinstance(item, Cabo) else item
            for item in session.projeto.elementos
        ),
    )
    proposals = tuple(
        replace(item, tipo_catalogo_sugerido_id=conventional.id)
        if isinstance(item, PropostaElemento)
        and item.categoria is CategoriaElemento.CABO
        and any(
            decision.proposta_id == item.id
            and decision.elemento_confirmado_id in confirmed_cable_ids
            for decision in session.decisoes
        )
        else item
        for item in session.propostas
    )
    page_id = project.documentos[0].paginas[0].id
    geometric = _proposal(
        "mixed-protected-cable",
        session.execucoes[0].id,
        CategoriaElemento.CABO,
        _line(page_id, (0.5, 0.5), (0.5, 0.1)),
        session.evidencias[0].id,
        protected.id,
    )
    region = replace(
        session.regioes[0],
        elemento_ids=(*session.regioes[0].elemento_ids, geometric.id),
    )
    fixture = replace(
        fixture,
        session=replace(
            session,
            projeto=project,
            propostas=(*proposals, geometric),
            regioes=(region,),
        ),
    )

    facts = _facts_by_key(fixture)

    assert facts["regiao.topologia_mt_avaliavel"] is False
    assert facts["regiao.componente_mt_completo"] is False
    assert "regiao.transicao_rede" not in facts
    assert "conexao.angulo_graus" not in facts
    assert "regiao.para_raios_mt_requerido" not in facts


def test_single_geometric_mt_cable_is_not_recognized_as_line_end() -> None:
    fixture = _fixture(compatible=True)
    session = fixture.session
    option_codes = {
        option.id: option.codigo
        for group in session.catalogo.grupos_opcao
        for option in group.opcoes
    }
    mt_cable = next(
        item
        for item in session.catalogo.itens_ativos(CategoriaElemento.CABO)
        if isinstance(item, TipoCabo) and option_codes[item.nivel_tensao_opcao_id] == "MT"
    )
    cable_elements = tuple(item for item in session.projeto.elementos if isinstance(item, Cabo))
    cable_element_ids = {item.id for item in cable_elements}
    cable_proposals = tuple(
        item
        for item in session.propostas
        if isinstance(item, PropostaElemento) and item.categoria is CategoriaElemento.CABO
    )
    kept_proposal = replace(cable_proposals[0], tipo_catalogo_sugerido_id=mt_cable.id)
    removed_proposal_ids = {item.id for item in cable_proposals[1:]}
    proposals = tuple(
        kept_proposal if item.id == kept_proposal.id else item
        for item in session.propostas
        if item.id not in removed_proposal_ids
    )
    region = replace(
        session.regioes[0],
        elemento_ids=tuple(
            item_id
            for item_id in session.regioes[0].elemento_ids
            if item_id in {p.id for p in proposals}
        ),
    )
    fixture = replace(
        fixture,
        session=replace(
            session,
            projeto=replace(
                session.projeto,
                elementos=tuple(
                    item for item in session.projeto.elementos if item.id not in cable_element_ids
                ),
            ),
            propostas=proposals,
            decisoes=tuple(
                item
                for item in session.decisoes
                if item.elemento_confirmado_id not in cable_element_ids
            ),
            regioes=(region,),
        ),
    )

    facts = _facts_by_key(fixture)

    assert facts["regiao.topologia_mt_avaliavel"] is False
    assert facts["regiao.componente_mt_completo"] is False
    assert "regiao.fim_rede" not in facts
    assert "regiao.para_raios_mt_requerido" not in facts


def test_intermediate_p2_with_two_same_technology_mt_edges_is_not_terminal_or_transition() -> None:
    fixture = _with_mt_technologies(_fixture(compatible=True), ("CONVENCIONAL", "CONVENCIONAL"))

    facts = _facts_by_key(fixture)

    assert facts["regiao.topologia_mt_avaliavel"] is True
    assert facts["regiao.componente_mt_completo"] is True
    assert facts["regiao.fim_rede"] is False
    assert facts["regiao.transicao_rede"] is False
    assert facts["conexao.angulo_graus"] == Decimal(0)
    assert "regiao.para_raios_mt_requerido" not in facts


def test_parallel_mt_cables_on_same_route_count_as_one_physical_edge() -> None:
    fixture = _with_mt_technologies(_fixture(compatible=True), ("CONVENCIONAL", "CONVENCIONAL"))
    session = fixture.session
    first = next(item for item in session.projeto.elementos if isinstance(item, Cabo))
    parallel = replace(first, id=_id("parallel-cable"))
    fixture = replace(
        fixture,
        session=replace(
            session,
            projeto=replace(
                session.projeto,
                elementos=(*session.projeto.elementos, parallel),
            ),
        ),
    )

    produced = prover_fatos_topologicos(
        ContextoProvedorFatos(fixture.session, (fixture.target,), Mercado.URBANO)
    )
    facts = {fact.chave: fact.valor for fact in produced}
    angles = {fact.valor for fact in produced if fact.chave == "conexao.angulo_graus"}

    assert facts["regiao.topologia_mt_avaliavel"] is True
    assert facts["regiao.fim_rede"] is False
    assert facts["regiao.transicao_rede"] is False
    assert angles == {Decimal(0)}


def test_known_service_drop_does_not_change_mt_degree_transition_or_angle() -> None:
    fixture = _with_mt_technologies(_fixture(compatible=True), ("CONVENCIONAL", "CONVENCIONAL"))
    session = fixture.session
    cables = tuple(item for item in session.projeto.elementos if isinstance(item, Cabo))
    center_point = next(
        point for point in session.projeto.pontos_rede if point.id == cables[0].ponto_origem_id
    )
    delivery = PontoRede(
        id=_id("service-drop-delivery"),
        poste_id=None,
        nome="Padrão do cliente",
        nivel_rede=NivelRede.MT,
        nivel_tensao_opcao_id=center_point.nivel_tensao_opcao_id,
        configuracao_fases_opcao_id=center_point.configuracao_fases_opcao_id,
        tipo=TipoPontoRede.ENTREGA,
        geometria=_geometry_point(center_point.geometria.pagina_id, 0.5, 0.1)
        if center_point.geometria is not None
        else None,
    )
    service_drop = Cabo(
        id=_id("service-drop"),
        tipo_catalogo_id=cables[0].tipo_catalogo_id,
        situacao=SituacaoProjeto.INSTALAR,
        geometria=_line(session.projeto.documentos[0].paginas[0].id, (0.5, 0.5), (0.5, 0.1)),
        ponto_origem_id=center_point.id,
        ponto_destino_id=delivery.id,
        tipo_trecho=TipoTrechoRede.RAMAL_CONEXAO,
    )
    fixture = replace(
        fixture,
        session=replace(
            session,
            projeto=replace(
                session.projeto,
                elementos=(*session.projeto.elementos, service_drop),
                pontos_rede=(*session.projeto.pontos_rede, delivery),
            ),
        ),
    )

    facts = _facts_by_key(fixture)

    assert facts["regiao.topologia_mt_avaliavel"] is True
    assert facts["regiao.componente_mt_completo"] is True
    assert facts["regiao.fim_rede"] is False
    assert facts["regiao.transicao_rede"] is False
    assert facts["conexao.angulo_graus"] == Decimal(0)
    assert "regiao.para_raios_mt_requerido" not in facts


def test_true_terminal_requires_one_edge_in_a_complete_mt_component() -> None:
    fixture = _with_mt_technologies(_fixture(compatible=True), ("CONVENCIONAL", "CONVENCIONAL"))
    session = fixture.session
    cables = tuple(item for item in session.projeto.elementos if isinstance(item, Cabo))
    removed = cables[1]
    removed_proposal_ids = {
        decision.proposta_id
        for decision in session.decisoes
        if decision.elemento_confirmado_id == removed.id
    }
    fixture = replace(
        fixture,
        session=replace(
            session,
            projeto=replace(
                session.projeto,
                elementos=tuple(
                    item for item in session.projeto.elementos if item.id != removed.id
                ),
            ),
            propostas=tuple(
                item for item in session.propostas if item.id not in removed_proposal_ids
            ),
            decisoes=tuple(
                item for item in session.decisoes if item.elemento_confirmado_id != removed.id
            ),
            regioes=(
                replace(
                    session.regioes[0],
                    elemento_ids=tuple(
                        item
                        for item in session.regioes[0].elemento_ids
                        if item not in removed_proposal_ids
                    ),
                ),
            ),
        ),
    )

    facts = _facts_by_key(fixture)

    assert facts["regiao.topologia_mt_avaliavel"] is True
    assert facts["regiao.componente_mt_completo"] is True
    assert facts["regiao.fim_rede"] is True
    assert facts["regiao.transicao_rede"] is False
    assert facts["regiao.para_raios_mt_requerido"] is True


def test_true_transition_requires_exactly_two_continuous_mt_technologies() -> None:
    fixture = _with_mt_technologies(_fixture(compatible=True), ("CONVENCIONAL", "PROTEGIDA"))

    facts = _facts_by_key(fixture)

    assert facts["regiao.topologia_mt_avaliavel"] is True
    assert facts["regiao.componente_mt_completo"] is True
    assert facts["regiao.fim_rede"] is False
    assert facts["regiao.transicao_rede"] is True
    assert facts["conexao.angulo_graus"] == Decimal(0)
    assert facts["regiao.para_raios_mt_requerido"] is True


def test_unknown_edge_makes_mt_component_not_evaluable_without_counting_degree() -> None:
    fixture = _with_mt_technologies(_fixture(compatible=True), ("CONVENCIONAL", "CONVENCIONAL"))
    session = fixture.session
    catalog = session.catalogo
    post_type = fixture.post_type
    page_id = session.projeto.documentos[0].paginas[0].id
    center_point = next(point for point in session.projeto.pontos_rede if point.nome == "P1-A")
    unknown_pole = Poste(
        id=_id("unknown-edge-pole"),
        tipo_catalogo_id=post_type.id,
        situacao=SituacaoProjeto.EXISTENTE,
        geometria=_geometry_point(page_id, 0.5, 0.1),
    )
    unknown_point = PontoRede(
        id=_id("unknown-edge-point"),
        poste_id=unknown_pole.id,
        nome="P4",
        nivel_rede=NivelRede.MT,
        nivel_tensao_opcao_id=center_point.nivel_tensao_opcao_id,
        configuracao_fases_opcao_id=center_point.configuracao_fases_opcao_id,
        geometria=unknown_pole.geometria,
    )
    cable_type = next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.CABO)
        if isinstance(item, TipoCabo)
        and item.id
        == next(
            cable.tipo_catalogo_id for cable in session.projeto.elementos if isinstance(cable, Cabo)
        )
    )
    unknown = Cabo(
        id=_id("unknown-edge"),
        tipo_catalogo_id=cable_type.id,
        situacao=SituacaoProjeto.INSTALAR,
        geometria=_line(page_id, (0.5, 0.5), (0.5, 0.1)),
        ponto_origem_id=center_point.id,
        ponto_destino_id=unknown_point.id,
        tipo_trecho=TipoTrechoRede.DESCONHECIDO,
    )
    fixture = replace(
        fixture,
        session=replace(
            session,
            projeto=replace(
                session.projeto,
                elementos=(*session.projeto.elementos, unknown_pole, unknown),
                pontos_rede=(*session.projeto.pontos_rede, unknown_point),
            ),
        ),
    )

    facts = _facts_by_key(fixture)

    assert facts["regiao.topologia_mt_avaliavel"] is False
    assert facts["regiao.componente_mt_completo"] is False
    assert "regiao.fim_rede" not in facts
    assert "regiao.transicao_rede" not in facts
    assert "conexao.angulo_graus" not in facts
    assert "regiao.para_raios_mt_requerido" not in facts


@pytest.mark.parametrize("structure_code", ("U4", "CM3", "S3R"))
def test_isolated_anchor_structure_never_proves_terminal_or_transition(
    structure_code: str,
) -> None:
    fixture = _fixture(compatible=True)
    session = fixture.session
    structure_type = next(
        item
        for item in session.catalogo.itens
        if isinstance(item, (TipoEstruturaMt, TipoEstruturaBt))
        and item.ativo
        and item.codigo == structure_code
    )
    structure = next(
        item for item in session.projeto.elementos if isinstance(item, (EstruturaMt, EstruturaBt))
    )
    structure_class = EstruturaMt if isinstance(structure_type, TipoEstruturaMt) else EstruturaBt
    replacement_structure = structure_class(
        id=structure.id,
        tipo_catalogo_id=structure_type.id,
        situacao=structure.situacao,
        geometria=structure.geometria,
        poste_id=structure.poste_id,
        pontos_fixados_ids=structure.pontos_fixados_ids,
    )
    cable_ids = {item.id for item in session.projeto.elementos if isinstance(item, Cabo)}
    cable_proposal_ids = {
        decision.proposta_id
        for decision in session.decisoes
        if decision.elemento_confirmado_id in cable_ids
    }
    fixture = replace(
        fixture,
        session=replace(
            session,
            projeto=replace(
                session.projeto,
                elementos=tuple(
                    replacement_structure if item.id == structure.id else item
                    for item in session.projeto.elementos
                    if item.id not in cable_ids
                ),
            ),
            propostas=tuple(
                replace(
                    item,
                    categoria=replacement_structure.categoria,
                    tipo_catalogo_sugerido_id=structure_type.id,
                )
                if item.id
                in {
                    decision.proposta_id
                    for decision in session.decisoes
                    if decision.elemento_confirmado_id == structure.id
                }
                and isinstance(item, PropostaElemento)
                else item
                for item in session.propostas
                if item.id not in cable_proposal_ids
            ),
            decisoes=tuple(
                item for item in session.decisoes if item.elemento_confirmado_id not in cable_ids
            ),
            regioes=(
                replace(
                    session.regioes[0],
                    elemento_ids=tuple(
                        item
                        for item in session.regioes[0].elemento_ids
                        if item not in cable_proposal_ids
                    ),
                ),
            ),
        ),
    )

    facts = _facts_by_key(fixture)

    assert facts["regiao.topologia_mt_avaliavel"] is False
    assert facts["regiao.componente_mt_completo"] is False
    assert "regiao.fim_rede" not in facts
    assert "regiao.transicao_rede" not in facts
    assert "regiao.para_raios_mt_requerido" not in facts


@dataclass(frozen=True, slots=True)
class _Fixture:
    session: SessaoRevisao
    target: AlvoConformidade
    post_type: TipoPoste
    post_format: str


def _with_mt_technologies(
    fixture: _Fixture,
    technologies: tuple[str, str],
) -> _Fixture:
    session = fixture.session
    option_codes = {
        option.id: option.codigo
        for group in session.catalogo.grupos_opcao
        for option in group.opcoes
    }
    cable_types = tuple(
        next(
            item
            for item in session.catalogo.itens_ativos(CategoriaElemento.CABO)
            if isinstance(item, TipoCabo)
            and option_codes[item.nivel_tensao_opcao_id] == "MT"
            and (
                option_codes[item.tecnologia_rede_opcao_id].startswith(technology)
                if technology == "CONVENCIONAL"
                else option_codes[item.tecnologia_rede_opcao_id] == technology
            )
        )
        for technology in technologies
    )
    cables = tuple(item for item in session.projeto.elementos if isinstance(item, Cabo))
    type_by_cable = dict(zip((item.id for item in cables), cable_types, strict=True))
    proposal_type = {
        decision.proposta_id: type_by_cable[decision.elemento_confirmado_id]
        for decision in session.decisoes
        if decision.elemento_confirmado_id in type_by_cable
    }
    return replace(
        fixture,
        session=replace(
            session,
            projeto=replace(
                session.projeto,
                elementos=tuple(
                    replace(item, tipo_catalogo_id=type_by_cable[item.id].id)
                    if isinstance(item, Cabo) and item.id in type_by_cable
                    else item
                    for item in session.projeto.elementos
                ),
            ),
            propostas=tuple(
                replace(item, tipo_catalogo_sugerido_id=proposal_type[item.id].id)
                if isinstance(item, PropostaElemento) and item.id in proposal_type
                else item
                for item in session.propostas
            ),
        ),
    )


def _fixture(*, compatible: bool) -> _Fixture:
    catalog = carregar_catalogo_inicial()
    items = {item.id: item for item in catalog.itens}
    option_codes = {
        option.id: option.codigo for group in catalog.grupos_opcao for option in group.opcoes
    }
    compatibility = next(
        item
        for item in catalog.compatibilidades
        if items[item.tipo_estrutura_id].ativo and items[item.tipo_cabo_id].ativo
    )
    structure_type = items[compatibility.tipo_estrutura_id]
    assert isinstance(structure_type, (TipoEstruturaMt, TipoEstruturaBt))
    compatible_cable_type = items[compatibility.tipo_cabo_id]
    assert isinstance(compatible_cable_type, TipoCabo)
    cable_type = (
        compatible_cable_type
        if compatible
        else next(
            item
            for item in catalog.itens_ativos(CategoriaElemento.CABO)
            if isinstance(item, TipoCabo)
            and (structure_type.id, item.id)
            not in {
                (entry.tipo_estrutura_id, entry.tipo_cabo_id) for entry in catalog.compatibilidades
            }
        )
    )
    post_type = next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.POSTE)
        if isinstance(item, TipoPoste)
    )
    transformer_type = next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.EQUIPAMENTO)
        if isinstance(item, TipoEquipamento)
        and option_codes[item.classe_equipamento_opcao_id] == "TRANSFORMADOR"
    )
    page = _page()
    document = DocumentoProjeto(
        id=_id("document"),
        nome_arquivo="topologia.pdf",
        sha256="b" * 64,
        paginas=(page,),
        tamanho_bytes=100,
    )
    pole = Poste(
        id=_id("pole"),
        tipo_catalogo_id=post_type.id,
        situacao=SituacaoProjeto.INSTALAR,
        geometria=_geometry_point(page.id, 0.5, 0.5),
    )
    outer_poles = tuple(
        Poste(
            id=_id(f"outer-pole-{index}"),
            tipo_catalogo_id=post_type.id,
            situacao=SituacaoProjeto.EXISTENTE,
            geometria=_geometry_point(page.id, x, 0.5),
        )
        for index, x in enumerate((0.1, 0.9), start=1)
    )
    network_points = (
        PontoRede(
            id=_id("network-center-1"),
            poste_id=pole.id,
            nome="P1-A",
            nivel_rede=NivelRede.MT,
            nivel_tensao_opcao_id=cable_type.nivel_tensao_opcao_id,
            configuracao_fases_opcao_id=cable_type.configuracao_fases_opcao_id,
            geometria=pole.geometria,
        ),
        PontoRede(
            id=_id("network-left"),
            poste_id=outer_poles[0].id,
            nome="P2",
            nivel_rede=NivelRede.MT,
            nivel_tensao_opcao_id=cable_type.nivel_tensao_opcao_id,
            configuracao_fases_opcao_id=cable_type.configuracao_fases_opcao_id,
            geometria=outer_poles[0].geometria,
        ),
        PontoRede(
            id=_id("network-center-2"),
            poste_id=pole.id,
            nome="P1-B",
            nivel_rede=NivelRede.MT,
            nivel_tensao_opcao_id=cable_type.nivel_tensao_opcao_id,
            configuracao_fases_opcao_id=cable_type.configuracao_fases_opcao_id,
            geometria=pole.geometria,
        ),
        PontoRede(
            id=_id("network-right"),
            poste_id=outer_poles[1].id,
            nome="P3",
            nivel_rede=NivelRede.MT,
            nivel_tensao_opcao_id=cable_type.nivel_tensao_opcao_id,
            configuracao_fases_opcao_id=cable_type.configuracao_fases_opcao_id,
            geometria=outer_poles[1].geometria,
        ),
    )
    cable_geometries = (
        _line(page.id, (0.5, 0.5), (0.1, 0.5)),
        _line(page.id, (0.5, 0.5), (0.9, 0.5)),
    )
    cables = tuple(
        Cabo(
            id=_id(f"cable-{index}"),
            tipo_catalogo_id=cable_type.id,
            situacao=SituacaoProjeto.INSTALAR,
            geometria=cable_geometries[index],
            ponto_origem_id=network_points[index * 2].id,
            ponto_destino_id=network_points[index * 2 + 1].id,
            tipo_trecho=TipoTrechoRede.REDE_DISTRIBUICAO,
        )
        for index in range(2)
    )
    structure_class = EstruturaMt if isinstance(structure_type, TipoEstruturaMt) else EstruturaBt
    structure = structure_class(
        id=_id("structure"),
        tipo_catalogo_id=structure_type.id,
        situacao=SituacaoProjeto.INSTALAR,
        geometria=pole.geometria,
        poste_id=pole.id,
    )
    transformer = Equipamento(
        id=_id("transformer"),
        tipo_catalogo_id=transformer_type.id,
        situacao=SituacaoProjeto.INSTALAR,
        geometria=pole.geometria,
        poste_id=pole.id,
    )
    project = Projeto(
        id=_id("project"),
        nome="Projeto topológico sintético",
        catalogo_versao_id=catalog.id,
        criado_em=_NOW,
        documentos=(document,),
        elementos=(pole, *outer_poles, structure, transformer, *cables),
        pontos_rede=network_points,
    )
    execution = ExecucaoAnalise(
        id=_id("execution"),
        projeto_id=project.id,
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=_NOW,
        finalizada_em=_NOW,
    )
    evidence = _evidence(execution.id, page.id)
    confirmed_pairs = (
        ("pole-proposal", CategoriaElemento.POSTE, post_type.id, pole.geometria, pole),
        (
            "structure-proposal",
            structure.categoria,
            structure_type.id,
            structure.geometria,
            structure,
        ),
        (
            "transformer-proposal",
            CategoriaElemento.EQUIPAMENTO,
            transformer_type.id,
            transformer.geometria,
            transformer,
        ),
        *tuple(
            (
                f"cable-proposal-{index}",
                CategoriaElemento.CABO,
                cable_type.id,
                cable.geometria,
                cable,
            )
            for index, cable in enumerate(cables)
        ),
    )
    confirmed_proposals = tuple(
        _proposal(
            key,
            execution.id,
            category,
            geometry,
            evidence.id,
            catalog_id,
        )
        for key, category, catalog_id, geometry, _element in confirmed_pairs
    )
    decisions = tuple(
        _decision(proposal.id, pair[-1].id)
        for proposal, pair in zip(confirmed_proposals, confirmed_pairs, strict=True)
    )
    symbols = tuple(
        _proposal(
            f"symbol-{symbol_class}",
            execution.id,
            CategoriaElemento.EQUIPAMENTO,
            _geometry_point(page.id, 0.5, 0.52 + index * 0.01),
            evidence.id,
            None,
            attributes=(
                ("classe_equipamento", symbol_class),
                ("reconhecido_por_simbologia", True),
            ),
        )
        for index, symbol_class in enumerate(
            ("CHAVE FUSIVEL", "PARA_RAIOS_MT", "PARA_RAIOS_BT", "ATERRAMENTO")
        )
    )
    proposals = (*confirmed_proposals, *symbols)
    region_geometry = GeometriaDocumento.caixa(
        page.id,
        _point(0.05, 0.40),
        _point(0.95, 0.65),
    )
    region = RegiaoAnalise(
        id=_id("region"),
        pagina_id=page.id,
        geometria=region_geometry,
        elemento_ids=tuple(item.id for item in proposals),
        rotulo_ponto="P1",
    )
    session = SessaoRevisao(
        projeto=project,
        catalogo=catalog,
        execucoes=(execution,),
        propostas=proposals,
        regioes=(region,),
        evidencias=(evidence,),
        decisoes=decisions,
        fontes_pdf=(),
    )
    target = AlvoConformidade(
        id=_id("target"),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="P1",
        referencia_id=region.id,
        pagina_id=page.id,
        geometria=region_geometry,
    )
    return _Fixture(
        session=session,
        target=target,
        post_type=post_type,
        post_format=option_codes[post_type.formato_opcao_id],
    )


def _facts_by_key(fixture: _Fixture) -> dict[str, object]:
    facts = prover_fatos_topologicos(
        ContextoProvedorFatos(fixture.session, (fixture.target,), Mercado.URBANO)
    )
    return {fact.chave: fact.valor for fact in facts}


def _proposal(
    key: str,
    execution_id: UUID,
    category: CategoriaElemento,
    geometry: GeometriaDocumento | None,
    evidence_id: UUID,
    catalog_id: UUID | None,
    *,
    attributes: tuple[tuple[str, JsonPrimitive], ...] = (),
) -> PropostaElemento:
    assert geometry is not None
    return PropostaElemento(
        id=_id(key),
        execucao_id=execution_id,
        categoria=category,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.CONFIRMADA if catalog_id else EstadoRevisao.PROPOSTA,
        evidencia_ids=(evidence_id,),
        geometria=geometry,
        tipo_catalogo_sugerido_id=catalog_id,
        atributos_sugeridos=attributes,
        confianca=Decimal("0.95"),
    )


def _decision(proposal_id: UUID, element_id: UUID) -> DecisaoRevisao:
    return DecisaoRevisao(
        id=uuid5(proposal_id, "decision"),
        proposta_id=proposal_id,
        decisao=TipoDecisaoRevisao.ACEITAR,
        revisor="fixture",
        decidida_em=_NOW,
        elemento_confirmado_id=element_id,
    )


def _evidence(execution_id: UUID, page_id: UUID) -> EvidenciaDocumento:
    return EvidenciaDocumento(
        id=_id("evidence"),
        execucao_id=execution_id,
        pagina_id=page_id,
        tipo=TipoEvidencia.TEXTO,
        geometria=_geometry_point(page_id, 0.5, 0.5),
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto="evidência topológica",
        criada_em=_NOW,
    )


def _page() -> PaginaDocumento:
    size = Decimal(1000)
    box = CaixaPagina(Decimal(0), Decimal(0), size, size)
    return PaginaDocumento(
        id=_id("page"),
        numero=1,
        largura_pontos=size,
        altura_pontos=size,
        rotacao_graus=0,
        media_box=box,
        crop_box=box,
    )


def _geometry_point(page_id: UUID, x: float, y: float) -> GeometriaDocumento:
    return GeometriaDocumento.ponto(page_id, _point(x, y))


def _line(
    page_id: UUID,
    start: tuple[float, float],
    end: tuple[float, float],
) -> GeometriaDocumento:
    return GeometriaDocumento.polilinha(page_id, (_point(*start), _point(*end)))


def _id(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"topology-compliance:{value}")
