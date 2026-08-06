"""Caso de uso para executar e persistir uma análise documental auditável."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from zeny_project_handler.domain.analysis import EvidenciaDocumento, ExecucaoAnalise
from zeny_project_handler.domain.catalog import ExtraAttributes
from zeny_project_handler.domain.documents import DocumentoProjeto
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.logging_config import OperationLogger, operation_logger
from zeny_project_handler.ports.analysis import (
    AnalisadorDocumentoPort,
    ConfiguracaoAnaliseDocumento,
    ResultadoAnaliseDocumento,
    SolicitacaoAnaliseDocumento,
)
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler.ports.persistence import UnitOfWorkPort

from .errors import (
    AnaliseDocumentoError,
    ApplicationError,
    DocumentoNaoEncontradoError,
    OrigemPdfNaoEncontradaError,
    ProjetoNaoEncontradoError,
)


@dataclass(frozen=True, slots=True)
class ResultadoExecucaoAnalise:
    execucao: ExecucaoAnalise
    evidencias: tuple[EvidenciaDocumento, ...]
    cache_utilizado: bool


class ExecutarAnaliseDocumento:
    def __init__(
        self,
        analisador: AnalisadorDocumentoPort,
        unidade_de_trabalho: Callable[[], UnitOfWorkPort],
        *,
        relogio: Callable[[], datetime] | None = None,
        gerador_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._analisador = analisador
        self._unidade_de_trabalho = unidade_de_trabalho
        self._relogio = relogio or (lambda: datetime.now(UTC))
        self._gerador_id = gerador_id

    @property
    def assinatura_analisador(self) -> str:
        """Identidade que invalida execuções persistidas quando o extrator muda."""
        return self._analisador.assinatura_capacidade

    def executar(
        self,
        projeto_id: UUID,
        documento_id: UUID,
        *,
        configuracao: ConfiguracaoAnaliseDocumento | None = None,
        senha: str | None = None,
        execucao_id: UUID | None = None,
    ) -> ResultadoExecucaoAnalise:
        execution_id = execucao_id or self._gerador_id()
        parameters = configuracao or ConfiguracaoAnaliseDocumento()
        observation = operation_logger(
            "pdf.analysis",
            project_id=projeto_id,
            document_id=documento_id,
            execution_id=execution_id,
        )
        with observation.context():
            observation.started()
            try:
                document, source = self._load_source(projeto_id, documento_id)
                started_at = self._aware_now()
            except Exception as error:
                observation.failed(error, expected=_is_expected_analysis_failure(error))
                raise
            return self._analyze_and_persist(
                document,
                source,
                projeto_id=projeto_id,
                execution_id=execution_id,
                started_at=started_at,
                parameters=parameters,
                senha=senha,
                observation=observation,
            )

    def _analyze_and_persist(
        self,
        document: DocumentoProjeto,
        source: ReferenciaFontePdf,
        *,
        projeto_id: UUID,
        execution_id: UUID,
        started_at: datetime,
        parameters: ConfiguracaoAnaliseDocumento,
        senha: str | None,
        observation: OperationLogger,
    ) -> ResultadoExecucaoAnalise:
        try:
            result = self._analisador.analisar(
                SolicitacaoAnaliseDocumento(
                    projeto_id=projeto_id,
                    documento=document,
                    fonte=source,
                    execucao_id=execution_id,
                    criada_em=started_at,
                    configuracao=parameters,
                    senha=senha,
                )
            )
        except Exception as error:
            observation.failed(error, expected=_is_expected_analysis_failure(error))
            failed = self._failed_execution(execution_id, projeto_id, started_at, parameters, error)
            try:
                self._persist(failed, ())
            except Exception as persistence_error:
                observation.failed(persistence_error, expected=False)
                raise
            raise AnaliseDocumentoError(
                f"A análise do documento falhou. Execução registrada: {execution_id}"
            ) from error
        execution = self._completed_execution(
            execution_id, projeto_id, started_at, parameters, result
        )
        try:
            self._persist(execution, result.evidencias)
        except Exception as error:
            observation.failed(error, expected=_is_expected_analysis_failure(error))
            raise
        response = ResultadoExecucaoAnalise(
            execucao=execution,
            evidencias=result.evidencias,
            cache_utilizado=result.cache_utilizado,
        )
        observation.succeeded(cache_hit=result.cache_utilizado)
        return response

    def _load_source(
        self, project_id: UUID, document_id: UUID
    ) -> tuple[DocumentoProjeto, ReferenciaFontePdf]:
        with self._unidade_de_trabalho() as work:
            project = work.projetos.obter(project_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para análise")
            document = next((item for item in project.documentos if item.id == document_id), None)
            if document is None:
                raise DocumentoNaoEncontradoError("Documento não encontrado no projeto")
            source = work.fontes_pdf.obter(document_id)
            if source is None:
                raise OrigemPdfNaoEncontradaError("Origem PDF não encontrada para análise")
            return document, source

    def _completed_execution(
        self,
        execution_id: UUID,
        project_id: UUID,
        started_at: datetime,
        configuration: ConfiguracaoAnaliseDocumento,
        result: ResultadoAnaliseDocumento,
    ) -> ExecucaoAnalise:
        return ExecucaoAnalise(
            id=execution_id,
            projeto_id=project_id,
            metodo=self._analisador.nome,
            versao_metodo=self._analisador.versao,
            parametros=self._execution_parameters(configuration),
            estado=EstadoExecucaoAnalise.CONCLUIDA,
            iniciada_em=started_at,
            finalizada_em=self._finished_at(started_at),
            diagnosticos=result.diagnosticos,
        )

    def _failed_execution(
        self,
        execution_id: UUID,
        project_id: UUID,
        started_at: datetime,
        configuration: ConfiguracaoAnaliseDocumento,
        error: Exception,
    ) -> ExecucaoAnalise:
        detail = str(error).strip() or error.__class__.__name__
        return ExecucaoAnalise(
            id=execution_id,
            projeto_id=project_id,
            metodo=self._analisador.nome,
            versao_metodo=self._analisador.versao,
            parametros=self._execution_parameters(configuration),
            estado=EstadoExecucaoAnalise.FALHOU,
            iniciada_em=started_at,
            finalizada_em=self._finished_at(started_at),
            erro=detail[:1000],
        )

    def _persist(
        self, execution: ExecucaoAnalise, evidence: tuple[EvidenciaDocumento, ...]
    ) -> None:
        with self._unidade_de_trabalho() as work:
            if work.projetos.obter(execution.projeto_id) is None:
                raise ProjetoNaoEncontradoError("Projeto removido durante a análise")
            work.execucoes_analise.salvar(execution)
            for item in evidence:
                work.evidencias.salvar(item)
            work.commit()

    def _execution_parameters(
        self,
        configuration: ConfiguracaoAnaliseDocumento,
    ) -> ExtraAttributes:
        return (
            *configuration.parametros(),
            ("assinatura_capacidade_analisador", self.assinatura_analisador),
        )

    def _aware_now(self) -> datetime:
        value = self._relogio()
        if value.tzinfo is None:
            raise ValueError("Relógio da aplicação deve retornar data com fuso horário")
        return value

    def _finished_at(self, started_at: datetime) -> datetime:
        finished_at = self._aware_now()
        return max(started_at, finished_at)


def _is_expected_analysis_failure(error: BaseException) -> bool:
    if isinstance(error, (ApplicationError, DomainValidationError, ValueError)):
        return True
    return any(
        error_type.__name__ == "PdfError"
        and error_type.__module__ == "zeny_project_handler.adapters.pdf.errors"
        for error_type in type(error).__mro__
    )
