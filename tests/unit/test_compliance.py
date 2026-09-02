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
    _cable_technology_facts,
    _document_control_facts,
    _region_fact_context,
    _region_facts,
    analisar_conformidade_projeto,
    detectar_gatilhos_acoes_projeto,
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
    TipoTrechoRede,
)
from zeny_project_handler.domain.market import Mercado
from zeny_project_handler.domain.project import Cabo, Poste, Projeto
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
        mercado=Mercado.URBANO,
    )
    facts = {(item.chave, item.valor) for item in result.fatos}
    findings = {item.regra_id: item.resultado.value for item in result.achados}

    assert ("projeto.nota_servico", "1234567890") in facts
    assert ("projeto.nota_servico_cabecalho", "1234567890") in facts
    assert all(key != "projeto.nota_servico_divergencia" for key, _value in facts)
    assert ("projeto.escala", "1:1000") in facts
    assert ("projeto.formato_folha", "A4") in facts
    assert all(key not in {"vao.comprimento_m", "conexao.angulo_graus"} for key, _value in facts)
    assert findings["nd31.desenho.numero-projeto"] == "CONFORME"
    assert "nd31.equipamento.estrutura-angulo" not in findings
    assert "nd31.vao.urbano-compacto-isolado" not in findings
    assert any(
        item.grupo == "Assinaturas" and item.estado == "IDENTIFICADO"
        for item in result.itens_documentais
    )


def test_project_service_note_rule_alerts_when_pdf_header_differs_from_project_name() -> None:
    session = _session_with_document_controls()
    body_reference = _text_evidence(
        session.execucoes[0].id,
        session.projeto.documentos[0].paginas[0].id,
        "REFERÊNCIA NO CORPO — NS: 0987654321",
        "0.45",
        "0.20",
    )
    session = replace(
        session,
        projeto=replace(session.projeto, nome="0987654321"),
        evidencias=(*session.evidencias, body_reference),
    )

    result = analisar_conformidade_projeto(
        session,
        carregar_registro_conformidade_inicial(),
        mercado=Mercado.URBANO,
    )

    finding = next(
        item for item in result.achados if item.regra_id == "nd31.desenho.numero-projeto"
    )
    facts = {(item.chave, item.valor) for item in result.fatos}
    header_evidence = next(
        item for item in session.evidencias if "NS:" in (item.conteudo_bruto or "")
    )
    divergence_fact = next(
        item for item in result.fatos if item.chave == "projeto.nota_servico_divergencia"
    )
    assert ("projeto.nota_servico", "0987654321") in facts
    assert ("projeto.nota_servico_cabecalho", "1234567890") in facts
    assert ("projeto.nota_servico_cabecalho", "0987654321") not in facts
    assert (
        "projeto.nota_servico_divergencia",
        "cabeçalho PDF: 1234567890; nome do projeto: 0987654321",
    ) in facts
    assert finding.resultado is ResultadoConformidade.DIVERGENCIA
    assert "igual à NS usada como nome do projeto" in finding.mensagem
    assert "cabeçalho PDF: 1234567890" in finding.mensagem
    assert "nome do projeto: 0987654321" in finding.mensagem
    assert header_evidence.id in finding.evidencia_ids
    assert divergence_fact.id in finding.fato_ids
    assert divergence_fact.geometria == header_evidence.geometria


def test_project_service_note_rule_accepts_full_project_number_header_label() -> None:
    session = _session_with_document_controls()
    header = session.evidencias[0]
    session = replace(
        session,
        projeto=replace(session.projeto, nome="0987654321"),
        evidencias=(
            replace(
                header,
                conteudo_bruto=(
                    "NÚMERO DO PROJETO: 1234567890 ESCALA: 1:1000 FORMATO: A4 RESPONSÁVEL TÉCNICO"
                ),
            ),
            *session.evidencias[1:],
        ),
    )

    result = analisar_conformidade_projeto(
        session,
        carregar_registro_conformidade_inicial(),
        mercado=Mercado.URBANO,
    )

    finding = next(
        item for item in result.achados if item.regra_id == "nd31.desenho.numero-projeto"
    )
    assert finding.resultado is ResultadoConformidade.DIVERGENCIA
    assert any(
        item.chave == "projeto.nota_servico_cabecalho" and item.valor == "1234567890"
        for item in result.fatos
    )


def test_project_service_note_ignores_divergent_ns_reference_in_drawing_body() -> None:
    session = _session_with_document_controls()
    body_reference = _text_evidence(
        session.execucoes[0].id,
        session.projeto.documentos[0].paginas[0].id,
        "NOTA DE CAMPO — NS: 0987654321",
        "0.45",
        "0.20",
    )
    session = replace(session, evidencias=(*session.evidencias, body_reference))

    result = analisar_conformidade_projeto(
        session,
        carregar_registro_conformidade_inicial(),
        mercado=Mercado.URBANO,
    )

    facts = {(item.chave, item.valor) for item in result.fatos}
    assert ("projeto.nota_servico_cabecalho", "1234567890") in facts
    assert ("projeto.nota_servico_cabecalho", "0987654321") not in facts
    assert all(item.chave != "projeto.nota_servico_divergencia" for item in result.fatos)
    finding = next(
        item for item in result.achados if item.regra_id == "nd31.desenho.numero-projeto"
    )
    assert finding.resultado is ResultadoConformidade.CONFORME


@pytest.mark.parametrize(
    ("identifiers", "expected_sequence", "expected_result"),
    (
        (("P1", "P2", "P3"), True, ResultadoConformidade.CONFORME),
        (("P1", "P3", "P4"), False, ResultadoConformidade.DIVERGENCIA),
    ),
)
def test_project_automation_evaluates_document_pack_and_post_sequence(
    identifiers: tuple[str, ...],
    expected_sequence: bool,
    expected_result: ResultadoConformidade,
) -> None:
    session = _session_with_document_controls()
    page_id = session.projeto.documentos[0].paginas[0].id
    execution_id = session.execucoes[0].id
    pole_type = next(
        item
        for item in session.catalogo.itens_ativos(CategoriaElemento.POSTE)
        if isinstance(item, TipoPoste)
    )
    poles = tuple(
        Poste(
            id=uuid4(),
            tipo_catalogo_id=pole_type.id,
            situacao=SituacaoProjeto.EXISTENTE,
            identificador_operacional=identifier,
            geometria=GeometriaDocumento.ponto(
                page_id,
                PontoNormalizado(Decimal("0.20") + Decimal(index) / 10, Decimal("0.45")),
            ),
        )
        for index, identifier in enumerate(identifiers)
    )
    package_evidence = _text_evidence(
        execution_id,
        page_id,
        "RELAÇÃO DE MATERIAIS E ORÇAMENTO · MEMÓRIA DE CÁLCULO",
        "0.50",
        "0.80",
    )
    session = replace(
        session,
        projeto=replace(session.projeto, elementos=poles),
        evidencias=(*session.evidencias, package_evidence),
    )

    result = analisar_conformidade_projeto(
        session,
        carregar_registro_conformidade_inicial(),
        mercado=Mercado.URBANO,
    )
    facts = {item.chave: item.valor for item in result.fatos}
    findings = {item.regra_id: item.resultado for item in result.achados}

    assert facts["projeto.relacao_materiais_orcamento_identificada"] is True
    assert facts["projeto.memoria_calculo_identificada"] is True
    assert facts["projeto.postes_total"] == 3
    assert facts["projeto.postes_numeracao_sequencial"] is expected_sequence
    assert findings["nd31.documentacao.relacao-materiais-orcamento"] is (
        ResultadoConformidade.CONFORME
    )
    assert findings["nd31.documentacao.memoria-calculo"] is ResultadoConformidade.CONFORME
    assert findings["nd31.desenho.numeracao-postes"] is expected_result


def test_rural_and_topological_rules_are_deterministic() -> None:
    project_target = AlvoConformidade(
        id=uuid4(),
        tipo=TipoEscopoConformidade.PROJETO,
        rotulo="Projeto rural",
    )
    region_target = AlvoConformidade(
        id=uuid4(),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="Região rural",
    )
    divergent_facts = (
        _fact(project_target.id, "rede.contexto_rural", True),
        _fact(project_target.id, "projeto.extensao_rede_instalar_avaliada", True),
        _fact(project_target.id, "projeto.extensao_rede_instalar_m", Decimal("350")),
        _fact(project_target.id, "projeto.prordr_identificado", False),
        _fact(project_target.id, "projeto.rede_compacta_extensao_m", Decimal("600")),
        _fact(project_target.id, "projeto.rede_compacta_maior_componente_m", Decimal("600")),
        _fact(project_target.id, "projeto.rede_compacta_ancoragem_avaliada", True),
        _fact(project_target.id, "projeto.rede_compacta_ancoragem_suficiente", False),
        _fact(region_target.id, "rede.contexto_rural", True),
        _fact(region_target.id, "vao.comprimento_m", Decimal("100")),
        _fact(region_target.id, "cabo.instalar_tecnologia", "CONVENCIONAL_CA"),
        _fact(region_target.id, "regiao.transformador_instalar", True),
        _fact(
            region_target.id,
            "regiao.poste_equipamento_instalar_resistencia_dan",
            Decimal("300"),
        ),
        _fact(region_target.id, "regiao.poste_equipamento_instalar_formato", "DUPLO_T"),
        _fact(region_target.id, "regiao.transicao_rede", True),
        _fact(region_target.id, "conexao.angulo_graus", Decimal("20")),
        _fact(region_target.id, "regiao.para_raios_mt_requerido", True),
        _fact(region_target.id, "regiao.para_raios_mt_requisito_presente", False),
    )
    corrected_values: dict[str, JsonPrimitive] = {
        "projeto.prordr_identificado": True,
        "projeto.rede_compacta_ancoragem_suficiente": True,
        "cabo.instalar_tecnologia": "CONVENCIONAL_CAA",
        "regiao.poste_equipamento_instalar_resistencia_dan": Decimal("600"),
        "regiao.poste_equipamento_instalar_formato": "CIRCULAR",
        "conexao.angulo_graus": Decimal("0"),
        "regiao.para_raios_mt_requisito_presente": True,
    }
    corrected_facts = tuple(
        replace(item, valor=corrected_values.get(item.chave, item.valor))
        for item in divergent_facts
    )
    rule_ids = {
        "nd22.projeto.prordr-acima-300",
        "nd22.cabo.rural-vao-maior-80-caa",
        "nd93.transformador.poste-novo-rural",
        "nd93.rede.transicao-sem-angulo",
        "nd31.rede.para-raios-mt-fim-transicao",
        "nd93.rede.compacta-ancoragem-500m",
    }

    divergent = avaliar_regras_conformidade(
        carregar_registro_conformidade_inicial(),
        (project_target, region_target),
        divergent_facts,
    )
    corrected = avaliar_regras_conformidade(
        carregar_registro_conformidade_inicial(),
        (project_target, region_target),
        corrected_facts,
    )

    assert {
        item.regra_id for item in divergent if item.resultado is ResultadoConformidade.DIVERGENCIA
    } >= rule_ids
    assert {
        item.regra_id for item in corrected if item.resultado is ResultadoConformidade.CONFORME
    } >= rule_ids


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
        mercado=Mercado.URBANO,
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


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("Impacto Ambiental: Sim", True),
        ("  IMPÁCTO   AMBIENTAL :  sim  ", True),
        ("Impacto Ambiental: Não", False),
        ("Impacto Ambiental:", False),
        ("Impacto Ambiental: SIMULAÇÃO", False),
    ),
)
def test_environmental_impact_trigger_requires_exact_sim_in_header(
    text: str,
    expected: bool,
) -> None:
    session = _session_with_document_controls()
    evidence = _text_evidence(
        session.execucoes[0].id,
        session.projeto.documentos[0].paginas[0].id,
        text,
        "0.70",
        "0.88",
    )
    triggers = detectar_gatilhos_acoes_projeto(
        replace(session, evidencias=(*session.evidencias, evidence))
    )

    assert bool(triggers.impacto_ambiental_sim) is expected
    assert (evidence.id in {item.id for item in triggers.impacto_ambiental_sim}) is expected


def test_action_triggers_ignore_body_and_review_comments_and_keep_reading_order() -> None:
    session = _session_with_document_controls()
    execution_id = session.execucoes[0].id
    page_id = session.projeto.documentos[0].paginas[0].id
    later = _text_evidence(
        execution_id,
        page_id,
        "Impacto Ambiental: SIM",
        "0.70",
        "0.92",
    )
    earlier = _text_evidence(
        execution_id,
        page_id,
        "Impacto Ambiental: Sim",
        "0.70",
        "0.84",
    )
    body = _text_evidence(
        execution_id,
        page_id,
        "Impacto Ambiental: Sim",
        "0.20",
        "0.20",
    )
    servitude = _text_evidence(
        execution_id,
        page_id,
        "FAIXA DE DOMÍNIO",
        "0.30",
        "0.30",
    )
    review_comment = replace(
        _text_evidence(
            execution_id,
            page_id,
            "Impacto Ambiental: Sim · SERVIDÃO",
            "0.75",
            "0.86",
        ),
        origem_pdf=OrigemObjetoPdf(
            tipo=TipoOrigemPdf.ANOTACAO,
            numero_objeto=91,
            indice_anotacao=0,
            subtipo_anotacao="FreeText",
        ),
    )
    triggers = detectar_gatilhos_acoes_projeto(
        replace(
            session,
            evidencias=(
                *session.evidencias,
                later,
                review_comment,
                body,
                servitude,
                earlier,
            ),
        )
    )

    assert tuple(item.id for item in triggers.impacto_ambiental_sim) == (
        earlier.id,
        later.id,
    )
    assert tuple(item.id for item in triggers.servidao_mencionada) == (servitude.id,)


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
        ("Carimbos e selos", "IDENTIFICADO"),
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

    first = _region_facts(
        session,
        mercado=Mercado.URBANO,
        region_targets={region.id: target},
    )
    second = _region_facts(
        session,
        mercado=Mercado.URBANO,
        region_targets={region.id: target},
    )

    assert first == second
    assert [fact.chave for fact in first] == [
        "regiao.equipamento_instalar",
        "regiao.equipamento_classe",
        "rede.contexto_urbano",
        "regiao.risco_abalroamento_avaliado",
        "regiao.transformador_trifasico_poste_existente_avaliavel",
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
        False,
    ]


@pytest.mark.parametrize(
    ("mercado", "metadata_context", "header_context", "expected_key"),
    (
        (Mercado.URBANO, "Rede rural", "Bairro: ÁREA RURAL", "rede.contexto_urbano"),
        (Mercado.RURAL, "Rede urbana", "Contexto: Urbano", "rede.contexto_rural"),
    ),
)
def test_external_market_is_the_only_context_source_for_project_and_regions(
    mercado: Mercado,
    metadata_context: str,
    header_context: str,
    expected_key: str,
) -> None:
    session = _session_with_document_controls()
    execution = session.execucoes[0]
    page_id = session.projeto.documentos[0].paginas[0].id
    conflicting_header = _text_evidence(
        execution.id,
        page_id,
        header_context,
        "0.45",
        "0.90",
    )
    first_region = session.regioes[0]
    second_region = replace(
        first_region,
        id=uuid4(),
        rotulo_ponto="P8",
    )
    session = replace(
        session,
        projeto=replace(
            session.projeto,
            metadados=MetadadosProjeto(tipo_servico=metadata_context),
        ),
        regioes=(first_region, second_region),
        evidencias=(*session.evidencias, conflicting_header),
    )
    result = analisar_conformidade_projeto(
        session,
        carregar_registro_conformidade_inicial(),
        mercado=mercado,
    )
    expected_target_ids = {
        item.id
        for item in result.alvos
        if item.tipo in {TipoEscopoConformidade.PROJETO, TipoEscopoConformidade.REGIAO}
    }
    context_facts = tuple(
        item
        for item in result.fatos
        if item.chave in {"rede.contexto_urbano", "rede.contexto_rural"}
    )
    opposite_key = (
        "rede.contexto_rural" if expected_key == "rede.contexto_urbano" else "rede.contexto_urbano"
    )

    assert {item.alvo_id for item in context_facts} == expected_target_ids
    assert all(item.chave == expected_key and item.valor is True for item in context_facts)
    assert all(item.chave != opposite_key for item in result.fatos)
    assert all(item.confianca == Decimal("1") for item in context_facts)
    assert all(item.origem == "consulta ao cadastro de Notas de Serviço" for item in context_facts)
    assert all(item.evidencia_ids == () and item.geometria is None for item in context_facts)


@pytest.mark.parametrize(
    ("mercado", "expected_rule", "opposite_rule"),
    (
        (
            Mercado.URBANO,
            "nd31.cabo.convencional-novo-urbano",
            "nd93.compatibilidade.estrutura-poste-duplo-t",
        ),
        (
            Mercado.RURAL,
            "nd93.compatibilidade.estrutura-poste-duplo-t",
            "nd31.cabo.convencional-novo-urbano",
        ),
    ),
)
def test_existing_when_semantics_select_only_rules_for_external_market(
    mercado: Mercado,
    expected_rule: str,
    opposite_rule: str,
) -> None:
    seed = carregar_registro_conformidade_inicial()
    selected = tuple(
        replace(
            rule,
            aplicabilidade=tuple(
                condition
                for condition in rule.aplicabilidade
                if condition.chave_fato.startswith("rede.contexto_")
            ),
            excecoes=(),
        )
        for rule in seed.regras
        if rule.id in {expected_rule, opposite_rule}
    )
    registry = replace(seed, regras=selected)

    result = analisar_conformidade_projeto(
        _session_with_document_controls(),
        registry,
        mercado=mercado,
    )

    finding_ids = {item.regra_id for item in result.achados}
    assert expected_rule in finding_ids
    assert opposite_rule not in finding_ids


def test_unconfirmed_cable_does_not_publish_network_rule_facts() -> None:
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

    facts = _region_facts(
        session,
        mercado=Mercado.URBANO,
        region_targets={region.id: target},
    )

    assert all(item.chave not in {"cabo.tecnologia", "cabo.instalar_tecnologia"} for item in facts)


@pytest.mark.parametrize(
    ("segment_type", "expected"),
    (
        (TipoTrechoRede.REDE_DISTRIBUICAO, True),
        (TipoTrechoRede.RAMAL_CONEXAO, False),
        (TipoTrechoRede.DESCONHECIDO, False),
    ),
)
def test_cable_rule_facts_require_a_confirmed_distribution_network_segment(
    segment_type: TipoTrechoRede,
    expected: bool,
) -> None:
    session = _session_with_document_controls()
    proposal = next(
        item
        for item in session.propostas
        if isinstance(item, PropostaElemento) and item.categoria is CategoriaElemento.CABO
    )
    assert proposal.tipo_catalogo_sugerido_id is not None
    confirmed = Cabo(
        id=uuid4(),
        tipo_catalogo_id=proposal.tipo_catalogo_sugerido_id,
        situacao=proposal.situacao_projeto,
        ponto_origem_id=uuid4(),
        ponto_destino_id=uuid4(),
        tipo_trecho=segment_type,
    )
    context = replace(
        _region_fact_context(session, Mercado.URBANO),
        confirmed_elements_by_proposal={proposal.id: confirmed},
    )

    facts = _cable_technology_facts(
        uuid4(),
        (proposal,),
        session,
        context,
    )

    assert bool(facts) is expected
    assert all(item.chave == "cabo.tecnologia" for item in facts)


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

    facts = _region_facts(
        session,
        mercado=Mercado.RURAL,
        region_targets={region.id: target},
    )

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
        mercado=Mercado.RURAL,
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
            None,
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
            "DIVERGENCIA",
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
def test_new_normative_rules_cover_conformity_divergence_and_context_exception(
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
    assert by_rule["nd31.equipamento.risco-abalroamento"] == "DIVERGENCIA"
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
    ("group", "invalid_value", "expected"),
    (
        (GrupoCondicaoConformidade.APLICABILIDADE, None, None),
        (GrupoCondicaoConformidade.EXCECAO, None, ResultadoConformidade.CONFORME),
        (GrupoCondicaoConformidade.REQUISITO, None, ResultadoConformidade.DIVERGENCIA),
        (GrupoCondicaoConformidade.APLICABILIDADE, "ilegível", None),
        (
            GrupoCondicaoConformidade.EXCECAO,
            "ilegível",
            ResultadoConformidade.CONFORME,
        ),
        (
            GrupoCondicaoConformidade.REQUISITO,
            "ilegível",
            ResultadoConformidade.DIVERGENCIA,
        ),
    ),
)
def test_missing_or_invalid_comparisons_are_false_in_every_condition_group(
    group: GrupoCondicaoConformidade,
    invalid_value: str | None,
    expected: ResultadoConformidade | None,
) -> None:
    seed = carregar_registro_conformidade_inicial()
    span_rule = next(item for item in seed.regras if item.id == "nd31.vao.urbano-compacto-isolado")
    comparison = span_rule.requisitos[0]
    baseline_requirement = span_rule.excecoes[0]
    rule = replace(
        span_rule,
        aplicabilidade=((comparison,) if group is GrupoCondicaoConformidade.APLICABILIDADE else ()),
        excecoes=((comparison,) if group is GrupoCondicaoConformidade.EXCECAO else ()),
        requisitos=(
            (comparison,)
            if group is GrupoCondicaoConformidade.REQUISITO
            else (baseline_requirement,)
        ),
    )
    registry = replace(seed, regras=(rule,))
    target = AlvoConformidade(
        id=uuid4(),
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="Vão sem valor comparável",
    )
    facts = (
        *(
            (_fact(target.id, baseline_requirement.chave_fato, True),)
            if group is not GrupoCondicaoConformidade.REQUISITO
            else ()
        ),
        *(
            (_fact(target.id, comparison.chave_fato, invalid_value),)
            if invalid_value is not None
            else ()
        ),
    )

    findings = avaliar_regras_conformidade(registry, (target,), facts)

    assert (findings[0].resultado if findings else None) is expected
    if findings:
        evaluation = findings[0].avaliacoes_condicoes[0]
        assert evaluation.grupo is group
        assert evaluation.resultado is ResultadoCondicaoConformidade.NAO_ATENDE


@pytest.mark.parametrize(
    ("quantifier", "known_length", "expected"),
    [
        (QuantificadorCondicao.QUALQUER, Decimal("40"), ResultadoConformidade.CONFORME),
        (
            QuantificadorCondicao.QUALQUER,
            Decimal("50"),
            ResultadoConformidade.DIVERGENCIA,
        ),
        (
            QuantificadorCondicao.TODOS,
            Decimal("40"),
            ResultadoConformidade.DIVERGENCIA,
        ),
        (QuantificadorCondicao.TODOS, Decimal("50"), ResultadoConformidade.DIVERGENCIA),
    ],
)
def test_condition_quantifiers_treat_invalid_values_as_false(
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
        }[expected]
    )


def test_missing_project_context_does_not_activate_normative_rules() -> None:
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

    assert findings == ()


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
        nome="1234567890",
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
