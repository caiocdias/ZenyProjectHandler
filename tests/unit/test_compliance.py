from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import pytest

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.compliance import (
    JsonComplianceRuleRegistry,
    carregar_registro_conformidade_inicial,
)
from zeny_project_handler.application.analysis_regions import RegiaoAnalise
from zeny_project_handler.application.compliance_evaluation import avaliar_regras_conformidade
from zeny_project_handler.application.human_review import SessaoRevisao
from zeny_project_handler.application.project_compliance import (
    _document_control_facts,
    _region_facts,
    analisar_conformidade_projeto,
)
from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    ExecucaoAnalise,
    OrigemObjetoPdf,
    PropostaElemento,
)
from zeny_project_handler.domain.catalog import (
    JsonPrimitive,
    TipoCabo,
    TipoEstruturaMt,
    TipoPoste,
)
from zeny_project_handler.domain.compliance import (
    AlvoConformidade,
    FatoConformidade,
    GrupoCondicaoConformidade,
    QuantificadorCondicao,
    ResultadoCondicaoConformidade,
    ResultadoConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    SituacaoProjeto,
    TipoEvidencia,
    TipoOrigemPdf,
)
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.domain.project_metadata import MetadadosProjeto
from zeny_project_handler.domain.values import (
    CaixaPagina,
    GeometriaDocumento,
    PontoNormalizado,
)


def test_initial_compliance_registry_is_stable_and_externalizable() -> None:
    first = carregar_registro_conformidade_inicial()
    second = carregar_registro_conformidade_inicial()
    path = (
        Path(__file__).parents[2]
        / "src"
        / "zeny_project_handler"
        / "adapters"
        / "compliance"
        / "data"
        / "regras_conformidade_v1.json"
    )

    assert first == JsonComplianceRuleRegistry(path).carregar()
    assert first.assinatura() == second.assinatura()
    assert len(first.assinatura()) == 64
    assert {rule.id for rule in first.regras} >= {
        "nd31.desenho.numero-projeto",
        "nd31.equipamento.estrutura-angulo",
        "nd31.vao.urbano-compacto-isolado",
        "nd31.cabo.convencional-novo-urbano",
        "nd93.compatibilidade.estrutura-poste-duplo-t",
    }


def test_project_compliance_extracts_header_without_deriving_spans_or_angles() -> None:
    session = _session_with_document_controls()

    result = analisar_conformidade_projeto(
        session,
        carregar_registro_conformidade_inicial(),
    )
    facts = {(item.chave, item.valor) for item in result.fatos}
    findings = {item.regra_id: item.resultado.value for item in result.achados}

    assert ("projeto.nota_servico", "1234567890") in facts
    assert ("projeto.escala", "1:1000") in facts
    assert ("projeto.formato_folha", "A4") in facts
    assert all(key not in {"vao.comprimento_m", "conexao.angulo_graus"} for key, _value in facts)
    assert findings["nd31.desenho.numero-projeto"] == "CONFORME"
    assert findings["nd31.equipamento.estrutura-angulo"] == "NAO_AVALIAVEL"
    assert findings["nd31.vao.urbano-compacto-isolado"] == "NAO_AVALIAVEL"
    assert any(
        item.grupo == "Assinaturas" and item.estado == "REQUER_REVISAO_VISUAL"
        for item in result.itens_documentais
    )


def test_documentation_lists_every_labeled_header_and_servitude_value() -> None:
    session = _session_with_document_controls()
    execution = session.execucoes[0]
    page_id = session.projeto.documentos[0].paginas[0].id
    added = (
        _text_evidence(execution.id, page_id, "SERVIDÃO", "0.20", "0.18"),
        _text_evidence(execution.id, page_id, "SOLIC.: AGNA DA SILVA MOURA", "0.12", "0.20"),
        _text_evidence(execution.id, page_id, "EXTENSÃO: 135m", "0.31", "0.20"),
        _text_evidence(execution.id, page_id, "INÍCIO: 465702.7772468", "0.12", "0.22"),
        _text_evidence(execution.id, page_id, "FINAL: 465800.7772517", "0.31", "0.22"),
        _text_evidence(execution.id, page_id, "Circuito: PYN 11", "0.10", "0.86"),
        _text_evidence(
            execution.id,
            page_id,
            "Dispositivo: CH. FUSÍVEL 31399-300A-6T-C",
            "0.10",
            "0.88",
        ),
        _text_evidence(
            execution.id,
            page_id,
            "Serviço: EXTENSÃO DE REDE / LIGAÇÃO NOVA",
            "0.45",
            "0.90",
        ),
        _text_evidence(execution.id, page_id, "Aprovação:", "0.10", "0.94"),
    )
    session = replace(session, evidencias=(*session.evidencias, *added))

    result = analisar_conformidade_projeto(
        session,
        carregar_registro_conformidade_inicial(),
    )
    servitude = {
        item.campo: item.valor for item in result.itens_documentais if item.grupo == "Servidão"
    }
    header = {
        item.campo: item.valor for item in result.itens_documentais if item.grupo == "Cabeçalho"
    }

    assert servitude == {
        "SOLIC.": "AGNA DA SILVA MOURA",
        "EXTENSÃO": "135m",
        "INÍCIO": "465702.7772468",
        "FINAL": "465800.7772517",
    }
    assert header["Circuito"] == "PYN 11"
    assert header["Dispositivo"] == "CH. FUSÍVEL 31399-300A-6T-C"
    assert header["Serviço"] == "EXTENSÃO DE REDE / LIGAÇÃO NOVA"
    assert header["Aprovação"] == "Não informado"


def test_document_control_facts_preserve_branch_order_ids_and_provenance() -> None:
    session = _session_with_document_controls()
    document = session.projeto.documentos[0]
    execution = session.execucoes[0]
    page_id = document.paginas[0].id
    servitude = _text_evidence(execution.id, page_id, "SERVIDÃO", "0.20", "0.18")
    servitude_field = _text_evidence(
        execution.id,
        page_id,
        "EXTENSÃO: 135m",
        "0.20",
        "0.20",
    )
    stamp = replace(
        _text_evidence(execution.id, page_id, "APROVADO", "0.80", "0.20"),
        origem_pdf=OrigemObjetoPdf(
            tipo=TipoOrigemPdf.ANOTACAO,
            indice_anotacao=0,
            subtipo_anotacao="Stamp",
        ),
    )
    empty_signature = replace(
        _text_evidence(execution.id, page_id, "Assinatura", "0.72", "0.88"),
        atributos_extraidos=(
            ("tipo_campo_formulario", "Sig"),
            ("campo_formulario_preenchido", False),
        ),
    )
    signed_signature = replace(
        _text_evidence(execution.id, page_id, "Responsável técnico", "0.75", "0.90"),
        atributos_extraidos=(
            ("tipo_campo_formulario", "Sig"),
            ("campo_formulario_preenchido", True),
        ),
    )
    evidence = (
        servitude,
        servitude_field,
        stamp,
        empty_signature,
        signed_signature,
    )
    target_id = uuid5(document.id, "characterization:document")

    first = _document_control_facts(document, target_id, evidence)
    second = _document_control_facts(document, target_id, evidence)
    facts, items = first

    assert first == second
    assert [fact.chave for fact in facts] == [
        "documento.servidao_mencionada",
        "documento.carimbo_candidato_quantidade",
        "documento.assinatura_pdf_preenchida",
    ]
    assert [fact.id for fact in facts] == [
        uuid5(
            target_id,
            f"documento.servidao_mencionada:True:menção textual:{servitude.id}",
        ),
        uuid5(
            target_id,
            "documento.carimbo_candidato_quantidade:1:"
            f"anotações PDF Stamp na zona de cabeçalho/rodapé:{stamp.id}",
        ),
        uuid5(
            target_id,
            "documento.assinatura_pdf_preenchida:True:campo PDF /Sig preenchido:"
            f"{signed_signature.id}",
        ),
    ]
    assert [(item.grupo, item.estado) for item in items] == [
        ("Servidão", "IDENTIFICADO"),
        ("Carimbos e selos", "REQUER_REVISAO_VISUAL"),
        ("Assinaturas", "ASSINATURA_PDF_PRESENTE"),
    ]
    assert items[0].evidencia_ids == (servitude_field.id,)
    assert items[1].evidencia_ids == (stamp.id,)
    assert items[2].evidencia_ids == (
        empty_signature.id,
        signed_signature.id,
    )


def test_review_comment_does_not_create_servitude_or_signature_facts() -> None:
    session = _session_with_document_controls()
    document = session.projeto.documentos[0]
    execution = session.execucoes[0]
    page_id = document.paginas[0].id
    review_comment = replace(
        _text_evidence(
            execution.id,
            page_id,
            "SERVIDÃO RESPONSÁVEL TÉCNICO",
            "0.75",
            "0.90",
        ),
        origem_pdf=OrigemObjetoPdf(
            tipo=TipoOrigemPdf.ANOTACAO,
            numero_objeto=88,
            indice_anotacao=0,
            subtipo_anotacao="FreeText",
        ),
    )

    facts, items = _document_control_facts(
        document,
        uuid5(document.id, "characterization:document"),
        (review_comment,),
    )

    assert all(
        item.chave not in {"documento.servidao_mencionada", "documento.assinatura_pdf_preenchida"}
        for item in facts
    )
    assert all(review_comment.id not in item.evidencia_ids for item in items)


def test_region_facts_preserve_semantic_order_and_deterministic_ids() -> None:
    session = _session_with_document_controls()
    region = session.regioes[0]
    execution = session.execucoes[0]
    risk = _text_evidence(
        execution.id,
        region.pagina_id,
        "RISCO DE ABALROAMENTO AVALIADO",
        "0.32",
        "0.36",
    )
    session = replace(session, evidencias=(*session.evidencias, risk))
    target = AlvoConformidade(
        id=uuid5(region.id, "characterization:region"),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="Região caracterizada",
        referencia_id=region.id,
        pagina_id=region.pagina_id,
        geometria=region.geometria,
    )

    first = _region_facts(session, region_targets={region.id: target})
    second = _region_facts(session, region_targets={region.id: target})

    assert first == second
    assert [fact.chave for fact in first] == [
        "regiao.equipamento_instalar",
        "regiao.equipamento_classe",
        "rede.contexto_urbano",
        "regiao.risco_abalroamento_avaliado",
        "cabo.tecnologia",
        "cabo.instalar_tecnologia",
    ]
    assert len({fact.id for fact in first}) == len(first)
    assert next(
        fact for fact in first if fact.chave == "regiao.risco_abalroamento_avaliado"
    ).evidencia_ids == (risk.id,)
    assert [fact.valor for fact in first] == [
        True,
        "TRANSFORMADOR",
        True,
        True,
        "PROTEGIDA",
        "PROTEGIDA",
    ]


@pytest.mark.parametrize(
    ("label", "expected_key"),
    (
        ("Bairro: ÁREA RURAL", "rede.contexto_rural"),
        ("Localização: Área urbana", "rede.contexto_urbano"),
        ("Contexto: Urbano", "rede.contexto_urbano"),
    ),
)
def test_explicit_header_area_publishes_network_context_without_metadata(
    label: str,
    expected_key: str,
) -> None:
    session = _session_with_document_controls()
    execution = session.execucoes[0]
    page_id = session.projeto.documentos[0].paginas[0].id
    context_evidence = _text_evidence(execution.id, page_id, label, "0.45", "0.90")
    session = replace(
        session,
        projeto=replace(session.projeto, metadados=None),
        evidencias=(*session.evidencias, context_evidence),
    )
    region = session.regioes[0]
    target = AlvoConformidade(
        id=uuid5(region.id, "characterization:region"),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="Região com contexto explícito",
        referencia_id=region.id,
        pagina_id=region.pagina_id,
        geometria=region.geometria,
    )

    facts = _region_facts(session, region_targets={region.id: target})
    context_fact = next(item for item in facts if item.chave == expected_key)

    assert context_fact.valor is True
    assert context_fact.origem == "classificação explícita no cabeçalho do projeto"
    assert context_fact.confianca == Decimal("0.95")
    assert context_fact.evidencia_ids == (context_evidence.id,)
    opposite_key = (
        "rede.contexto_urbano" if expected_key == "rede.contexto_rural" else "rede.contexto_rural"
    )
    assert all(item.chave != opposite_key for item in facts)


@pytest.mark.parametrize("text", ("RURAL", "ÁREA URBANA"))
def test_unlabeled_context_text_outside_header_does_not_activate_rules(text: str) -> None:
    session = _session_with_document_controls()
    execution = session.execucoes[0]
    page_id = session.projeto.documentos[0].paginas[0].id
    loose_text = _text_evidence(execution.id, page_id, text, "0.45", "0.35")
    session = replace(
        session,
        projeto=replace(session.projeto, metadados=None),
        evidencias=(*session.evidencias, loose_text),
    )
    region = session.regioes[0]
    target = AlvoConformidade(
        id=uuid5(region.id, "characterization:region"),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="Região sem campo de contexto",
        referencia_id=region.id,
        pagina_id=region.pagina_id,
        geometria=region.geometria,
    )

    facts = _region_facts(session, region_targets={region.id: target})

    assert all(item.chave not in {"rede.contexto_urbano", "rede.contexto_rural"} for item in facts)


@pytest.mark.parametrize("label", ("Contexto: Não urbana", "Bairro: Jardim Rural"))
def test_ambiguous_labeled_header_value_does_not_activate_context(label: str) -> None:
    session = _session_with_document_controls()
    execution = session.execucoes[0]
    page_id = session.projeto.documentos[0].paginas[0].id
    header = _text_evidence(execution.id, page_id, label, "0.45", "0.90")
    session = replace(
        session,
        projeto=replace(session.projeto, metadados=None),
        evidencias=(*session.evidencias, header),
    )
    region = session.regioes[0]
    target = AlvoConformidade(
        id=uuid5(region.id, "characterization:region"),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="Região com contexto ambíguo",
        referencia_id=region.id,
        pagina_id=region.pagina_id,
        geometria=region.geometria,
    )

    facts = _region_facts(session, region_targets={region.id: target})

    assert all(item.chave not in {"rede.contexto_urbano", "rede.contexto_rural"} for item in facts)


def test_conflicting_or_review_annotation_context_is_not_published() -> None:
    session = _session_with_document_controls()
    execution = session.execucoes[0]
    page_id = session.projeto.documentos[0].paginas[0].id
    rural_header = _text_evidence(
        execution.id,
        page_id,
        "Bairro: ÁREA RURAL",
        "0.45",
        "0.90",
    )
    conflicting_session = replace(
        session,
        evidencias=(*session.evidencias, rural_header),
    )
    review_annotation = replace(
        rural_header,
        id=uuid4(),
        origem_pdf=OrigemObjetoPdf(
            tipo=TipoOrigemPdf.ANOTACAO,
            numero_objeto=77,
            indice_anotacao=0,
            subtipo_anotacao="FreeText",
        ),
    )
    annotation_only_session = replace(
        session,
        projeto=replace(session.projeto, metadados=None),
        evidencias=(*session.evidencias, review_annotation),
    )
    region = session.regioes[0]
    target = AlvoConformidade(
        id=uuid5(region.id, "characterization:region"),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="Região sem contexto inequívoco",
        referencia_id=region.id,
        pagina_id=region.pagina_id,
        geometria=region.geometria,
    )

    for candidate_session in (conflicting_session, annotation_only_session):
        facts = _region_facts(candidate_session, region_targets={region.id: target})
        assert all(
            item.chave not in {"rede.contexto_urbano", "rede.contexto_rural"} for item in facts
        )


def test_installation_cable_fact_does_not_reclassify_existing_cable_as_new_work() -> None:
    session = _session_with_document_controls()
    cable = next(
        item
        for item in session.propostas
        if isinstance(item, PropostaElemento) and item.categoria is CategoriaElemento.CABO
    )
    session = replace(
        session,
        propostas=tuple(
            replace(item, situacao_projeto=SituacaoProjeto.EXISTENTE)
            if isinstance(item, PropostaElemento) and item.id == cable.id
            else item
            for item in session.propostas
        ),
    )
    region = session.regioes[0]
    target = AlvoConformidade(
        id=uuid5(region.id, "characterization:region"),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="Região caracterizada",
        referencia_id=region.id,
        pagina_id=region.pagina_id,
        geometria=region.geometria,
    )

    facts = _region_facts(session, region_targets={region.id: target})

    assert any(item.chave == "cabo.tecnologia" for item in facts)
    assert all(item.chave != "cabo.instalar_tecnologia" for item in facts)


def test_region_facts_publish_unambiguous_rural_structure_post_compatibility() -> None:
    session = _session_with_document_controls()
    catalog = session.catalogo
    page_id = session.projeto.documentos[0].paginas[0].id
    execution = session.execucoes[0]
    structure_item = next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.ESTRUTURA_MT)
        if isinstance(item, TipoEstruturaMt) and item.codigo == "CE1"
    )
    double_t_option = next(
        option.id
        for group in catalog.grupos_opcao
        if group.chave == "formato_poste"
        for option in group.opcoes
        if option.codigo == "DUPLO_T"
    )
    pole_item = next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.POSTE)
        if isinstance(item, TipoPoste) and item.formato_opcao_id == double_t_option
    )
    structure_evidence = _text_evidence(execution.id, page_id, "CE1", "0.30", "0.32")
    pole_evidence = _text_evidence(execution.id, page_id, "POSTE DUPLO T", "0.31", "0.32")
    structure = PropostaElemento(
        id=uuid4(),
        execucao_id=execution.id,
        categoria=CategoriaElemento.ESTRUTURA_MT,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.CONFIRMADA,
        evidencia_ids=(structure_evidence.id,),
        geometria=GeometriaDocumento.ponto(
            page_id,
            PontoNormalizado(Decimal("0.30"), Decimal("0.32")),
        ),
        tipo_catalogo_sugerido_id=structure_item.id,
        codigo_observado=structure_item.codigo,
        confianca=Decimal("0.99"),
    )
    pole = PropostaElemento(
        id=uuid4(),
        execucao_id=execution.id,
        categoria=CategoriaElemento.POSTE,
        situacao_projeto=SituacaoProjeto.EXISTENTE,
        estado_revisao=EstadoRevisao.CONFIRMADA,
        evidencia_ids=(pole_evidence.id,),
        geometria=GeometriaDocumento.ponto(
            page_id,
            PontoNormalizado(Decimal("0.31"), Decimal("0.32")),
        ),
        tipo_catalogo_sugerido_id=pole_item.id,
        codigo_observado=pole_item.codigo,
        confianca=Decimal("0.99"),
    )
    region = replace(session.regioes[0], elemento_ids=(structure.id, pole.id))
    session = replace(
        session,
        projeto=replace(
            session.projeto,
            metadados=MetadadosProjeto(tipo_servico="Rede rural"),
        ),
        propostas=(structure, pole),
        regioes=(region,),
        evidencias=(*session.evidencias, structure_evidence, pole_evidence),
    )
    target = AlvoConformidade(
        id=uuid5(region.id, "characterization:region"),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="Região rural caracterizada",
        referencia_id=region.id,
        pagina_id=region.pagina_id,
        geometria=region.geometria,
    )

    facts = _region_facts(session, region_targets={region.id: target})

    assert {(item.chave, item.valor) for item in facts} >= {
        ("rede.contexto_rural", True),
        ("regiao.estrutura_mt_instalar_codigo", "CE1"),
        ("regiao.poste_ativo_formato", "DUPLO_T"),
    }

    second_pole = replace(pole, id=uuid4())
    ambiguous_region = replace(
        region,
        elemento_ids=(structure.id, pole.id, second_pole.id),
    )
    ambiguous_session = replace(
        session,
        propostas=(structure, pole, second_pole),
        regioes=(ambiguous_region,),
    )
    ambiguous_target = replace(
        target,
        referencia_id=ambiguous_region.id,
        pagina_id=ambiguous_region.pagina_id,
        geometria=ambiguous_region.geometria,
    )

    ambiguous_facts = _region_facts(
        ambiguous_session,
        region_targets={ambiguous_region.id: ambiguous_target},
    )

    assert all(
        item.chave not in {"regiao.estrutura_mt_instalar_codigo", "regiao.poste_ativo_formato"}
        for item in ambiguous_facts
    )


@pytest.mark.parametrize(
    ("rule_id", "fact_values", "expected"),
    [
        (
            "nd31.cabo.convencional-novo-urbano",
            (("rede.contexto_urbano", True), ("cabo.instalar_tecnologia", "PROTEGIDA")),
            "CONFORME",
        ),
        (
            "nd31.cabo.convencional-novo-urbano",
            (
                ("rede.contexto_urbano", True),
                ("cabo.instalar_tecnologia", "CONVENCIONAL_CA"),
            ),
            "DIVERGENCIA",
        ),
        (
            "nd31.cabo.convencional-novo-urbano",
            (("rede.contexto_urbano", True),),
            "NAO_AVALIAVEL",
        ),
        (
            "nd31.cabo.convencional-novo-urbano",
            (
                ("rede.contexto_urbano", False),
                ("cabo.instalar_tecnologia", "CONVENCIONAL_CA"),
            ),
            None,
        ),
        (
            "nd93.compatibilidade.estrutura-poste-duplo-t",
            (
                ("rede.contexto_rural", True),
                ("regiao.estrutura_mt_instalar_codigo", "CE1"),
                ("regiao.poste_ativo_formato", "CIRCULAR"),
            ),
            "CONFORME",
        ),
        (
            "nd93.compatibilidade.estrutura-poste-duplo-t",
            (
                ("rede.contexto_rural", True),
                ("regiao.estrutura_mt_instalar_codigo", "CEM4"),
                ("regiao.poste_ativo_formato", "DUPLO_T"),
            ),
            "DIVERGENCIA",
        ),
        (
            "nd93.compatibilidade.estrutura-poste-duplo-t",
            (
                ("rede.contexto_rural", True),
                ("regiao.estrutura_mt_instalar_codigo", "CEJ2"),
            ),
            "NAO_AVALIAVEL",
        ),
        (
            "nd93.compatibilidade.estrutura-poste-duplo-t",
            (
                ("rede.contexto_rural", False),
                ("regiao.estrutura_mt_instalar_codigo", "CE1"),
                ("regiao.poste_ativo_formato", "DUPLO_T"),
            ),
            None,
        ),
    ],
)
def test_new_normative_rules_cover_conformity_divergence_unknown_and_context_exception(
    rule_id: str,
    fact_values: tuple[tuple[str, JsonPrimitive], ...],
    expected: str | None,
) -> None:
    target = AlvoConformidade(
        id=uuid4(),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="Região sintética",
    )
    findings = avaliar_regras_conformidade(
        carregar_registro_conformidade_inicial(),
        (target,),
        tuple(_fact(target.id, key, value) for key, value in fact_values),
    )
    finding = next((item for item in findings if item.regra_id == rule_id), None)

    assert (finding.resultado.value if finding else None) == expected


def test_compliance_requires_collision_review_and_honors_documented_span_exception() -> None:
    target = AlvoConformidade(
        id=uuid4(),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="Região P8",
    )
    facts = (
        _fact(target.id, "regiao.equipamento_instalar", True),
        _fact(target.id, "regiao.equipamento_classe", "TRANSFORMADOR"),
        _fact(target.id, "conexao.angulo_graus", Decimal("20")),
        _fact(target.id, "rede.contexto_urbano", True),
        _fact(target.id, "cabo.tecnologia", "PROTEGIDA"),
        _fact(target.id, "vao.comprimento_m", Decimal("52")),
        _fact(target.id, "vao.aplicabilidade_excecao_45_60_resolvida", True),
        _fact(target.id, "vao.excecao_45_60_demonstrada", True),
    )

    findings = avaliar_regras_conformidade(
        carregar_registro_conformidade_inicial(),
        (target,),
        facts,
    )
    by_rule = {item.regra_id: item.resultado.value for item in findings}

    assert by_rule["nd31.equipamento.estrutura-angulo"] == "CONFORME"
    assert by_rule["nd31.equipamento.risco-abalroamento"] == "NAO_AVALIAVEL"
    assert "nd31.vao.urbano-compacto-isolado" not in by_rule


def test_finding_keeps_observed_expected_values_and_condition_audit() -> None:
    target = AlvoConformidade(
        id=uuid4(),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="Região urbana",
    )
    facts = (
        _fact(target.id, "rede.contexto_urbano", True),
        _fact(target.id, "cabo.instalar_tecnologia", "CONVENCIONAL_CA"),
    )

    findings = avaliar_regras_conformidade(
        carregar_registro_conformidade_inicial(),
        (target,),
        facts,
    )
    finding = next(
        item for item in findings if item.regra_id == "nd31.cabo.convencional-novo-urbano"
    )
    requirement = next(
        item
        for item in finding.avaliacoes_condicoes
        if item.grupo is GrupoCondicaoConformidade.REQUISITO
    )

    assert requirement.valores_observados == ("CONVENCIONAL_CA",)
    assert requirement.valores_esperados == (
        "CONVENCIONAL_CA",
        "CONVENCIONAL_CA_CAA",
        "CONVENCIONAL_CAA",
    )
    assert requirement.resultado is ResultadoCondicaoConformidade.NAO_ATENDE
    assert requirement.fato_ids == (facts[1].id,)
    assert finding.fato_ids == (facts[0].id, facts[1].id)
    assert "Valor observado: CONVENCIONAL_CA" in finding.mensagem
    assert "esperado: cabo.instalar_tecnologia nao_em" in finding.mensagem


@pytest.mark.parametrize(
    ("quantifier", "known_length", "expected"),
    [
        (QuantificadorCondicao.QUALQUER, Decimal("40"), ResultadoConformidade.CONFORME),
        (
            QuantificadorCondicao.QUALQUER,
            Decimal("50"),
            ResultadoConformidade.NAO_AVALIAVEL,
        ),
        (
            QuantificadorCondicao.TODOS,
            Decimal("40"),
            ResultadoConformidade.NAO_AVALIAVEL,
        ),
        (QuantificadorCondicao.TODOS, Decimal("50"), ResultadoConformidade.DIVERGENCIA),
    ],
)
def test_condition_quantifiers_preserve_unknown_values(
    quantifier: QuantificadorCondicao,
    known_length: Decimal,
    expected: ResultadoConformidade,
) -> None:
    seed = carregar_registro_conformidade_inicial()
    span_rule = next(item for item in seed.regras if item.id == "nd31.vao.urbano-compacto-isolado")
    requirement = replace(span_rule.requisitos[0], quantificador=quantifier)
    registry = replace(seed, regras=(replace(span_rule, requisitos=(requirement,)),))
    target = AlvoConformidade(
        id=uuid4(),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="VÃ£o com leitura parcial",
    )
    facts = (
        _fact(target.id, "rede.contexto_urbano", True),
        _fact(target.id, "cabo.tecnologia", "PROTEGIDA"),
        _fact(target.id, "vao.aplicabilidade_excecao_45_60_resolvida", True),
        _fact(target.id, "vao.comprimento_m", known_length),
        _fact(target.id, "vao.comprimento_m", "ilegÃ­vel"),
    )

    finding = avaliar_regras_conformidade(registry, (target,), facts)[0]
    requirement_audit = next(
        item
        for item in finding.avaliacoes_condicoes
        if item.grupo is GrupoCondicaoConformidade.REQUISITO
    )

    assert finding.resultado is expected
    assert (
        requirement_audit.resultado
        is {
            ResultadoConformidade.CONFORME: ResultadoCondicaoConformidade.ATENDE,
            ResultadoConformidade.DIVERGENCIA: ResultadoCondicaoConformidade.NAO_ATENDE,
            ResultadoConformidade.NAO_AVALIAVEL: ResultadoCondicaoConformidade.DESCONHECIDO,
        }[expected]
    )


def test_unknown_project_context_is_not_reported_as_normative_divergence() -> None:
    target = AlvoConformidade(
        id=uuid4(),
        tipo=TipoEscopoConformidade.PROJETO,
        rotulo="Projeto sem contexto",
    )

    findings = avaliar_regras_conformidade(
        carregar_registro_conformidade_inicial(),
        (target,),
        (),
    )

    assert len(findings) == 2
    assert {item.resultado.value for item in findings} == {"NAO_AVALIAVEL"}


def _fact(target_id: UUID, key: str, value: JsonPrimitive) -> FatoConformidade:
    return FatoConformidade(
        id=uuid4(),
        alvo_id=target_id,
        chave=key,
        valor=value,
        origem="fixture",
    )


def _session_with_document_controls() -> SessaoRevisao:
    catalog = carregar_catalogo_inicial()
    box = CaixaPagina(Decimal(0), Decimal(0), Decimal(595), Decimal(842))
    page = PaginaDocumento(
        id=uuid4(),
        numero=1,
        largura_pontos=Decimal(595),
        altura_pontos=Decimal(842),
        rotacao_graus=0,
        media_box=box,
        crop_box=box,
    )
    document = DocumentoProjeto(
        id=uuid4(),
        nome_arquivo="projeto.pdf",
        sha256="a" * 64,
        paginas=(page,),
        tamanho_bytes=1000,
    )
    project = Projeto(
        id=uuid4(),
        nome="Projeto urbano",
        catalogo_versao_id=catalog.id,
        criado_em=datetime(2026, 7, 23, 12, tzinfo=UTC),
        documentos=(document,),
        metadados=MetadadosProjeto(tipo_servico="Rede urbana"),
    )
    execution = ExecucaoAnalise(
        id=uuid4(),
        projeto_id=project.id,
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=datetime(2026, 7, 23, 12, tzinfo=UTC),
        finalizada_em=datetime(2026, 7, 23, 12, 1, tzinfo=UTC),
    )
    header = _text_evidence(
        execution.id,
        page.id,
        "NS: 1234567890 ESCALA: 1:1000 FORMATO: A4 RESPONSÁVEL TÉCNICO",
        "0.70",
        "0.82",
    )
    cable_evidence = _text_evidence(execution.id, page.id, "CABO PROTEGIDO", "0.39", "0.31")
    equipment_evidence = _text_evidence(
        execution.id,
        page.id,
        "TRANSFORMADOR",
        "0.31",
        "0.34",
    )
    protected_option = next(
        option.id
        for group in catalog.grupos_opcao
        if group.chave == "tecnologia_rede"
        for option in group.opcoes
        if option.codigo == "PROTEGIDA"
    )
    cable_item = next(
        item
        for item in catalog.itens_ativos(CategoriaElemento.CABO)
        if isinstance(item, TipoCabo) and item.tecnologia_rede_opcao_id == protected_option
    )
    cable_geometry = GeometriaDocumento.polilinha(
        page.id,
        (
            PontoNormalizado(Decimal("0.10"), Decimal("0.30")),
            PontoNormalizado(Decimal("0.30"), Decimal("0.30")),
        ),
    )
    cable = PropostaElemento(
        id=uuid4(),
        execucao_id=execution.id,
        categoria=CategoriaElemento.CABO,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(cable_evidence.id,),
        geometria=cable_geometry,
        tipo_catalogo_sugerido_id=cable_item.id,
        codigo_observado=cable_item.codigo,
        confianca=Decimal("0.94"),
    )
    equipment_item = catalog.itens_ativos(CategoriaElemento.EQUIPAMENTO)[0]
    equipment = PropostaElemento(
        id=uuid4(),
        execucao_id=execution.id,
        categoria=CategoriaElemento.EQUIPAMENTO,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(equipment_evidence.id,),
        geometria=GeometriaDocumento.ponto(
            page.id,
            PontoNormalizado(Decimal("0.31"), Decimal("0.31")),
        ),
        tipo_catalogo_sugerido_id=equipment_item.id,
        confianca=Decimal("0.90"),
    )
    region = RegiaoAnalise(
        id=uuid4(),
        pagina_id=page.id,
        geometria=GeometriaDocumento.caixa(
            page.id,
            PontoNormalizado(Decimal("0.10"), Decimal("0.28")),
            PontoNormalizado(Decimal("0.40"), Decimal("0.40")),
        ),
        elemento_ids=(cable.id, equipment.id),
        rotulo_ponto="P7",
    )
    return SessaoRevisao(
        projeto=project,
        catalogo=catalog,
        execucoes=(execution,),
        propostas=(cable, equipment),
        regioes=(region,),
        evidencias=(header, cable_evidence, equipment_evidence),
        decisoes=(),
        fontes_pdf=(),
    )


def _text_evidence(
    execution_id: UUID,
    page_id: UUID,
    text: str,
    x: str,
    y: str,
) -> EvidenciaDocumento:
    return EvidenciaDocumento(
        id=uuid4(),
        execucao_id=execution_id,
        pagina_id=page_id,
        tipo=TipoEvidencia.TEXTO,
        geometria=GeometriaDocumento.ponto(
            page_id,
            PontoNormalizado(Decimal(x), Decimal(y)),
        ),
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto=text,
        criada_em=datetime(2026, 7, 23, 12, tzinfo=UTC),
    )
