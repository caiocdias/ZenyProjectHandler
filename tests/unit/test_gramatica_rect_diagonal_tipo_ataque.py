"""Ataques ao tipo `rect_diagonal`: tipos errados, schema x validador, isolamento do motor."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.declarative_symbols.corpus import draw_symbol
from tests.unit.test_gramatica_rect_diagonal_tipo import (
    _BASE,
    _CASO_MOLDURA,
    _CLASSE,
    _SCHEMA,
    _carrega,
    _gramatica,
    _pacote_com,
)

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
from zeny_project_handler.adapters.analysis.model_symbols import perfil_pacotes_modelo

_MENSAGEM = "invalid grammar fields"


def _ramo() -> dict[str, Any]:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    ramos = [
        r
        for r in schema["$defs"]["grammar"]["oneOf"]
        if r["properties"]["kind"].get("const") == "rect_diagonal"
    ]
    assert len(ramos) == 1
    ramo: dict[str, Any] = ramos[0]
    return ramo


def _numero_json(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _schema_aceita(gramatica: dict[str, Any]) -> bool:
    """Avaliador mínimo do ramo (sem biblioteca): required, additionalProperties, const, enum."""
    ramo = _ramo()
    props = ramo["properties"]
    if not set(ramo["required"]) <= set(gramatica):
        return False
    if ramo["additionalProperties"] is False and set(gramatica) - set(props):
        return False
    if gramatica["kind"] != props["kind"]["const"]:
        return False
    enclosure = gramatica["enclosure"]
    if not isinstance(enclosure, str) or enclosure not in props["enclosure"]["enum"]:
        return False
    if not isinstance(gramatica["removal_mark"], bool):
        return False
    span = gramatica["max_span"]
    regra = props["max_span"]
    if not _numero_json(span) or not math.isfinite(span):
        return False
    return bool(span > regra["exclusiveMinimum"] and span <= regra["maximum"])


_CASOS: list[Any] = [
    pytest.param(_gramatica(), id="base"),
    pytest.param(_gramatica(enclosure="ellipse", removal_mark=True), id="v003"),
    pytest.param(_gramatica(enclosure="none", removal_mark=True), id="v004"),
    pytest.param(_gramatica(max_span=0.5), id="span-0.5"),
    pytest.param(_gramatica(max_span=72), id="span-72"),
    pytest.param(_gramatica(max_span=72.0), id="span-72.0"),
    pytest.param(_gramatica(max_span=1e-9), id="span-minusculo"),
    pytest.param(_gramatica(max_span=72.0001), id="span-acima"),
    pytest.param(_gramatica(max_span=96), id="span-96"),
    pytest.param(_gramatica(max_span=0.0), id="span-zero-float"),
    pytest.param(_gramatica(max_span=-1), id="span-negativo"),
    pytest.param(_gramatica(max_span="40"), id="span-string"),
    pytest.param(_gramatica(max_span=None), id="span-nulo"),
    pytest.param(_gramatica(max_span=[40]), id="span-lista"),
    pytest.param(_gramatica(max_span={"v": 40}), id="span-dict"),
    pytest.param(_gramatica(max_span=False), id="span-false"),
    pytest.param(_gramatica(max_span=True), id="span-true"),
    pytest.param(_gramatica(enclosure=None), id="enclosure-nulo"),
    pytest.param(_gramatica(enclosure=1), id="enclosure-inteiro"),
    pytest.param(_gramatica(enclosure=True), id="enclosure-bool"),
    pytest.param(_gramatica(enclosure={"a": 1}), id="enclosure-dict"),
    pytest.param(_gramatica(enclosure=[["none"]]), id="enclosure-lista-aninhada"),
    pytest.param(_gramatica(enclosure=""), id="enclosure-vazio"),
    pytest.param(_gramatica(enclosure="ELLIPSE"), id="enclosure-caixa-alta"),
    pytest.param(_gramatica(enclosure=" none"), id="enclosure-espaco"),
    pytest.param(_gramatica(removal_mark=None), id="removal-nulo"),
    pytest.param(_gramatica(removal_mark=0), id="removal-zero"),
    pytest.param(_gramatica(removal_mark=1.0), id="removal-float"),
    pytest.param(_gramatica(removal_mark="true"), id="removal-string"),
    pytest.param(_gramatica(removal_mark=[]), id="removal-lista"),
    pytest.param(_gramatica(removal_mark={}), id="removal-dict"),
    pytest.param({**_BASE, "bars": 3}, id="campo-de-stem-bars"),
    pytest.param({**_BASE, "frame": "rect"}, id="campo-de-moldura"),
    pytest.param({k: v for k, v in _BASE.items() if k != "max_span"}, id="sem-max-span"),
    pytest.param({k: v for k, v in _BASE.items() if k != "removal_mark"}, id="sem-removal"),
]


@pytest.mark.parametrize("gramatica", _CASOS)
def test_schema_e_validador_concordam(tmp_path: Path, gramatica: dict[str, Any]) -> None:
    esperado = _schema_aceita(gramatica)
    try:
        carregou = len(_carrega(tmp_path, _pacote_com(gramatica))) == 1
    except ValueError:
        carregou = False
    assert carregou is esperado


@pytest.mark.parametrize("cru", ["NaN", "Infinity", "-Infinity"])
def test_max_span_nao_finito_no_json_recusa(tmp_path: Path, cru: str) -> None:
    texto = json.dumps(_pacote_com(_gramatica())).replace('"max_span": 40', f'"max_span": {cru}')
    assert cru in texto
    (tmp_path / "cru.json").write_text(texto, encoding="utf-8")
    with pytest.raises(ValueError, match=_MENSAGEM):
        carregar_pacotes(packages_dir=tmp_path)


@pytest.mark.parametrize("tipo", [["rect_diagonal"], {"k": 1}, None, 3, "Rect_Diagonal"])
def test_kind_de_tipo_errado_recusa_sem_type_error(tmp_path: Path, tipo: Any) -> None:
    with pytest.raises(ValueError, match="unsupported grammar"):
        _carrega(tmp_path, _pacote_com(_gramatica(kind=tipo)))


def test_as_quatro_situacoes_no_mesmo_pacote_carregam_e_o_modelo_conta_todas(
    tmp_path: Path,
) -> None:
    pacote = _pacote_com(_gramatica())
    moldura, base = pacote["variants"]
    variantes = [moldura]
    for i, (enc, marca) in enumerate(
        [("none", False), ("ellipse", False), ("ellipse", True), ("none", True)], start=1
    ):
        v = copy.deepcopy(base)
        v["id"] = f"autoral-rect-diagonal-00{i}"
        v["recognition"]["grammar"] = _gramatica(enclosure=enc, removal_mark=marca)
        variantes.append(v)
    pacote["variants"] = variantes
    pacotes = _carrega(tmp_path, pacote)

    assert len(variantes_do_motor(pacotes)) == 1
    perfil = perfil_pacotes_modelo(pacotes, carregar_tabela_glifos())
    assert ("enabled_variants", 5) in perfil.parametros
    assert perfil.classes_suportadas.count(_CLASSE) == 1


def test_perfil_do_motor_com_so_rect_diagonal_fica_vazio(tmp_path: Path) -> None:
    pacote = _pacote_com(_gramatica())
    pacote["variants"] = pacote["variants"][1:]
    pacotes = _carrega(tmp_path, pacote)

    perfil = perfil_pacotes(pacotes)
    assert perfil.classes_suportadas == ()
    assert ("enabled_variants", 0) in perfil.parametros
    assert variantes_do_motor(pacotes) == ()
    assert len(_enabled(pacotes)) == 1


def test_motor_nao_observa_rect_diagonal_mesmo_com_o_desenho_na_pagina(tmp_path: Path) -> None:
    """Retângulo, diagonal e elipse desenhados: o motor antigo não os lê como nada."""
    pacote = _pacote_com(_gramatica(enclosure="ellipse"))
    pacote["variants"] = pacote["variants"][1:]
    pacotes = _carrega(tmp_path, pacote)
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=300)
        pagina.draw_rect((100, 100, 130, 112), color=(0, 0, 0), width=0.5)
        pagina.draw_line((95, 118), (135, 94), color=(0, 0, 0), width=0.5)
        pagina.draw_oval((90, 88, 140, 124), color=(0, 0, 0), width=0.5)
        resultado = observar_pacotes(
            pagina, documento_id="d", documento_sha256="0" * 64, pagina_numero=1, pacotes=pacotes
        )
    assert resultado.observacoes == ()
    assert resultado.perfil.classes_suportadas == ()


def test_motor_com_stem_bars_e_rect_diagonal_misturadas_ignora_as_duas(tmp_path: Path) -> None:
    pacote = _pacote_com(_gramatica())
    moldura, rect = pacote["variants"]
    haste = copy.deepcopy(rect)
    haste["id"] = "autoral-haste-000"
    haste["class_code"] = "HASTE_AUTORAL"
    haste["recognition"]["grammar"] = {
        "kind": "stem_bars",
        "bars": 3,
        "taper": "decreasing",
        "enclosure": "none",
        "removal_mark": False,
        "max_span": 40,
    }
    pacote["variants"] = [rect, moldura, haste]
    pacotes = _carrega(tmp_path, pacote)

    assert [v["id"] for _, v in variantes_do_motor(pacotes)] == [_CASO_MOLDURA.variant_id]
    assert [v["id"] for _, v in _enabled(pacotes)] == [
        "autoral-rect-diagonal-001",
        _CASO_MOLDURA.variant_id,
        "autoral-haste-000",
    ]
    motor = perfil_pacotes(pacotes)
    assert _CLASSE not in motor.classes_suportadas
    assert "HASTE_AUTORAL" not in motor.classes_suportadas
    modelo = perfil_pacotes_modelo(pacotes, carregar_tabela_glifos())
    assert {_CLASSE, "HASTE_AUTORAL"} <= set(modelo.classes_suportadas)
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=300)
        draw_symbol(pagina, _CASO_MOLDURA)
        resultado = observar_pacotes(
            pagina, documento_id="d", documento_sha256="0" * 64, pagina_numero=1, pacotes=pacotes
        )
    variantes = {dict(o.atributos).get("variante_inventario") for o in resultado.observacoes}
    assert variantes == {_CASO_MOLDURA.variant_id}


def test_enabled_e_variantes_do_motor_preservam_ordem_com_rect_diagonal(tmp_path: Path) -> None:
    pacote = _pacote_com(_gramatica())
    moldura, rect = pacote["variants"]
    outra = copy.deepcopy(moldura)
    outra["id"] = "autoral-moldura-999"
    pacote["variants"] = [rect, outra, moldura]
    pacotes = _carrega(tmp_path, pacote)

    todos = [v["id"] for _, v in _enabled(pacotes)]
    motor = [v["id"] for _, v in variantes_do_motor(pacotes)]
    assert todos == ["autoral-rect-diagonal-001", "autoral-moldura-999", _CASO_MOLDURA.variant_id]
    assert motor == todos[1:]


def test_pacotes_reais_nao_tem_rect_diagonal_e_nada_muda() -> None:
    reais = carregar_pacotes()
    tipos = {v["recognition"]["grammar"]["kind"] for _, v in _enabled(reais)}
    assert "rect_diagonal" not in tipos
    assert len(_enabled(reais)) == 30
    assert len(variantes_do_motor(reais)) == 22
    assert frozenset({"stem_bars", "rect_diagonal"}) == GRAMATICAS_SO_MODELO
    modelo = perfil_pacotes_modelo(reais, carregar_tabela_glifos())
    motor = perfil_pacotes(reais)
    assert set(modelo.classes_suportadas) - set(motor.classes_suportadas) == {
        "ATERRAMENTO",
        "PARA_RAIOS_MT",
    }
    assert "PARA_RAIOS_BT" not in motor.classes_suportadas
