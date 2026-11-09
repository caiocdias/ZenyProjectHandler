"""Ataques ao tipo `forked_stem`: forma exata, schema x validador, isolamento do motor antigo."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.declarative_symbols.corpus import draw_symbol
from tests.unit.test_gramatica_estai_tipo import (
    _BASE,
    _CASO_MOLDURA,
    _CLASSE,
    _SCHEMA,
    _carrega,
    _gramatica,
    _pacote_com,
)
from tests.unit.test_gramatica_triangulo_tipo_ataque import _avalia

from zeny_project_handler.adapters.analysis import declarative_symbols as ds
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

_MENSAGEM = "invalid grammar fields"


def _ramo() -> dict[str, Any]:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    ramos = [
        r
        for r in schema["$defs"]["grammar"]["oneOf"]
        if r["properties"]["kind"].get("const") == "forked_stem"
    ]
    assert len(ramos) == 1
    ramo: dict[str, Any] = ramos[0]
    return ramo


def _sem(campo: str) -> dict[str, Any]:
    return {k: v for k, v in _BASE.items() if k != campo}


_CASOS: list[Any] = [
    pytest.param(_gramatica(), id="base"),
    pytest.param(_gramatica(enclosure="ellipse"), id="elipse"),
    pytest.param(_gramatica(removal_mark=True), id="x"),
    pytest.param(_gramatica(enclosure="ellipse", removal_mark=True), id="elipse-com-x"),
    pytest.param(_gramatica(max_span=72), id="span-72"),
    pytest.param(_gramatica(max_span=72.0), id="span-72.0"),
    pytest.param(_gramatica(max_span=math.nextafter(72.0, math.inf)), id="span-acima"),
    pytest.param(_gramatica(max_span=96), id="span-96"),
    pytest.param(_gramatica(max_span=1e-300), id="span-minusculo"),
    pytest.param(_gramatica(max_span=0), id="span-zero"),
    pytest.param(_gramatica(max_span=-0.0), id="span-menos-zero"),
    pytest.param(_gramatica(max_span=-1), id="span-negativo"),
    pytest.param(_gramatica(max_span=float("inf")), id="span-inf"),
    pytest.param(_gramatica(max_span=float("-inf")), id="span-menos-inf"),
    pytest.param(_gramatica(max_span=float("nan")), id="span-nan"),
    pytest.param(_gramatica(max_span=True), id="span-true"),
    pytest.param(_gramatica(max_span=False), id="span-false"),
    pytest.param(_gramatica(max_span="40"), id="span-texto"),
    pytest.param(_gramatica(max_span=None), id="span-nulo"),
    pytest.param(_gramatica(max_span=[40]), id="span-lista"),
    pytest.param(_gramatica(max_span={"v": 40}), id="span-dict"),
    pytest.param(_gramatica(enclosure="ELLIPSE"), id="enclosure-caixa-alta"),
    pytest.param(_gramatica(enclosure=" none"), id="enclosure-espaco"),
    pytest.param(_gramatica(enclosure=""), id="enclosure-vazio"),
    pytest.param(_gramatica(enclosure=None), id="enclosure-nulo"),
    pytest.param(_gramatica(enclosure=True), id="enclosure-bool"),
    pytest.param(_gramatica(enclosure=1), id="enclosure-inteiro"),
    pytest.param(_gramatica(enclosure=["none"]), id="enclosure-lista"),
    pytest.param(_gramatica(enclosure=[["ellipse"]]), id="enclosure-lista-aninhada"),
    pytest.param(_gramatica(enclosure={"a": 1}), id="enclosure-dict"),
    pytest.param(_gramatica(removal_mark=0), id="removal-zero"),
    pytest.param(_gramatica(removal_mark=1), id="removal-um"),
    pytest.param(_gramatica(removal_mark=1.0), id="removal-float"),
    pytest.param(_gramatica(removal_mark="false"), id="removal-texto"),
    pytest.param(_gramatica(removal_mark=None), id="removal-nulo"),
    pytest.param(_gramatica(removal_mark=[]), id="removal-lista"),
    pytest.param(_gramatica(removal_mark={}), id="removal-dict"),
    pytest.param(_gramatica(enclosure="ellipse", removal_mark=1), id="elipse-removal-inteiro"),
    pytest.param({**_BASE, "extra": 1}, id="campo-extra"),
    pytest.param({**_BASE, "fill": "outline"}, id="campo-de-split-triangle"),
    pytest.param({**_BASE, "bars": 3}, id="campo-de-stem-bars"),
    pytest.param(_sem("kind"), id="sem-kind"),
    pytest.param(_sem("enclosure"), id="sem-enclosure"),
    pytest.param(_sem("removal_mark"), id="sem-removal"),
    pytest.param(_sem("max_span"), id="sem-max-span"),
]


def _schema_aceita(gramatica: dict[str, Any]) -> bool:
    span = gramatica.get("max_span")
    if isinstance(span, float) and (span != span or abs(span) == float("inf")):
        return False  # JSON estrito não tem NaN/Infinity
    return _avalia(_ramo(), gramatica)


@pytest.mark.parametrize("gramatica", _CASOS)
def test_schema_e_validador_concordam(tmp_path: Path, gramatica: dict[str, Any]) -> None:
    esperado = _schema_aceita(gramatica)
    try:
        carregou = len(_carrega(tmp_path, _pacote_com(gramatica))) == 1
    except ValueError:
        carregou = False
    assert carregou is esperado


@pytest.mark.parametrize(
    "valor", [["none"], {"k": 1}, [["ellipse"]], {"none": 1}, None, 1, True, 1.5, ("none",)]
)
def test_enclosure_nao_textual_recusa_sem_type_error(valor: Any) -> None:
    assert ds._forked_stem_grammar_ok(_gramatica(enclosure=valor)) is False


@pytest.mark.parametrize("cru", ["NaN", "Infinity", "-Infinity"])
def test_max_span_nao_finito_no_json_recusa(tmp_path: Path, cru: str) -> None:
    texto = json.dumps(_pacote_com(_gramatica())).replace('"max_span": 40', f'"max_span": {cru}')
    assert cru in texto
    (tmp_path / "cru.json").write_text(texto, encoding="utf-8")
    with pytest.raises(ValueError, match=_MENSAGEM):
        carregar_pacotes(packages_dir=tmp_path)


@pytest.mark.parametrize("tipo", [["forked_stem"], {"k": 1}, None, 3, "Forked_Stem", "forked-stem"])
def test_kind_de_tipo_errado_recusa_sem_type_error(tmp_path: Path, tipo: Any) -> None:
    with pytest.raises(ValueError, match="unsupported grammar"):
        _carrega(tmp_path, _pacote_com(_gramatica(kind=tipo)))


def test_validadores_e_gramaticas_coerentes() -> None:
    assert set(ds._GRAMMAR_FIELD_VALIDATORS) == ds._GRAMMARS
    assert ds._GRAMMAR_FIELD_VALIDATORS["forked_stem"] is ds._forked_stem_grammar_ok
    assert GRAMATICAS_SO_MODELO <= ds._GRAMMARS


def test_schema_e_codigo_listam_os_mesmos_tipos() -> None:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    kinds = {r["properties"]["kind"]["const"] for r in schema["$defs"]["grammar"]["oneOf"]}
    assert kinds == ds._GRAMMARS


def test_so_modelo_nao_inclui_tipos_do_motor_antigo() -> None:
    antigos = ds._GRAMMARS - GRAMATICAS_SO_MODELO
    assert {"label_in_frame", "terminal_disc", "framed_diagonals"} <= antigos
    assert "forked_stem" not in antigos


@pytest.mark.parametrize(
    ("enclosure", "removal_mark"), [("none", False), ("none", True), ("ellipse", False)]
)
def test_schema_aceita_as_tres_combinacoes_validas(enclosure: str, removal_mark: bool) -> None:
    assert _avalia(_ramo(), _gramatica(enclosure=enclosure, removal_mark=removal_mark)) is True


def test_forked_stem_sozinho_no_motor_nao_observa_nada(tmp_path: Path) -> None:
    pacote = _pacote_com(_gramatica(enclosure="ellipse"))
    pacote["variants"] = pacote["variants"][1:]
    pacotes = _carrega(tmp_path, pacote)
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=300)
        pagina.draw_line((100, 80), (100, 130), color=(0, 0, 0))
        pagina.draw_line((100, 100), (90, 85), color=(0, 0, 0))
        pagina.draw_line((100, 100), (110, 85), color=(0, 0, 0))
        pagina.draw_oval((85, 75, 115, 135), color=(0, 0, 0), width=0.5)
        resultado = observar_pacotes(
            pagina, documento_id="d", documento_sha256="0" * 64, pagina_numero=1, pacotes=pacotes
        )
    assert resultado.observacoes == ()
    assert resultado.perfil.classes_suportadas == ()
    assert variantes_do_motor(pacotes) == ()


def test_perfil_do_motor_nao_anuncia_forked_stem(tmp_path: Path) -> None:
    perfil = perfil_pacotes(_carrega(tmp_path, _pacote_com(_gramatica())))
    assert _CLASSE not in perfil.classes_suportadas


def test_perfil_do_modelo_nao_anuncia_forked_stem_pendente(tmp_path: Path) -> None:
    pacote = _pacote_com(_gramatica())
    pacote["variants"][1]["recognition"] = {
        "status": "pending",
        "reason": "ainda sem gramática curada",
        "negative_examples": ["haste simples sem garfo"],
    }
    perfil = perfil_pacotes_modelo(_carrega(tmp_path, pacote), carregar_tabela_glifos())
    assert _CLASSE not in perfil.classes_suportadas


def test_perfil_do_modelo_anuncia_classe_uma_vez_com_duas_variantes(tmp_path: Path) -> None:
    pacote = _pacote_com(_gramatica())
    outra = copy.deepcopy(pacote["variants"][1])
    outra["id"] = "autoral-forked-stem-002"
    outra["recognition"]["grammar"] = _gramatica(enclosure="ellipse")
    pacote["variants"].append(outra)
    perfil = perfil_pacotes_modelo(_carrega(tmp_path, pacote), carregar_tabela_glifos())
    assert perfil.classes_suportadas.count(_CLASSE) == 1
    assert ("enabled_variants", 3) in perfil.parametros


def test_motor_com_forked_stem_e_moldura_observa_so_a_moldura(tmp_path: Path) -> None:
    pacotes = _carrega(tmp_path, _pacote_com(_gramatica()))
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=300)
        draw_symbol(pagina, _CASO_MOLDURA)
        resultado = observar_pacotes(
            pagina, documento_id="d", documento_sha256="0" * 64, pagina_numero=1, pacotes=pacotes
        )
    variantes = {dict(o.atributos).get("variante_inventario") for o in resultado.observacoes}
    assert variantes == {_CASO_MOLDURA.variant_id}
