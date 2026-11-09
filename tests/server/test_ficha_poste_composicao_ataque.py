"""E07.2.1 (ataque): só ``symbol_composition`` decide o interpretador da composição."""

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


def _compor(
    monkeypatch: pytest.MonkeyPatch, settings: ServerSettings
) -> list[tuple[Any, tuple[Any, ...]]]:
    recebidos: list[tuple[Any, tuple[Any, ...]]] = []
    original = ExecutarPipelineInterpretacao

    def registrar(interpretador: Any, *args: Any, **kwargs: Any) -> Any:
        recebidos.append((interpretador, args))
        return original(interpretador, *args, **kwargs)

    monkeypatch.setattr(server_composition, "ExecutarPipelineInterpretacao", registrar)
    runtime = server_composition.compose_server_runtime(
        settings,
        market_classifier=FakeClassificadorMercado(),
        action_verifier=FakeVerificadorAcoesConcluidas(),
    )
    runtime.close()
    return recebidos


def _settings(data: Path, **extras: Any) -> ServerSettings:
    return ServerSettings(
        password="senha de composição da ficha do poste",
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=data,
        **extras,
    )


@pytest.mark.parametrize(
    "extras",
    [
        pytest.param({}, id="padrao"),
        pytest.param({"symbol_profile": "vector-only"}, id="perfil-vector-only"),
        pytest.param({"symbol_profile": "balanced", "symbol_raster_dpi": 200}, id="dpi-alterado"),
        pytest.param({"complementary_ocr": True}, id="ocr-complementar"),
        pytest.param(
            {"symbol_model_path": Path("modelo-que-nao-existe.onnx")}, id="caminho-de-modelo"
        ),
    ],
)
def test_opcao_desligada_ignora_as_demais_opcoes_de_simbolos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extras: dict[str, Any]
) -> None:
    recebidos = _compor(
        monkeypatch, _settings(tmp_path / "dados", symbol_composition=False, **extras)
    )

    assert [type(item) for item, _ in recebidos] == [InterpretadorRegrasExplicitas]
    assert recebidos[0][0].versao == "25.0"
    assert recebidos[0][0].nome == InterpretadorRegrasExplicitas.nome


@pytest.mark.parametrize("perfil", ["balanced", "vector-only"])
def test_opcao_ligada_usa_a_subclasse_em_qualquer_perfil(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, perfil: str
) -> None:
    recebidos = _compor(
        monkeypatch,
        _settings(tmp_path / "dados", symbol_composition=True, symbol_profile=perfil),
    )

    assert [type(item) for item, _ in recebidos] == [InterpretadorFichaPoste]
    assert recebidos[0][0].versao == "27.0"


def test_subclasse_e_padrao_compartilham_nome_e_registro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desligada = _compor(monkeypatch, _settings(tmp_path / "a", symbol_composition=False))
    ligada = _compor(monkeypatch, _settings(tmp_path / "b", symbol_composition=True))

    assert desligada[0][0].nome == ligada[0][0].nome
    assert desligada[0][1][0].assinatura() == ligada[0][1][0].assinatura()


@pytest.mark.parametrize(
    ("ambiente", "classe", "versao"),
    [
        pytest.param({}, InterpretadorRegrasExplicitas, "25.0", id="ausente"),
        pytest.param(
            {"ZENY_SERVER_SYMBOL_COMPOSITION": "false"},
            InterpretadorRegrasExplicitas,
            "25.0",
            id="false",
        ),
        pytest.param(
            {"ZENY_SERVER_SYMBOL_PROFILE": "vector-only"},
            InterpretadorRegrasExplicitas,
            "25.0",
            id="perfil-sem-a-flag",
        ),
        pytest.param(
            {"ZENY_SERVER_SYMBOL_COMPOSITION": "TRUE"},
            InterpretadorFichaPoste,
            "27.0",
            id="true-maiusculo",
        ),
    ],
)
def test_ambiente_decide_pela_variavel_da_composicao(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ambiente: dict[str, str],
    classe: type,
    versao: str,
) -> None:
    settings = ServerSettings.from_environment(
        {
            "ZENY_SERVER_PASSWORD": "senha de composição da ficha do poste",
            "ZENY_MARKET_SQLSERVER_CONNECTION_STRING": "fixture-market-connection",
            "ZENY_SERVER_DATA_DIRECTORY": str(tmp_path / "dados"),
            **ambiente,
        }
    )

    recebidos = _compor(monkeypatch, settings)

    assert [type(item) for item, _ in recebidos] == [classe]
    assert recebidos[0][0].versao == versao


def test_reabrir_o_servidor_no_mesmo_volume_mantem_a_escolha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dados = tmp_path / "dados"
    ligada = _settings(dados, symbol_composition=True)
    desligada = _settings(dados, symbol_composition=False)

    sequencia = [
        _compor(monkeypatch, ligada),
        _compor(monkeypatch, ligada),
        _compor(monkeypatch, desligada),
        _compor(monkeypatch, ligada),
    ]

    assert [[type(i) for i, _ in s] for s in sequencia] == [
        [InterpretadorFichaPoste],
        [InterpretadorFichaPoste],
        [InterpretadorRegrasExplicitas],
        [InterpretadorFichaPoste],
    ]
