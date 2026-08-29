from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from tests.market_fakes import FakeVerificadorAcoesConcluidas

from zeny_project_handler.adapters.market.sql_server import (
    CONSULTA_ACAO_CONCLUIDA_SQL,
    CONSULTA_MERCADO_SQL,
    ClassificadorMercadoSqlServer,
    VerificadorAcoesConcluidasSqlServer,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.market import DescricaoAcao, Mercado
from zeny_project_handler.ports.market import (
    DadosAcoesInvalidosError,
    DadosMercadoInvalidosError,
    DependenciaAcoesError,
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
    timeout_error: Exception | None = None
    closed: bool = False
    _timeout: int = field(default=0, init=False, repr=False)

    @property
    def timeout(self) -> int:
        return self._timeout

    @timeout.setter
    def timeout(self, value: int) -> None:
        if self.timeout_error is not None:
            raise self.timeout_error
        self._timeout = value

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


def _action_gateway(
    rows: list[tuple[object, ...]],
    *,
    execute_error: Exception | None = None,
    fetch_error: Exception | None = None,
    timeout_error: Exception | None = None,
    cursor_error: Exception | None = None,
    cursor_close_error: Exception | None = None,
    connection_close_error: Exception | None = None,
) -> tuple[
    VerificadorAcoesConcluidasSqlServer,
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
        timeout_error=timeout_error,
    )
    factory = FakeConnectionFactory(connection)
    gateway = VerificadorAcoesConcluidasSqlServer(
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


def test_action_description_is_closed_over_the_two_exact_values() -> None:
    assert tuple(DescricaoAcao) == (
        DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL,
        DescricaoAcao.FALTA_SERVIDAO,
    )
    assert DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL.value == "AVALIAR IMPACTO AMBIENTAL"
    assert DescricaoAcao.FALTA_SERVIDAO.value == "FALTA SERVIDÃO"

    with pytest.raises(ValueError):
        DescricaoAcao("FALTA SERVIDAO")


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

    assert not imported & {
        "fastapi",
        "pyodbc",
        "sqlalchemy",
        "zeny_project_handler_client",
    }


def test_action_fake_preserves_strings_records_calls_and_controls_results() -> None:
    fake = FakeVerificadorAcoesConcluidas(resultado=True)

    assert fake.existe_acao_concluida(
        "0012345678",
        ("0007", "0123"),
        DescricaoAcao.FALTA_SERVIDAO,
    )
    assert fake.consultas == [
        (
            "0012345678",
            ("0007", "0123"),
            DescricaoAcao.FALTA_SERVIDAO,
        )
    ]

    failure = DependenciaAcoesError("falha segura")
    fake.erro = failure
    with pytest.raises(DependenciaAcoesError) as captured:
        fake.existe_acao_concluida(
            "0012345678",
            ("0007",),
            DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL,
        )
    assert captured.value is failure


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


@pytest.mark.parametrize(
    "action",
    [
        DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL,
        DescricaoAcao.FALTA_SERVIDAO,
    ],
)
def test_action_gateway_binds_one_service_and_exact_action(action: DescricaoAcao) -> None:
    gateway, factory, connection, cursor = _action_gateway([(action.value,)])

    assert gateway.existe_acao_concluida("0012345678", ("0007",), action)

    expected_sql = (
        "SELECT TACOES_DES FROM vBIAcoes "
        "WHERE NOTAS_NUM_NS = ? "
        "AND TSERVICOS_CT_COD IN (?) "
        "AND TACOES_DES = ? "
        "AND ACOES_DAT_CONCLUSAO IS NOT NULL;"
    )
    assert CONSULTA_ACAO_CONCLUIDA_SQL.format(placeholders="?") == expected_sql
    assert cursor.executions == [(expected_sql, (12345678, 7, action.value))]
    assert cursor.fetch_sizes == [1]
    assert factory.calls == [(CONNECTION_STRING, 7)]
    assert connection.timeout == 7
    assert cursor.closed
    assert connection.closed


def test_action_gateway_builds_only_n_placeholders_and_binds_parameters_in_order() -> None:
    action = DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL
    gateway, _, connection, cursor = _action_gateway([(action.value,)])

    assert gateway.existe_acao_concluida(
        "0000000042",
        ("0007", "0123", "9000"),
        action,
    )

    sql, parameters = cursor.executions[0]
    assert sql == (
        "SELECT TACOES_DES FROM vBIAcoes "
        "WHERE NOTAS_NUM_NS = ? "
        "AND TSERVICOS_CT_COD IN (?, ?, ?) "
        "AND TACOES_DES = ? "
        "AND ACOES_DAT_CONCLUSAO IS NOT NULL;"
    )
    assert parameters == (42, 7, 123, 9000, "AVALIAR IMPACTO AMBIENTAL")
    assert sql.count("?") == len(parameters)
    assert all(value not in sql for value in ("0000000042", "0007", "0123", "9000", action.value))
    assert cursor.closed
    assert connection.closed


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([], False),
        ([("FALTA SERVIDÃO",)], True),
        ([("FALTA SERVIDÃO",), ("FALTA SERVIDÃO",)], True),
    ],
)
def test_action_gateway_has_existential_cardinality(
    rows: list[tuple[object, ...]],
    expected: bool,
) -> None:
    gateway, _, connection, cursor = _action_gateway(rows)

    assert (
        gateway.existe_acao_concluida(
            "1234567890",
            ("1234",),
            DescricaoAcao.FALTA_SERVIDAO,
        )
        is expected
    )
    assert cursor.fetch_sizes == [1]
    assert cursor.closed
    assert connection.closed


def test_action_gateway_default_connection_preserves_readonly_autocommit_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action = DescricaoAcao.FALTA_SERVIDAO
    cursor = FakeCursor([(action.value,)])
    connection = FakeConnection(cursor)
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_connect(connection_string: str, **options: object) -> FakeConnection:
        calls.append((connection_string, options))
        return connection

    monkeypatch.setattr(
        "zeny_project_handler.adapters.market.sql_server.pyodbc.connect",
        fake_connect,
    )
    gateway = VerificadorAcoesConcluidasSqlServer(CONNECTION_STRING, timeout_seconds=9)

    assert gateway.existe_acao_concluida("1234567890", ("0007",), action)
    assert calls == [
        (
            CONNECTION_STRING,
            {"autocommit": True, "readonly": True, "timeout": 9},
        )
    ]
    assert connection.timeout == 9
    assert cursor.closed
    assert connection.closed


@pytest.mark.parametrize(
    ("numero_ns", "service_codes", "action"),
    [
        ("123", ("0007",), DescricaoAcao.FALTA_SERVIDAO),
        ("1234567890", (), DescricaoAcao.FALTA_SERVIDAO),
        ("1234567890", ("007",), DescricaoAcao.FALTA_SERVIDAO),
        ("1234567890", ("\uff11\uff12\uff13\uff14",), DescricaoAcao.FALTA_SERVIDAO),
        (
            "1234567890",
            ("0007",),
            cast(DescricaoAcao, "AÇÃO ARBITRÁRIA"),
        ),
    ],
)
def test_action_gateway_rejects_invalid_input_before_opening_connection(
    numero_ns: str,
    service_codes: tuple[str, ...],
    action: DescricaoAcao,
) -> None:
    gateway, factory, _, _ = _action_gateway([])

    with pytest.raises(DomainValidationError):
        gateway.existe_acao_concluida(numero_ns, service_codes, action)

    assert factory.calls == []


@pytest.mark.parametrize(
    "rows",
    [
        [(None,)],
        [("FALTA SERVIDÃO",)],
        [("AVALIAR IMPACTO AMBIENTAL", "unexpected")],
    ],
)
def test_action_gateway_rejects_invalid_external_rows_and_closes_resources(
    rows: list[tuple[object, ...]],
) -> None:
    gateway, _, connection, cursor = _action_gateway(rows)

    with pytest.raises(DadosAcoesInvalidosError, match="dados inconsistentes"):
        gateway.existe_acao_concluida(
            "1234567890",
            ("0007",),
            DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL,
        )

    assert cursor.closed
    assert connection.closed


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


@pytest.mark.parametrize("failure_stage", ["connection", "timeout", "cursor", "execute", "fetch"])
def test_action_gateway_translates_every_driver_stage_and_closes_available_resources(
    failure_stage: str,
) -> None:
    driver_error = TimeoutError(f"HYT00 timeout {CONNECTION_STRING}")
    gateway, factory, connection, cursor = _action_gateway(
        [(DescricaoAcao.FALTA_SERVIDAO.value,)],
        timeout_error=driver_error if failure_stage == "timeout" else None,
        cursor_error=driver_error if failure_stage == "cursor" else None,
        execute_error=driver_error if failure_stage == "execute" else None,
        fetch_error=driver_error if failure_stage == "fetch" else None,
    )
    if failure_stage == "connection":
        factory.error = driver_error

    with pytest.raises(DependenciaAcoesError) as captured:
        gateway.existe_acao_concluida(
            "0012345678",
            ("0007",),
            DescricaoAcao.FALTA_SERVIDAO,
        )

    public_error = f"{captured.value!s} {captured.value!r}"
    assert str(captured.value) == "O cadastro externo de ações não pôde ser consultado"
    assert "sql-fixture.invalid" not in public_error
    assert "fixture-user" not in public_error
    assert "fixture-secret" not in public_error
    assert "HYT00" not in public_error
    assert captured.value.__cause__ is driver_error
    assert connection.closed is (failure_stage != "connection")
    assert cursor.closed is (failure_stage in {"execute", "fetch"})


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


@pytest.mark.parametrize("failure_stage", ["cursor_close", "connection_close"])
def test_action_gateway_translates_cleanup_failure_and_attempts_both_closes(
    failure_stage: str,
) -> None:
    cleanup_error = RuntimeError(f"cleanup {CONNECTION_STRING}")
    gateway, _, connection, cursor = _action_gateway(
        [(DescricaoAcao.FALTA_SERVIDAO.value,)],
        cursor_close_error=cleanup_error if failure_stage == "cursor_close" else None,
        connection_close_error=cleanup_error if failure_stage == "connection_close" else None,
    )

    with pytest.raises(DependenciaAcoesError) as captured:
        gateway.existe_acao_concluida(
            "1234567890",
            ("0007",),
            DescricaoAcao.FALTA_SERVIDAO,
        )

    assert captured.value.__cause__ is cleanup_error
    assert str(captured.value) == "O cadastro externo de ações não pôde ser consultado"
    assert CONNECTION_STRING not in str(captured.value)
    assert cursor.closed
    assert connection.closed


def test_action_cleanup_failure_does_not_mask_invalid_external_data() -> None:
    gateway, _, connection, cursor = _action_gateway(
        [(None,)],
        cursor_close_error=RuntimeError("close cursor"),
        connection_close_error=RuntimeError("close connection"),
    )

    with pytest.raises(DadosAcoesInvalidosError):
        gateway.existe_acao_concluida(
            "1234567890",
            ("0007",),
            DescricaoAcao.FALTA_SERVIDAO,
        )

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


def test_action_gateway_configuration_is_validated_and_secret_is_absent_from_repr() -> None:
    gateway, _, _, _ = _action_gateway([])

    assert CONNECTION_STRING not in repr(gateway)
    assert "connection_string" not in repr(gateway)
    assert "timeout_seconds" not in repr(gateway)

    with pytest.raises(ValueError, match="string de conexão"):
        VerificadorAcoesConcluidasSqlServer("   ")
    with pytest.raises(ValueError, match="inteiro positivo"):
        VerificadorAcoesConcluidasSqlServer(CONNECTION_STRING, timeout_seconds=0)
    with pytest.raises(ValueError, match="inteiro positivo"):
        VerificadorAcoesConcluidasSqlServer(CONNECTION_STRING, timeout_seconds=True)
