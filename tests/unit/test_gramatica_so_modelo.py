"""Tipo de gramática `stem_bars`: aceito pelos pacotes e só executado pelo modelo de desenho."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.declarative_symbols.corpus import ENABLED_CASES, draw_symbol

from zeny_project_handler.adapters.analysis.declarative_symbols import (
    GRAMATICAS_SO_MODELO,
    _enabled,
    carregar_pacotes,
    observar_pacotes,
    perfil_pacotes,
    variantes_do_motor,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    CasamentoGramatica,
)
from zeny_project_handler.adapters.analysis.model_symbols import perfil_pacotes_modelo

_RAIZ = Path(__file__).resolve().parents[2]
_SCHEMA = _RAIZ / "docs" / "schemas" / "pacotes-simbologia.schema.json"
_CASO_MOLDURA = next(caso for caso in ENABLED_CASES if caso.variant_id == "cemig-eo-r3-s30-v001")
_CLASSE_HASTE = "HASTE_AUTORAL"

_BASE: dict[str, Any] = {
    "kind": "stem_bars",
    "bars": 3,
    "taper": "decreasing",
    "enclosure": "none",
    "removal_mark": False,
    "max_span": 40,
}


def _gramatica(**mudancas: Any) -> dict[str, Any]:
    return {**_BASE, **mudancas}


def _pacote_com(gramatica: dict[str, Any], *, com_moldura: bool = True) -> dict[str, Any]:
    real = next(
        pacote
        for pacote in carregar_pacotes()
        if any(v["id"] == _CASO_MOLDURA.variant_id for v in pacote["variants"])
    )
    moldura = next(v for v in real["variants"] if v["id"] == _CASO_MOLDURA.variant_id)
    haste = copy.deepcopy(moldura)
    haste["id"] = "autoral-haste-001"
    haste["class_code"] = _CLASSE_HASTE
    haste["recognition"] = {
        "status": "enabled",
        "grammar": gramatica,
        "negative_examples": ["haste com barras fora do padrão"],
    }
    variantes = [copy.deepcopy(moldura), haste] if com_moldura else [haste]
    return {**copy.deepcopy(real), "variants": variantes}


def _carrega(tmp_path: Path, pacote: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    (tmp_path / f"{pacote['family_id']}.json").write_text(json.dumps(pacote), encoding="utf-8")
    return carregar_pacotes(packages_dir=tmp_path)


@pytest.mark.parametrize("enclosure", ["none", "ellipse"])
@pytest.mark.parametrize("removal_mark", [False, True])
@pytest.mark.parametrize(("bars", "taper"), [(3, "decreasing"), (4, "alternating")])
def test_stem_bars_valido_carrega(
    tmp_path: Path, bars: int, taper: str, enclosure: str, removal_mark: bool
) -> None:
    gramatica = _gramatica(bars=bars, taper=taper, enclosure=enclosure, removal_mark=removal_mark)

    assert len(_carrega(tmp_path, _pacote_com(gramatica))) == 1


@pytest.mark.parametrize(
    "gramatica",
    [
        pytest.param({**_BASE, "extra": 1}, id="campo-a-mais"),
        pytest.param(_gramatica(bars=2), id="bars-2"),
        pytest.param(_gramatica(bars=5), id="bars-5"),
        pytest.param(_gramatica(bars=3, taper="alternating"), id="3-alternating"),
        pytest.param(_gramatica(bars=4, taper="decreasing"), id="4-decreasing"),
        pytest.param(_gramatica(taper="increasing"), id="taper-desconhecido"),
        pytest.param(_gramatica(enclosure="square"), id="enclosure-desconhecido"),
        pytest.param(_gramatica(removal_mark=1), id="removal-mark-nao-booleano"),
        pytest.param(_gramatica(max_span=0), id="max-span-0"),
        pytest.param(_gramatica(max_span=73), id="max-span-73"),
        pytest.param(_gramatica(max_span=True), id="max-span-booleano"),
        pytest.param(_gramatica(bars=True), id="bars-booleano"),
        pytest.param({k: v for k, v in _BASE.items() if k != "taper"}, id="campo-faltando"),
    ],
)
def test_stem_bars_invalido_recusa(tmp_path: Path, gramatica: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="invalid grammar fields"):
        _carrega(tmp_path, _pacote_com(gramatica))


def _ramos_stem_bars() -> list[dict[str, Any]]:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    ramos = schema["$defs"]["grammar"]["oneOf"]
    return [r for r in ramos if r["properties"]["kind"].get("const") == "stem_bars"]


def test_schema_tem_o_ramo_stem_bars() -> None:
    ramos = _ramos_stem_bars()
    assert ramos

    pares: set[tuple[int, str]] = set()
    for ramo in ramos:
        assert ramo["additionalProperties"] is False
        assert set(ramo["required"]) == set(_BASE)
        props = ramo["properties"]
        assert props["enclosure"] == {"enum": ["none", "ellipse"]}
        assert props["removal_mark"] == {"type": "boolean"}
        assert props["max_span"]["exclusiveMinimum"] == 0
        assert props["max_span"]["maximum"] == 72
        assert props["bars"] == {"enum": [3, 4]}
        assert props["taper"] == {"enum": ["decreasing", "alternating"]}
        for sub in ramo["oneOf"]:
            sub_props = sub["properties"]
            pares.add((sub_props["bars"]["const"], sub_props["taper"]["const"]))
    assert pares == {(3, "decreasing"), (4, "alternating")}


def test_motor_ignora_variante_so_do_modelo(tmp_path: Path) -> None:
    pacotes = _carrega(tmp_path, _pacote_com(_gramatica()))

    perfil = perfil_pacotes(pacotes)
    assert _CLASSE_HASTE not in perfil.classes_suportadas
    assert _CASO_MOLDURA.variant_id in {v["id"] for _, v in variantes_do_motor(pacotes)}
    assert ("enabled_variants", 1) in perfil.parametros

    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=300)
        draw_symbol(pagina, _CASO_MOLDURA)
        resultado = observar_pacotes(
            pagina,
            documento_id="doc",
            documento_sha256="0" * 64,
            pagina_numero=1,
            pacotes=pacotes,
        )
    variantes = {dict(o.atributos).get("variante_inventario") for o in resultado.observacoes}
    assert variantes == {_CASO_MOLDURA.variant_id}


def test_perfil_do_modelo_conta_a_variante_so_do_modelo(tmp_path: Path) -> None:
    pacotes = _carrega(tmp_path, _pacote_com(_gramatica()))

    perfil = perfil_pacotes_modelo(pacotes, carregar_tabela_glifos())

    assert _CLASSE_HASTE in perfil.classes_suportadas
    assert len(perfil.classes_suportadas) == 2
    assert ("enabled_variants", 2) in perfil.parametros


def test_enabled_continua_com_todas(tmp_path: Path) -> None:
    pacotes = _carrega(tmp_path, _pacote_com(_gramatica()))

    assert frozenset({"stem_bars"}) == GRAMATICAS_SO_MODELO
    assert len(_enabled(pacotes)) == 2
    assert len(variantes_do_motor(pacotes)) == 1


def test_casamento_sem_componentes_por_padrao() -> None:
    casamento = CasamentoGramatica(pacote={}, variante={}, caixa=(0.0, 0.0, 1.0, 1.0), caminho=0)

    assert casamento.componentes == ()
