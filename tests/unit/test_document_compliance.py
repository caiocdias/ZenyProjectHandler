from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4, uuid5

import pytest

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.application.compliance_evaluation import avaliar_regras_conformidade
from zeny_project_handler.application.compliance_fact_providers import ContextoProvedorFatos
from zeny_project_handler.application.document_compliance import prover_fatos_documentais
from zeny_project_handler.application.human_review import SessaoRevisao
from zeny_project_handler.domain.analysis import EvidenciaDocumento, ExecucaoAnalise
from zeny_project_handler.domain.compliance import (
    AlvoConformidade,
    FatoConformidade,
    ResultadoConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise, TipoEvidencia
from zeny_project_handler.domain.market import Mercado
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.domain.values import (
    CaixaPagina,
    GeometriaDocumento,
    PontoNormalizado,
)

_COHERENCE_RULES = {
    "pacote.coerencia.transformador-potencia",
    "pacote.coerencia.fases",
    "pacote.coerencia.codigo",
    "pacote.coerencia.circuito",
}


@pytest.mark.parametrize(
    ("materials_text", "expected"),
    (
        (
            "CIRCUITO: ALM-01 TRANSFORMADOR TRIFASICO 75 KVA COD: -3-75",
            ResultadoConformidade.CONFORME,
        ),
        (
            "CIRCUITO: ALM-02 TRANSFORMADOR MONOFASICO 45 KVA CODIGO: -1-45",
            ResultadoConformidade.DIVERGENCIA,
        ),
    ),
)
def test_document_provider_compares_power_phases_code_and_circuit(
    materials_text: str,
    expected: ResultadoConformidade,
) -> None:
    session = _session(
        (
            "projeto-desenho.pdf",
            "CIRCUITO: ALM-01 TRANSFORMADOR TRIFASICO 75 KVA CODIGO: -3-75",
        ),
        ("relacao-materiais-orcamento.pdf", materials_text),
    )
    target = _project_target(session)
    facts = prover_fatos_documentais(
        ContextoProvedorFatos(sessao=session, alvos=(target,), mercado=Mercado.URBANO)
    )
    findings = avaliar_regras_conformidade(
        carregar_registro_conformidade_inicial(),
        (target,),
        facts,
    )
    by_rule = {item.regra_id: item for item in findings}

    assert by_rule.keys() >= _COHERENCE_RULES
    assert all(by_rule[rule_id].resultado is expected for rule_id in _COHERENCE_RULES)
    assert all(by_rule[rule_id].evidencia_ids for rule_id in _COHERENCE_RULES)


@pytest.mark.parametrize(
    ("materials_text", "expected"),
    (
        (
            "TRANSFORMADOR TRIFASICO 45 KVA; TRANSFORMADOR TRIFASICO 75 KVA",
            ResultadoConformidade.CONFORME,
        ),
        (
            "TRANSFORMADOR TRIFASICO 75 KVA",
            ResultadoConformidade.DIVERGENCIA,
        ),
    ),
)
def test_document_provider_compares_multiple_explicit_values_as_sets(
    materials_text: str,
    expected: ResultadoConformidade,
) -> None:
    session = _session(
        (
            "projeto-desenho.pdf",
            "TRANSFORMADOR TRIFASICO 45 KVA; TRANSFORMADOR TRIFASICO 75 KVA",
        ),
        ("orcamento.pdf", materials_text),
    )
    target = _project_target(session)
    facts = prover_fatos_documentais(
        ContextoProvedorFatos(sessao=session, alvos=(target,), mercado=Mercado.URBANO)
    )
    by_key = {item.chave: item.valor for item in facts}
    findings = avaliar_regras_conformidade(
        carregar_registro_conformidade_inicial(),
        (target,),
        facts,
    )

    assert by_key["projeto.coerencia_potencia_transformador_avaliada"] is True
    assert (
        next(
            item for item in findings if item.regra_id == "pacote.coerencia.transformador-potencia"
        ).resultado
        is expected
    )


def test_document_provider_skips_comparison_when_one_document_has_no_value() -> None:
    session = _session(
        ("projeto-desenho.pdf", "TRANSFORMADOR TRIFASICO 75 KVA"),
        ("orcamento.pdf", "RELACAO DE MATERIAIS SEM TRANSFORMADOR"),
    )
    target = _project_target(session)
    facts = prover_fatos_documentais(
        ContextoProvedorFatos(sessao=session, alvos=(target,), mercado=Mercado.URBANO)
    )
    by_key = {item.chave: item.valor for item in facts}
    findings = avaliar_regras_conformidade(
        carregar_registro_conformidade_inicial(),
        (target,),
        facts,
    )

    assert by_key["projeto.coerencia_potencia_transformador_avaliada"] is False
    assert "projeto.coerencia_potencia_transformador" not in by_key
    assert all(item.regra_id != "pacote.coerencia.transformador-potencia" for item in findings)


@pytest.mark.parametrize(
    ("support_document", "expected"),
    (
        (None, ResultadoConformidade.DIVERGENCIA),
        (("parecer-de-acesso.pdf", "PARECER DE ACESSO"), ResultadoConformidade.CONFORME),
    ),
)
def test_gd_document_rule_uses_explicit_package_markers(
    support_document: tuple[str, str] | None,
    expected: ResultadoConformidade,
) -> None:
    documents = [("projeto-desenho.pdf", "PROJETO DE MICROGERACAO DISTRIBUIDA")]
    if support_document is not None:
        documents.append(support_document)
    session = _session(*documents)
    target = _project_target(session)
    facts = prover_fatos_documentais(
        ContextoProvedorFatos(sessao=session, alvos=(target,), mercado=Mercado.URBANO)
    )
    finding = next(
        item
        for item in avaliar_regras_conformidade(
            carregar_registro_conformidade_inicial(),
            (target,),
            facts,
        )
        if item.regra_id == "pacote.documentacao.gd"
    )

    assert finding.resultado is expected


@pytest.mark.parametrize(
    ("documents", "expected"),
    (
        (
            (("projeto-rural.pdf", "PRORDR"),),
            ResultadoConformidade.DIVERGENCIA,
        ),
        (
            (
                ("projeto-rural.pdf", "PRORDR"),
                ("registro-fotografico.pdf", "IMAGENS DE CAMPO"),
            ),
            ResultadoConformidade.CONFORME,
        ),
    ),
)
def test_prordr_photo_rule_uses_detected_photo_document(
    documents: tuple[tuple[str, str], ...],
    expected: ResultadoConformidade,
) -> None:
    session = _session(*documents)
    target = _project_target(session)
    document_facts = prover_fatos_documentais(
        ContextoProvedorFatos(
            sessao=session,
            alvos=(target,),
            mercado=Mercado.URBANO,
        )
    )
    facts = (
        *document_facts,
        _fact(target.id, "rede.contexto_rural", True),
        _fact(target.id, "projeto.extensao_rede_instalar_avaliada", True),
        _fact(target.id, "projeto.extensao_rede_instalar_m", Decimal("350")),
        _fact(target.id, "projeto.prordr_identificado", True),
    )
    finding = next(
        item
        for item in avaliar_regras_conformidade(
            carregar_registro_conformidade_inicial(),
            (target,),
            facts,
        )
        if item.regra_id == "pacote.documentacao.prordr-fotos"
    )

    assert finding.resultado is expected


def _session(*documents_with_text: tuple[str, str]) -> SessaoRevisao:
    catalog = carregar_catalogo_inicial()
    box = CaixaPagina(Decimal(0), Decimal(0), Decimal(595), Decimal(842))
    documents: list[DocumentoProjeto] = []
    for index, (file_name, _text) in enumerate(documents_with_text, start=1):
        page = PaginaDocumento(
            id=uuid4(),
            numero=1,
            largura_pontos=Decimal(595),
            altura_pontos=Decimal(842),
            rotacao_graus=0,
            media_box=box,
            crop_box=box,
        )
        documents.append(
            DocumentoProjeto(
                id=uuid4(),
                nome_arquivo=file_name,
                sha256=f"{index:064x}",
                paginas=(page,),
                tamanho_bytes=1000,
            )
        )
    project = Projeto(
        id=uuid4(),
        nome="1234567890",
        catalogo_versao_id=catalog.id,
        criado_em=datetime(2026, 8, 14, 12, tzinfo=UTC),
        documentos=tuple(documents),
    )
    execution = ExecucaoAnalise(
        id=uuid4(),
        projeto_id=project.id,
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=datetime(2026, 8, 14, 12, tzinfo=UTC),
        finalizada_em=datetime(2026, 8, 14, 12, 1, tzinfo=UTC),
    )
    evidence = tuple(
        EvidenciaDocumento(
            id=uuid4(),
            execucao_id=execution.id,
            pagina_id=document.paginas[0].id,
            tipo=TipoEvidencia.TEXTO,
            geometria=GeometriaDocumento.ponto(
                document.paginas[0].id,
                PontoNormalizado(Decimal("0.50"), Decimal("0.50")),
            ),
            metodo="fixture",
            versao_metodo="1",
            parametros=(),
            conteudo_bruto=text,
            criada_em=datetime(2026, 8, 14, 12, tzinfo=UTC),
        )
        for document, (_file_name, text) in zip(
            documents,
            documents_with_text,
            strict=True,
        )
    )
    return SessaoRevisao(
        projeto=project,
        catalogo=catalog,
        execucoes=(execution,),
        propostas=(),
        regioes=(),
        evidencias=evidence,
        decisoes=(),
        fontes_pdf=(),
    )


def _project_target(session: SessaoRevisao) -> AlvoConformidade:
    return AlvoConformidade(
        id=uuid5(session.projeto.id, "conformidade:projeto"),
        tipo=TipoEscopoConformidade.PROJETO,
        rotulo=session.projeto.nome,
        referencia_id=session.projeto.id,
    )


def _fact(target_id: UUID, key: str, value: bool | Decimal) -> FatoConformidade:
    return FatoConformidade(
        id=uuid4(),
        alvo_id=target_id,
        chave=key,
        valor=value,
        origem="fixture",
    )
