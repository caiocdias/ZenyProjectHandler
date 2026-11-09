"""Opção desligada: sem `ZENY_SERVER_SYMBOL_COMPOSITION` o motor de símbolos nunca roda."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.pdf_fixtures import create_analysis_pdf
from tests.server.test_e15_symbol_jobs import (
    _client,
    _create_project_with_pdf,
    _settings,
    _start_analysis,
    _terminal,
)
from zeny_project_handler.adapters.analysis import model_symbols
from zeny_project_handler.application.mvp_workflow import ServicoFluxoMvp
from zeny_project_handler_contracts.enums import JobStatus
from zeny_project_handler_server.config import (
    SYMBOL_COMPOSITION_ENVIRONMENT_VARIABLE,
    ServerSettings,
)
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner


@pytest.mark.parametrize("valor", ["false", "FALSE", " false "])
def test_variavel_desligada_ou_ausente_nao_liga_a_composicao(valor: str) -> None:
    base = {
        "ZENY_SERVER_PASSWORD": "senha segura da opcao desligada",
        "ZENY_MARKET_SQLSERVER_CONNECTION_STRING": "fixture-market-connection",
    }
    ausente = ServerSettings.from_environment({**base})
    explicita = ServerSettings.from_environment(
        {**base, SYMBOL_COMPOSITION_ENVIRONMENT_VARIABLE: valor}
    )
    assert ausente.symbol_composition is False
    assert explicita.symbol_composition is False


def test_desligada_o_runner_e_none_e_nenhuma_observacao_do_modelo_chega_a_analise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def proibido(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("o motor de símbolos não pode rodar com a opção desligada")

    monkeypatch.setattr(SymbolCompositionRunner, "__init__", proibido)
    monkeypatch.setattr(SymbolCompositionRunner, "run", proibido)
    monkeypatch.setattr(model_symbols, "observar_pacotes_modelo", proibido)
    runners: list[Any] = []
    original = ServicoFluxoMvp.__init__

    def espiar(self: ServicoFluxoMvp, *args: Any, **kwargs: Any) -> None:
        runners.append(kwargs.get("symbol_runner"))
        original(self, *args, **kwargs)

    monkeypatch.setattr(ServicoFluxoMvp, "__init__", espiar)

    source = create_analysis_pdf(tmp_path / "desligada.pdf")
    data = tmp_path / "server-data"
    settings = _settings(data, enabled=False)
    with _client(settings) as client:
        project_id, version, _document_id = _create_project_with_pdf(client, source)
        job_id = _start_analysis(client, project_id, version, key="desligada")
        assert _terminal(client, job_id)["status"] == JobStatus.SUCCEEDED.value

    assert runners == [None]
    assert not list((data / "symbol_partial_runs").glob("*.json"))
    assert not list((settings.core_settings().analysis_cache_directory / "symbols").glob("*.json"))
