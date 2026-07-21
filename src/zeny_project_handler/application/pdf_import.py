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
        inspection = self._leitor.inspecionar(caminho, senha=senha)
        self._leitor.verificar_origem(inspection)
        with self._unidade_de_trabalho() as work:
            project = work.projetos.obter(projeto_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para importação do PDF")
            if any(
                document.sha256 == inspection.documento.sha256 for document in project.documentos
            ):
                raise DocumentoDuplicadoError("O projeto já contém este conteúdo PDF")
            updated = replace(
                project,
                documentos=(*project.documentos, inspection.documento),
            )
            work.projetos.salvar(updated)
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
            self._leitor.verificar_origem(inspection)
            work.commit()
        return ResultadoImportacaoPdf(projeto=updated, inspecao=inspection)
