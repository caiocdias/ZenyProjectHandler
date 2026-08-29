"""Contratos neutros para consultar o cadastro operacional externo."""

from collections.abc import Sequence
from typing import Protocol

from zeny_project_handler.domain.market import DescricaoAcao, Mercado


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


class VerificacaoAcoesError(RuntimeError):
    """Erro esperado e seguro ao verificar ações externas concluídas."""


class DadosAcoesInvalidosError(VerificacaoAcoesError):
    """A consulta de ações retornou uma linha incompatível com seu contrato."""


class DependenciaAcoesError(VerificacaoAcoesError):
    """A dependência externa não pôde concluir a verificação de ações."""


class VerificadorAcoesConcluidasPort(Protocol):
    """Verifique a existência de ação concluída sem expor infraestrutura."""

    def existe_acao_concluida(
        self,
        numero_ns: str,
        codigos_servico: Sequence[str],
        acao: DescricaoAcao,
    ) -> bool: ...
