from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.application.compliance_fact_providers import ContextoProvedorFatos
from zeny_project_handler.application.human_review import SessaoRevisao
from zeny_project_handler.application.topology_compliance import (
    _assess_paths,
    medir_extensao_rede_instalar,
    prover_fatos_topologicos,
)
from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    ExecucaoAnalise,
    PropostaElemento,
)
from zeny_project_handler.domain.catalog import TipoCabo, TipoEstruturaMt, TipoPoste
from zeny_project_handler.domain.compliance import AlvoConformidade, TipoEscopoConformidade
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    NivelRede,
    SituacaoProjeto,
    TipoEvidencia,
    TipoPontoRede,
    TipoTrechoRede,
)
from zeny_project_handler.domain.market import Mercado
from zeny_project_handler.domain.project import Cabo, EstruturaMt, PontoRede, Poste, Projeto
from zeny_project_handler.domain.values import CaixaPagina, GeometriaDocumento, PontoNormalizado

_NOW = datetime(2026, 8, 14, 18, tzinfo=UTC)


def test_path_assessment_uses_components_and_marker_position() -> None:
    cables, points, poles = _network(((0, 1, 400), (2, 3, 400)))

    disconnected = _assess_paths(cables, points, set())

    assert disconnected is not None
    assert disconnected.total_length_m == Decimal(800)
    assert disconnected.largest_component_m == Decimal(400)
    assert disconnected.maximum_uninterrupted_m == Decimal(400)

    cables, points, poles = _network(((0, 1, 450), (1, 2, 450)))
    centered = _assess_paths(cables, points, {poles[1]})
    displaced = _assess_paths(cables, points, {poles[0]})

    assert centered is not None and centered.maximum_uninterrupted_m == Decimal(450)
    assert displaced is not None and displaced.maximum_uninterrupted_m == Decimal(900)


def test_installed_extension_deduplicates_parallel_pole_route() -> None:
    cables, points, pole_ids = _network(((0, 1, 125), (0, 1, 125), (1, 2, 75)))
    catalog = carregar_catalogo_inicial()
    post_type = next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.POSTE)
        if isinstance(item, TipoPoste)
    )
    poles = tuple(
        Poste(
            id=pole_id,
            tipo_catalogo_id=post_type.id,
            situacao=SituacaoProjeto.INSTALAR,
        )
        for pole_id in pole_ids
    )
    project = Projeto(
        id=_id("extension-project"),
        nome="Extensão deduplicada",
        catalogo_versao_id=catalog.id,
        criado_em=_NOW,
        elementos=(*poles, *cables),
        pontos_rede=tuple(points.values()),
    )

    length, complete, _geometry = medir_extensao_rede_instalar(project)

    assert length == Decimal(200)
    assert complete is True


def test_installed_extension_uses_only_distribution_network_segments() -> None:
    cables, points, pole_ids = _network(((0, 1, 100), (2, 3, 800), (4, 5, 900)))
    catalog = carregar_catalogo_inicial()
    post_type = next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.POSTE)
        if isinstance(item, TipoPoste)
    )
    delivery_point_id = cables[2].ponto_destino_id
    typed_points = tuple(
        replace(point, poste_id=None, tipo=TipoPontoRede.ENTREGA)
        if point.id == delivery_point_id
        else point
        for point in points.values()
    )
    typed_cables = (
        cables[0],
        replace(cables[1], tipo_trecho=TipoTrechoRede.DESCONHECIDO),
        replace(cables[2], tipo_trecho=TipoTrechoRede.RAMAL_CONEXAO),
    )
    poles = tuple(
        Poste(
            id=pole_id,
            tipo_catalogo_id=post_type.id,
            situacao=SituacaoProjeto.INSTALAR,
        )
        for pole_id in pole_ids
    )
    project = Projeto(
        id=_id("typed-extension-project"),
        nome="Extensão apenas da rede de distribuição",
        catalogo_versao_id=catalog.id,
        criado_em=_NOW,
        elementos=(*poles, *typed_cables),
        pontos_rede=typed_points,
    )

    length, complete, _geometry = medir_extensao_rede_instalar(project)

    assert length == Decimal(100)
    assert complete is True


@pytest.mark.parametrize(
    ("with_ground", "expected_gap", "expected"), ((False, 300, False), (True, 150, True))
)
def test_neutral_grounding_uses_symbol_associated_to_route_pole(
    with_ground: bool,
    expected_gap: int,
    expected: bool,
) -> None:
    session, target = _provider_session(network="neutral", with_ground=with_ground)

    facts = {
        item.chave: item.valor
        for item in prover_fatos_topologicos(
            ContextoProvedorFatos(session, (target,), Mercado.URBANO)
        )
    }

    assert facts["projeto.neutro_maior_componente_m"] == Decimal(300)
    assert facts["projeto.neutro_maior_trecho_sem_aterramento_m"] == Decimal(expected_gap)
    assert facts["projeto.neutro_aterramento_periodico_suficiente"] is expected


def test_compact_anchoring_uses_actual_anchor_position() -> None:
    session, target = _provider_session(network="compact", with_ground=False)

    facts = {
        item.chave: item.valor
        for item in prover_fatos_topologicos(
            ContextoProvedorFatos(session, (target,), Mercado.URBANO)
        )
    }

    assert facts["projeto.rede_compacta_extensao_m"] == Decimal(900)
    assert facts["projeto.rede_compacta_maior_componente_m"] == Decimal(900)
    assert facts["projeto.rede_compacta_maior_trecho_sem_ancoragem_m"] == Decimal(450)
    assert facts["projeto.rede_compacta_ancoragem_suficiente"] is True
    assert facts["projeto.rede_compacta_aterramento_temporario_avaliado"] is True
    assert facts["projeto.rede_compacta_maior_trecho_sem_aterramento_m"] == Decimal(900)
    assert facts["projeto.rede_compacta_aterramento_temporario_suficiente"] is False


def test_violation_facts_point_to_an_edge_in_the_longest_uninterrupted_branch() -> None:
    session, target = _provider_session(
        network="compact",
        with_ground=True,
        lengths=(100, 600),
    )
    cables = tuple(item for item in session.projeto.elementos if isinstance(item, Cabo))
    short_cable = next(item for item in cables if item.comprimento_m == Decimal(100))
    violating_cable = next(item for item in cables if item.comprimento_m == Decimal(600))

    facts = {
        item.chave: item
        for item in prover_fatos_topologicos(
            ContextoProvedorFatos(session, (target,), Mercado.URBANO)
        )
    }

    assert facts["projeto.rede_compacta_maior_trecho_sem_ancoragem_m"].valor == Decimal(600)
    assert facts["projeto.rede_compacta_ancoragem_suficiente"].valor is False
    assert facts["projeto.rede_compacta_maior_trecho_sem_aterramento_m"].valor == Decimal(600)
    assert facts["projeto.rede_compacta_aterramento_temporario_suficiente"].valor is False
    for key in (
        "projeto.rede_compacta_maior_trecho_sem_ancoragem_m",
        "projeto.rede_compacta_ancoragem_suficiente",
        "projeto.rede_compacta_maior_trecho_sem_aterramento_m",
        "projeto.rede_compacta_aterramento_temporario_suficiente",
    ):
        assert facts[key].geometria == violating_cable.geometria
        assert facts[key].geometria != short_cable.geometria

    neutral_session, neutral_target = _provider_session(
        network="neutral",
        with_ground=True,
        lengths=(50, 250),
    )
    neutral_cables = tuple(
        item for item in neutral_session.projeto.elementos if isinstance(item, Cabo)
    )
    neutral_violation = next(item for item in neutral_cables if item.comprimento_m == Decimal(250))
    neutral_facts = {
        item.chave: item
        for item in prover_fatos_topologicos(
            ContextoProvedorFatos(neutral_session, (neutral_target,), Mercado.URBANO)
        )
    }

    assert neutral_facts["projeto.neutro_maior_trecho_sem_aterramento_m"].geometria == (
        neutral_violation.geometria
    )
    assert neutral_facts["projeto.neutro_aterramento_periodico_suficiente"].geometria == (
        neutral_violation.geometria
    )


def _provider_session(
    *,
    network: str,
    with_ground: bool,
    lengths: tuple[int, int] | None = None,
) -> tuple[SessaoRevisao, AlvoConformidade]:
    catalog = carregar_catalogo_inicial()
    option_codes = {
        option.id: option.codigo for group in catalog.grupos_opcao for option in group.opcoes
    }
    cable_type = next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.CABO)
        if isinstance(item, TipoCabo)
        and (
            item.codigo.startswith("N-")
            if network == "neutral"
            else option_codes[item.tecnologia_rede_opcao_id] == "PROTEGIDA"
        )
    )
    route_lengths = lengths or ((150, 150) if network == "neutral" else (450, 450))
    cables, points, pole_ids = _network(
        ((0, 1, route_lengths[0]), (1, 2, route_lengths[1])),
        cable_type=cable_type,
    )
    page = _page()
    post_type = next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.POSTE)
        if isinstance(item, TipoPoste)
    )
    poles = tuple(
        Poste(
            id=pole_id,
            tipo_catalogo_id=post_type.id,
            situacao=SituacaoProjeto.INSTALAR,
            geometria=_point_geometry(page.id, 0.2 + index * 0.3, 0.5),
        )
        for index, pole_id in enumerate(pole_ids)
    )
    pole_geometries = {pole.id: pole.geometria for pole in poles}

    def pole_geometry(pole_id: UUID) -> GeometriaDocumento:
        geometry = pole_geometries[pole_id]
        assert geometry is not None
        return geometry

    def point_pole_id(point: PontoRede) -> UUID:
        assert point.poste_id is not None
        return point.poste_id

    remapped_points = tuple(
        PontoRede(
            id=point.id,
            poste_id=point.poste_id,
            nome=point.nome,
            nivel_rede=point.nivel_rede,
            nivel_tensao_opcao_id=point.nivel_tensao_opcao_id,
            configuracao_fases_opcao_id=point.configuracao_fases_opcao_id,
            geometria=pole_geometry(point_pole_id(point)),
        )
        for point in points.values()
    )
    point_map = {item.id: item for item in remapped_points}

    def point_position(point_id: UUID) -> PontoNormalizado:
        geometry = point_map[point_id].geometria
        assert geometry is not None
        return geometry.pontos[0]

    remapped_cables = tuple(
        Cabo(
            id=cable.id,
            tipo_catalogo_id=cable_type.id,
            situacao=SituacaoProjeto.INSTALAR,
            geometria=GeometriaDocumento.polilinha(
                page.id,
                (
                    point_position(cable.ponto_origem_id),
                    point_position(cable.ponto_destino_id),
                ),
            ),
            ponto_origem_id=cable.ponto_origem_id,
            ponto_destino_id=cable.ponto_destino_id,
            tipo_trecho=cable.tipo_trecho,
            comprimento_m=cable.comprimento_m,
        )
        for cable in cables
    )
    structures: tuple[EstruturaMt, ...] = ()
    if network == "compact":
        anchor_type = next(
            item
            for item in catalog.itens_ativos(CategoriaElemento.ESTRUTURA_MT)
            if isinstance(item, TipoEstruturaMt) and item.ancoragem
        )
        structures = (
            EstruturaMt(
                id=_id("anchor"),
                tipo_catalogo_id=anchor_type.id,
                situacao=SituacaoProjeto.INSTALAR,
                geometria=pole_geometry(poles[1].id),
                poste_id=poles[1].id,
            ),
        )
    document = DocumentoProjeto(
        id=_id(f"document-{network}"),
        nome_arquivo=f"{network}.pdf",
        sha256="c" * 64,
        paginas=(page,),
        tamanho_bytes=100,
    )
    project = Projeto(
        id=_id(f"project-{network}-{with_ground}"),
        nome=f"Rede {network}",
        catalogo_versao_id=catalog.id,
        criado_em=_NOW,
        documentos=(document,),
        elementos=(*poles, *remapped_cables, *structures),
        pontos_rede=remapped_points,
    )
    execution = ExecucaoAnalise(
        id=_id(f"execution-{network}-{with_ground}"),
        projeto_id=project.id,
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=_NOW,
        finalizada_em=_NOW,
    )
    evidence = EvidenciaDocumento(
        id=_id(f"evidence-{network}-{with_ground}"),
        execucao_id=execution.id,
        pagina_id=page.id,
        tipo=TipoEvidencia.TEXTO,
        geometria=pole_geometry(poles[1].id),
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto="ATERRAMENTO",
        criada_em=_NOW,
    )
    proposals = (
        (
            PropostaElemento(
                id=_id(f"ground-{network}"),
                execucao_id=execution.id,
                categoria=CategoriaElemento.EQUIPAMENTO,
                situacao_projeto=SituacaoProjeto.INSTALAR,
                estado_revisao=EstadoRevisao.PROPOSTA,
                evidencia_ids=(evidence.id,),
                geometria=pole_geometry(poles[1].id),
                atributos_sugeridos=(
                    ("classe_equipamento", "ATERRAMENTO"),
                    ("reconhecido_por_simbologia", True),
                ),
                confianca=Decimal("0.95"),
            ),
        )
        if with_ground
        else ()
    )
    session = SessaoRevisao(
        projeto=project,
        catalogo=catalog,
        execucoes=(execution,),
        propostas=proposals,
        regioes=(),
        evidencias=(evidence,),
        decisoes=(),
        fontes_pdf=(),
    )
    target = AlvoConformidade(
        id=_id(f"target-{network}"),
        tipo=TipoEscopoConformidade.PROJETO,
        rotulo="Projeto",
    )
    return session, target


def _network(
    edges: tuple[tuple[int, int, int], ...],
    *,
    cable_type: TipoCabo | None = None,
) -> tuple[tuple[Cabo, ...], dict[UUID, PontoRede], tuple[UUID, ...]]:
    nodes = sorted({node for first, second, _length in edges for node in (first, second)})
    pole_ids = tuple(_id(f"pole-{node}") for node in nodes)
    by_node = dict(zip(nodes, pole_ids, strict=True))
    voltage_id = cable_type.nivel_tensao_opcao_id if cable_type else _id("voltage")
    phases_id = cable_type.configuracao_fases_opcao_id if cable_type else _id("phases")
    points = {
        _id(f"point-{node}"): PontoRede(
            id=_id(f"point-{node}"),
            poste_id=by_node[node],
            nome=f"P{node}",
            nivel_rede=NivelRede.BT
            if cable_type and cable_type.codigo.startswith("N-")
            else NivelRede.MT,
            nivel_tensao_opcao_id=voltage_id,
            configuracao_fases_opcao_id=phases_id,
        )
        for node in nodes
    }
    point_by_pole = {point.poste_id: point for point in points.values()}
    cables = tuple(
        Cabo(
            id=_id(f"cable-{index}"),
            tipo_catalogo_id=cable_type.id if cable_type else _id("cable-type"),
            situacao=SituacaoProjeto.INSTALAR,
            ponto_origem_id=point_by_pole[by_node[first]].id,
            ponto_destino_id=point_by_pole[by_node[second]].id,
            tipo_trecho=TipoTrechoRede.REDE_DISTRIBUICAO,
            comprimento_m=Decimal(length),
        )
        for index, (first, second, length) in enumerate(edges)
    )
    return cables, points, pole_ids


def _page() -> PaginaDocumento:
    size = Decimal(1000)
    box = CaixaPagina(Decimal(), Decimal(), size, size)
    return PaginaDocumento(_id("page"), 1, size, size, 0, box, box)


def _point_geometry(page_id: UUID, x: float, y: float) -> GeometriaDocumento:
    return GeometriaDocumento.ponto(
        page_id,
        PontoNormalizado(Decimal(str(x)), Decimal(str(y))),
    )


def _id(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"topology-path:{value}")
