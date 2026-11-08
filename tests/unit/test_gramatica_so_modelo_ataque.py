"""Ataques ao tipo `stem_bars`: bordas da validação, ordem e isolamento do motor antigo."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.declarative_symbols.corpus import draw_symbol
from tests.unit.test_gramatica_so_modelo import (
    _BASE,
    _CASO_MOLDURA,
    _CLASSE_HASTE,
    _carrega,
    _gramatica,
    _pacote_com,
    _ramos_stem_bars,
)

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

_MENSAGEM = "invalid grammar fields"


@pytest.mark.parametrize("max_span", [0.5, 40.5, 72, 72.0, 1e-9])
def test_max_span_nas_bordas_validas_carrega(tmp_path: Path, max_span: float) -> None:
    assert len(_carrega(tmp_path, _pacote_com(_gramatica(max_span=max_span)))) == 1


@pytest.mark.parametrize(
    "max_span",
    [-1, 0.0, 72.0001, 96, "40", None, [40]],
    ids=["negativo", "zero-float", "acima-de-72", "96-so-label", "string", "nulo", "lista"],
)
def test_max_span_invalido_recusa(tmp_path: Path, max_span: Any) -> None:
    with pytest.raises(ValueError, match=_MENSAGEM):
        _carrega(tmp_path, _pacote_com(_gramatica(max_span=max_span)))


@pytest.mark.parametrize("cru", ["NaN", "Infinity", "-Infinity"])
def test_max_span_nao_finito_recusa(tmp_path: Path, cru: str) -> None:
    texto = json.dumps(_pacote_com(_gramatica())).replace('"max_span": 40', f'"max_span": {cru}')
    assert cru in texto
    (tmp_path / "cru.json").write_text(texto, encoding="utf-8")
    with pytest.raises(ValueError, match=_MENSAGEM):
        carregar_pacotes(packages_dir=tmp_path)


@pytest.mark.parametrize(
    "bars", [3.0, "3", None, 3.5], ids=["float-3", "string", "nulo", "float-fracionario"]
)
def test_bars_de_tipo_errado_recusa(tmp_path: Path, bars: Any) -> None:
    with pytest.raises(ValueError, match=_MENSAGEM):
        _carrega(tmp_path, _pacote_com(_gramatica(bars=bars)))


@pytest.mark.parametrize("campo", ["taper", "enclosure"])
@pytest.mark.parametrize("valor", [None, 1, ["none"], {}, True, ""])
def test_taper_e_enclosure_de_tipo_errado_recusam(tmp_path: Path, campo: str, valor: Any) -> None:
    with pytest.raises(ValueError, match=_MENSAGEM):
        _carrega(tmp_path, _pacote_com(_gramatica(**{campo: valor})))


@pytest.mark.parametrize("valor", [0, None, "true", "false", []])
def test_removal_mark_nao_booleano_recusa(tmp_path: Path, valor: Any) -> None:
    with pytest.raises(ValueError, match=_MENSAGEM):
        _carrega(tmp_path, _pacote_com(_gramatica(removal_mark=valor)))


def test_gramatica_de_outro_tipo_nao_aceita_campos_de_stem_bars(tmp_path: Path) -> None:
    pacote = _pacote_com(_gramatica())
    pacote["variants"][0]["recognition"]["grammar"]["bars"] = 3
    with pytest.raises(ValueError, match=_MENSAGEM):
        _carrega(tmp_path, pacote)


def test_schema_tem_um_unico_ramo_stem_bars_com_os_seis_campos() -> None:
    assert len(_ramos_stem_bars()) == 1
    assert set(_ramos_stem_bars()[0]["properties"]) == set(_BASE)


def _unica_haste() -> tuple[dict[str, Any], ...]:
    return (_pacote_com(_gramatica(), com_moldura=False),)


def test_motor_so_com_variante_do_modelo_nao_observa_e_nao_falha(tmp_path: Path) -> None:
    pacotes = _carrega(tmp_path, _pacote_com(_gramatica(), com_moldura=False))
    perfil = perfil_pacotes(pacotes)
    assert perfil.classes_suportadas == ()
    assert ("enabled_variants", 0) in perfil.parametros
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=300)
        draw_symbol(pagina, _CASO_MOLDURA)
        resultado = observar_pacotes(
            pagina, documento_id="d", documento_sha256="0" * 64, pagina_numero=1, pacotes=pacotes
        )
    assert resultado.observacoes == ()


def test_variantes_do_motor_com_pacotes_reais_igual_a_enabled() -> None:
    reais = carregar_pacotes()
    assert variantes_do_motor(reais) == _enabled(reais)
    motor = perfil_pacotes(reais)
    assert dict(motor.parametros)["enabled_variants"] == len(_enabled(reais))


def test_perfil_do_modelo_com_pacotes_reais_igual_ao_do_motor() -> None:
    reais = carregar_pacotes()
    motor = perfil_pacotes(reais)
    modelo = perfil_pacotes_modelo(reais, carregar_tabela_glifos())
    assert modelo.classes_suportadas == motor.classes_suportadas
    assert dict(modelo.parametros)["enabled_variants"] == dict(motor.parametros)["enabled_variants"]


def test_perfil_do_modelo_com_pacotes_reais_herda_todos_os_parametros_do_motor() -> None:
    reais = carregar_pacotes()
    motor = dict(perfil_pacotes(reais).parametros)
    modelo = dict(perfil_pacotes_modelo(reais, carregar_tabela_glifos()).parametros)
    assert {k: modelo[k] for k in motor} == motor
    assert set(modelo) - set(motor) == {
        "modelo_desenho",
        "tabela_glifos_versao",
        "tabela_glifos_sha256",
        "limite_consultas",
    }


def test_modelo_so_com_haste_anuncia_a_classe_e_uma_variante(tmp_path: Path) -> None:
    pacotes = _carrega(tmp_path, _pacote_com(_gramatica(), com_moldura=False))
    perfil = perfil_pacotes_modelo(pacotes, carregar_tabela_glifos())
    assert perfil.classes_suportadas == (_CLASSE_HASTE,)
    assert ("enabled_variants", 1) in perfil.parametros


def test_modelo_ainda_nao_executa_stem_bars_e_falha_alto(tmp_path: Path) -> None:
    """Caracterização: a gramática chega na E06.3.2.2; até lá habilitar uma é erro explícito."""
    pacotes = _carrega(tmp_path, _pacote_com(_gramatica()))
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=300)
        draw_symbol(pagina, _CASO_MOLDURA)
        with pytest.raises(ValueError, match="stem_bars"):
            observar_pacotes_modelo(
                pagina,
                documento_id="d",
                documento_sha256="0" * 64,
                pagina_numero=1,
                pacotes=pacotes,
                tabela=carregar_tabela_glifos(),
            )


def test_enabled_e_variantes_do_motor_preservam_ordem(tmp_path: Path) -> None:
    pacote = _pacote_com(_gramatica())
    moldura, haste = pacote["variants"]
    haste = copy.deepcopy(haste)
    haste["id"] = "autoral-haste-000"
    pacote["variants"] = [haste, moldura]
    pacotes = _carrega(tmp_path, pacote)
    todos = [v["id"] for _, v in _enabled(pacotes)]
    motor = [v["id"] for _, v in variantes_do_motor(pacotes)]
    assert todos[0] == "autoral-haste-000"
    assert motor == todos[1:]
