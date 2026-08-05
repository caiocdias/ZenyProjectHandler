"""Banco SQLite autocontido de um único projeto portátil."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from zeny_project_handler.application.errors import PortabilidadeProjetoError
from zeny_project_handler.ports.portability import ConteudoBancoProjetoPortatil

from .database import managed_sqlite_engine, upgrade_database
from .unit_of_work import SqlAlchemyUnitOfWork


class SqlitePortableProjectDatabase:
    def criar(self, destino: Path, conteudo: ConteudoBancoProjetoPortatil) -> Path:
        target = destino.expanduser().resolve()
        if target.exists():
            raise PortabilidadeProjetoError("Banco temporário do pacote já existe")
        with managed_sqlite_engine(target) as engine:
            upgrade_database(engine)
            with SqlAlchemyUnitOfWork(engine) as work:
                work.catalogos.salvar(conteudo.catalogo)
                work.projetos.salvar(conteudo.projeto)
                for execution in conteudo.execucoes:
                    work.execucoes_analise.salvar(execution)
                for evidence in conteudo.evidencias:
                    work.evidencias.salvar(evidence)
                for proposal in conteudo.propostas:
                    work.propostas.salvar(proposal)
                for decision in conteudo.decisoes:
                    work.decisoes_revisao.salvar(decision)
                work.commit()
        return target

    def carregar(self, origem: Path, projeto_id: UUID) -> ConteudoBancoProjetoPortatil:
        source = origem.expanduser().resolve()
        if not source.is_file():
            raise PortabilidadeProjetoError("Banco do projeto não foi encontrado no pacote")
        with managed_sqlite_engine(source) as engine:
            upgrade_database(engine)
            with SqlAlchemyUnitOfWork(engine) as work:
                project = work.projetos.obter(projeto_id)
                if project is None:
                    raise PortabilidadeProjetoError("Projeto do manifesto não existe no banco")
                catalog = work.catalogos.obter(project.catalogo_versao_id)
                if catalog is None:
                    raise PortabilidadeProjetoError("Catálogo do projeto não existe no banco")
                executions = work.execucoes_analise.listar_do_projeto(project.id)
                evidence = tuple(
                    item
                    for execution in executions
                    for item in work.evidencias.listar_da_execucao(execution.id)
                )
                proposals = tuple(
                    item
                    for execution in executions
                    for item in work.propostas.listar_da_execucao(execution.id)
                )
                decisions = tuple(
                    decision
                    for proposal in proposals
                    if (decision := work.decisoes_revisao.obter_da_proposta(proposal.id))
                    is not None
                )
                return ConteudoBancoProjetoPortatil(
                    projeto=project,
                    catalogo=catalog,
                    execucoes=executions,
                    evidencias=evidence,
                    propostas=proposals,
                    decisoes=decisions,
                )
