"""Consultas somente leitura no cadastro operacional externo SQL Server."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol, TypeAlias, cast

import pyodbc  # type: ignore[import-not-found]

from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.market import DescricaoAcao, Mercado
from zeny_project_handler.domain.project_metadata import (
    normalizar_codigo_servico,
    normalizar_numero_ns,
)
from zeny_project_handler.ports.market import (
    ClassificacaoMercadoError,
    DadosAcoesInvalidosError,
    DadosMercadoInvalidosError,
    DependenciaAcoesError,
    DependenciaMercadoError,
    MercadoNaoEncontradoError,
    VerificacaoAcoesError,
)

CONSULTA_MERCADO_SQL = "SELECT NOTAS_COD_MERCADO FROM TB_NOTAS WHERE NOTAS_NUM_NS = ?;"
CONSULTA_ACAO_CONCLUIDA_SQL = (
    "SELECT TACOES_DES FROM vBIAcoes "
    "WHERE NOTAS_NUM_NS = ? "
    "AND TSERVICOS_CT_COD IN ({placeholders}) "
    "AND TACOES_DES = ? "
    "AND ACOES_DAT_CONCLUSAO IS NOT NULL;"
)
_MENSAGEM_DEPENDENCIA = "O cadastro externo de mercado não pôde ser consultado"
_MENSAGEM_DADOS_INVALIDOS = "O cadastro externo de mercado retornou dados inconsistentes"
_MENSAGEM_DEPENDENCIA_ACOES = "O cadastro externo de ações não pôde ser consultado"
_MENSAGEM_DADOS_ACOES_INVALIDOS = "O cadastro externo de ações retornou dados inconsistentes"


class _CursorOdbc(Protocol):
    def execute(self, sql: str, *parametros: object) -> object: ...

    def fetchmany(self, tamanho: int) -> Sequence[Sequence[object]]: ...

    def close(self) -> None: ...


class _ConexaoOdbc(Protocol):
    timeout: int

    def cursor(self) -> _CursorOdbc: ...

    def close(self) -> None: ...


FabricaConexao: TypeAlias = Callable[[str, int], _ConexaoOdbc]


def _conectar_pyodbc(connection_string: str, timeout_seconds: int) -> _ConexaoOdbc:
    connection = pyodbc.connect(
        connection_string,
        autocommit=True,
        readonly=True,
        timeout=timeout_seconds,
    )
    return cast(_ConexaoOdbc, connection)


@dataclass(frozen=True, slots=True)
class ClassificadorMercadoSqlServer:
    """Consulte exatamente uma classificação por conexão ODBC curta."""

    connection_string: str = field(repr=False)
    timeout_seconds: int = field(default=15, repr=False)
    connection_factory: FabricaConexao = field(default=_conectar_pyodbc, repr=False)

    def __post_init__(self) -> None:
        if not self.connection_string.strip():
            raise ValueError("A string de conexão SQL Server deve ser informada")
        if isinstance(self.timeout_seconds, bool) or self.timeout_seconds < 1:
            raise ValueError("O timeout SQL Server deve ser um inteiro positivo")

    def classificar(self, numero_ns: str) -> Mercado:
        numero_normalizado = normalizar_numero_ns(numero_ns)
        parametro_ns = int(numero_normalizado)
        connection: _ConexaoOdbc | None = None
        cursor: _CursorOdbc | None = None

        try:
            connection = self.connection_factory(self.connection_string, self.timeout_seconds)
            connection.timeout = self.timeout_seconds
            cursor = connection.cursor()
            cursor.execute(CONSULTA_MERCADO_SQL, parametro_ns)
            rows = cursor.fetchmany(2)
            return _mercado_das_linhas(rows)
        except ClassificacaoMercadoError:
            raise
        except Exception as error:
            raise DependenciaMercadoError(_MENSAGEM_DEPENDENCIA) from error
        finally:
            cleanup_error = _fechar_recursos(cursor, connection)
            if cleanup_error is not None and sys.exc_info()[0] is None:
                raise DependenciaMercadoError(_MENSAGEM_DEPENDENCIA) from cleanup_error


@dataclass(frozen=True, slots=True)
class VerificadorAcoesConcluidasSqlServer:
    """Consulte existencialmente ações concluídas por uma conexão ODBC curta."""

    connection_string: str = field(repr=False)
    timeout_seconds: int = field(default=15, repr=False)
    connection_factory: FabricaConexao = field(default=_conectar_pyodbc, repr=False)

    def __post_init__(self) -> None:
        if not self.connection_string.strip():
            raise ValueError("A string de conexão SQL Server deve ser informada")
        if isinstance(self.timeout_seconds, bool) or self.timeout_seconds < 1:
            raise ValueError("O timeout SQL Server deve ser um inteiro positivo")

    def existe_acao_concluida(
        self,
        numero_ns: str,
        codigos_servico: Sequence[str],
        acao: DescricaoAcao,
    ) -> bool:
        numero_normalizado = normalizar_numero_ns(numero_ns)
        servicos_normalizados = tuple(
            normalizar_codigo_servico(codigo) for codigo in codigos_servico
        )
        if not servicos_normalizados:
            raise DomainValidationError("Ao menos um código de serviço deve ser informado")
        if not isinstance(acao, DescricaoAcao):
            raise DomainValidationError("A descrição da ação deve ser uma das opções permitidas")

        placeholders = ", ".join("?" for _ in servicos_normalizados)
        consulta = CONSULTA_ACAO_CONCLUIDA_SQL.format(placeholders=placeholders)
        parametros: tuple[object, ...] = (
            int(numero_normalizado),
            *(int(codigo) for codigo in servicos_normalizados),
            acao.value,
        )
        connection: _ConexaoOdbc | None = None
        cursor: _CursorOdbc | None = None

        try:
            connection = self.connection_factory(self.connection_string, self.timeout_seconds)
            connection.timeout = self.timeout_seconds
            cursor = connection.cursor()
            cursor.execute(consulta, *parametros)
            rows = cursor.fetchmany(1)
            return _acao_existe_nas_linhas(rows, acao)
        except VerificacaoAcoesError:
            raise
        except Exception as error:
            raise DependenciaAcoesError(_MENSAGEM_DEPENDENCIA_ACOES) from error
        finally:
            cleanup_error = _fechar_recursos(cursor, connection)
            if cleanup_error is not None and sys.exc_info()[0] is None:
                raise DependenciaAcoesError(_MENSAGEM_DEPENDENCIA_ACOES) from cleanup_error


def _mercado_das_linhas(rows: Sequence[Sequence[object]]) -> Mercado:
    if not rows:
        raise MercadoNaoEncontradoError("A NS não possui mercado cadastrado")
    if len(rows) != 1:
        raise DadosMercadoInvalidosError(_MENSAGEM_DADOS_INVALIDOS)

    row = rows[0]
    if len(row) != 1 or not isinstance(row[0], str):
        raise DadosMercadoInvalidosError(_MENSAGEM_DADOS_INVALIDOS)
    normalized = row[0].strip().upper()
    try:
        return Mercado(normalized)
    except ValueError as error:
        raise DadosMercadoInvalidosError(_MENSAGEM_DADOS_INVALIDOS) from error


def _acao_existe_nas_linhas(
    rows: Sequence[Sequence[object]],
    acao: DescricaoAcao,
) -> bool:
    if not rows:
        return False
    row = rows[0]
    if len(row) != 1 or row[0] != acao.value:
        raise DadosAcoesInvalidosError(_MENSAGEM_DADOS_ACOES_INVALIDOS)
    return True


def _fechar_recursos(
    cursor: _CursorOdbc | None,
    connection: _ConexaoOdbc | None,
) -> Exception | None:
    cleanup_error: Exception | None = None
    if cursor is not None:
        try:
            cursor.close()
        except Exception as error:
            cleanup_error = error
    if connection is not None:
        try:
            connection.close()
        except Exception as error:
            if cleanup_error is None:
                cleanup_error = error
    return cleanup_error
