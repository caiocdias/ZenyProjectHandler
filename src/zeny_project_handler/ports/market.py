"""Contrato neutro para classificar o mercado de uma Nota de Serviço."""

from typing import Protocol

from zeny_project_handler.domain.market import Mercado


class ClassificacaoMercadoError(RuntimeError):
    """Erro esperado e seguro ao consultar a classificação externa."""


class MercadoNaoEncontradoError(ClassificacaoMercadoError):
    """A NS não possui classificação no cadastro externo."""


class DadosMercadoInvalidosError(ClassificacaoMercadoError):
    """O cadastro externo retornou cardinalidade ou valor inválido."""


class DependenciaMercadoError(ClassificacaoMercadoError):
    """A dependência externa não pôde concluir a classificação."""


class ClassificadorMercadoPort(Protocol):
    """Classifique uma NS de 10 dígitos sem expor detalhes de infraestrutura."""

    def classificar(self, numero_ns: str) -> Mercado: ...
