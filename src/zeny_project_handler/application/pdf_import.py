"""Caso de uso transacional para anexar um PDF já validado a um projeto."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID

from zeny_project_handler.application.errors import ApplicationError
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.logging_config import operation_logger
from zeny_project_handler.ports.pdf import InspecaoPdf, LeitorPdfPort, ReferenciaFontePdf
from zeny_project_handler.ports.persistence import UnitOfWorkPort

from .errors import DocumentoDuplicadoError, ProjetoNaoEncontradoError
from .operation_coordinator import CoordenadorOperacoes, TipoOperacao


@dataclass(frozen=True, slots=True)
class ResultadoImportacaoPdf:
    projeto: Projeto
    inspecao: InspecaoPdf


@dataclass(frozen=True, slots=True)
class ResultadoImportacaoPdfs:
    projeto: Projeto
    inspecoes: tuple[InspecaoPdf, ...]


class ImportarPdfNoProjeto:
    """Valida primeiro e só então altera projeto e referência na mesma transação."""

    def __init__(
        self,
        leitor: LeitorPdfPort,
        unidade_de_trabalho: Callable[[], UnitOfWorkPort],
        *,
        coordenador: CoordenadorOperacoes | None = None,
    ) -> None:
        self._leitor = leitor
        self._unidade_de_trabalho = unidade_de_trabalho
        self._coordenador = coordenador or CoordenadorOperacoes()

    def executar(
        self,
        projeto_id: UUID,
        caminho: Path,
        *,
        senha: str | None = None,
        documento_id: UUID | None = None,
        nome_exibicao: str | None = None,
    ) -> ResultadoImportacaoPdf:
        result = ImportarPdfsNoProjeto(
            self._leitor,
            self._unidade_de_trabalho,
            coordenador=self._coordenador,
        ).executar(
            projeto_id,
            (caminho,),
            senha=senha,
            documentos_ids=(documento_id,) if documento_id is not None else None,
            nomes_exibicao=(nome_exibicao,) if nome_exibicao is not None else None,
        )
        return ResultadoImportacaoPdf(projeto=result.projeto, inspecao=result.inspecoes[0])


class ImportarPdfsNoProjeto:
    """Valide e publique uma sequência de PDFs em uma única transação."""

    def __init__(
        self,
        leitor: LeitorPdfPort,
        unidade_de_trabalho: Callable[[], UnitOfWorkPort],
        *,
        coordenador: CoordenadorOperacoes | None = None,
    ) -> None:
        self._leitor = leitor
        self._unidade_de_trabalho = unidade_de_trabalho
        self._coordenador = coordenador or CoordenadorOperacoes()

    def executar(
        self,
        projeto_id: UUID,
        caminhos: tuple[Path, ...],
        *,
        senha: str | None = None,
        documentos_ids: tuple[UUID, ...] | None = None,
        nomes_exibicao: tuple[str, ...] | None = None,
    ) -> ResultadoImportacaoPdfs:
        with self._coordenador.adquirir(TipoOperacao.IMPORTACAO_PDFS):
            return self._executar_observado(
                projeto_id,
                caminhos,
                senha=senha,
                documentos_ids=documentos_ids,
                nomes_exibicao=nomes_exibicao,
            )

    def _executar_observado(
        self,
        projeto_id: UUID,
        caminhos: tuple[Path, ...],
        *,
        senha: str | None,
        documentos_ids: tuple[UUID, ...] | None,
        nomes_exibicao: tuple[str, ...] | None,
    ) -> ResultadoImportacaoPdfs:
        observation = operation_logger(
            "pdf.import",
            project_id=projeto_id,
        )
        with observation.context():
            observation.started(item_count=len(caminhos))
            try:
                result = self._executar(
                    projeto_id,
                    caminhos,
                    senha=senha,
                    documentos_ids=documentos_ids,
                    nomes_exibicao=nomes_exibicao,
                )
            except Exception as error:
                observation.failed(error, expected=_is_expected_import_failure(error))
                raise
            observation.succeeded(
                item_count=len(result.inspecoes),
                document_ids=tuple(item.documento.id for item in result.inspecoes),
            )
            return result

    def _executar(
        self,
        projeto_id: UUID,
        caminhos: tuple[Path, ...],
        *,
        senha: str | None,
        documentos_ids: tuple[UUID, ...] | None,
        nomes_exibicao: tuple[str, ...] | None,
    ) -> ResultadoImportacaoPdfs:
        if not caminhos:
            raise ValueError("Selecione ao menos um PDF para importar")
        if documentos_ids is not None and len(documentos_ids) != len(caminhos):
            raise ValueError("A quantidade de IDs deve corresponder aos PDFs selecionados")
        if nomes_exibicao is not None and len(nomes_exibicao) != len(caminhos):
            raise ValueError("A quantidade de nomes deve corresponder aos PDFs selecionados")
        inspections = tuple(
            self._leitor.inspecionar(
                path,
                senha=senha,
                documento_id=(documentos_ids[index] if documentos_ids is not None else None),
            )
            for index, path in enumerate(caminhos)
        )
        if nomes_exibicao is not None:
            inspections = tuple(
                replace(
                    inspection,
                    documento=replace(
                        inspection.documento,
                        nome_arquivo=nomes_exibicao[index],
                    ),
                )
                for index, inspection in enumerate(inspections)
            )
        for inspection in inspections:
            self._leitor.verificar_origem(inspection)
        selected_hashes = [inspection.documento.sha256 for inspection in inspections]
        if len(set(selected_hashes)) != len(selected_hashes):
            raise DocumentoDuplicadoError("A seleção contém conteúdo PDF duplicado")
        with self._unidade_de_trabalho() as work:
            project = work.projetos.obter(projeto_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para importação do PDF")
            existing_hashes = {document.sha256 for document in project.documentos}
            if existing_hashes.intersection(selected_hashes):
                raise DocumentoDuplicadoError("O projeto já contém este conteúdo PDF")
            updated = replace(
                project,
                documentos=(
                    *project.documentos,
                    *(inspection.documento for inspection in inspections),
                ),
                ordem_leitura_paginas=(
                    *project.ordem_leitura_paginas,
                    *(
                        page.id
                        for inspection in inspections
                        for page in inspection.documento.paginas
                    ),
                ),
            )
            work.projetos.salvar(updated)
            for inspection in inspections:
                work.fontes_pdf.salvar(
                    ReferenciaFontePdf(
                        documento_id=inspection.documento.id,
                        projeto_id=project.id,
                        caminho_canonico=inspection.caminho_origem,
                        sha256=inspection.documento.sha256,
                        tamanho_bytes=inspection.tamanho_bytes,
                        modificado_em_ns=inspection.modificado_em_ns,
                    )
                )
            for inspection in inspections:
                self._leitor.verificar_origem(inspection)
            work.commit()
        return ResultadoImportacaoPdfs(projeto=updated, inspecoes=inspections)


def _is_expected_import_failure(error: BaseException) -> bool:
    if isinstance(error, (ApplicationError, DomainValidationError, ValueError)):
        return True
    return any(
        error_type.__name__ == "PdfError"
        and error_type.__module__ == "zeny_project_handler.adapters.pdf.errors"
        for error_type in type(error).__mro__
    )
