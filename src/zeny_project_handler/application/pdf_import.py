"""Caso de uso transacional para anexar um PDF já validado a um projeto."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID

from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.pdf import InspecaoPdf, LeitorPdfPort, ReferenciaFontePdf
from zeny_project_handler.ports.persistence import UnitOfWorkPort

from .errors import DocumentoDuplicadoError, ProjetoNaoEncontradoError


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
    ) -> None:
        self._leitor = leitor
        self._unidade_de_trabalho = unidade_de_trabalho

    def executar(
        self,
        projeto_id: UUID,
        caminho: Path,
        *,
        senha: str | None = None,
    ) -> ResultadoImportacaoPdf:
        result = ImportarPdfsNoProjeto(self._leitor, self._unidade_de_trabalho).executar(
            projeto_id,
            (caminho,),
            senha=senha,
        )
        return ResultadoImportacaoPdf(projeto=result.projeto, inspecao=result.inspecoes[0])


class ImportarPdfsNoProjeto:
    """Valide e publique uma sequência de PDFs em uma única transação."""

    def __init__(
        self,
        leitor: LeitorPdfPort,
        unidade_de_trabalho: Callable[[], UnitOfWorkPort],
    ) -> None:
        self._leitor = leitor
        self._unidade_de_trabalho = unidade_de_trabalho

    def executar(
        self,
        projeto_id: UUID,
        caminhos: tuple[Path, ...],
        *,
        senha: str | None = None,
    ) -> ResultadoImportacaoPdfs:
        if not caminhos:
            raise ValueError("Selecione ao menos um PDF para importar")
        inspections = tuple(self._leitor.inspecionar(path, senha=senha) for path in caminhos)
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
