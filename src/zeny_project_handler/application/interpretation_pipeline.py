"""Orquestração auditável e idempotente do pipeline de interpretação."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid5

from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    ExecucaoAnalise,
    PropostaElemento,
    PropostaRelacao,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico, ExtraAttributes
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise
from zeny_project_handler.domain.interpretation import RegistroRegrasInterpretacao
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.interpretation import (
    ConfiguracaoInterpretacao,
    InterpretadorEvidenciasPort,
    ResultadoInterpretacao,
    SolicitacaoInterpretacao,
)
from zeny_project_handler.ports.interpretation import (
    InterpretacaoCanceladaError as PortInterpretacaoCanceladaError,
)
from zeny_project_handler.ports.persistence import UnitOfWorkPort

from .errors import (
    InterpretacaoCanceladaError,
    InterpretacaoProjetoError,
    ProjetoNaoEncontradoError,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoExecucaoInterpretacao:
    execucao: ExecucaoAnalise
    elementos: tuple[PropostaElemento, ...]
    relacoes: tuple[PropostaRelacao, ...]
    resultado_reutilizado: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextoInterpretacao:
    projeto: Projeto
    catalogo: CatalogoTecnico
    execucao_extracao: ExecucaoAnalise
    evidencias: tuple[EvidenciaDocumento, ...]


class ExecutarPipelineInterpretacao:
    def __init__(
        self,
        interpretador: InterpretadorEvidenciasPort,
        registro: RegistroRegrasInterpretacao,
        unidade_de_trabalho: Callable[[], UnitOfWorkPort],
        *,
        relogio: Callable[[], datetime] | None = None,
    ) -> None:
        self._interpreter = interpretador
        self._registry = registro
        self._unit_of_work = unidade_de_trabalho
        self._clock = relogio or (lambda: datetime.now(UTC))

    def executar(
        self,
        projeto_id: UUID,
        execucao_extracao_id: UUID,
        *,
        configuracao: ConfiguracaoInterpretacao | None = None,
        cancelado: Callable[[], bool] | None = None,
    ) -> ResultadoExecucaoInterpretacao:
        config = configuracao or ConfiguracaoInterpretacao()
        context = self._load_context(projeto_id, execucao_extracao_id)
        execution_id = _execution_id(
            projeto_id,
            execucao_extracao_id,
            self._registry,
            config,
            interpreter_name=self._interpreter.nome,
            interpreter_version=self._interpreter.versao,
        )
        stored = self._load_completed(execution_id)
        if stored is not None:
            return stored
        started_at = self._aware_now()
        parameters = _execution_parameters(execucao_extracao_id, self._registry, config)
        self._persist_execution(
            ExecucaoAnalise(
                id=execution_id,
                projeto_id=projeto_id,
                metodo=self._interpreter.nome,
                versao_metodo=self._interpreter.versao,
                parametros=parameters,
                estado=EstadoExecucaoAnalise.INICIADA,
                iniciada_em=started_at,
            )
        )
        request = SolicitacaoInterpretacao(
            projeto_id=projeto_id,
            execucao_id=execution_id,
            execucao_extracao_id=execucao_extracao_id,
            catalogo=context.catalogo,
            evidencias=context.evidencias,
            registro=self._registry,
            configuracao=config,
        )
        try:
            result = self._interpreter.interpretar(request, cancelado=cancelado)
        except PortInterpretacaoCanceladaError as error:
            cancelled = self._finished_execution(
                execution_id,
                projeto_id,
                parameters,
                started_at,
                EstadoExecucaoAnalise.CANCELADA,
            )
            self._persist_execution(cancelled)
            raise InterpretacaoCanceladaError(
                f"Interpretação cancelada. Execução retomável: {execution_id}"
            ) from error
        except Exception as error:
            failed = self._finished_execution(
                execution_id,
                projeto_id,
                parameters,
                started_at,
                EstadoExecucaoAnalise.FALHOU,
                erro=(str(error).strip() or error.__class__.__name__)[:1000],
            )
            self._persist_execution(failed)
            raise InterpretacaoProjetoError(
                f"A interpretação falhou. Execução registrada: {execution_id}"
            ) from error
        completed = self._finished_execution(
            execution_id,
            projeto_id,
            parameters,
            started_at,
            EstadoExecucaoAnalise.CONCLUIDA,
            result=result,
        )
        self._persist_result(completed, result)
        return ResultadoExecucaoInterpretacao(
            execucao=completed,
            elementos=result.elementos,
            relacoes=result.relacoes,
            resultado_reutilizado=False,
        )

    def _load_context(self, project_id: UUID, source_execution_id: UUID) -> ContextoInterpretacao:
        with self._unit_of_work() as work:
            project = work.projetos.obter(project_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para interpretação")
            catalog = work.catalogos.obter(project.catalogo_versao_id)
            if catalog is None:
                raise InterpretacaoProjetoError("Catálogo do projeto não está disponível")
            source_execution = work.execucoes_analise.obter(source_execution_id)
            if source_execution is None or source_execution.projeto_id != project_id:
                raise InterpretacaoProjetoError("Execução de extração não pertence ao projeto")
            if source_execution.estado is not EstadoExecucaoAnalise.CONCLUIDA:
                raise InterpretacaoProjetoError("Execução de extração precisa estar concluída")
            evidence = work.evidencias.listar_da_execucao(source_execution_id)
            return ContextoInterpretacao(
                projeto=project,
                catalogo=catalog,
                execucao_extracao=source_execution,
                evidencias=evidence,
            )

    def _load_completed(self, execution_id: UUID) -> ResultadoExecucaoInterpretacao | None:
        with self._unit_of_work() as work:
            execution = work.execucoes_analise.obter(execution_id)
            if execution is None or execution.estado is not EstadoExecucaoAnalise.CONCLUIDA:
                return None
            proposals = work.propostas.listar_da_execucao(execution_id)
        return ResultadoExecucaoInterpretacao(
            execucao=execution,
            elementos=tuple(item for item in proposals if isinstance(item, PropostaElemento)),
            relacoes=tuple(item for item in proposals if isinstance(item, PropostaRelacao)),
            resultado_reutilizado=True,
        )

    def _persist_execution(self, execution: ExecucaoAnalise) -> None:
        with self._unit_of_work() as work:
            if work.projetos.obter(execution.projeto_id) is None:
                raise ProjetoNaoEncontradoError("Projeto removido durante a interpretação")
            work.execucoes_analise.salvar(execution)
            work.commit()

    def _persist_result(self, execution: ExecucaoAnalise, result: ResultadoInterpretacao) -> None:
        with self._unit_of_work() as work:
            if work.projetos.obter(execution.projeto_id) is None:
                raise ProjetoNaoEncontradoError("Projeto removido durante a interpretação")
            work.execucoes_analise.salvar(execution)
            for element_proposal in result.elementos:
                work.propostas.salvar(element_proposal)
            for relation_proposal in result.relacoes:
                work.propostas.salvar(relation_proposal)
            work.commit()

    def _finished_execution(
        self,
        execution_id: UUID,
        project_id: UUID,
        parameters: ExtraAttributes,
        started_at: datetime,
        state: EstadoExecucaoAnalise,
        *,
        erro: str | None = None,
        result: ResultadoInterpretacao | None = None,
    ) -> ExecucaoAnalise:
        return ExecucaoAnalise(
            id=execution_id,
            projeto_id=project_id,
            metodo=self._interpreter.nome,
            versao_metodo=self._interpreter.versao,
            parametros=parameters,
            estado=state,
            iniciada_em=started_at,
            finalizada_em=max(started_at, self._aware_now()),
            erro=erro,
            diagnosticos=result.diagnosticos if result is not None else (),
        )

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("Relógio da aplicação deve retornar data com fuso horário")
        return value


def _execution_parameters(
    source_execution_id: UUID,
    registry: RegistroRegrasInterpretacao,
    config: ConfiguracaoInterpretacao,
) -> ExtraAttributes:
    return tuple(
        sorted(
            (
                *config.parametros(),
                ("execucao_extracao_id", str(source_execution_id)),
                ("registro_regras_assinatura", registry.assinatura()),
                ("registro_regras_versao", registry.versao),
            )
        )
    )


def _execution_id(
    project_id: UUID,
    source_execution_id: UUID,
    registry: RegistroRegrasInterpretacao,
    config: ConfiguracaoInterpretacao,
    *,
    interpreter_name: str,
    interpreter_version: str,
) -> UUID:
    identity = ":".join(
        (
            str(project_id),
            str(source_execution_id),
            registry.assinatura(),
            config.assinatura(),
            interpreter_name,
            interpreter_version,
        )
    )
    return uuid5(registry.id, identity)
