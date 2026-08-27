"""Smoke opt-in e somente leitura do classificador SQL Server da release."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Protocol

from zeny_project_handler.adapters.market.sql_server import ClassificadorMercadoSqlServer
from zeny_project_handler.domain.market import Mercado

OPT_IN_ENVIRONMENT_VARIABLE = "ZENY_MARKET_SQLSERVER_SMOKE_ENABLED"
SERVICE_NOTE_ENVIRONMENT_VARIABLE = "ZENY_MARKET_SQLSERVER_SMOKE_NS"
CONNECTION_ENVIRONMENT_VARIABLE = "ZENY_MARKET_SQLSERVER_CONNECTION_STRING"
TIMEOUT_ENVIRONMENT_VARIABLE = "ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS"


class _Classificador(Protocol):
    def classificar(self, numero_ns: str) -> Mercado: ...


class _FabricaClassificador(Protocol):
    def __call__(
        self,
        connection_string: str,
        *,
        timeout_seconds: int,
    ) -> _Classificador: ...


def run_smoke(
    environment: Mapping[str, str] | None = None,
    *,
    classifier_factory: _FabricaClassificador = ClassificadorMercadoSqlServer,
    output: Callable[[str], None] = print,
) -> int:
    """Consulte uma NS somente quando o opt-in exato estiver presente."""
    values = os.environ if environment is None else environment
    if values.get(OPT_IN_ENVIRONMENT_VARIABLE) != "1":
        output(
            "SMOKE SQL SERVER: NÃO EXECUTADO — "
            f"defina {OPT_IN_ENVIRONMENT_VARIABLE}=1 explicitamente"
        )
        return 2

    connection_string = values.get(CONNECTION_ENVIRONMENT_VARIABLE, "").strip()
    numero_ns = values.get(SERVICE_NOTE_ENVIRONMENT_VARIABLE, "").strip()
    if not connection_string or not numero_ns:
        output("SMOKE SQL SERVER: REPROVADO — configuração obrigatória ausente")
        return 1

    try:
        timeout_seconds = int(values.get(TIMEOUT_ENVIRONMENT_VARIABLE, "15"))
        if timeout_seconds <= 0:
            raise ValueError
        classifier = classifier_factory(
            connection_string,
            timeout_seconds=timeout_seconds,
        )
        market = classifier.classificar(numero_ns)
    except Exception:
        # O detalhe ODBC pode conter host/usuário; a evidência do smoke é deliberadamente opaca.
        output("SMOKE SQL SERVER: REPROVADO — consulta somente leitura não concluída")
        return 1

    output(f"SMOKE SQL SERVER: APROVADO — mercado={market.value}")
    return 0


def main() -> int:
    return run_smoke()


if __name__ == "__main__":
    raise SystemExit(main())
