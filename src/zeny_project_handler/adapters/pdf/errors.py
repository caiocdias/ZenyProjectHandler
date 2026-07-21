"""Falhas controladas da fronteira de leitura de PDFs."""


class PdfError(RuntimeError):
    """Erro esperado durante inspeção ou renderização."""


class PdfArquivoInvalidoError(PdfError):
    """O arquivo não existe, não é PDF ou não pode ser aberto com segurança."""


class PdfProtegidoError(PdfError):
    """O PDF requer uma senha válida."""


class PdfOrigemAlteradaError(PdfError):
    """A origem mudou depois da inspeção registrada."""


class PdfPaginaInvalidaError(PdfError):
    """A página ou os parâmetros de rasterização são inválidos."""
