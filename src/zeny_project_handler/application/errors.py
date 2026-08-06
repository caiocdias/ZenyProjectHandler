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


class InterpretacaoProjetoError(ApplicationError):
    """A interpretação semântica terminou com falha fatal e auditável."""


class InterpretacaoCanceladaError(ApplicationError):
    """A interpretação foi cancelada e pode ser retomada com a mesma configuração."""


class RevisaoHumanaError(ApplicationError):
    """A revisão solicitada viola o estado atual ou exige dados adicionais."""


class FluxoMvpCanceladoError(ApplicationError):
    """O fluxo operacional foi cancelado em um ponto seguro e pode ser retomado."""


class PortabilidadeProjetoError(ApplicationError):
    """O pacote, anexo, backup ou recuperação não pôde ser concluído com segurança."""


class PlanoImportacaoObsoletoError(PortabilidadeProjetoError):
    """O pacote ou o destino mudou depois do preflight de importação."""


class RecuperacaoImportacaoBloqueadaError(PortabilidadeProjetoError):
    """O journal não permite reconciliar a importação sem risco para os dados."""


class PortabilidadeCanceladaError(ApplicationError):
    """A portabilidade foi cancelada antes de uma fronteira de publicação segura."""


class OperacaoEmAndamentoError(ApplicationError):
    """Uma operação incompatível já possui o estado compartilhado."""

    def __init__(self, *, operacao_solicitada: str, operacao_em_andamento: str) -> None:
        self.operacao_solicitada = operacao_solicitada
        self.operacao_em_andamento = operacao_em_andamento
        super().__init__(
            f"Não foi possível iniciar {operacao_solicitada}: "
            f"{operacao_em_andamento} está em andamento. Aguarde a conclusão ou o cancelamento."
        )
