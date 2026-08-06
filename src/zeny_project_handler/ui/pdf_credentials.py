"""Resolução segura de senhas PDF exclusivamente na thread principal do Qt."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Generic, TypeVar

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QWidget

from zeny_project_handler.adapters.pdf.errors import PdfProtegidoError
from zeny_project_handler.application.pdf_credentials import (
    IdentidadeCredencialPdf,
    ProvedorCredenciaisPdfMemoria,
    identificar_origem_pdf,
)

MAX_TENTATIVAS_SENHA_PDF = 3
T = TypeVar("T")
AcaoCredenciada = Callable[[str | None], T]


class EstadoResolucaoCredencialPdf(StrEnum):
    SUCESSO = "sucesso"
    CANCELADA = "cancelada"
    TENTATIVAS_ESGOTADAS = "tentativas_esgotadas"


@dataclass(frozen=True, slots=True)
class ResultadoResolucaoCredencialPdf(Generic[T]):
    estado: EstadoResolucaoCredencialPdf
    valor: T | None = None
    identidade: IdentidadeCredencialPdf | None = None
    senha: str | None = field(default=None, repr=False, compare=False)
    tentativas: int = 0


class ResolvedorCredenciaisPdf:
    """Execute uma ação e abra modal apenas quando a fronteira acusar proteção."""

    def __init__(self, provedor: ProvedorCredenciaisPdfMemoria) -> None:
        self._provedor = provedor

    @property
    def provedor(self) -> ProvedorCredenciaisPdfMemoria:
        return self._provedor

    def executar(
        self,
        *,
        parent: QWidget,
        caminho: Path,
        acao: AcaoCredenciada[T],
        identidade_sugerida: IdentidadeCredencialPdf | None = None,
    ) -> ResultadoResolucaoCredencialPdf[T]:
        identidade = _identidade_reutilizavel(caminho, identidade_sugerida)
        senha_memoria = self._provedor.obter(identidade) if identidade is not None else None
        try:
            valor = acao(senha_memoria)
        except PdfProtegidoError:
            if identidade is not None and senha_memoria is not None:
                self._provedor.descartar(identidade)
            if identidade is None:
                identidade = identificar_origem_pdf(caminho)
            senha_memoria = self._provedor.obter(identidade)
            if senha_memoria is not None:
                try:
                    valor = acao(senha_memoria)
                except PdfProtegidoError:
                    self._provedor.descartar(identidade)
                else:
                    return ResultadoResolucaoCredencialPdf(
                        estado=EstadoResolucaoCredencialPdf.SUCESSO,
                        valor=valor,
                        identidade=identidade,
                        senha=senha_memoria,
                    )
            return self._solicitar_e_repetir(
                parent=parent,
                caminho=caminho,
                identidade=identidade,
                acao=acao,
            )
        return ResultadoResolucaoCredencialPdf(
            estado=EstadoResolucaoCredencialPdf.SUCESSO,
            valor=valor,
            identidade=identidade,
            senha=senha_memoria,
        )

    def _solicitar_e_repetir(
        self,
        *,
        parent: QWidget,
        caminho: Path,
        identidade: IdentidadeCredencialPdf,
        acao: AcaoCredenciada[T],
    ) -> ResultadoResolucaoCredencialPdf[T]:
        for tentativa in range(1, MAX_TENTATIVAS_SENHA_PDF + 1):
            senha, confirmada = _solicitar_senha(parent, caminho.name, tentativa)
            if not confirmada:
                return ResultadoResolucaoCredencialPdf(
                    estado=EstadoResolucaoCredencialPdf.CANCELADA,
                    identidade=identidade,
                    tentativas=tentativa - 1,
                )
            try:
                valor = acao(senha)
            except PdfProtegidoError:
                self._provedor.descartar(identidade)
                continue
            self._provedor.guardar(identidade, senha)
            return ResultadoResolucaoCredencialPdf(
                estado=EstadoResolucaoCredencialPdf.SUCESSO,
                valor=valor,
                identidade=identidade,
                senha=senha,
                tentativas=tentativa,
            )
        return ResultadoResolucaoCredencialPdf(
            estado=EstadoResolucaoCredencialPdf.TENTATIVAS_ESGOTADAS,
            identidade=identidade,
            tentativas=MAX_TENTATIVAS_SENHA_PDF,
        )


def _identidade_reutilizavel(
    caminho: Path,
    identidade: IdentidadeCredencialPdf | None,
) -> IdentidadeCredencialPdf | None:
    if identidade is None or not identidade.ainda_descreve(caminho):
        return None
    return identidade


def _solicitar_senha(parent: QWidget, nome: str, tentativa: int) -> tuple[str, bool]:
    _exigir_thread_principal()
    if tentativa == 1:
        orientacao = "O PDF é protegido. Informe a senha para continuar."
    else:
        orientacao = "Senha incorreta. Tente novamente."
    return QInputDialog.getText(
        parent,
        "Senha do PDF",
        f"{nome}\n{orientacao}\nTentativa {tentativa} de {MAX_TENTATIVAS_SENHA_PDF}",
        QLineEdit.EchoMode.Password,
    )


def _exigir_thread_principal() -> None:
    application = QApplication.instance()
    if application is None or QThread.currentThread() != application.thread():
        raise RuntimeError("O diálogo de senha PDF exige a thread principal da interface")
