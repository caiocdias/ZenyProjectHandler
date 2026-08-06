"""Falhas controladas da fronteira de leitura de PDFs."""


class PdfError(RuntimeError):
    """Erro esperado durante inspeção ou renderização."""


class PdfArquivoInvalidoError(PdfError):
    """O arquivo não existe, não é PDF ou não pode ser aberto com segurança."""


class PdfProtegidoError(PdfError):
    """O PDF requer uma senha válida."""

    def __init__(self, *, senha_fornecida: bool) -> None:
        self.senha_fornecida = senha_fornecida
        mensagem = (
            "A senha informada para o PDF está incorreta"
            if senha_fornecida
            else "O PDF é protegido e requer uma senha"
        )
        super().__init__(mensagem)


class PdfOrigemAlteradaError(PdfError):
    """A origem mudou depois da inspeção registrada."""


class PdfPaginaInvalidaError(PdfError):
    """A página ou os parâmetros de rasterização são inválidos."""
