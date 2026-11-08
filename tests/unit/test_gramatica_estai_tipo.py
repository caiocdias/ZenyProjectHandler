"""Tipo de gramática `forked_stem` (ESTAI): aceito pelos pacotes e só executado pelo modelo."""

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
    GRAMMAR_FORKED_STEM,
    carregar_pacotes,
    observar_pacotes,
    perfil_pacotes,
    variantes_do_motor,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.model_symbols import perfil_pacotes_modelo

_RAIZ = Path(__file__).resolve().parents[2]
_SCHEMA = _RAIZ / "docs" / "schemas" / "pacotes-simbologia.schema.json"
_CASO_MOLDURA = next(caso for caso in ENABLED_CASES if caso.variant_id == "cemig-eo-r3-s30-v001")
_CLASSE = "ESTAI_AUTORAL"

_BASE: dict[str, Any] = {
    "kind": "forked_stem",
    "enclosure": "none",
    "removal_mark": False,
    "max_span": 40,
}


def _gramatica(**mudancas: Any) -> dict[str, Any]:
    return {**_BASE, **mudancas}


def _pacote_com(gramatica: dict[str, Any]) -> dict[str, Any]:
    real = next(
        pacote
        for pacote in carregar_pacotes()
        if any(v["id"] == _CASO_MOLDURA.variant_id for v in pacote["variants"])
    )
    moldura = next(v for v in real["variants"] if v["id"] == _CASO_MOLDURA.variant_id)
    novo = copy.deepcopy(moldura)
    novo["id"] = "autoral-forked-stem-001"
    novo["class_code"] = _CLASSE
    novo["recognition"] = {
        "status": "enabled",
        "grammar": gramatica,
        "negative_examples": ["haste simples sem garfo"],
    }
    return {**copy.deepcopy(real), "variants": [copy.deepcopy(moldura), novo]}


def _carrega(tmp_path: Path, pacote: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    (tmp_path / f"{pacote['family_id']}.json").write_text(json.dumps(pacote), encoding="utf-8")
    return carregar_pacotes(packages_dir=tmp_path)


def test_constante_do_tipo() -> None:
    assert GRAMMAR_FORKED_STEM == "forked_stem"


@pytest.mark.parametrize(
    ("enclosure", "removal_mark"),
    [("none", False), ("none", True), ("ellipse", False)],
)
def test_forked_stem_valido_carrega(tmp_path: Path, enclosure: str, removal_mark: bool) -> None:
    gramatica = _gramatica(enclosure=enclosure, removal_mark=removal_mark)

    assert len(_carrega(tmp_path, _pacote_com(gramatica))) == 1


@pytest.mark.parametrize("max_span", [72, 0.5, 1])
def test_forked_stem_aceita_max_span_na_borda(tmp_path: Path, max_span: float) -> None:
    assert len(_carrega(tmp_path, _pacote_com(_gramatica(max_span=max_span)))) == 1


@pytest.mark.parametrize(
    "gramatica",
    [
        pytest.param({**_BASE, "extra": 1}, id="campo-a-mais"),
        pytest.param({k: v for k, v in _BASE.items() if k != "enclosure"}, id="campo-faltando"),
        pytest.param({k: v for k, v in _BASE.items() if k != "max_span"}, id="max-span-faltando"),
        pytest.param(_gramatica(enclosure="square"), id="enclosure-desconhecido"),
        pytest.param(_gramatica(enclosure=["none"]), id="enclosure-lista"),
        pytest.param(_gramatica(removal_mark=1), id="removal-mark-inteiro"),
        pytest.param(_gramatica(removal_mark="true"), id="removal-mark-texto"),
        pytest.param(_gramatica(removal_mark=None), id="removal-mark-nulo"),
        pytest.param(_gramatica(enclosure="ellipse", removal_mark=True), id="ellipse-com-x"),
        pytest.param(_gramatica(max_span=0), id="max-span-0"),
        pytest.param(_gramatica(max_span=-1), id="max-span-negativo"),
        pytest.param(_gramatica(max_span=73), id="max-span-73"),
        pytest.param(_gramatica(max_span=float("nan")), id="max-span-nan"),
        pytest.param(_gramatica(max_span=float("inf")), id="max-span-inf"),
        pytest.param(_gramatica(max_span=True), id="max-span-booleano"),
        pytest.param(_gramatica(max_span="40"), id="max-span-texto"),
    ],
)
def test_forked_stem_invalido_recusa(tmp_path: Path, gramatica: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="invalid grammar fields"):
        _carrega(tmp_path, _pacote_com(gramatica))


def test_schema_tem_o_ramo_forked_stem() -> None:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    ramos = [
        r
        for r in schema["$defs"]["grammar"]["oneOf"]
        if r["properties"]["kind"].get("const") == "forked_stem"
    ]
    assert len(ramos) == 1

    ramo = ramos[0]
    assert ramo["additionalProperties"] is False
    assert set(ramo["required"]) == set(_BASE)
    props = ramo["properties"]
    assert props["enclosure"] == {"enum": ["none", "ellipse"]}
    assert props["removal_mark"] == {"type": "boolean"}
    assert props["max_span"]["exclusiveMinimum"] == 0
    assert props["max_span"]["maximum"] == 72
    # X vence a envolvente: o schema recusa ellipse + X como o validador.
    assert ramo["not"]["properties"] == {
        "enclosure": {"const": "ellipse"},
        "removal_mark": {"const": True},
    }
    assert set(ramo["not"]["required"]) == {"enclosure", "removal_mark"}


def test_gramatica_so_modelo_inclui_forked_stem() -> None:
    assert "forked_stem" in GRAMATICAS_SO_MODELO


def test_motor_ignora_forked_stem(tmp_path: Path) -> None:
    pacotes = _carrega(tmp_path, _pacote_com(_gramatica()))

    perfil = perfil_pacotes(pacotes)
    assert _CLASSE not in perfil.classes_suportadas
    assert _CASO_MOLDURA.variant_id in {v["id"] for _, v in variantes_do_motor(pacotes)}
    assert len(variantes_do_motor(pacotes)) == 1
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


def test_perfil_do_modelo_anuncia_forked_stem(tmp_path: Path) -> None:
    pacotes = _carrega(tmp_path, _pacote_com(_gramatica()))

    perfil = perfil_pacotes_modelo(pacotes, carregar_tabela_glifos())

    assert _CLASSE in perfil.classes_suportadas
    assert len(perfil.classes_suportadas) == 2
    assert ("enabled_variants", 2) in perfil.parametros
