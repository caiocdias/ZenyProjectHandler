from __future__ import annotations

import pytest

from zeny_project_handler.domain.market import Mercado
from zeny_project_handler_server.market_smoke import run_smoke

CONNECTION = (
    "Driver={ODBC Driver 18 for SQL Server};Server=smoke.invalid;Uid=fixture;Pwd=segredo-smoke"
)


class _Classifier:
    def __init__(self, result: Mercado | Exception) -> None:
        self._result = result
        self.calls: list[str] = []

    def classificar(self, numero_ns: str) -> Mercado:
        self.calls.append(numero_ns)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _environment(**overrides: str) -> dict[str, str]:
    return {
        "ZENY_MARKET_SQLSERVER_SMOKE_ENABLED": "1",
        "ZENY_MARKET_SQLSERVER_SMOKE_NS": "0012345678",
        "ZENY_MARKET_SQLSERVER_CONNECTION_STRING": CONNECTION,
        "ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS": "9",
        **overrides,
    }


def test_smoke_does_not_construct_classifier_without_explicit_opt_in() -> None:
    constructed = False

    def factory(connection_string: str, *, timeout_seconds: int) -> _Classifier:
        nonlocal constructed
        del connection_string, timeout_seconds
        constructed = True
        return _Classifier(Mercado.RURAL)

    messages: list[str] = []
    result = run_smoke(
        {},
        classifier_factory=factory,
        output=messages.append,
    )

    assert result == 2
    assert not constructed
    assert messages == [
        "SMOKE SQL SERVER: NÃO EXECUTADO — "
        "defina ZENY_MARKET_SQLSERVER_SMOKE_ENABLED=1 explicitamente"
    ]


def test_smoke_executes_one_safe_read_with_configured_timeout() -> None:
    classifier = _Classifier(Mercado.URBANO)
    factory_calls: list[tuple[str, int]] = []

    def factory(connection_string: str, *, timeout_seconds: int) -> _Classifier:
        factory_calls.append((connection_string, timeout_seconds))
        return classifier

    messages: list[str] = []
    result = run_smoke(
        _environment(),
        classifier_factory=factory,
        output=messages.append,
    )

    assert result == 0
    assert factory_calls == [(CONNECTION, 9)]
    assert classifier.calls == ["0012345678"]
    assert messages == ["SMOKE SQL SERVER: APROVADO — mercado=URBANO"]
    assert CONNECTION not in "".join(messages)


@pytest.mark.parametrize(
    "environment",
    [
        _environment(ZENY_MARKET_SQLSERVER_CONNECTION_STRING=""),
        _environment(ZENY_MARKET_SQLSERVER_SMOKE_NS=""),
        _environment(ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS="0"),
        _environment(ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS="inválido"),
    ],
)
def test_smoke_rejects_missing_or_invalid_configuration_without_secret(
    environment: dict[str, str],
) -> None:
    messages: list[str] = []

    result = run_smoke(environment, output=messages.append)

    assert result == 1
    assert CONNECTION not in "".join(messages)


def test_smoke_hides_unexpected_driver_details() -> None:
    failure = RuntimeError(f"HYT00 host user password {CONNECTION}")
    classifier = _Classifier(failure)

    def factory(connection_string: str, *, timeout_seconds: int) -> _Classifier:
        del connection_string, timeout_seconds
        return classifier

    messages: list[str] = []
    result = run_smoke(
        _environment(),
        classifier_factory=factory,
        output=messages.append,
    )

    assert result == 1
    rendered = "".join(messages)
    assert rendered == "SMOKE SQL SERVER: REPROVADO — consulta somente leitura não concluída"
    assert CONNECTION not in rendered
