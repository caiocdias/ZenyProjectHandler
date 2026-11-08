"""Ataque ao diff núcleo x motor com variante habilitada de tipo só do modelo (R-E06.3.2-5)."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pymupdf
import pytest
import scripts.diff_simbolos_nucleo_motor as diff
from tests.fixtures.declarative_symbols.corpus import draw_symbol
from tests.fixtures.symbol_grammars.stem_bars import CASOS_HASTE, desenhar_positivo
from tests.unit.test_diff_simbolos_nucleo_motor import (
    _CASO_MOLDURA,
    _categorias,
    _moldura_e_haste,
    _pacotes_com_haste,
    _pagina,
    _recursos,
    _rodar,
    _uma_folha,
)

from zeny_project_handler.adapters.analysis import declarative_symbols

_HASTE_ID = CASOS_HASTE[0][0]
Injetar = Callable[[diff.Recursos], None]


@pytest.fixture
def injetar(monkeypatch: pytest.MonkeyPatch) -> Iterator[Injetar]:
    diff.recursos.cache_clear()

    def _injeta(meios: diff.Recursos) -> None:
        monkeypatch.setattr(diff, "recursos", lambda: meios)

    yield _injeta
    monkeypatch.undo()
    diff.recursos.cache_clear()


def _so_haste(pagina: pymupdf.Page) -> None:
    desenhar_positivo(pagina, _HASTE_ID, centro=(240.0, 240.0))


def _so_moldura(pagina: pymupdf.Page) -> None:
    draw_symbol(pagina, _CASO_MOLDURA)


def _vazia(pagina: pymupdf.Page) -> None:
    pagina.draw_line((10, 10), (20, 10), color=(0, 0, 0), width=0.5)


def _medir(
    tmp_path: Path,
    injetar: Injetar,
    desenho: Callable[[pymupdf.Page], None],
    com: bool,
    rotacao: int = 0,
) -> dict[str, Any]:
    nome = "com" if com else "sem"
    injetar(_recursos(_pacotes_com_haste(tmp_path / f"pacotes-{nome}", com_haste=com)))
    rodada = _uma_folha(tmp_path / f"folha-{nome}", desenho, rotacao)
    return _pagina(_rodar(rodada, tmp_path / f"saida-{nome}"))


def test_pagina_so_com_haste_nao_tem_variante_na_comparacao(
    tmp_path: Path, injetar: Injetar
) -> None:
    com = _medir(tmp_path, injetar, _so_haste, True)
    sem = _medir(tmp_path, injetar, _so_haste, False)
    assert com["situacao"] == "comparada"
    assert com["variantes"] == {}
    assert com["gasto"]["gramaticas"] > sem["gasto"]["gramaticas"]
    assert com["gasto_motivo"] is None


def test_pagina_sem_moldura_nem_haste_continua_comparada_e_vazia(
    tmp_path: Path, injetar: Injetar
) -> None:
    com = _medir(tmp_path, injetar, _vazia, True)
    assert com["situacao"] == "comparada"
    assert com["variantes"] == {}
    assert com["gasto"] is not None


def test_pagina_so_com_moldura_nao_ganha_variante_da_haste(
    tmp_path: Path, injetar: Injetar
) -> None:
    com = _medir(tmp_path, injetar, _so_moldura, True)
    assert set(com["variantes"]) == {_CASO_MOLDURA.variant_id}
    assert len(_categorias(com, _CASO_MOLDURA.variant_id)["ambos"]) == 1


def test_haste_em_pagina_girada_tambem_fica_fora_da_comparacao(
    tmp_path: Path, injetar: Injetar
) -> None:
    com = _medir(tmp_path, injetar, _moldura_e_haste, True, rotacao=90)
    assert com["rotacao"] == 90
    assert set(com["variantes"]) == {_CASO_MOLDURA.variant_id}
    moldura = _categorias(com, _CASO_MOLDURA.variant_id)
    assert len(moldura["ambos"]) == 1
    for categoria in ("so_motor", "so_nucleo", "indice_diverge", "geometria_diverge"):
        assert moldura[categoria] == []


def test_so_haste_habilitada_sem_nenhuma_variante_do_motor(
    tmp_path: Path, injetar: Injetar
) -> None:
    """Pacote só com a variante do modelo: o motor não tem classe e a página fica não comparada.

    Caracterização (inalcançável com os pacotes reais, que sempre têm variante do motor): o
    gasto do núcleo continua medido e o relatório não quebra.
    """
    real = next(
        pacote
        for pacote in declarative_symbols.carregar_pacotes()
        if any(v["id"] == _CASO_MOLDURA.variant_id for v in pacote["variants"])
    )
    moldura = next(v for v in real["variants"] if v["id"] == _CASO_MOLDURA.variant_id)
    haste = copy.deepcopy(moldura)
    haste["id"] = _HASTE_ID
    haste["class_code"] = "ATERRAMENTO"
    haste["recognition"] = {
        "status": "enabled",
        "grammar": copy.deepcopy(CASOS_HASTE[0][1]),
        "negative_examples": ["haste com barras fora do padrão"],
    }
    pasta = tmp_path / "pacotes"
    pasta.mkdir()
    (pasta / f"{real['family_id']}.json").write_text(
        json.dumps({**copy.deepcopy(real), "variants": [haste]}), encoding="utf-8"
    )
    pacotes = declarative_symbols.carregar_pacotes(packages_dir=pasta)
    assert declarative_symbols.variantes_do_motor(pacotes) == ()
    injetar(_recursos(pacotes))
    rodada = _uma_folha(tmp_path / "folha", _moldura_e_haste)
    pagina = _pagina(_rodar(rodada, tmp_path / "saida"))
    assert pagina["situacao"] == "nao_comparada"
    assert pagina["motivo"].startswith("motor:")
    assert pagina["variantes"] == {}
    assert pagina["gasto"]["gramaticas"] > 0


def test_cache_de_recursos_reflete_os_pacotes_reais_depois_de_um_teste_com_injecao(
    tmp_path: Path, injetar: Injetar
) -> None:
    """Depois de usar a fixture de injeção, `recursos()` real volta a ler os pacotes reais."""
    _medir(tmp_path, injetar, _so_haste, True)


def test_cache_de_recursos_real_sem_haste_sintetica() -> None:
    diff.recursos.cache_clear()
    try:
        assert diff.recursos().pacotes == declarative_symbols.carregar_pacotes()
    finally:
        diff.recursos.cache_clear()
