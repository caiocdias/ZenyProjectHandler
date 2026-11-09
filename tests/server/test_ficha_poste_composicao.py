"""E07.2.1: a composição escolhe o interpretador conforme ``symbol_composition``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.market_fakes import FakeClassificadorMercado, FakeVerificadorAcoesConcluidas
from zeny_project_handler.adapters.interpretation import InterpretadorRegrasExplicitas
from zeny_project_handler.adapters.interpretation.ficha_poste import InterpretadorFichaPoste
from zeny_project_handler.application.interpretation_pipeline import ExecutarPipelineInterpretacao
from zeny_project_handler_server import composition as server_composition
from zeny_project_handler_server.config import ServerSettings


def _interpretadores_compostos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, symbol_composition: bool
) -> list[Any]:
    recebidos: list[Any] = []
    original = ExecutarPipelineInterpretacao

    def registrar(interpretador: Any, *args: Any, **kwargs: Any) -> Any:
        recebidos.append(interpretador)
        return original(interpretador, *args, **kwargs)

    monkeypatch.setattr(server_composition, "ExecutarPipelineInterpretacao", registrar)
    settings = ServerSettings(
        password="senha de composição da ficha do poste",
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=tmp_path / "server-data",
        symbol_composition=symbol_composition,
        symbol_profile="vector-only",
        symbol_model_path=None,
    )
    runtime = server_composition.compose_server_runtime(
        settings,
        market_classifier=FakeClassificadorMercado(),
        action_verifier=FakeVerificadorAcoesConcluidas(),
    )
    runtime.close()
    return recebidos


def test_sem_symbol_composition_usa_o_interpretador_padrao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recebidos = _interpretadores_compostos(tmp_path, monkeypatch, symbol_composition=False)

    assert [type(item) for item in recebidos] == [InterpretadorRegrasExplicitas]
    assert recebidos[0].versao == "25.0"


def test_com_symbol_composition_usa_a_subclasse_da_ficha_do_poste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recebidos = _interpretadores_compostos(tmp_path, monkeypatch, symbol_composition=True)

    assert [type(item) for item in recebidos] == [InterpretadorFichaPoste]
    assert recebidos[0].versao == "26.0"
