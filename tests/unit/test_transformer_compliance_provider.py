from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.application.analysis_regions import RegiaoAnalise
from zeny_project_handler.application.human_review import SessaoRevisao
from zeny_project_handler.application.project_compliance import (
    ResultadoConformidadeProjeto,
    analisar_conformidade_projeto,
)
from zeny_project_handler.domain.analysis import (
    DecisaoRevisao,
    EvidenciaDocumento,
    ExecucaoAnalise,
    PropostaElemento,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico, TipoEquipamento, TipoPoste
from zeny_project_handler.domain.compliance import AchadoConformidade
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    SituacaoProjeto,
    TipoDecisaoRevisao,
    TipoEvidencia,
)
from zeny_project_handler.domain.project import Equipamento, Poste, Projeto, RelacaoConfirmada
from zeny_project_handler.domain.project_metadata import MetadadosProjeto
from zeny_project_handler.domain.values import CaixaPagina, GeometriaDocumento, PontoNormalizado

_NOW = datetime(2026, 8, 14, 14, tzinfo=UTC)
_SMALL_RULE = "nd31.transformador.poste-existente-30-75"
_LARGE_RULE = "nd31.transformador.poste-existente-150-300"


@dataclass(frozen=True, slots=True)
class _TransformerFixture:
    session: SessaoRevisao
    region_id: UUID


@pytest.mark.parametrize(
    ("equipment_code", "resistance", "post_format", "rule_id", "expected"),
    (
        ("-3-75", 300, "CIRCULAR", _SMALL_RULE, "CONFORME"),
        ("-3-75", 150, "CIRCULAR", _SMALL_RULE, "DIVERGENCIA"),
        ("-3-75", 300, "MADEIRA", _SMALL_RULE, "DIVERGENCIA"),
        ("-3-150", 600, "CIRCULAR", _LARGE_RULE, "CONFORME"),
        ("-3-150", 300, "CIRCULAR", _LARGE_RULE, "DIVERGENCIA"),
        ("-3-150", 600, "DUPLO_T", _LARGE_RULE, "DIVERGENCIA"),
    ),
)
def test_transformer_rules_correlate_exact_power_with_the_same_existing_post(
    equipment_code: str,
    resistance: int,
    post_format: str,
    rule_id: str,
    expected: str,
) -> None:
    fixture = _transformer_fixture(
        equipment_code=equipment_code,
        resistance=resistance,
        post_format=post_format,
    )

    result = analisar_conformidade_projeto(
        fixture.session,
        carregar_registro_conformidade_inicial(),
    )

    finding = _region_finding(result, fixture.region_id, rule_id)
    assert finding is not None
    assert finding.resultado.value == expected
    facts = {
        item.chave: item
        for item in result.fatos
        if item.chave.startswith("regiao.transformador_")
        or item.chave.startswith("regiao.poste_transformador_")
    }
    assert facts["regiao.transformador_trifasico_poste_existente_avaliavel"].valor is True
    assert facts["regiao.transformador_potencia_kva"].valor == int(equipment_code.rsplit("-", 1)[1])
    assert facts["regiao.poste_transformador_resistencia_dan"].valor == resistance
    assert facts["regiao.poste_transformador_formato"].valor == post_format
    assert facts["regiao.transformador_potencia_kva"].evidencia_ids
    assert facts["regiao.poste_transformador_resistencia_dan"].geometria is not None


@pytest.mark.parametrize(
    ("explicit_existing", "inferred_format"),
    (
        (False, False),
        (True, True),
    ),
)
def test_transformer_rule_uses_semantic_situation_and_canonical_format(
    explicit_existing: bool,
    inferred_format: bool,
) -> None:
    fixture = _transformer_fixture(
        equipment_code="-3-150",
        resistance=600,
        post_format="CIRCULAR",
        explicit_existing=explicit_existing,
        inferred_format=inferred_format,
    )

    result = analisar_conformidade_projeto(
        fixture.session,
        carregar_registro_conformidade_inicial(),
    )

    applicability = tuple(
        item
        for item in result.fatos
        if item.chave == "regiao.transformador_trifasico_poste_existente_avaliavel"
        and item.valor is True
    )
    assert bool(applicability)
    assert any(
        item.chave == "regiao.poste_transformador_formato" and item.valor == "CIRCULAR"
        for item in result.fatos
    )
    finding = _region_finding(result, fixture.region_id, _LARGE_RULE)
    assert finding is not None
    assert finding.resultado.value == "CONFORME"


def test_transformer_rule_uses_confirmed_relation_when_region_has_two_poles() -> None:
    fixture = _transformer_fixture(
        equipment_code="-3-75",
        resistance=300,
        post_format="CIRCULAR",
        second_pole=True,
    )

    result = analisar_conformidade_projeto(
        fixture.session,
        carregar_registro_conformidade_inicial(),
    )

    assert any(
        item.chave == "regiao.transformador_trifasico_poste_existente_avaliavel"
        and item.valor is True
        for item in result.fatos
    )
    finding = _region_finding(result, fixture.region_id, _SMALL_RULE)
    assert finding is not None
    assert finding.resultado.value == "CONFORME"


def test_transformer_rule_is_known_not_applicable_outside_urban_context() -> None:
    fixture = _transformer_fixture(
        equipment_code="-3-75",
        resistance=300,
        post_format="CIRCULAR",
        context="Rede rural",
    )

    result = analisar_conformidade_projeto(
        fixture.session,
        carregar_registro_conformidade_inicial(),
    )

    applicability = next(
        item
        for item in result.fatos
        if item.chave == "regiao.transformador_trifasico_poste_existente_avaliavel"
    )
    assert applicability.valor is False
    assert _region_finding(result, fixture.region_id, _SMALL_RULE) is None
    assert _region_finding(result, fixture.region_id, _LARGE_RULE) is None


def _transformer_fixture(
    *,
    equipment_code: str,
    resistance: int,
    post_format: str,
    explicit_existing: bool = True,
    inferred_format: bool = False,
    second_pole: bool = False,
    context: str = "Rede urbana",
) -> _TransformerFixture:
    catalog = carregar_catalogo_inicial()
    page = _page()
    document = DocumentoProjeto(
        id=_id("document"),
        nome_arquivo="transformador-sintetico.pdf",
        sha256="a" * 64,
        paginas=(page,),
        tamanho_bytes=100,
    )
    post_type = _post_type(catalog, resistance, post_format)
    equipment_type = _equipment_type(catalog, equipment_code)
    post_geometry = _point(page.id, "0.50", "0.50")
    equipment_geometry = _point(page.id, "0.51", "0.50")
    post = Poste(
        id=_id("post"),
        tipo_catalogo_id=post_type.id,
        situacao=SituacaoProjeto.EXISTENTE,
        geometria=post_geometry,
    )
    equipment = Equipamento(
        id=_id("equipment"),
        tipo_catalogo_id=equipment_type.id,
        situacao=SituacaoProjeto.INSTALAR,
        geometria=equipment_geometry,
        poste_id=post.id,
    )
    relation = RelacaoConfirmada(
        id=_id("relation"),
        tipo_relacao="INSTALADO_EM",
        origem_id=equipment.id,
        destino_id=post.id,
    )
    extra_post = (
        Poste(
            id=_id("second-post"),
            tipo_catalogo_id=post_type.id,
            situacao=SituacaoProjeto.EXISTENTE,
            geometria=_point(page.id, "0.54", "0.50"),
        )
        if second_pole
        else None
    )
    project = Projeto(
        id=_id("project"),
        nome="Projeto urbano sintético",
        catalogo_versao_id=catalog.id,
        criado_em=_NOW,
        documentos=(document,),
        elementos=(post, equipment, *((extra_post,) if extra_post is not None else ())),
        relacoes_confirmadas=(relation,),
        metadados=MetadadosProjeto(tipo_servico=context),
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
    post_evidence = _evidence(
        execution.id,
        page.id,
        post_type.codigo,
        post_geometry,
        color="#000000" if explicit_existing else None,
    )
    equipment_evidence = _evidence(
        execution.id,
        page.id,
        equipment_type.codigo,
        equipment_geometry,
        color="#008000",
    )
    post_proposal = _proposal(
        "post-proposal",
        execution.id,
        CategoriaElemento.POSTE,
        SituacaoProjeto.EXISTENTE,
        post_type.id,
        post_geometry,
        post_evidence.id,
        inferred_format=inferred_format,
    )
    equipment_proposal = _proposal(
        "equipment-proposal",
        execution.id,
        CategoriaElemento.EQUIPAMENTO,
        SituacaoProjeto.INSTALAR,
        equipment_type.id,
        equipment_geometry,
        equipment_evidence.id,
    )
    extra_proposal = (
        _proposal(
            "second-post-proposal",
            execution.id,
            CategoriaElemento.POSTE,
            SituacaoProjeto.EXISTENTE,
            post_type.id,
            extra_post.geometria,
            post_evidence.id,
        )
        if extra_post is not None and extra_post.geometria is not None
        else None
    )
    proposals = (
        post_proposal,
        equipment_proposal,
        *((extra_proposal,) if extra_proposal is not None else ()),
    )
    decisions = (
        _decision(post_proposal.id, post.id),
        _decision(equipment_proposal.id, equipment.id),
        *((_decision(extra_proposal.id, extra_post.id),) if extra_proposal and extra_post else ()),
    )
    region = RegiaoAnalise(
        id=_id("region"),
        pagina_id=page.id,
        geometria=GeometriaDocumento.caixa(
            page.id,
            PontoNormalizado(Decimal("0.45"), Decimal("0.45")),
            PontoNormalizado(Decimal("0.60"), Decimal("0.55")),
        ),
        elemento_ids=tuple(item.id for item in proposals),
        rotulo_ponto="P1",
    )
    return _TransformerFixture(
        session=SessaoRevisao(
            projeto=project,
            catalogo=catalog,
            execucoes=(execution,),
            propostas=proposals,
            regioes=(region,),
            evidencias=(post_evidence, equipment_evidence),
            decisoes=decisions,
            fontes_pdf=(),
        ),
        region_id=region.id,
    )


def _region_finding(
    result: ResultadoConformidadeProjeto,
    region_id: UUID,
    rule_id: str,
) -> AchadoConformidade | None:
    targets = {item.id: item for item in result.alvos}
    return next(
        (
            item
            for item in result.achados
            if item.regra_id == rule_id and targets[item.alvo_id].referencia_id == region_id
        ),
        None,
    )


def _post_type(catalog: CatalogoTecnico, resistance: int, post_format: str) -> TipoPoste:
    formats = {
        option.id: option.codigo
        for group in catalog.grupos_opcao
        if group.chave == "formato_poste"
        for option in group.opcoes
    }
    return next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.POSTE)
        if isinstance(item, TipoPoste)
        and item.resistencia_dan == resistance
        and formats[item.formato_opcao_id] == post_format
    )


def _equipment_type(catalog: CatalogoTecnico, code: str) -> TipoEquipamento:
    return next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.EQUIPAMENTO)
        if isinstance(item, TipoEquipamento) and item.codigo == code
    )


def _proposal(
    key: str,
    execution_id: UUID,
    category: CategoriaElemento,
    situation: SituacaoProjeto,
    catalog_item_id: UUID,
    geometry: GeometriaDocumento,
    evidence_id: UUID,
    *,
    inferred_format: bool = False,
) -> PropostaElemento:
    attributes = (("catalogo_inferido", True),) if inferred_format else ()
    return PropostaElemento(
        id=_id(key),
        execucao_id=execution_id,
        categoria=category,
        situacao_projeto=situation,
        estado_revisao=EstadoRevisao.CONFIRMADA,
        evidencia_ids=(evidence_id,),
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
    geometry: GeometriaDocumento,
    *,
    color: str | None,
) -> EvidenciaDocumento:
    return EvidenciaDocumento(
        id=_id(f"evidence:{content}:{color}"),
        execucao_id=execution_id,
        pagina_id=page_id,
        tipo=TipoEvidencia.TEXTO,
        geometria=geometry,
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto=content,
        criada_em=_NOW,
        atributos_extraidos=(("cor", color),) if color is not None else (),
    )


def _page() -> PaginaDocumento:
    width = Decimal("595")
    height = Decimal("842")
    box = CaixaPagina(Decimal(0), Decimal(0), width, height)
    return PaginaDocumento(
        id=_id("page"),
        numero=1,
        largura_pontos=width,
        altura_pontos=height,
        rotacao_graus=0,
        media_box=box,
        crop_box=box,
    )


def _point(page_id: UUID, x: str, y: str) -> GeometriaDocumento:
    return GeometriaDocumento.ponto(page_id, PontoNormalizado(Decimal(x), Decimal(y)))


def _id(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"transformer-compliance:{value}")
