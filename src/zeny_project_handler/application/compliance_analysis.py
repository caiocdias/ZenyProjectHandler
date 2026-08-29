"""Caso de uso único para executar e consultar conformidade auditável."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid5

from zeny_project_handler.domain.compliance import (
    ExecucaoConformidade,
    RevisaoRegistroConformidade,
    assinatura_conteudo_conformidade,
)
from zeny_project_handler.domain.market import DescricaoAcao
from zeny_project_handler.ports.market import (
    ClassificadorMercadoPort,
    DependenciaAcoesError,
    VerificadorAcoesConcluidasPort,
)
from zeny_project_handler.ports.persistence import UnitOfWorkPort

from .compliance_fact_providers import (
    ContextoAcoesProjeto,
    EstadoVerificacaoAcao,
    ProvedorFatosConformidade,
    ResultadoVerificacaoAcao,
)
from .errors import AnaliseConformidadeCanceladaError, RegistroConformidadeError
from .human_review import SessaoRevisao
from .project_compliance import analisar_conformidade_projeto, detectar_gatilhos_acoes_projeto

VERSAO_METODO_CONFORMIDADE = "9"


def resultado_conformidade_desatualizado(
    execution: ExecucaoConformidade,
    active_rules_signature: str,
    *,
    numero_ns_atual: str,
    codigos_servico_atuais: tuple[str, ...],
) -> bool:
    """Compare método, regras, NS e serviços com os fatos do snapshot."""

    if (
        execution.versao_metodo != VERSAO_METODO_CONFORMIDADE
        or execution.assinatura_regras != active_rules_signature
    ):
        return True
    execution_service_notes = tuple(
        str(fact.valor) for fact in execution.fatos if fact.chave == "projeto.nota_servico"
    )
    execution_service_codes = tuple(
        sorted(
            str(fact.valor) for fact in execution.fatos if fact.chave == "projeto.codigo_servico"
        )
    )
    return execution_service_notes != (numero_ns_atual,) or execution_service_codes != tuple(
        sorted(codigos_servico_atuais)
    )


class ExecutarAnaliseConformidade:
    """Capture regras, avalie a sessão semântica e publique um snapshot atômico."""

    def __init__(
        self,
        unidade_de_trabalho: Callable[[], UnitOfWorkPort],
        carregar_sessao_semantica: Callable[[UUID], SessaoRevisao],
        *,
        classificador_mercado: ClassificadorMercadoPort,
        verificador_acoes: VerificadorAcoesConcluidasPort | None = None,
        provedores_fatos: tuple[ProvedorFatosConformidade, ...] | None = None,
        relogio: Callable[[], datetime] | None = None,
    ) -> None:
        self._unit_of_work = unidade_de_trabalho
        self._load_semantic_session = carregar_sessao_semantica
        self._market_classifier = classificador_mercado
        self._action_verifier = verificador_acoes
        self._fact_providers = provedores_fatos
        self._clock = relogio or (lambda: datetime.now(UTC))

    def executar(
        self,
        projeto_id: UUID,
        *,
        cancelado: Callable[[], bool] | None = None,
    ) -> ExecucaoConformidade:
        revision = self._capture_active_revision()
        self._ensure_not_cancelled(cancelado)
        session = self._load_semantic_session(projeto_id)
        self._ensure_not_cancelled(cancelado)
        market = self._market_classifier.classificar(session.projeto.nome)
        self._ensure_not_cancelled(cancelado)
        action_context = self._action_context(session, cancelado=cancelado)
        result = analisar_conformidade_projeto(
            session,
            revision.registro,
            mercado=market,
            acoes_projeto=action_context,
            provedores_fatos=self._fact_providers,
        )
        source_ids = tuple(item.id for item in session.execucoes)
        session_signature = assinatura_conteudo_conformidade(
            source_ids,
            result.alvos,
            result.fatos,
            result.itens_documentais,
        )
        execution_id = uuid5(
            projeto_id,
            "conformidade:"
            f"{VERSAO_METODO_CONFORMIDADE}:{revision.id}:"
            f"{revision.assinatura}:{session_signature}",
        )
        self._ensure_not_cancelled(cancelado)
        with self._unit_of_work() as work:
            existing = work.execucoes_conformidade.obter(execution_id)
            if existing is not None:
                return existing
            execution = ExecucaoConformidade(
                id=execution_id,
                projeto_id=projeto_id,
                execucoes_semanticas_ids=source_ids,
                revisao_regras_id=revision.id,
                registro_regras_id=revision.registro.id,
                versao_regras=revision.registro.versao,
                assinatura_regras=revision.assinatura,
                assinatura_sessao=session_signature,
                versao_metodo=VERSAO_METODO_CONFORMIDADE,
                executada_em=self._aware_now(),
                alvos=result.alvos,
                fatos=result.fatos,
                achados=result.achados,
                itens_documentais=result.itens_documentais,
            )
            work.execucoes_conformidade.salvar(execution)
            self._ensure_not_cancelled(cancelado)
            work.commit()
            return execution

    def obter_ultima(self, projeto_id: UUID) -> ExecucaoConformidade | None:
        with self._unit_of_work() as work:
            return work.execucoes_conformidade.obter_ultima(projeto_id)

    def listar_historico(self, projeto_id: UUID) -> tuple[ExecucaoConformidade, ...]:
        with self._unit_of_work() as work:
            return work.execucoes_conformidade.listar_do_projeto(projeto_id)

    def resultado_desatualizado(self, execution: ExecucaoConformidade) -> bool:
        revision = self._capture_active_revision()
        if (
            execution.versao_metodo != VERSAO_METODO_CONFORMIDADE
            or execution.assinatura_regras != revision.assinatura
        ):
            return True
        session = self._load_semantic_session(execution.projeto_id)
        return resultado_conformidade_desatualizado(
            execution,
            revision.assinatura,
            numero_ns_atual=session.projeto.nome,
            codigos_servico_atuais=session.projeto.codigos_servico,
        )

    def _action_context(
        self,
        session: SessaoRevisao,
        *,
        cancelado: Callable[[], bool] | None,
    ) -> ContextoAcoesProjeto:
        triggers = detectar_gatilhos_acoes_projeto(session)
        service_codes = session.projeto.codigos_servico
        results: list[ResultadoVerificacaoAcao] = []
        for action in DescricaoAcao:
            self._ensure_not_cancelled(cancelado)
            evidence = triggers.evidencias_para(action)
            if not evidence:
                state = EstadoVerificacaoAcao.NAO_APLICAVEL
            elif not service_codes:
                state = EstadoVerificacaoAcao.SEM_CODIGOS_SERVICO
            else:
                if self._action_verifier is None:
                    raise DependenciaAcoesError(
                        "O cadastro externo de ações não pôde ser consultado"
                    )
                completed = self._action_verifier.existe_acao_concluida(
                    session.projeto.nome,
                    service_codes,
                    action,
                )
                state = (
                    EstadoVerificacaoAcao.CONCLUIDA if completed else EstadoVerificacaoAcao.PENDENTE
                )
                self._ensure_not_cancelled(cancelado)
            results.append(ResultadoVerificacaoAcao(action, state))
        return ContextoAcoesProjeto(
            codigos_servico=service_codes,
            gatilhos=triggers,
            resultados=tuple(results),
        )

    def _capture_active_revision(self) -> RevisaoRegistroConformidade:
        with self._unit_of_work() as work:
            revision = work.registros_conformidade.obter_ativa()
        if revision is None:
            raise RegistroConformidadeError("Registro de regras ainda não foi inicializado")
        return revision

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Relógio da conformidade deve retornar data com fuso horário")
        return value

    @staticmethod
    def _ensure_not_cancelled(cancelled: Callable[[], bool] | None) -> None:
        if cancelled is not None and cancelled():
            raise AnaliseConformidadeCanceladaError(
                "Análise de conformidade cancelada sem publicar resultado parcial"
            )
