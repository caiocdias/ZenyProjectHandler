"""Coordenação não bloqueante das operações que compartilham o estado local.

O coordenador usa uma única exclusão global e recusa conflitos imediatamente. O
``Lock`` interno protege somente a troca do token ativo; ele nunca permanece
adquirido durante a operação de aplicação. Assim, não há espera circular nem
ordenação de múltiplos locks que possa produzir deadlock.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from enum import StrEnum
from threading import Lock
from types import TracebackType

from .errors import OperacaoEmAndamentoError


class TipoOperacao(StrEnum):
    """Operações exclusivas apresentadas de forma segura ao usuário."""

    ANALISE = "análise do projeto"
    IMPORTACAO_PDFS = "importação de PDFs"
    EXPORTACAO_PROJETO = "exportação do projeto"
    IMPORTACAO_PROJETO = "importação do projeto"
    BACKUP = "criação do backup"
    RESTAURACAO = "restauração do backup"
    EXCLUSAO_PROJETO = "exclusão do projeto"
    EXCLUSAO_DOCUMENTOS = "remoção de PDFs"
    EXCLUSAO_FOTO = "remoção de foto"
    ALTERACAO_PROJETO = "alteração do projeto"


class TokenOperacao:
    """Posse exclusiva liberada pelo gerenciador de contexto ou explicitamente."""

    def __init__(self, coordenador: CoordenadorOperacoes, operacao: TipoOperacao) -> None:
        self._coordenador = coordenador
        self.operacao = operacao
        self._liberado = False

    @property
    def liberado(self) -> bool:
        return self._liberado

    def liberar(self) -> bool:
        """Libere uma vez; liberações repetidas são inofensivas e retornam ``False``."""
        return self._coordenador._liberar(self)

    def __enter__(self) -> TokenOperacao:
        return self

    def __exit__(
        self,
        _tipo: type[BaseException] | None,
        _erro: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.liberar()


class CoordenadorOperacoes:
    """Recuse qualquer segunda operação enquanto a primeira estiver ativa."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._ativo: TokenOperacao | None = None
        self._observadores: set[Callable[[TipoOperacao | None], None]] = set()

    @property
    def operacao_em_andamento(self) -> TipoOperacao | None:
        with self._lock:
            return self._ativo.operacao if self._ativo is not None else None

    def adquirir(self, operacao: TipoOperacao) -> TokenOperacao:
        """Adquira sem espera ou informe qual operação impede a solicitação."""
        with self._lock:
            if self._ativo is not None:
                raise OperacaoEmAndamentoError(
                    operacao_solicitada=operacao.value,
                    operacao_em_andamento=self._ativo.operacao.value,
                )
            token = TokenOperacao(self, operacao)
            self._ativo = token
            observadores = tuple(self._observadores)
        self._notificar(observadores, operacao)
        return token

    def observar(self, observador: Callable[[TipoOperacao | None], None]) -> Callable[[], None]:
        """Observe trocas de estado sem acoplar o coordenador a um framework de interface."""
        with self._lock:
            self._observadores.add(observador)
            atual = self._ativo.operacao if self._ativo is not None else None
        self._notificar((observador,), atual)

        def remover() -> None:
            with self._lock:
                self._observadores.discard(observador)

        return remover

    def _liberar(self, token: TokenOperacao) -> bool:
        with self._lock:
            if token._liberado:
                return False
            if self._ativo is not token:
                raise RuntimeError("Token não pertence à operação ativa")
            token._liberado = True
            self._ativo = None
            observadores = tuple(self._observadores)
        self._notificar(observadores, None)
        return True

    @staticmethod
    def _notificar(
        observadores: tuple[Callable[[TipoOperacao | None], None], ...],
        operacao: TipoOperacao | None,
    ) -> None:
        for observador in observadores:
            # Observabilidade não pode reter um token nem transformar sucesso em falha.
            with suppress(Exception):
                observador(operacao)
