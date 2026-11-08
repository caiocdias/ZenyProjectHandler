"""Costuras da E06.3.2.2 com os pacotes reais (8 hastes habilitadas): runner, matriz e diff."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pymupdf
import pytest
import scripts.diff_simbolos_nucleo_motor as diff
from scripts.coverage_matrix_e16 import ROOT, _package_digest, build
from tests.fixtures.symbol_grammars.rect_diagonal import CASOS_RECT_DIAGONAL
from tests.fixtures.symbol_grammars.stem_bars import CASOS_HASTE, desenhar_positivo
from tests.integration.test_model_symbols_runner import _METODO_NOVO, _fonte, _settings
from tests.unit.test_diff_simbolos_nucleo_motor import _pagina, _recursos, _rodada, _rodar

from zeny_project_handler.adapters.analysis import declarative_symbols
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

_IDS_HASTE = [identidade for identidade, _ in CASOS_HASTE]
_IDS_BT = [identidade for identidade, _ in CASOS_RECT_DIAGONAL]
_CLASSE = {"s19": "ATERRAMENTO", "s21": "PARA_RAIOS_MT"}
# Quatro situações de cada família numa só página, longe umas das outras.
_CENTROS = [(80.0 + 120.0 * (i % 4), 80.0 + 160.0 * (i // 4)) for i in range(8)]


def _desenhar_as_oito(pagina: pymupdf.Page) -> None:
    for (identidade, _), centro in zip(CASOS_HASTE, _CENTROS, strict=True):
        desenhar_positivo(pagina, identidade, centro=centro)


def _pdf_das_oito(caminho: Path) -> None:
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        _desenhar_as_oito(documento.new_page(width=560, height=400))
        documento.save(caminho)


def test_pacotes_reais_tem_as_oito_hastes_habilitadas() -> None:
    habilitadas = {
        v["id"]
        for p in declarative_symbols.carregar_pacotes()
        for v in p["variants"]
        if v["recognition"]["status"] == "enabled"
        and v["recognition"].get("grammar", {}).get("kind") == "stem_bars"
    }
    assert habilitadas == set(_IDS_HASTE)


def test_runner_com_pacotes_reais_observa_e_reconcilia_as_oito_situacoes(tmp_path: Path) -> None:
    _pdf_das_oito(tmp_path / "h.pdf")
    documento, fonte = _fonte(tmp_path / "h.pdf")
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO)

    composto = runner.run(documento, fonte)

    assinatura = novo.assinatura()
    com_o_novo = [
        o
        for o in composto.occurrences
        if any(obs.metodo_assinatura == assinatura for obs in o.observations)
    ]
    classes = sorted(str(next(iter(o.alternatives)).classe) for o in com_o_novo if o.alternatives)
    assert classes == sorted(["ATERRAMENTO"] * 4 + ["PARA_RAIOS_MT"] * 4)
    # Cada ocorrência é uma só (legado e modelo fundidos), nunca duplicada.
    assert len(com_o_novo) == 8
    assert all(len({obs.metodo_assinatura for obs in o.observations}) >= 2 for o in com_o_novo)


def test_perfil_do_modelo_no_runner_esta_na_versao_1_2_0(tmp_path: Path) -> None:
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO)
    assert novo.versao == "1.2.0"
    assert novo.assinatura() != replace(novo, versao="1.1.0").assinatura()


def _e07_do_pacote(tmp_path: Path, pacotes: Path) -> Path:
    caminho = tmp_path / "e07.json"
    caminho.write_text(
        json.dumps(
            {
                "complete_inference": True,
                "package_sha256": _package_digest(pacotes),
                "by_family": {},
                "decisions": [],
            }
        ),
        encoding="utf-8",
    )
    return caminho


def test_matriz_dos_pacotes_reais_marca_as_doze_so_do_modelo_fora_do_dominio_no_motor(tmp_path: Path) -> None:
    pacotes = ROOT / "src/zeny_project_handler/adapters/analysis/symbol_packages"
    base = ROOT / "docs/data/matriz-simbologia-e16.csv"
    linhas, _ = build(
        ROOT / "docs/data/inventario-simbologia-v1.json",
        pacotes,
        None,
        None,
        _e07_do_pacote(tmp_path, pacotes),
        base,
    )
    por_id: dict[str, Any] = {linha["id"]: linha for linha in linhas}
    for identidade in [*_IDS_HASTE, *_IDS_BT]:
        assert por_id[identidade]["package_status"] == "enabled", identidade
        assert por_id[identidade]["declarative-vector-packages"] == "fora_do_dominio", identidade
    # Contraprova: uma variante habilitada de outra gramática continua exata.
    outras = [
        linha
        for linha in linhas
        if linha["package_status"] == "enabled"
        and linha["id"] not in {*_IDS_HASTE, *_IDS_BT}
    ]
    assert outras
    assert all(linha["declarative-vector-packages"] == "id_exato_sintetico" for linha in outras)


def test_diff_com_pacotes_reais_deixa_as_hastes_fora_da_comparacao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diff.recursos.cache_clear()
    monkeypatch.setattr(diff, "recursos", lambda: _recursos(declarative_symbols.carregar_pacotes()))
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _pdf_das_oito(corpus / "folha.pdf")
    sha = hashlib.sha256((corpus / "folha.pdf").read_bytes()).hexdigest()
    rodada = _rodada(tmp_path, [("a" * 8, "folha.pdf", sha)])
    relatorio = _rodar(rodada, tmp_path / "saida")
    pagina = _pagina(relatorio, "a" * 8)
    for identidade in _IDS_HASTE:
        categorias = pagina["variantes"].get(identidade, {})
        for nome in ("ambos", "so_motor", "so_nucleo", "indice_diverge", "geometria_diverge"):
            assert categorias.get(nome, []) == [], (identidade, nome)
    assert pagina["gasto"] is not None
    monkeypatch.undo()
    diff.recursos.cache_clear()
