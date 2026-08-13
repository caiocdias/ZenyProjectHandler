from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.application.analysis_regions import RegiaoAnalise
from zeny_project_handler.application.compliance_fact_providers import ContextoProvedorFatos
from zeny_project_handler.application.human_review import SessaoRevisao
from zeny_project_handler.application.project_compliance import (
    _targets,
    analisar_conformidade_projeto,
)
from zeny_project_handler.application.span_compliance import prover_fatos_vaos
from zeny_project_handler.domain.analysis import (
    DecisaoRevisao,
    EvidenciaDocumento,
    ExecucaoAnalise,
    OrigemObjetoPdf,
    PropostaElemento,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico, JsonPrimitive, TipoCabo
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    NivelRede,
    OrigemComprimentoVao,
    SituacaoProjeto,
    TipoDecisaoRevisao,
    TipoEvidencia,
    TipoOrigemPdf,
)
from zeny_project_handler.domain.project import Cabo, PontoRede, Poste, Projeto
from zeny_project_handler.domain.project_metadata import MetadadosProjeto
from zeny_project_handler.domain.values import (
    CaixaPagina,
    CoordenadaCampo,
    GeometriaDocumento,
    PontoNormalizado,
)

_NOW = datetime(2026, 8, 12, 20, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _SpanFixture:
    session: SessaoRevisao
    region_id: UUID
    page_id: UUID
    cable_geometry: GeometriaDocumento
    length_evidence: EvidenciaDocumento
    cable_evidence: EvidenciaDocumento
    coordinate_evidence_ids: tuple[UUID, ...]
    exception_evidence: EvidenciaDocumento


def test_annotated_length_preserves_origin_evidence_region_page_and_label_geometry() -> None:
    fixture = _span_fixture(
        length=Decimal("52"),
        origin=OrigemComprimentoVao.ANOTACAO_DESENHO,
    )
    targets = _targets(fixture.session)

    facts = prover_fatos_vaos(ContextoProvedorFatos(fixture.session, targets))

    fact = next(item for item in facts if item.chave == "vao.comprimento_m")
    target = next(item for item in targets if item.id == fact.alvo_id)
    assert fact.valor == Decimal("52")
    assert fact.origem == "detectar_vaos:ANOTACAO_DESENHO"
    assert fact.evidencia_ids == (fixture.length_evidence.id,)
    assert fact.geometria == fixture.length_evidence.geometria
    assert target.referencia_id == fixture.region_id
    assert target.pagina_id == fixture.page_id
    assert all(item.chave != "vao.aplicabilidade_excecao_45_60_resolvida" for item in facts)


def test_coordinate_length_preserves_endpoint_evidence_and_cable_geometry() -> None:
    fixture = _span_fixture(length=None, coordinates=True)

    facts = prover_fatos_vaos(ContextoProvedorFatos(fixture.session, _targets(fixture.session)))

    fact = next(item for item in facts if item.chave == "vao.comprimento_m")
    assert fact.valor == Decimal("50.00")
    assert fact.origem == "detectar_vaos:COORDENADAS"
    assert fact.evidencia_ids == (
        fixture.cable_evidence.id,
        *fixture.coordinate_evidence_ids,
    )
    assert fact.geometria == fixture.cable_geometry
    assert fact.geometria.pagina_id == fixture.page_id


def test_missing_length_does_not_publish_a_measurement() -> None:
    fixture = _span_fixture(length=None)

    facts = prover_fatos_vaos(ContextoProvedorFatos(fixture.session, _targets(fixture.session)))

    assert all(item.chave != "vao.comprimento_m" for item in facts)


def test_review_annotation_from_legacy_session_does_not_publish_span_measurement() -> None:
    fixture = _span_fixture(
        length=Decimal("52"),
        origin=OrigemComprimentoVao.ANOTACAO_DESENHO,
    )
    review_evidence = replace(
        fixture.length_evidence,
        origem_pdf=OrigemObjetoPdf(
            tipo=TipoOrigemPdf.ANOTACAO,
            numero_objeto=52,
            indice_anotacao=0,
            subtipo_anotacao="FreeText",
        ),
    )
    session = replace(
        fixture.session,
        evidencias=tuple(
            review_evidence if item.id == review_evidence.id else item
            for item in fixture.session.evidencias
        ),
    )

    facts = prover_fatos_vaos(ContextoProvedorFatos(session, _targets(session)))

    assert all(item.chave != "vao.comprimento_m" for item in facts)


@pytest.mark.parametrize(
    ("positive", "with_evidence", "expected"),
    (
        (True, True, True),
        (False, True, False),
        (True, False, False),
    ),
)
def test_span_exception_requires_positive_flag_and_traceable_evidence(
    positive: bool,
    with_evidence: bool,
    expected: bool,
) -> None:
    fixture = _span_fixture(
        length=Decimal("52"),
        origin=OrigemComprimentoVao.ANOTACAO_DESENHO,
        exception=positive,
        exception_evidence=with_evidence,
    )

    facts = prover_fatos_vaos(ContextoProvedorFatos(fixture.session, _targets(fixture.session)))
    exceptions = tuple(item for item in facts if item.chave == "vao.excecao_45_60_demonstrada")
    applicability = tuple(
        item for item in facts if item.chave == "vao.aplicabilidade_excecao_45_60_resolvida"
    )

    assert bool(exceptions) is expected
    assert bool(applicability) is expected
    if exceptions:
        assert exceptions[0].valor is True
        assert exceptions[0].evidencia_ids == (fixture.exception_evidence.id,)
        assert exceptions[0].geometria == fixture.exception_evidence.geometria


@pytest.mark.parametrize(
    ("length", "coordinates", "exception", "expected"),
    (
        (Decimal("40"), False, False, "CONFORME"),
        (Decimal("45"), False, False, "CONFORME"),
        (Decimal("52"), False, False, "NAO_AVALIAVEL"),
        (Decimal("60"), False, False, "NAO_AVALIAVEL"),
        (None, False, False, "NAO_AVALIAVEL"),
        (Decimal("52"), False, True, None),
        (Decimal("60"), False, True, None),
        (None, True, False, "NAO_AVALIAVEL"),
        (Decimal("61"), False, False, "DIVERGENCIA"),
        (Decimal("61"), False, True, "DIVERGENCIA"),
    ),
)
def test_current_span_rule_crosses_the_complete_provider_and_evaluation_flow(
    length: Decimal | None,
    coordinates: bool,
    exception: bool,
    expected: str | None,
) -> None:
    fixture = _span_fixture(
        length=length,
        origin=(OrigemComprimentoVao.ANOTACAO_DESENHO if length is not None else None),
        coordinates=coordinates,
        exception=exception,
    )

    result = analisar_conformidade_projeto(
        fixture.session,
        carregar_registro_conformidade_inicial(),
    )
    finding = next(
        (
            item
            for item in result.achados
            if item.regra_id == "nd31.vao.urbano-compacto-isolado"
            and next(target for target in result.alvos if target.id == item.alvo_id).referencia_id
            == fixture.region_id
        ),
        None,
    )

    assert (finding.resultado.value if finding is not None else None) == expected
    if finding is not None and expected == "DIVERGENCIA":
        fact = next(item for item in result.fatos if item.chave == "vao.comprimento_m")
        assert fact.id in finding.fato_ids
        assert fact.geometria is not None


def _span_fixture(
    *,
    length: Decimal | None,
    origin: OrigemComprimentoVao | None = None,
    coordinates: bool = False,
    exception: bool = False,
    exception_evidence: bool = True,
) -> _SpanFixture:
    catalog = carregar_catalogo_inicial()
    page = _page("primary")
    distractor_page = _page("distractor", number=2)
    document = DocumentoProjeto(
        id=_id("document"),
        nome_arquivo="vao-sintetico.pdf",
        sha256="a" * 64,
        paginas=(page, distractor_page),
        tamanho_bytes=100,
    )
    cable_type = _protected_cable(catalog)
    pole_type_id = catalog.itens_ativos(CategoriaElemento.POSTE)[0].id
    first_pole = Poste(
        id=_id("pole-1"),
        tipo_catalogo_id=pole_type_id,
        situacao=SituacaoProjeto.INSTALAR,
        geometria=_point(page.id, "0.20", "0.40"),
        coordenada_campo=_coordinate("100", "200") if coordinates else None,
    )
    second_pole = Poste(
        id=_id("pole-2"),
        tipo_catalogo_id=pole_type_id,
        situacao=SituacaoProjeto.INSTALAR,
        geometria=_point(page.id, "0.80", "0.40"),
        coordenada_campo=_coordinate("130", "240") if coordinates else None,
    )
    first_point = PontoRede(
        id=_id("network-point-1"),
        poste_id=first_pole.id,
        nome="P1-MT",
        nivel_rede=NivelRede.MT,
        nivel_tensao_opcao_id=cable_type.nivel_tensao_opcao_id,
        configuracao_fases_opcao_id=cable_type.configuracao_fases_opcao_id,
        geometria=first_pole.geometria,
    )
    second_point = PontoRede(
        id=_id("network-point-2"),
        poste_id=second_pole.id,
        nome="P2-MT",
        nivel_rede=NivelRede.MT,
        nivel_tensao_opcao_id=cable_type.nivel_tensao_opcao_id,
        configuracao_fases_opcao_id=cable_type.configuracao_fases_opcao_id,
        geometria=second_pole.geometria,
    )
    cable_geometry = GeometriaDocumento.polilinha(
        page.id,
        (
            PontoNormalizado(Decimal("0.20"), Decimal("0.40")),
            PontoNormalizado(Decimal("0.80"), Decimal("0.40")),
        ),
    )
    cable = Cabo(
        id=_id("cable"),
        tipo_catalogo_id=cable_type.id,
        situacao=SituacaoProjeto.INSTALAR,
        geometria=cable_geometry,
        ponto_origem_id=first_point.id,
        ponto_destino_id=second_point.id,
        comprimento_m=length,
        origem_comprimento=origin,
    )
    project = Projeto(
        id=_id("project"),
        nome="Projeto urbano sintético",
        catalogo_versao_id=catalog.id,
        criado_em=_NOW,
        documentos=(document,),
        elementos=(first_pole, second_pole, cable),
        pontos_rede=(first_point, second_point),
        metadados=MetadadosProjeto(tipo_servico="Rede urbana"),
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
    cable_evidence = _evidence(execution.id, page.id, "CABO PROTEGIDO", "0.50", "0.40")
    length_evidence = _evidence(execution.id, page.id, "52 m", "0.50", "0.34")
    first_coordinate = _evidence(execution.id, page.id, "E 100 N 200", "0.20", "0.44")
    second_coordinate = _evidence(execution.id, page.id, "E 130 N 240", "0.80", "0.44")
    positive_exception = _evidence(
        execution.id,
        page.id,
        "EXCEÇÃO SINTÉTICA COMPROVADA",
        "0.50",
        "0.48",
    )
    cable_attributes: list[tuple[str, JsonPrimitive]] = []
    if length is not None:
        cable_attributes.extend(
            (
                ("comprimento_m", length),
                ("comprimento_origem", "anotacao_desenho"),
                ("evidencia_comprimento_id", str(length_evidence.id)),
            )
        )
    if exception:
        cable_attributes.append(("excecao_45_60_demonstrada", True))
        if exception_evidence:
            cable_attributes.append(("evidencia_excecao_45_60_id", str(positive_exception.id)))
    cable_evidence_ids = [cable_evidence.id]
    if length is not None:
        cable_evidence_ids.append(length_evidence.id)
    if exception and exception_evidence:
        cable_evidence_ids.append(positive_exception.id)
    cable_proposal = _proposal(
        "cable-proposal",
        execution.id,
        cable_type.id,
        CategoriaElemento.CABO,
        cable_geometry,
        tuple(cable_evidence_ids),
        tuple(cable_attributes),
    )
    first_pole_proposal = _proposal(
        "pole-proposal-1",
        execution.id,
        pole_type_id,
        CategoriaElemento.POSTE,
        first_pole.geometria,
        (first_coordinate.id,),
        (("coordenada_leste", 100), ("coordenada_norte", 200)) if coordinates else (),
    )
    second_pole_proposal = _proposal(
        "pole-proposal-2",
        execution.id,
        pole_type_id,
        CategoriaElemento.POSTE,
        second_pole.geometria,
        (second_coordinate.id,),
        (("coordenada_leste", 130), ("coordenada_norte", 240)) if coordinates else (),
    )
    region = RegiaoAnalise(
        id=_id("region"),
        pagina_id=page.id,
        geometria=cable_geometry,
        elemento_ids=(cable_proposal.id,),
        rotulo_ponto="V1",
    )
    distractor_region = RegiaoAnalise(
        id=_id("distractor-region"),
        pagina_id=distractor_page.id,
        geometria=_point(distractor_page.id, "0.50", "0.50"),
        elemento_ids=(),
        rotulo_ponto="P99",
    )
    proposals = (cable_proposal, first_pole_proposal, second_pole_proposal)
    decisions = (
        _decision(cable_proposal.id, cable.id),
        _decision(first_pole_proposal.id, first_pole.id),
        _decision(second_pole_proposal.id, second_pole.id),
    )
    session = SessaoRevisao(
        projeto=project,
        catalogo=catalog,
        execucoes=(execution,),
        propostas=proposals,
        regioes=(region, distractor_region),
        evidencias=(
            cable_evidence,
            length_evidence,
            first_coordinate,
            second_coordinate,
            positive_exception,
        ),
        decisoes=decisions,
        fontes_pdf=(),
    )
    return _SpanFixture(
        session=session,
        region_id=region.id,
        page_id=page.id,
        cable_geometry=cable_geometry,
        length_evidence=length_evidence,
        cable_evidence=cable_evidence,
        coordinate_evidence_ids=(first_coordinate.id, second_coordinate.id),
        exception_evidence=positive_exception,
    )


def _protected_cable(catalog: CatalogoTecnico) -> TipoCabo:
    protected = next(
        option.id
        for group in catalog.grupos_opcao
        if group.chave == "tecnologia_rede"
        for option in group.opcoes
        if option.codigo == "PROTEGIDA"
    )
    return next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.CABO)
        if isinstance(item, TipoCabo) and item.tecnologia_rede_opcao_id == protected
    )


def _proposal(
    key: str,
    execution_id: UUID,
    catalog_item_id: UUID,
    category: CategoriaElemento,
    geometry: GeometriaDocumento | None,
    evidence_ids: tuple[UUID, ...],
    attributes: tuple[tuple[str, JsonPrimitive], ...],
) -> PropostaElemento:
    assert geometry is not None
    return PropostaElemento(
        id=_id(key),
        execucao_id=execution_id,
        categoria=category,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.CONFIRMADA,
        evidencia_ids=evidence_ids,
        geometria=geometry,
        tipo_catalogo_sugerido_id=catalog_item_id,
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


def _evidence(
    execution_id: UUID,
    page_id: UUID,
    content: str,
    x: str,
    y: str,
) -> EvidenciaDocumento:
    return EvidenciaDocumento(
        id=_id(f"evidence:{content}"),
        execucao_id=execution_id,
        pagina_id=page_id,
        tipo=TipoEvidencia.TEXTO,
        geometria=_point(page_id, x, y),
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto=content,
        criada_em=_NOW,
    )


def _page(key: str, *, number: int = 1) -> PaginaDocumento:
    width = Decimal("595")
    height = Decimal("842")
    box = CaixaPagina(Decimal(0), Decimal(0), width, height)
    return PaginaDocumento(
        id=_id(f"page:{key}"),
        numero=number,
        largura_pontos=width,
        altura_pontos=height,
        rotacao_graus=0,
        media_box=box,
        crop_box=box,
    )


def _point(page_id: UUID, x: str, y: str) -> GeometriaDocumento:
    return GeometriaDocumento.ponto(
        page_id,
        PontoNormalizado(Decimal(x), Decimal(y)),
    )


def _coordinate(east: str, north: str) -> CoordenadaCampo:
    return CoordenadaCampo(
        leste=Decimal(east),
        norte=Decimal(north),
        sistema_referencia="UTM",
    )


def _id(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"span-compliance:{value}")
