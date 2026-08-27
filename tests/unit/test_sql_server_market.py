from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from zeny_project_handler.adapters.market.sql_server import (
    CONSULTA_MERCADO_SQL,
    ClassificadorMercadoSqlServer,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.market import Mercado
from zeny_project_handler.ports.market import (
    DadosMercadoInvalidosError,
    DependenciaMercadoError,
    MercadoNaoEncontradoError,
)

ROOT = Path(__file__).parents[2]
CONNECTION_STRING = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=sql-fixture.invalid;UID=fixture-user;PWD=fixture-secret;"
)


@dataclass
class FakeCursor:
    rows: list[tuple[object, ...]]
    execute_error: Exception | None = None
    fetch_error: Exception | None = None
    close_error: Exception | None = None
    executions: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    fetch_sizes: list[int] = field(default_factory=list)
    closed: bool = False

    def execute(self, sql: str, *parameters: object) -> object:
        self.executions.append((sql, parameters))
        if self.execute_error is not None:
            raise self.execute_error
        return self

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        self.fetch_sizes.append(size)
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.rows[:size]

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


@dataclass
class FakeConnection:
    cursor_value: FakeCursor
    cursor_error: Exception | None = None
    close_error: Exception | None = None
    timeout: int = 0
    closed: bool = False

    def cursor(self) -> FakeCursor:
        if self.cursor_error is not None:
            raise self.cursor_error
        return self.cursor_value

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


@dataclass
class FakeConnectionFactory:
    connection: FakeConnection
    error: Exception | None = None
    calls: list[tuple[str, int]] = field(default_factory=list)

    def __call__(self, connection_string: str, timeout_seconds: int) -> FakeConnection:
        self.calls.append((connection_string, timeout_seconds))
        if self.error is not None:
            raise self.error
        return self.connection


def _gateway(
    rows: list[tuple[object, ...]],
    *,
    execute_error: Exception | None = None,
    fetch_error: Exception | None = None,
    cursor_error: Exception | None = None,
    cursor_close_error: Exception | None = None,
    connection_close_error: Exception | None = None,
) -> tuple[
    ClassificadorMercadoSqlServer,
    FakeConnectionFactory,
    FakeConnection,
    FakeCursor,
]:
    cursor = FakeCursor(
        rows,
        execute_error=execute_error,
        fetch_error=fetch_error,
        close_error=cursor_close_error,
    )
    connection = FakeConnection(
        cursor,
        cursor_error=cursor_error,
        close_error=connection_close_error,
    )
    factory = FakeConnectionFactory(connection)
    gateway = ClassificadorMercadoSqlServer(
        CONNECTION_STRING,
        timeout_seconds=7,
        connection_factory=factory,
    )
    return gateway, factory, connection, cursor


def test_market_enum_is_canonical_and_rejects_other_values() -> None:
    assert tuple(Mercado) == (Mercado.RURAL, Mercado.URBANO)
    assert Mercado.RURAL.value == "RURAL"
    assert Mercado.URBANO.value == "URBANO"

    with pytest.raises(ValueError):
        Mercado("INDUSTRIAL")


def test_market_port_has_no_infrastructure_dependency() -> None:
    source = ROOT / "src" / "zeny_project_handler" / "ports" / "market.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = {
        node.module.partition(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported.update(
        alias.name.partition(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert not imported & {"pyodbc", "sqlalchemy", "fastapi"}


@pytest.mark.parametrize(
    ("database_value", "expected"),
    [(" rural ", Mercado.RURAL), ("uRbAnO", Mercado.URBANO)],
)
def test_gateway_accepts_only_limited_market_normalization(
    database_value: str,
    expected: Mercado,
) -> None:
    gateway, _, connection, cursor = _gateway([(database_value,)])

    assert gateway.classificar("1234567890") is expected
    assert connection.closed
    assert cursor.closed


def test_gateway_sends_exact_sql_integer_parameter_and_two_row_limit() -> None:
    gateway, factory, connection, cursor = _gateway([("URBANO",)])

    result = gateway.classificar("0012345678")

    assert result is Mercado.URBANO
    assert CONSULTA_MERCADO_SQL == (
        "SELECT NOTAS_COD_MERCADO FROM TB_NOTAS WHERE NOTAS_NUM_NS = ?;"
    )
    assert cursor.executions == [(CONSULTA_MERCADO_SQL, (12345678,))]
    assert cursor.fetch_sizes == [2]
    assert factory.calls == [(CONNECTION_STRING, 7)]
    assert connection.timeout == 7
    assert cursor.closed
    assert connection.closed


def test_default_connection_uses_read_only_autocommit_and_connection_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor([("RURAL",)])
    connection = FakeConnection(cursor)
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_connect(connection_string: str, **options: object) -> FakeConnection:
        calls.append((connection_string, options))
        return connection

    monkeypatch.setattr(
        "zeny_project_handler.adapters.market.sql_server.pyodbc.connect",
        fake_connect,
    )

    gateway = ClassificadorMercadoSqlServer(CONNECTION_STRING, timeout_seconds=9)

    assert gateway.classificar("1234567890") is Mercado.RURAL
    assert calls == [
        (
            CONNECTION_STRING,
            {"autocommit": True, "readonly": True, "timeout": 9},
        )
    ]
    assert connection.timeout == 9


def test_gateway_rejects_invalid_ns_before_opening_connection() -> None:
    gateway, factory, _, _ = _gateway([("RURAL",)])

    with pytest.raises(DomainValidationError):
        gateway.classificar("123")

    assert factory.calls == []


def test_gateway_reports_absent_market_and_closes_resources() -> None:
    gateway, _, connection, cursor = _gateway([])

    with pytest.raises(MercadoNaoEncontradoError, match="não possui mercado cadastrado"):
        gateway.classificar("1234567890")

    assert cursor.closed
    assert connection.closed


@pytest.mark.parametrize("database_value", [None, "INDUSTRIAL", "UR BANO", 1])
def test_gateway_rejects_null_or_invalid_market(database_value: object) -> None:
    gateway, _, connection, cursor = _gateway([(database_value,)])

    with pytest.raises(DadosMercadoInvalidosError, match="dados inconsistentes"):
        gateway.classificar("1234567890")

    assert cursor.closed
    assert connection.closed


def test_gateway_rejects_duplicate_rows() -> None:
    gateway, _, connection, cursor = _gateway([("RURAL",), ("RURAL",), ("RURAL",)])

    with pytest.raises(DadosMercadoInvalidosError, match="dados inconsistentes"):
        gateway.classificar("1234567890")

    assert cursor.fetch_sizes == [2]
    assert cursor.closed
    assert connection.closed


@pytest.mark.parametrize("failure_stage", ["execute", "fetch"])
def test_gateway_translates_driver_error_and_closes_resources(failure_stage: str) -> None:
    driver_error = TimeoutError(f"HYT00 timeout {CONNECTION_STRING}")
    gateway, _, connection, cursor = _gateway(
        [("RURAL",)],
        execute_error=driver_error if failure_stage == "execute" else None,
        fetch_error=driver_error if failure_stage == "fetch" else None,
    )

    with pytest.raises(DependenciaMercadoError) as captured:
        gateway.classificar("1234567890")

    public_error = f"{captured.value!s} {captured.value!r}"
    assert "sql-fixture.invalid" not in public_error
    assert "fixture-user" not in public_error
    assert "fixture-secret" not in public_error
    assert "HYT00" not in public_error
    assert captured.value.__cause__ is driver_error
    assert cursor.closed
    assert connection.closed


def test_gateway_translates_connection_timeout_without_leaking_connection() -> None:
    gateway, factory, _, _ = _gateway([("RURAL",)])
    timeout = TimeoutError(f"login timeout {CONNECTION_STRING}")
    factory.error = timeout

    with pytest.raises(DependenciaMercadoError) as captured:
        gateway.classificar("1234567890")

    assert str(captured.value) == "O cadastro externo de mercado não pôde ser consultado"
    assert CONNECTION_STRING not in str(captured.value)
    assert captured.value.__cause__ is timeout


def test_gateway_closes_connection_when_cursor_creation_fails() -> None:
    failure = RuntimeError("cursor failure")
    gateway, _, connection, cursor = _gateway([("RURAL",)], cursor_error=failure)

    with pytest.raises(DependenciaMercadoError) as captured:
        gateway.classificar("1234567890")

    assert captured.value.__cause__ is failure
    assert not cursor.closed
    assert connection.closed


@pytest.mark.parametrize("failure_stage", ["cursor_close", "connection_close"])
def test_gateway_translates_cleanup_failure_and_attempts_both_closes(
    failure_stage: str,
) -> None:
    cleanup_error = RuntimeError(f"cleanup {CONNECTION_STRING}")
    gateway, _, connection, cursor = _gateway(
        [("RURAL",)],
        cursor_close_error=cleanup_error if failure_stage == "cursor_close" else None,
        connection_close_error=cleanup_error if failure_stage == "connection_close" else None,
    )

    with pytest.raises(DependenciaMercadoError) as captured:
        gateway.classificar("1234567890")

    assert captured.value.__cause__ is cleanup_error
    assert CONNECTION_STRING not in str(captured.value)
    assert cursor.closed
    assert connection.closed


def test_cleanup_failure_does_not_mask_invalid_external_data() -> None:
    gateway, _, connection, cursor = _gateway(
        [(None,)],
        cursor_close_error=RuntimeError("close cursor"),
        connection_close_error=RuntimeError("close connection"),
    )

    with pytest.raises(DadosMercadoInvalidosError):
        gateway.classificar("1234567890")

    assert cursor.closed
    assert connection.closed


def test_gateway_configuration_is_validated_and_secret_is_absent_from_repr() -> None:
    gateway, _, _, _ = _gateway([("RURAL",)])

    assert CONNECTION_STRING not in repr(gateway)
    assert "connection_string" not in repr(gateway)
    assert "timeout_seconds" not in repr(gateway)

    with pytest.raises(ValueError, match="string de conexão"):
        ClassificadorMercadoSqlServer("   ")
    with pytest.raises(ValueError, match="inteiro positivo"):
        ClassificadorMercadoSqlServer(CONNECTION_STRING, timeout_seconds=0)
    with pytest.raises(ValueError, match="inteiro positivo"):
        ClassificadorMercadoSqlServer(CONNECTION_STRING, timeout_seconds=True)
