"""Ataques a Task 4 (E06.3.3.1): PARA_RAIOS_BT habilitado com os pacotes reais."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.rect_diagonal import (
    CASOS_RECT_DIAGONAL,
    NEGATIVOS,
    desenhar_bt_classico,
    desenhar_positivo,
)
from tests.fixtures.symbol_grammars.stem_bars import CASOS_HASTE
from tests.fixtures.symbol_grammars.stem_bars import desenhar_positivo as desenhar_haste

from zeny_project_handler.adapters.analysis.declarative_symbols import (
    _enabled,
    carregar_pacotes,
    observar_pacotes,
    perfil_pacotes,
    variantes_do_motor,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.model_symbols import (
    observar_pacotes_modelo,
    perfil_pacotes_modelo,
)

_ROOT = Path(__file__).resolve().parents[2]
_IDS = [identidade for identidade, _ in CASOS_RECT_DIAGONAL]
_CLASSE = "PARA_RAIOS_BT"


def _pagina_com(desenhar: Any, tamanho: float = 300.0) -> tuple[pymupdf.Document, pymupdf.Page]:
    documento = pymupdf.open()  # type: ignore[no-untyped-call]
    pagina = documento.new_page(width=tamanho, height=tamanho)
    desenhar(pagina)
    return documento, pagina


def _modelo(pagina: pymupdf.Page) -> list[tuple[str, str]]:
    resultado = observar_pacotes_modelo(
        pagina,
        documento_id="d",
        documento_sha256="0" * 64,
        pagina_numero=1,
        pacotes=carregar_pacotes(),
        tabela=carregar_tabela_glifos(),
    )
    return [
        (str(o.alternativas[0].classe), str(dict(o.atributos).get("variante_inventario")))
        for o in resultado.observacoes
    ]


def _motor(pagina: pymupdf.Page) -> list[str]:
    resultado = observar_pacotes(
        pagina,
        documento_id="d",
        documento_sha256="0" * 64,
        pagina_numero=1,
        pacotes=carregar_pacotes(),
    )
    return [str(o.alternativas[0].classe) for o in resultado.observacoes]


def _variantes_reais() -> dict[str, dict[str, Any]]:
    return {v["id"]: v for _, v in _enabled(carregar_pacotes())}


def test_negative_examples_das_quatro_sao_os_confusable_negatives_do_inventario() -> None:
    inventario = json.loads(
        (_ROOT / "docs/data/inventario-simbologia-v1.json").read_text(encoding="utf-8")
    )
    por_id = {v["id"]: v for v in inventario["variants"]}
    reais = _variantes_reais()
    for identidade in _IDS:
        assert (
            reais[identidade]["recognition"]["negative_examples"]
            == (por_id[identidade]["confusable_negatives"])
        ), identidade


def test_reconhecimento_das_quatro_tem_so_status_gramatica_e_negativos() -> None:
    reais = _variantes_reais()
    for identidade in _IDS:
        assert set(reais[identidade]["recognition"]) == {
            "status",
            "grammar",
            "negative_examples",
        }, identidade
        assert reais[identidade]["class_code"] == _CLASSE


def test_so_as_quatro_variantes_de_bt_sao_rect_diagonal_nos_pacotes_reais() -> None:
    usam = {
        i
        for i, v in _variantes_reais().items()
        if v["recognition"]["grammar"]["kind"] == "rect_diagonal"
    }
    assert usam == set(_IDS)


def test_motor_antigo_com_pacotes_reais_nao_tem_as_quatro() -> None:
    ids = {v["id"] for _, v in variantes_do_motor(carregar_pacotes())}
    assert ids.isdisjoint(_IDS)
    assert len(ids) == 22
    assert _CLASSE not in perfil_pacotes(carregar_pacotes()).classes_suportadas


@pytest.mark.parametrize("situacao", _IDS)
def test_motor_antigo_nao_observa_bt_mesmo_com_o_desenho_exato(situacao: str) -> None:
    documento, pagina = _pagina_com(lambda p: desenhar_positivo(p, situacao))
    with documento:
        assert _CLASSE not in _motor(pagina)


@pytest.mark.parametrize("situacao", _IDS)
def test_modelo_com_pacotes_reais_observa_exatamente_a_variante_desenhada(situacao: str) -> None:
    documento, pagina = _pagina_com(lambda p: desenhar_positivo(p, situacao))
    with documento:
        assert _modelo(pagina) == [(_CLASSE, situacao)]


@pytest.mark.parametrize("situacao", _IDS)
def test_modelo_com_pacotes_reais_observa_o_desenho_classico_na_variante_certa(
    situacao: str,
) -> None:
    documento, pagina = _pagina_com(lambda p: desenhar_bt_classico(p, situacao))
    with documento:
        assert (_CLASSE, situacao) in _modelo(pagina)


def test_quatro_situacoes_na_mesma_pagina_dao_quatro_observacoes_distintas() -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        for i, situacao in enumerate(_IDS):
            desenhar_positivo(pagina, situacao, centro=(60.0 + 60.0 * i, 150.0))

    documento, pagina = _pagina_com(desenhar)
    with documento:
        assert sorted(_modelo(pagina)) == sorted((_CLASSE, s) for s in _IDS)


@pytest.mark.parametrize("nome", sorted(NEGATIVOS))
def test_negativos_do_rect_diagonal_nao_viram_bt_com_pacotes_reais(nome: str) -> None:
    documento, pagina = _pagina_com(NEGATIVOS[nome])
    with documento:
        assert _CLASSE not in {classe for classe, _ in _modelo(pagina)}


@pytest.mark.parametrize("situacao", [identidade for identidade, _ in CASOS_HASTE])
def test_haste_nao_vira_bt_com_pacotes_reais(situacao: str) -> None:
    documento, pagina = _pagina_com(lambda p: desenhar_haste(p, situacao))
    with documento:
        assert _CLASSE not in {classe for classe, _ in _modelo(pagina)}


@pytest.mark.parametrize("situacao", _IDS)
def test_bt_nao_vira_haste_nem_outra_classe_com_pacotes_reais(situacao: str) -> None:
    documento, pagina = _pagina_com(lambda p: desenhar_positivo(p, situacao))
    with documento:
        assert {classe for classe, _ in _modelo(pagina)} == {_CLASSE}


@pytest.mark.parametrize("rotacao", [90, 180, 270])
def test_bt_com_rotate_de_pagina_segue_na_variante_certa(rotacao: int) -> None:
    def desenhar(pagina: pymupdf.Page) -> None:
        desenhar_positivo(pagina, _IDS[2])
        pagina.set_rotation(rotacao)  # type: ignore[no-untyped-call]

    documento, pagina = _pagina_com(desenhar)
    with documento:
        assert _modelo(pagina) == [(_CLASSE, _IDS[2])]


def test_versao_1_5_0_no_perfil_do_modelo_e_muda_a_assinatura() -> None:
    perfil = perfil_pacotes_modelo(carregar_pacotes(), carregar_tabela_glifos())
    assert perfil.versao == "1.5.0"
    assert perfil.metodo_id == "declarative-drawing-model"
    assert dict(perfil.parametros)["enabled_variants"] == 52
    anterior = replace(perfil, versao="1.3.0")
    assert perfil.assinatura() != anterior.assinatura()


def test_perfil_do_motor_segue_1_1_0_com_22_variantes() -> None:
    motor = perfil_pacotes(carregar_pacotes())
    assert motor.metodo_id != "declarative-drawing-model"
    assert motor.versao == "1.1.0"
    assert dict(motor.parametros)["enabled_variants"] == 22
