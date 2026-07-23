from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.compliance import (
    JsonComplianceRuleRegistry,
    carregar_registro_conformidade_inicial,
)
from zeny_project_handler.application.analysis_regions import RegiaoAnalise
from zeny_project_handler.application.compliance_evaluation import avaliar_regras_conformidade
from zeny_project_handler.application.human_review import SessaoRevisao
from zeny_project_handler.application.project_compliance import analisar_conformidade_projeto
from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    ExecucaoAnalise,
    PropostaElemento,
)
from zeny_project_handler.domain.catalog import JsonPrimitive, TipoCabo
from zeny_project_handler.domain.compliance import (
    AlvoConformidade,
    FatoConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    SituacaoProjeto,
    TipoEvidencia,
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

    assert len(findings) == 3
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
