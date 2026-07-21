"""Erros dos casos de uso da aplicação."""


class ApplicationError(RuntimeError):
    """Falha esperada de um caso de uso."""


class ProjetoNaoEncontradoError(ApplicationError):
    """O projeto solicitado não existe."""


class DocumentoDuplicadoError(ApplicationError):
    """O projeto já contém um PDF com o mesmo conteúdo."""


class DocumentoNaoEncontradoError(ApplicationError):
    """O documento solicitado não pertence ao projeto."""


class OrigemPdfNaoEncontradaError(ApplicationError):
    """A referência ao PDF original não está disponível."""


class AnaliseDocumentoError(ApplicationError):
    """A análise documental terminou com falha fatal e auditável."""
