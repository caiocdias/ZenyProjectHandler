from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from zeny_project_handler.domain.analysis import (
    ArtefatoExtraido,
    DecisaoRevisao,
    DiagnosticoAnalise,
    EvidenciaDocumento,
    ExecucaoAnalise,
    OrigemObjetoPdf,
    PropostaElemento,
    PropostaRelacao,
)
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    SituacaoProjeto,
    TipoDecisaoRevisao,
    TipoEvidencia,
    TipoOrigemPdf,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado


def test_analysis_execution_requires_consistent_lifecycle() -> None:
    started = datetime(2026, 7, 21, 10, tzinfo=UTC)
    execution = ExecucaoAnalise(
        id=uuid4(),
        projeto_id=uuid4(),
        metodo="vetores-pdf",
        versao_metodo="1",
        parametros=(("tolerancia", Decimal("0.1")),),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=started,
        finalizada_em=started + timedelta(seconds=2),
    )

    assert execution.estado is EstadoExecucaoAnalise.CONCLUIDA
    with pytest.raises(DomainValidationError, match="data de término"):
        ExecucaoAnalise(
            id=uuid4(),
            projeto_id=uuid4(),
            metodo="vetores-pdf",
            versao_metodo="1",
            parametros=(),
            estado=EstadoExecucaoAnalise.CONCLUIDA,
            iniciada_em=started,
        )
    with pytest.raises(DomainValidationError, match="registrar o erro"):
        ExecucaoAnalise(
            id=uuid4(),
            projeto_id=uuid4(),
            metodo="vetores-pdf",
            versao_metodo="1",
            parametros=(),
            estado=EstadoExecucaoAnalise.FALHOU,
            iniciada_em=started,
            finalizada_em=started,
        )


def test_partial_analysis_diagnostic_is_validated_and_kept() -> None:
    diagnostic = DiagnosticoAnalise(
        codigo="analise.vetores_falhou",
        mensagem="Falha localizada",
        extrator="vetores",
        pagina_numero=2,
        objeto_xref=42,
    )
    execution = ExecucaoAnalise(
        id=uuid4(),
        projeto_id=uuid4(),
        metodo="pymupdf-nativo",
        versao_metodo="1",
        parametros=(),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=datetime(2026, 7, 21, tzinfo=UTC),
        finalizada_em=datetime(2026, 7, 21, 0, 1, tzinfo=UTC),
        diagnosticos=(diagnostic,),
    )

    assert execution.diagnosticos == (diagnostic,)
    with pytest.raises(DomainValidationError, match="Página"):
        DiagnosticoAnalise(codigo="erro", mensagem="erro", extrator="teste", pagina_numero=0)
    with pytest.raises(DomainValidationError, match="Objeto"):
        DiagnosticoAnalise(codigo="erro", mensagem="erro", extrator="teste", objeto_xref=0)


def test_evidence_preserves_provenance_and_page() -> None:
    page_id = uuid4()
    created = datetime(2026, 7, 21, tzinfo=UTC)
    evidence = EvidenciaDocumento(
        id=uuid4(),
        execucao_id=uuid4(),
        pagina_id=page_id,
        tipo=TipoEvidencia.VETOR,
        geometria=GeometriaDocumento.ponto(
            page_id, PontoNormalizado(Decimal("0.1"), Decimal("0.2"))
        ),
        metodo="extrator-vetorial",
        versao_metodo="1",
        parametros=(("cor", "#000000"),),
        conteudo_bruto=" linha ",
        criada_em=created,
    )

    assert evidence.conteudo_bruto == "linha"
    with pytest.raises(DomainValidationError, match="página informada"):
        EvidenciaDocumento(
            id=uuid4(),
            execucao_id=uuid4(),
            pagina_id=uuid4(),
            tipo=TipoEvidencia.VETOR,
            geometria=evidence.geometria,
            metodo="extrator-vetorial",
            versao_metodo="1",
            parametros=(),
            conteudo_bruto=None,
            criada_em=created,
        )


def test_project_situation_is_independent_from_review_state() -> None:
    proposal = PropostaElemento(
        id=uuid4(),
        execucao_id=uuid4(),
        categoria=CategoriaElemento.POSTE,
        situacao_projeto=SituacaoProjeto.REMOVER,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(uuid4(),),
        geometria=GeometriaDocumento.ponto(
            uuid4(), PontoNormalizado(Decimal("0.2"), Decimal("0.3"))
        ),
    )

    assert proposal.situacao_projeto is SituacaoProjeto.REMOVER
    assert proposal.estado_revisao is EstadoRevisao.PROPOSTA


def test_review_decision_controls_confirmed_element_reference() -> None:
    now = datetime(2026, 7, 21, tzinfo=UTC)
    confirmed_id = uuid4()
    accepted = DecisaoRevisao(
        id=uuid4(),
        proposta_id=uuid4(),
        decisao=TipoDecisaoRevisao.ACEITAR,
        revisor="Caio",
        decidida_em=now,
        elemento_confirmado_id=confirmed_id,
    )

    assert accepted.elemento_confirmado_id == confirmed_id
    with pytest.raises(DomainValidationError, match="não pode gerar"):
        DecisaoRevisao(
            id=uuid4(),
            proposta_id=uuid4(),
            decisao=TipoDecisaoRevisao.REJEITAR,
            revisor="Caio",
            decidida_em=now,
            elemento_confirmado_id=uuid4(),
        )
    with pytest.raises(DomainValidationError, match="deve indicar"):
        DecisaoRevisao(
            id=uuid4(),
            proposta_id=uuid4(),
            decisao=TipoDecisaoRevisao.AJUSTAR,
            revisor="Caio",
            decidida_em=now,
        )


def test_relation_proposal_rejects_self_relation() -> None:
    reference_id = uuid4()
    with pytest.raises(DomainValidationError, match="referências distintas"):
        PropostaRelacao(
            id=uuid4(),
            execucao_id=uuid4(),
            origem_referencia_id=reference_id,
            destino_referencia_id=reference_id,
            tipo_relacao="CONECTA",
            evidencia_ids=(uuid4(),),
        )


def test_evidence_preserves_annotation_appearance_and_extracted_artifact() -> None:
    page_id = uuid4()
    evidence = EvidenciaDocumento(
        id=uuid4(),
        execucao_id=uuid4(),
        pagina_id=page_id,
        tipo=TipoEvidencia.IMAGEM,
        geometria=GeometriaDocumento.caixa(
            page_id,
            PontoNormalizado(Decimal("0.1"), Decimal("0.1")),
            PontoNormalizado(Decimal("0.4"), Decimal("0.5")),
        ),
        metodo="extrator-anotacoes",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto=None,
        criada_em=datetime(2026, 7, 21, tzinfo=UTC),
        origem_pdf=OrigemObjetoPdf(
            tipo=TipoOrigemPdf.APARENCIA_ANOTACAO,
            numero_objeto=42,
            indice_anotacao=3,
            subtipo_anotacao="Stamp",
            nome_recurso="/N",
        ),
        artefato=ArtefatoExtraido(
            caminho_relativo="artefatos\\pagina-1-objeto-42.png",
            sha256="a" * 64,
            mime_type="IMAGE/PNG",
            tamanho_bytes=1234,
        ),
        atributos_extraidos=(("subtipo", "Stamp"),),
    )

    assert evidence.origem_pdf.tipo is TipoOrigemPdf.APARENCIA_ANOTACAO
    assert evidence.artefato is not None
    assert evidence.artefato.caminho_relativo == "artefatos/pagina-1-objeto-42.png"
    assert evidence.artefato.mime_type == "image/png"
    with pytest.raises(DomainValidationError, match="objeto ou índice"):
        OrigemObjetoPdf(tipo=TipoOrigemPdf.ANOTACAO)


def test_proposal_can_keep_unmapped_code_attributes_and_confidence() -> None:
    proposal = PropostaElemento(
        id=uuid4(),
        execucao_id=uuid4(),
        categoria=CategoriaElemento.EQUIPAMENTO,
        situacao_projeto=SituacaoProjeto.EXISTENTE,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(uuid4(),),
        geometria=GeometriaDocumento.ponto(
            uuid4(), PontoNormalizado(Decimal("0.2"), Decimal("0.3"))
        ),
        codigo_observado=" RELIG. 560A ",
        atributos_sugeridos=(("classe", "RELIGADOR"), ("corrente_a", 560)),
        confianca=Decimal("0.82"),
        justificativa=" Texto e símbolo próximos ",
    )

    assert proposal.tipo_catalogo_sugerido_id is None
    assert proposal.codigo_observado == "RELIG. 560A"
    assert proposal.confianca == Decimal("0.82")
    with pytest.raises(DomainValidationError, match="entre 0 e 1"):
        PropostaRelacao(
            id=uuid4(),
            execucao_id=uuid4(),
            origem_referencia_id=uuid4(),
            destino_referencia_id=uuid4(),
            tipo_relacao="CONECTA",
            evidencia_ids=(uuid4(),),
            confianca=Decimal("1.1"),
        )
