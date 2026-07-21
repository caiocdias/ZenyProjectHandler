"""Ponte sem persistência entre o pipeline real e o benchmark de avaliação."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid5

from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.interpretation import InterpretadorRegrasExplicitas
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.evaluation import (
    AmostraAvaliacao,
    GeometriaAvaliacao,
    RotuloElementoAvaliacao,
    RotuloRelacaoAvaliacao,
)
from zeny_project_handler.domain.interpretation import RegistroRegrasInterpretacao
from zeny_project_handler.ports.analysis import (
    AnalisadorDocumentoPort,
    ConfiguracaoAnaliseDocumento,
    SolicitacaoAnaliseDocumento,
)
from zeny_project_handler.ports.evaluation import ResultadoInterpretacaoAvaliacao
from zeny_project_handler.ports.interpretation import (
    ConfiguracaoInterpretacao,
    SolicitacaoInterpretacao,
)
from zeny_project_handler.ports.pdf import LeitorPdfPort, ReferenciaFontePdf

_EVALUATION_NAMESPACE = UUID("6e55709a-0d4e-5af3-8e61-ecc532acbf46")


class InterpretadorRegrasAvaliacao:
    nome = "pipeline-regras-explicitas"
    versao = "1.0"

    def __init__(
        self,
        catalogo: CatalogoTecnico,
        registro: RegistroRegrasInterpretacao,
        *,
        leitor: LeitorPdfPort | None = None,
        analisador_documento: AnalisadorDocumentoPort | None = None,
        configuracao_extracao: ConfiguracaoAnaliseDocumento | None = None,
        configuracao_interpretacao: ConfiguracaoInterpretacao | None = None,
    ) -> None:
        self._catalog = catalogo
        self._registry = registro
        self._reader = leitor or PyMuPdfReader()
        self._document_analyzer = analisador_documento or PyMuPdfDocumentAnalyzer()
        self._extraction_config = configuracao_extracao or ConfiguracaoAnaliseDocumento(
            habilitar_ocr_condicional=False
        )
        self._interpretation_config = configuracao_interpretacao or ConfiguracaoInterpretacao()
        self._semantic_interpreter = InterpretadorRegrasExplicitas(registro)

    def interpretar(
        self,
        amostra: AmostraAvaliacao,
        caminho_pdf: Path,
    ) -> ResultadoInterpretacaoAvaliacao:
        project_id = uuid5(_EVALUATION_NAMESPACE, f"projeto:{amostra.id}")
        document_id = uuid5(_EVALUATION_NAMESPACE, f"documento:{amostra.id}")
        extraction_id = uuid5(_EVALUATION_NAMESPACE, f"extracao:{amostra.id}")
        semantic_id = uuid5(
            self._registry.id,
            f"avaliacao:{amostra.id}:{self._registry.assinatura()}:"
            f"{self._interpretation_config.assinatura()}",
        )
        inspection = self._reader.inspecionar(caminho_pdf, documento_id=document_id)
        if inspection.documento.sha256 != amostra.sha256:
            raise ValueError("Hash do PDF diverge da amostra de avaliação")
        if len(inspection.documento.paginas) != amostra.total_paginas:
            raise ValueError("Quantidade de páginas diverge da amostra de avaliação")
        source = ReferenciaFontePdf(
            documento_id=document_id,
            projeto_id=project_id,
            caminho_canonico=inspection.caminho_origem,
            sha256=inspection.documento.sha256,
            tamanho_bytes=inspection.tamanho_bytes,
            modificado_em_ns=inspection.modificado_em_ns,
        )
        extraction = self._document_analyzer.analisar(
            SolicitacaoAnaliseDocumento(
                projeto_id=project_id,
                documento=inspection.documento,
                fonte=source,
                execucao_id=extraction_id,
                criada_em=datetime.now(UTC),
                configuracao=self._extraction_config,
            )
        )
        semantic = self._semantic_interpreter.interpretar(
            SolicitacaoInterpretacao(
                projeto_id=project_id,
                execucao_id=semantic_id,
                execucao_extracao_id=extraction_id,
                catalogo=self._catalog,
                evidencias=extraction.evidencias,
                registro=self._registry,
                configuracao=self._interpretation_config,
            )
        )
        page_numbers = {page.id: page.numero for page in inspection.documento.paginas}
        elements = tuple(
            RotuloElementoAvaliacao(
                id=str(item.id),
                categoria=item.categoria,
                situacao=item.situacao_projeto,
                geometria=GeometriaAvaliacao(
                    pagina_numero=page_numbers[item.geometria.pagina_id],
                    tipo=item.geometria.tipo,
                    pontos=item.geometria.pontos,
                ),
                codigo_catalogo=item.codigo_observado,
            )
            for item in semantic.elementos
        )
        relations = tuple(
            RotuloRelacaoAvaliacao(
                id=str(item.id),
                origem_id=str(item.origem_referencia_id),
                destino_id=str(item.destino_referencia_id),
                tipo_relacao=item.tipo_relacao,
            )
            for item in semantic.relacoes
        )
        failures = tuple(item.codigo for item in (*extraction.diagnosticos, *semantic.diagnosticos))
        return ResultadoInterpretacaoAvaliacao(
            elementos=elements,
            relacoes=relations,
            falhas_extracao=failures,
        )
