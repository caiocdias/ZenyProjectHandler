"""Tipo de gramática `disc_mark`: aceito pelos pacotes e só executado pelo modelo."""

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
_CLASSE = "EQUIPAMENTO_INTERRUPCAO_AUTORAL"

_BASE: dict[str, Any] = {
    "kind": "disc_mark",
    "fill": "red",
    "content": "fuse_curve",
    "min_span": 3,
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
    novo["id"] = "autoral-disc-mark-001"
    novo["class_code"] = _CLASSE
    novo["recognition"] = {
        "status": "enabled",
        "grammar": gramatica,
        "negative_examples": ["disco vermelho sem curva fusível"],
    }
    return {**copy.deepcopy(real), "variants": [copy.deepcopy(moldura), novo]}


def _carrega(tmp_path: Path, pacote: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    (tmp_path / f"{pacote['family_id']}.json").write_text(json.dumps(pacote), encoding="utf-8")
    return carregar_pacotes(packages_dir=tmp_path)


@pytest.mark.parametrize("content", ["fuse_curve", "double_box"])
def test_disc_mark_valido_carrega(tmp_path: Path, content: str) -> None:
    assert len(_carrega(tmp_path, _pacote_com(_gramatica(content=content)))) == 1


@pytest.mark.parametrize(
    "gramatica",
    [
        pytest.param({**_BASE, "extra": 1}, id="campo-a-mais"),
        pytest.param({k: v for k, v in _BASE.items() if k != "content"}, id="content-faltando"),
        pytest.param({k: v for k, v in _BASE.items() if k != "min_span"}, id="min-span-faltando"),
        pytest.param({k: v for k, v in _BASE.items() if k != "fill"}, id="fill-faltando"),
        pytest.param(_gramatica(fill="purple"), id="fill-desconhecido"),
        pytest.param(_gramatica(fill=["red"]), id="fill-lista"),
        pytest.param(_gramatica(content="chevron"), id="content-desconhecido"),
        pytest.param(_gramatica(content=["fuse_curve"]), id="content-lista"),
        pytest.param(_gramatica(min_span=0), id="min-span-0"),
        pytest.param(_gramatica(min_span=-1), id="min-span-negativo"),
        pytest.param(_gramatica(min_span=73, max_span=72), id="min-span-73"),
        pytest.param(_gramatica(min_span=True), id="min-span-booleano"),
        pytest.param(_gramatica(min_span="3"), id="min-span-texto"),
        pytest.param(_gramatica(min_span=float("nan")), id="min-span-nan"),
        pytest.param(_gramatica(max_span=0), id="max-span-0"),
        pytest.param(_gramatica(max_span=73), id="max-span-73"),
        pytest.param(_gramatica(max_span=True), id="max-span-booleano"),
        pytest.param(_gramatica(max_span="40"), id="max-span-texto"),
        pytest.param(_gramatica(max_span=float("nan")), id="max-span-nan"),
        pytest.param(_gramatica(min_span=10, max_span=10), id="min-igual-max"),
        pytest.param(_gramatica(min_span=20, max_span=10), id="min-maior-que-max"),
    ],
)
def test_disc_mark_invalido_recusa(tmp_path: Path, gramatica: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="invalid grammar fields"):
        _carrega(tmp_path, _pacote_com(gramatica))


def test_disc_mark_aceita_limite_superior_72(tmp_path: Path) -> None:
    gramatica = _gramatica(min_span=0.5, max_span=72)

    assert len(_carrega(tmp_path, _pacote_com(gramatica))) == 1


def test_schema_tem_o_ramo_disc_mark() -> None:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    ramos = [
        r
        for r in schema["$defs"]["grammar"]["oneOf"]
        if r["properties"]["kind"].get("const") == "disc_mark"
    ]
    assert len(ramos) == 1

    ramo = ramos[0]
    assert ramo["additionalProperties"] is False
    assert set(ramo["required"]) == set(_BASE)
    props = ramo["properties"]
    assert props["fill"] == {"enum": ["red"]}
    assert props["content"] == {"enum": ["fuse_curve", "double_box"]}
    for campo in ("min_span", "max_span"):
        assert props[campo]["type"] == "number"
        assert props[campo]["exclusiveMinimum"] == 0
        assert props[campo]["maximum"] == 72


def test_gramatica_so_modelo_inclui_disc_mark() -> None:
    assert "disc_mark" in GRAMATICAS_SO_MODELO


def test_motor_ignora_disc_mark(tmp_path: Path) -> None:
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


def test_perfil_do_modelo_anuncia_disc_mark(tmp_path: Path) -> None:
    pacotes = _carrega(tmp_path, _pacote_com(_gramatica()))

    perfil = perfil_pacotes_modelo(pacotes, carregar_tabela_glifos())

    assert _CLASSE in perfil.classes_suportadas
    assert len(perfil.classes_suportadas) == 2
    assert ("enabled_variants", 2) in perfil.parametros
