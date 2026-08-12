"""Fluxo vertical do MVP, da criação do projeto até as propostas revisáveis."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from zeny_project_handler.domain.analysis import ExecucaoAnalise
from zeny_project_handler.domain.documents import DocumentoProjeto
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise, EstadoRevisao
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.analysis import ConfiguracaoAnaliseDocumento
from zeny_project_handler.ports.interpretation import ConfiguracaoInterpretacao
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler.ports.persistence import UnitOfWorkPort

from .compliance_analysis import ExecutarAnaliseConformidade
from .document_analysis import ExecutarAnaliseDocumento
from .errors import (
    AnaliseConformidadeCanceladaError,
    FluxoMvpCanceladoError,
    InterpretacaoCanceladaError,
    ProjetoNaoEncontradoError,
)
from .interpretation_pipeline import ExecutarPipelineInterpretacao
from .managed_files import GerenciadorArquivosGerenciados, fotos_removidas
from .operation_coordinator import CoordenadorOperacoes, TipoOperacao
from .pdf_import import ImportarPdfsNoProjeto, ResultadoImportacaoPdfs
from .project_document_removal import project_without_documents

_project_without_documents = project_without_documents

ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True, slots=True)
class ResumoProjetoMvp:
    projeto_id: UUID
    nome: str
    documentos: int
    paginas: int
    ultima_extracao: EstadoExecucaoAnalise | None
    ultima_interpretacao: EstadoExecucaoAnalise | None
    propostas_pendentes: int
    decisoes_realizadas: int


@dataclass(frozen=True, slots=True)
class SessaoProjetoMvp:
    projeto: Projeto
    fontes_pdf: tuple[ReferenciaFontePdf, ...]
    resumo: ResumoProjetoMvp


@dataclass(frozen=True, slots=True)
class ResultadoFluxoMvp:
    projeto_id: UUID
    execucoes_interpretacao: tuple[UUID, ...]
    execucao_conformidade_id: UUID
    propostas_geradas: int
    documentos_processados: int


@dataclass(frozen=True, slots=True)
class ResultadoRemocaoDocumentos:
    sessao: SessaoProjetoMvp
    documentos_removidos: tuple[str, ...]
    execucoes_removidas: int
    elementos_removidos: int
    arquivos_gerenciados_removidos: int = 0
    limpeza_pendente: bool = False


@dataclass(frozen=True, slots=True)
class ResultadoExclusaoProjeto:
    projeto_id: UUID
    arquivos_gerenciados_removidos: int = 0
    limpeza_pendente: bool = False

    def __bool__(self) -> bool:
        return True


class ServicoFluxoMvp:
    """Orquestre os casos de uso existentes sem expor ferramentas internas ao usuário."""

    def __init__(
        self,
        unidade_de_trabalho: Callable[[], UnitOfWorkPort],
        *,
        catalogo_inicial_id: UUID,
        importador: ImportarPdfsNoProjeto,
        extrator: ExecutarAnaliseDocumento,
        interpretador: ExecutarPipelineInterpretacao,
        analisador_conformidade: ExecutarAnaliseConformidade,
        gerenciador_arquivos: GerenciadorArquivosGerenciados,
        coordenador: CoordenadorOperacoes | None = None,
        relogio: Callable[[], datetime] | None = None,
        gerar_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._unit_of_work = unidade_de_trabalho
        self._initial_catalog_id = catalogo_inicial_id
        self._importer = importador
        self._extractor = extrator
        self._interpreter = interpretador
        self._compliance_analyzer = analisador_conformidade
        self._managed_files = gerenciador_arquivos
        self._coordinator = coordenador or CoordenadorOperacoes()
        self._clock = relogio or (lambda: datetime.now(UTC))
        self._generate_id = gerar_id

    @property
    def coordenador(self) -> CoordenadorOperacoes:
        return self._coordinator

    def listar_projetos(self) -> tuple[ResumoProjetoMvp, ...]:
        with self._unit_of_work() as work:
            return tuple(self._summary(work, project) for project in work.projetos.listar())

    def criar_projeto(self, nome: str) -> SessaoProjetoMvp:
        with self._coordinator.adquirir(TipoOperacao.ALTERACAO_PROJETO):
            return self._criar_projeto(nome)

    def _criar_projeto(self, nome: str) -> SessaoProjetoMvp:
        project = Projeto(
            id=self._generate_id(),
            nome=nome,
            catalogo_versao_id=self._initial_catalog_id,
            criado_em=self._aware_now(),
        )
        with self._unit_of_work() as work:
            if work.catalogos.obter(self._initial_catalog_id) is None:
                raise RuntimeError("Catálogo inicial publicado não está disponível")
            work.projetos.salvar(project)
            work.commit()
        return self.abrir_projeto(project.id)

    def renomear_projeto(self, projeto_id: UUID, nome: str) -> SessaoProjetoMvp:
        with self._coordinator.adquirir(TipoOperacao.ALTERACAO_PROJETO):
            return self._renomear_projeto(projeto_id, nome)

    def _renomear_projeto(self, projeto_id: UUID, nome: str) -> SessaoProjetoMvp:
        with self._unit_of_work() as work:
            project = work.projetos.obter(projeto_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para renomear")
            work.projetos.salvar(replace(project, nome=nome))
            work.commit()
        return self.abrir_projeto(projeto_id)

    def excluir_projeto(self, projeto_id: UUID) -> ResultadoExclusaoProjeto:
        with self._coordinator.adquirir(TipoOperacao.EXCLUSAO_PROJETO):
            return self._excluir_projeto(projeto_id)

    def _excluir_projeto(self, projeto_id: UUID) -> ResultadoExclusaoProjeto:
        with self._unit_of_work() as work:
            if work.projetos.obter(projeto_id) is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para exclusão")
            journal = self._managed_files.preparar_exclusao_projeto(projeto_id)
            try:
                if not work.projetos.remover(projeto_id):
                    raise ProjetoNaoEncontradoError("Projeto não encontrado para exclusão")
                work.commit()
            except Exception:
                work.rollback()
                self._managed_files.cancelar(journal)
                raise
        cleanup = self._managed_files.concluir(journal)
        return ResultadoExclusaoProjeto(
            projeto_id=projeto_id,
            arquivos_gerenciados_removidos=cleanup.arquivos_removidos,
            limpeza_pendente=cleanup.pendente,
        )

    def abrir_projeto(self, projeto_id: UUID) -> SessaoProjetoMvp:
        with self._unit_of_work() as work:
            project = work.projetos.obter(projeto_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado")
            sources = tuple(
                source
                for document in project.documentos
                if (source := work.fontes_pdf.obter(document.id)) is not None
            )
            return SessaoProjetoMvp(
                projeto=project,
                fontes_pdf=sources,
                resumo=self._summary(work, project),
            )

    def importar_pdfs(
        self,
        projeto_id: UUID,
        caminhos: tuple[Path, ...],
        *,
        senha: str | None = None,
    ) -> ResultadoImportacaoPdfs:
        return self._importer.executar(projeto_id, caminhos, senha=senha)

    def reordenar_paginas(
        self,
        projeto_id: UUID,
        paginas_ids: tuple[UUID, ...],
    ) -> SessaoProjetoMvp:
        """Persista a ordem de leitura das páginas de um projeto."""
        with self._coordinator.adquirir(TipoOperacao.ALTERACAO_PROJETO):
            return self._reordenar_paginas(projeto_id, paginas_ids)

    def _reordenar_paginas(
        self,
        projeto_id: UUID,
        paginas_ids: tuple[UUID, ...],
    ) -> SessaoProjetoMvp:
        with self._unit_of_work() as work:
            project = work.projetos.obter(projeto_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para reordenar páginas")
            current_ids = project.ordem_leitura_paginas
            if len(set(paginas_ids)) != len(paginas_ids):
                raise ValueError("A ordem das páginas contém identificadores duplicados")
            if set(paginas_ids) != set(current_ids) or len(paginas_ids) != len(current_ids):
                raise ValueError(
                    "A nova ordem deve conter todas as páginas do projeto uma única vez"
                )
            work.projetos.salvar(replace(project, ordem_leitura_paginas=paginas_ids))
            work.commit()
        return self.abrir_projeto(projeto_id)

    def remover_documentos(
        self,
        projeto_id: UUID,
        documentos_ids: tuple[UUID, ...],
    ) -> ResultadoRemocaoDocumentos:
        with self._coordinator.adquirir(TipoOperacao.EXCLUSAO_DOCUMENTOS):
            return self._remover_documentos(projeto_id, documentos_ids)

    def _remover_documentos(
        self,
        projeto_id: UUID,
        documentos_ids: tuple[UUID, ...],
    ) -> ResultadoRemocaoDocumentos:
        if not documentos_ids:
            raise ValueError("Selecione ao menos um PDF para remover")
        requested_ids = set(documentos_ids)
        if len(requested_ids) != len(documentos_ids):
            raise ValueError("A seleção de PDFs contém identificadores duplicados")
        with self._unit_of_work() as work:
            project = work.projetos.obter(projeto_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para remover PDFs")
            selected = tuple(
                document for document in project.documentos if document.id in requested_ids
            )
            if len(selected) != len(requested_ids):
                raise ValueError("Um dos PDFs selecionados não pertence ao projeto")
            page_ids = {page.id for document in selected for page in document.paginas}
            updated = _project_without_documents(project, requested_ids, page_ids)
            execution_ids = self._affected_execution_ids(
                work,
                project,
                selected,
                page_ids,
            )
            for execution_id in reversed(execution_ids):
                work.execucoes_analise.remover(execution_id)
            journal = self._managed_files.preparar_coleta_fotos(
                projeto_id,
                fotos_removidas(project, updated),
            )
            try:
                work.projetos.salvar(updated)
                work.commit()
            except Exception:
                work.rollback()
                self._managed_files.cancelar(journal)
                raise
        cleanup = self._managed_files.concluir(journal)
        return ResultadoRemocaoDocumentos(
            sessao=self.abrir_projeto(projeto_id),
            documentos_removidos=tuple(document.nome_arquivo for document in selected),
            execucoes_removidas=len(execution_ids),
            elementos_removidos=len(project.elementos) - len(updated.elementos),
            arquivos_gerenciados_removidos=cleanup.arquivos_removidos,
            limpeza_pendente=cleanup.pendente,
        )

    def executar_pipeline(
        self,
        projeto_id: UUID,
        *,
        progresso: ProgressCallback | None = None,
        cancelado: Callable[[], bool] | None = None,
        configuracao_extracao: ConfiguracaoAnaliseDocumento | None = None,
        configuracao_interpretacao: ConfiguracaoInterpretacao | None = None,
        senhas_documentos: Mapping[UUID, str] | None = None,
    ) -> ResultadoFluxoMvp:
        with self._coordinator.adquirir(TipoOperacao.ANALISE):
            return self._executar_pipeline(
                projeto_id,
                progresso=progresso,
                cancelado=cancelado,
                configuracao_extracao=configuracao_extracao,
                configuracao_interpretacao=configuracao_interpretacao,
                senhas_documentos=senhas_documentos,
            )

    def _executar_pipeline(
        self,
        projeto_id: UUID,
        *,
        progresso: ProgressCallback | None,
        cancelado: Callable[[], bool] | None,
        configuracao_extracao: ConfiguracaoAnaliseDocumento | None,
        configuracao_interpretacao: ConfiguracaoInterpretacao | None,
        senhas_documentos: Mapping[UUID, str] | None,
    ) -> ResultadoFluxoMvp:
        session = self.abrir_projeto(projeto_id)
        documents = session.projeto.documentos
        if not documents:
            raise ValueError("Importe ao menos um PDF antes de executar a análise")
        extraction_config = configuracao_extracao or ConfiguracaoAnaliseDocumento()
        interpretation_config = configuracao_interpretacao or ConfiguracaoInterpretacao()
        total_steps = len(documents) * 2 + 1
        interpretation_ids: list[UUID] = []
        proposal_count = 0
        for index, document in enumerate(documents):
            self._ensure_not_cancelled(cancelado)
            extraction_id = _extraction_id(
                session.projeto,
                document.id,
                document.sha256,
                extraction_config,
                self._extractor.assinatura_analisador,
            )
            self._progress(
                progresso,
                index * 2,
                total_steps,
                f"Extraindo evidências de {document.nome_arquivo}",
            )
            extraction = self._completed_execution(extraction_id)
            if extraction is None:
                extraction = self._extractor.executar(
                    projeto_id,
                    document.id,
                    configuracao=extraction_config,
                    senha=(senhas_documentos or {}).get(document.id),
                    execucao_id=extraction_id,
                ).execucao
            self._ensure_not_cancelled(cancelado)
            self._progress(
                progresso,
                index * 2 + 1,
                total_steps,
                f"Interpretando evidências de {document.nome_arquivo}",
            )
            try:
                interpreted = self._interpreter.executar(
                    projeto_id,
                    extraction.id,
                    configuracao=interpretation_config,
                    cancelado=cancelado,
                )
            except InterpretacaoCanceladaError as error:
                raise FluxoMvpCanceladoError(
                    "Análise cancelada em um ponto seguro; use Retomar análise para continuar"
                ) from error
            interpretation_ids.append(interpreted.execucao.id)
            proposal_count += len(interpreted.elementos) + len(interpreted.relacoes)
        self._ensure_not_cancelled(cancelado)
        self._progress(
            progresso,
            total_steps - 1,
            total_steps,
            "Avaliando conformidade com a revisão ativa capturada",
        )
        try:
            compliance_execution = self._compliance_analyzer.executar(
                projeto_id,
                cancelado=cancelado,
            )
        except AnaliseConformidadeCanceladaError as error:
            raise FluxoMvpCanceladoError(
                "Análise cancelada antes de publicar a conformidade; use Retomar análise"
            ) from error
        self._progress(progresso, total_steps, total_steps, "Análise concluída")
        return ResultadoFluxoMvp(
            projeto_id=projeto_id,
            execucoes_interpretacao=tuple(interpretation_ids),
            execucao_conformidade_id=compliance_execution.id,
            propostas_geradas=proposal_count,
            documentos_processados=len(documents),
        )

    def _completed_execution(self, execution_id: UUID) -> ExecucaoAnalise | None:
        with self._unit_of_work() as work:
            execution = work.execucoes_analise.obter(execution_id)
            if execution is not None and execution.estado is EstadoExecucaoAnalise.CONCLUIDA:
                return execution
            return None

    def _affected_execution_ids(
        self,
        work: UnitOfWorkPort,
        project: Projeto,
        selected_documents: tuple[DocumentoProjeto, ...],
        page_ids: set[UUID],
    ) -> tuple[UUID, ...]:
        runs = work.execucoes_analise.listar_do_projeto(project.id)
        extraction_ids = {
            run.id
            for run in runs
            if "execucao_extracao_id" not in dict(run.parametros)
            and any(
                evidence.pagina_id in page_ids
                for evidence in work.evidencias.listar_da_execucao(run.id)
            )
        }
        default_config = ConfiguracaoAnaliseDocumento()
        extraction_ids.update(
            _extraction_id(
                project,
                document.id,
                document.sha256,
                default_config,
                self._extractor.assinatura_analisador,
            )
            for document in selected_documents
        )
        existing_ids = {run.id for run in runs}
        extraction_ids.intersection_update(existing_ids)
        affected = set(extraction_ids)
        changed = True
        while changed:
            changed = False
            for run in runs:
                source = dict(run.parametros).get("execucao_extracao_id")
                if source is not None and UUID(str(source)) in affected and run.id not in affected:
                    affected.add(run.id)
                    changed = True
        return tuple(run.id for run in runs if run.id in affected)

    def _summary(self, work: UnitOfWorkPort, project: Projeto) -> ResumoProjetoMvp:
        runs = work.execucoes_analise.listar_do_projeto(project.id)
        extractions = tuple(
            run for run in runs if "execucao_extracao_id" not in dict(run.parametros)
        )
        interpretations = tuple(
            run for run in runs if "execucao_extracao_id" in dict(run.parametros)
        )
        latest_interpretations = _latest_interpretations_by_source(interpretations)
        proposals = tuple(
            proposal
            for run in latest_interpretations
            for proposal in work.propostas.listar_da_execucao(run.id)
        )
        pending = sum(
            proposal.estado_revisao in {EstadoRevisao.PROPOSTA, EstadoRevisao.CONFLITANTE}
            for proposal in proposals
        )
        decided = sum(
            work.decisoes_revisao.obter_da_proposta(proposal.id) is not None
            for proposal in proposals
        )
        return ResumoProjetoMvp(
            projeto_id=project.id,
            nome=project.nome,
            documentos=len(project.documentos),
            paginas=sum(len(document.paginas) for document in project.documentos),
            ultima_extracao=extractions[-1].estado if extractions else None,
            ultima_interpretacao=interpretations[-1].estado if interpretations else None,
            propostas_pendentes=pending,
            decisoes_realizadas=decided + len(project.historico_revisao_manual),
        )

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("Relógio da aplicação deve retornar data com fuso horário")
        return value

    @staticmethod
    def _ensure_not_cancelled(cancelled: Callable[[], bool] | None) -> None:
        if cancelled is not None and cancelled():
            raise FluxoMvpCanceladoError(
                "Análise cancelada em um ponto seguro; use Retomar análise para continuar"
            )

    @staticmethod
    def _progress(
        callback: ProgressCallback | None,
        current: int,
        total: int,
        message: str,
    ) -> None:
        if callback is not None:
            callback(current, total, message)


def _extraction_id(
    project: Projeto,
    document_id: UUID,
    document_hash: str,
    configuration: ConfiguracaoAnaliseDocumento,
    analyzer_identity: str,
) -> UUID:
    identity = ":".join(
        (
            str(project.id),
            str(document_id),
            document_hash,
            repr(configuration.parametros()),
            analyzer_identity,
        )
    )
    return uuid5(NAMESPACE_URL, identity)


def _latest_interpretations_by_source(
    executions: tuple[ExecucaoAnalise, ...],
) -> tuple[ExecucaoAnalise, ...]:
    latest: dict[str, ExecucaoAnalise] = {}
    for execution in executions:
        source_id = str(dict(execution.parametros).get("execucao_extracao_id", execution.id))
        latest[source_id] = execution
    return tuple(latest.values())
