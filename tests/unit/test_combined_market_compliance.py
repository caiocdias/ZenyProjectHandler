"""Matriz pública da união, com o catálogo normativo intacto e alvos reais."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from tests.unit.test_compliance import _session_with_document_controls
from tests.unit.test_span_compliance_provider import _span_fixture
from tests.unit.test_topology_path_compliance import _provider_session
from tests.unit.test_transformer_compliance_provider import _transformer_fixture

from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.application.human_review import SessaoRevisao
from zeny_project_handler.application.project_compliance import (
    ResultadoConformidadeProjeto,
    analisar_conformidade_projeto,
)
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.catalog import TipoCabo
from zeny_project_handler.domain.compliance import AchadoConformidade, TipoEscopoConformidade
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    ModalidadeTrecho,
    OrigemComprimentoVao,
    SituacaoProjeto,
    TipoTrechoRede,
)
from zeny_project_handler.domain.market import ClassificacaoMercado, ClassificacaoProjeto, Mercado
from zeny_project_handler.domain.project import Cabo, Poste


def _findings(result: ResultadoConformidadeProjeto) -> dict[tuple[str, UUID], AchadoConformidade]:
    findings = {(item.regra_id, item.alvo_id): item for item in result.achados}
    assert len(findings) == len(result.achados), "Regra comum duplicada no mesmo alvo"
    return findings


def _assert_union(session: SessaoRevisao) -> ResultadoConformidadeProjeto:
    registry = carregar_registro_conformidade_inicial()
    rural = analisar_conformidade_projeto(session, registry, mercado=Mercado.RURAL)
    urban = analisar_conformidade_projeto(session, registry, mercado=Mercado.URBANO)
    both = analisar_conformidade_projeto(session, registry, mercado=ClassificacaoMercado.AMBOS)
    # Compara achados completos: resultado, fonte, condição, fatos, geometria/evidência por ID.
    rural_findings, urban_findings = _findings(rural), _findings(urban)
    for key in rural_findings.keys() & urban_findings.keys():
        assert rural_findings[key] == urban_findings[key]
    assert _findings(both) == rural_findings | urban_findings
    assert both == analisar_conformidade_projeto(
        session, registry, mercado=ClassificacaoMercado.AMBOS
    )
    target_ids = {
        item.id
        for item in both.alvos
        if item.tipo in {TipoEscopoConformidade.PROJETO, TipoEscopoConformidade.REGIAO}
    }
    context_facts = tuple(item for item in both.fatos if item.chave.startswith("rede.contexto_"))
    assert {(item.alvo_id, item.chave, item.valor) for item in context_facts} == {
        (target, key, True)
        for target in target_ids
        for key in ("rede.contexto_rural", "rede.contexto_urbano")
    }
    assert len(context_facts) == 2 * len(target_ids)
    return both


def test_both_applies_to_every_region_regardless_of_document_metadata() -> None:
    session = _session_with_document_controls()
    region = session.regioes[0]
    session = replace(session, regioes=(region, replace(region, id=UUID(int=2), rotulo_ponto="P8")))
    _assert_union(session)


def test_persisted_choice_is_the_source_for_every_provider_even_with_old_caller_market() -> None:
    session = _session_with_document_controls()
    now = datetime(2026, 9, 10, tzinfo=UTC)
    classification = ClassificacaoProjeto.inicializar("0012345678", Mercado.RURAL, now).editar(
        ClassificacaoMercado.AMBOS, now
    )
    session = replace(
        session,
        projeto=replace(
            session.projeto,
            nome="0012345678",
            classificacao_mercado=classification,
        ),
    )
    registry = carregar_registro_conformidade_inicial()
    both = analisar_conformidade_projeto(session, registry, mercado=ClassificacaoMercado.AMBOS)
    assert both == analisar_conformidade_projeto(session, registry, mercado=Mercado.RURAL)
    assert both == analisar_conformidade_projeto(session, registry, mercado=Mercado.URBANO)


@pytest.mark.parametrize("network", ["compact", "neutral"])
@pytest.mark.parametrize("with_ground", [True, False])
def test_both_keeps_project_path_rules_and_guarded_findings(
    network: str, with_ground: bool
) -> None:
    session, _ = _provider_session(network=network, with_ground=with_ground)
    result = _assert_union(session)
    ids = {item.regra_id for item in result.achados}
    if network == "compact":
        assert {
            "nd93.rede.compacta-ancoragem-500m",
            "nd31.rede.compacta-aterramento-temporario-160m",
            "nd22.projeto.prordr-acima-300",
        } <= ids
    else:
        assert "nd31.rede.neutro-aterramento-200m" in ids


@pytest.mark.parametrize(
    "power,resistance,form",
    [
        ("-3-75", 300, "CIRCULAR"),
        ("-3-75", 150, "CIRCULAR"),
        ("-3-150", 600, "CIRCULAR"),
        ("-3-150", 300, "CIRCULAR"),
    ],
)
@pytest.mark.parametrize("relation", ["confirmed", "missing", "ambiguous", "new_post"])
def test_both_preserves_transformer_guard_and_rural_new_post_rules(
    power: str, resistance: int, form: str, relation: str
) -> None:
    fixture = _transformer_fixture(equipment_code=power, resistance=resistance, post_format=form)
    session = fixture.session
    if relation == "missing":
        session = replace(session, projeto=replace(session.projeto, relacoes_confirmadas=()))
    elif relation == "ambiguous":
        existing = session.projeto.relacoes_confirmadas[0]
        session = replace(
            session,
            projeto=replace(
                session.projeto,
                relacoes_confirmadas=(
                    existing,
                    replace(existing, id=UUID(int=1)),
                ),
            ),
        )
    elif relation == "new_post":
        session = replace(
            session,
            projeto=replace(
                session.projeto,
                elementos=tuple(
                    replace(item, situacao=SituacaoProjeto.INSTALAR)
                    if isinstance(item, Poste)
                    else item
                    for item in session.projeto.elementos
                ),
            ),
            propostas=tuple(
                replace(item, situacao_projeto=SituacaoProjeto.INSTALAR)
                if isinstance(item, PropostaElemento) and item.categoria is CategoriaElemento.POSTE
                else item
                for item in session.propostas
            ),
        )
    result = _assert_union(session)
    existing_findings = [item for item in result.achados if ".poste-existente-" in item.regra_id]
    assert bool(existing_findings) == (relation == "confirmed")
    if relation == "confirmed":
        assert existing_findings[0].evidencia_ids and existing_findings[0].fato_ids
    if relation == "new_post":
        assert "nd93.transformador.poste-novo-rural" in {item.regra_id for item in result.achados}


@pytest.mark.parametrize(
    "length,exception",
    [(None, False), (45, False), (52, False), (52, True), (61, True), (90, False)],
)
def test_both_keeps_span_thresholds_missing_evidence_and_exceptions(
    length: int | None, exception: bool
) -> None:
    fixture = _span_fixture(
        length=Decimal(length) if length is not None else None,
        origin=OrigemComprimentoVao.ANOTACAO_DESENHO if length is not None else None,
        exception=exception,
    )
    _assert_union(fixture.session)


@pytest.mark.parametrize(
    "length,modality,expected",
    [
        (30, ModalidadeTrecho.AEREO, "CONFORME"),
        (31, ModalidadeTrecho.AEREO, "DIVERGENCIA"),
        (None, ModalidadeTrecho.AEREO, "NAO_AVALIAVEL"),
        (31, ModalidadeTrecho.DESCONHECIDO, "NAO_AVALIAVEL"),
        (31, ModalidadeTrecho.SUBTERRANEO, None),
    ],
)
def test_both_keeps_service_drop_separate_and_common_rule_unique(
    length: int | None, modality: ModalidadeTrecho, expected: str | None
) -> None:
    fixture = _span_fixture(
        length=Decimal(length) if length is not None else None,
        origin=OrigemComprimentoVao.ANOTACAO_DESENHO if length is not None else None,
        segment_type=TipoTrechoRede.RAMAL_CONEXAO,
        modality=modality,
    )
    result = _assert_union(fixture.session)
    branch = [
        item for item in result.achados if item.regra_id == "nd51.ramal-conexao-aereo-comprimento"
    ]
    assert [item.resultado.value for item in branch] == ([expected] if expected else [])
    assert all(not item.chave.startswith("vao.") for item in result.fatos)
    if expected == "NAO_AVALIAVEL":
        assert all(item.grupo.value != "REQUISITO" for item in branch[0].avaliacoes_condicoes)


def test_distinct_rural_and_urban_rules_preserve_divergent_results_on_same_cable() -> None:
    session = _span_fixture(
        length=Decimal(90), origin=OrigemComprimentoVao.ANOTACAO_DESENHO
    ).session
    options = {
        item.id: item.codigo for group in session.catalogo.grupos_opcao for item in group.opcoes
    }
    cable_type = next(
        item
        for item in session.catalogo.itens_ativos(CategoriaElemento.CABO)
        if isinstance(item, TipoCabo)
        and options[item.tecnologia_rede_opcao_id] == "CONVENCIONAL_CAA"
    )
    session = replace(
        session,
        projeto=replace(
            session.projeto,
            elementos=tuple(
                replace(item, tipo_catalogo_id=cable_type.id) if isinstance(item, Cabo) else item
                for item in session.projeto.elementos
            ),
        ),
        propostas=tuple(
            replace(item, tipo_catalogo_sugerido_id=cable_type.id)
            if isinstance(item, PropostaElemento) and item.categoria is CategoriaElemento.CABO
            else item
            for item in session.propostas
        ),
    )
    result = _assert_union(session)
    rural = next(
        item for item in result.achados if item.regra_id == "nd22.cabo.rural-vao-maior-80-caa"
    )
    urban = next(
        item for item in result.achados if item.regra_id == "nd31.cabo.convencional-novo-urbano"
    )
    assert rural.alvo_id == urban.alvo_id
    assert rural.resultado.value == "CONFORME"
    assert urban.resultado.value == "DIVERGENCIA"
    assert rural.fonte != urban.fonte
    assert rural.id != urban.id
