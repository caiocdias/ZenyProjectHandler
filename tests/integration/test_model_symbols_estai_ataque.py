# mypy: disable-error-code="no-untyped-call"
"""E06.3.4, Task 3 (testador): ataques à habilitação das 3 variantes de estai e à versão 1.5.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.pdf_temporario import salvar_pagina
from tests.integration.test_model_symbols_estai_runner import (
    _BASE,
    _CINZA,
    _DENTE,
    _ESPESSURA,
    _PRETO,
    _VARIANTES,
    _de_estai,
    _desenhar,
)
from tests.integration.test_model_symbols_runner import _METODO_NOVO, _fonte, _settings

from zeny_project_handler.adapters.analysis import declarative_symbols, model_symbols
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

pytestmark = pytest.mark.integration


def _variantes() -> list[dict[str, Any]]:
    return [v for p in declarative_symbols.carregar_pacotes() for v in p.get("variants", [])]


def test_forked_stem_habilitado_so_nas_tres_variantes_de_f02_14() -> None:
    habilitadas = {
        v["id"]
        for v in _variantes()
        if v["recognition"]["status"] == "enabled"
        and v["recognition"]["grammar"]["kind"] == "forked_stem"
    }
    assert habilitadas == set(_VARIANTES)


def test_s15_continua_pendente_com_motivo() -> None:
    s15 = [v for v in _variantes() if "-s15-" in v["id"]]
    assert s15, "variantes s15 sumiram do inventario"
    for v in s15:
        assert v["recognition"]["status"] == "pending", v["id"]
        assert v["recognition"]["reason"], v["id"]


def test_estai_habilitado_sem_reason_e_as_outras_14_pendentes() -> None:
    f14 = [v for v in _variantes() if v["id"].startswith("cemig-eo-r3-s14-")]
    habilitadas = [v for v in f14 if v["recognition"]["status"] == "enabled"]
    pendentes = [v for v in f14 if v["recognition"]["status"] == "pending"]
    assert {v["id"] for v in habilitadas} == set(_VARIANTES)
    assert all("reason" not in v["recognition"] for v in habilitadas)
    assert len(pendentes) == len(f14) - 3
    assert all(v["recognition"]["reason"] for v in pendentes)
    assert all(v["recognition"]["grammar"]["max_span"] == 40 for v in habilitadas)


def test_contagens_52_habilitadas_e_371_pendentes() -> None:
    estados = [v["recognition"]["status"] for v in _variantes()]
    assert estados.count("enabled") == 52
    assert estados.count("pending") == 371
    assert len(estados) == 423


def test_versao_do_metodo_do_modelo_e_1_5_0() -> None:
    assert model_symbols._VERSAO == "1.5.0"


def test_padrao_nao_liga_a_composicao_de_simbolos(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for nome in list(os.environ):
        if "SYMBOL" in nome.upper():
            monkeypatch.delenv(nome, raising=False)
    padrao = ServerSettings(
        password="senha segura do padrao", market_sqlserver_connection_string="x"
    )
    assert padrao.symbol_composition is False


def _rodar(tmp_path: Path, desenhar: Any) -> list[Any]:
    caminho = salvar_pagina(tmp_path, desenhar)
    documento, fonte = _fonte(caminho)
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()
    composto = runner.run(documento, fonte)
    return [o for o in _de_estai(composto) if o.metodo_assinatura == novo]


def test_dois_estais_distantes_geram_duas_observacoes(tmp_path: Path) -> None:
    def desenho(pagina: pymupdf.Page) -> None:
        _desenhar(pagina, _PRETO, False, False)
        for ini, fim in (((_BASE[0], _BASE[1] + 100), (_BASE[0] + 16, _BASE[1] + 100)),):
            pagina.draw_line(ini, fim, color=_CINZA, width=_ESPESSURA)
        v = (_BASE[0] + 16, _BASE[1] + 100)
        pagina.draw_line(v, (v[0] + _DENTE * 0.9, v[1] - 5.3), color=_CINZA, width=_ESPESSURA)
        pagina.draw_line(v, (v[0] + _DENTE * 0.9, v[1] + 5.3), color=_CINZA, width=_ESPESSURA)

    assert len(_rodar(tmp_path, desenho)) == 2


def test_haste_sem_garfo_nao_gera_estai(tmp_path: Path) -> None:
    def desenho(pagina: pymupdf.Page) -> None:
        pagina.draw_line(_BASE, (_BASE[0] + 16, _BASE[1]), color=_PRETO, width=_ESPESSURA)

    assert _rodar(tmp_path, desenho) == []


def test_estai_acima_do_max_span_40_nao_e_reconhecido(tmp_path: Path) -> None:
    def desenho(pagina: pymupdf.Page) -> None:
        _desenhar(pagina, _PRETO, False, False)
        # amplia drasticamente: haste de 80 + garfo
        pagina.draw_line((10.0, 250.0), (110.0, 250.0), color=_PRETO, width=_ESPESSURA)
        pagina.draw_line((110.0, 250.0), (150.0, 230.0), color=_PRETO, width=_ESPESSURA)
        pagina.draw_line((110.0, 250.0), (150.0, 270.0), color=_PRETO, width=_ESPESSURA)

    assert len(_rodar(tmp_path, desenho)) == 1  # so o pequeno
