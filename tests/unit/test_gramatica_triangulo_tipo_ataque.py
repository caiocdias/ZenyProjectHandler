"""Ataques ao tipo `split_triangle`: tipos errados, schema x validador, isolamento do motor."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.declarative_symbols.corpus import draw_symbol
from tests.unit.test_gramatica_triangulo_tipo import (
    _BASE,
    _CASO_MOLDURA,
    _CLASSE,
    _SCHEMA,
    _carrega,
    _gramatica,
    _pacote_com,
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
from zeny_project_handler.adapters.analysis.model_symbols import perfil_pacotes_modelo

_MENSAGEM = "invalid grammar fields"


def _ramo() -> dict[str, Any]:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    ramos = [
        r
        for r in schema["$defs"]["grammar"]["oneOf"]
        if r["properties"]["kind"].get("const") == "split_triangle"
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
    for campo in ("fill", "enclosure"):
        valor = gramatica[campo]
        if not isinstance(valor, str) or valor not in props[campo]["enum"]:
            return False
    if not isinstance(gramatica["removal_mark"], bool):
        return False
    # Minor 1 da revisão final: elipse com X não é grupo da R-1 (o mesmo que
    # test_envolvente_com_marcador_de_retirada_recusa_no_schema afirma do ramo).
    if gramatica["enclosure"] == "ellipse" and gramatica["removal_mark"] is True:
        return False
    span = gramatica["max_span"]
    regra = props["max_span"]
    if not _numero_json(span) or not math.isfinite(span):
        return False
    return bool(span > regra["exclusiveMinimum"] and span <= regra["maximum"])


_CASOS: list[Any] = [
    pytest.param(_gramatica(), id="base"),
    pytest.param(_gramatica(fill="outline", enclosure="ellipse", removal_mark=True), id="outline"),
    pytest.param(_gramatica(max_span=72), id="span-72"),
    pytest.param(_gramatica(max_span=72.0), id="span-72.0"),
    pytest.param(_gramatica(max_span=72.0000001), id="span-acima-minimo"),
    pytest.param(_gramatica(max_span=1e-300), id="span-1e-300"),
    pytest.param(_gramatica(max_span=-0.0), id="span-menos-zero"),
    pytest.param(_gramatica(max_span=0), id="span-zero"),
    pytest.param(_gramatica(max_span=-1), id="span-negativo"),
    pytest.param(_gramatica(max_span=96), id="span-96"),
    pytest.param(_gramatica(max_span=float("inf")), id="span-inf"),
    pytest.param(_gramatica(max_span=float("-inf")), id="span-menos-inf"),
    pytest.param(_gramatica(max_span="40"), id="span-string"),
    pytest.param(_gramatica(max_span=None), id="span-nulo"),
    pytest.param(_gramatica(max_span=[40]), id="span-lista"),
    pytest.param(_gramatica(max_span={"v": 40}), id="span-dict"),
    pytest.param(_gramatica(max_span=False), id="span-false"),
    pytest.param(_gramatica(max_span=True), id="span-true"),
    pytest.param(_gramatica(fill="HALF_CYAN"), id="fill-caixa-alta"),
    pytest.param(_gramatica(fill=" half_cyan"), id="fill-espaco"),
    pytest.param(_gramatica(fill=""), id="fill-vazio"),
    pytest.param(_gramatica(fill=None), id="fill-nulo"),
    pytest.param(_gramatica(fill=1), id="fill-inteiro"),
    pytest.param(_gramatica(fill=True), id="fill-bool"),
    pytest.param(_gramatica(fill=["half_cyan"]), id="fill-lista"),
    pytest.param(_gramatica(fill=[["outline"]]), id="fill-lista-aninhada"),
    pytest.param(_gramatica(fill={"a": 1}), id="fill-dict"),
    pytest.param(_gramatica(enclosure="circle"), id="enclosure-circle"),
    pytest.param(_gramatica(enclosure="ELLIPSE"), id="enclosure-caixa-alta"),
    pytest.param(_gramatica(enclosure=True), id="enclosure-bool"),
    pytest.param(_gramatica(enclosure=None), id="enclosure-nulo"),
    pytest.param(_gramatica(enclosure=["none"]), id="enclosure-lista"),
    pytest.param(_gramatica(enclosure={"a": 1}), id="enclosure-dict"),
    pytest.param(_gramatica(removal_mark=0), id="removal-zero"),
    pytest.param(_gramatica(removal_mark=1), id="removal-um"),
    pytest.param(_gramatica(removal_mark="true"), id="removal-string"),
    pytest.param(_gramatica(removal_mark=None), id="removal-nulo"),
    pytest.param(_gramatica(removal_mark=[]), id="removal-lista"),
    pytest.param(_gramatica(removal_mark={}), id="removal-dict"),
    pytest.param({**_BASE, "bars": 3}, id="campo-de-stem-bars"),
    pytest.param({**_BASE, "frame": "rect"}, id="campo-de-moldura"),
    pytest.param({k: v for k, v in _BASE.items() if k != "max_span"}, id="sem-max-span"),
    pytest.param({k: v for k, v in _BASE.items() if k != "removal_mark"}, id="sem-removal"),
    pytest.param({k: v for k, v in _BASE.items() if k != "fill"}, id="sem-fill"),
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


@pytest.mark.parametrize("tipo", [["split_triangle"], {"k": 1}, None, 3, "Split_Triangle"])
def test_kind_de_tipo_errado_recusa_sem_type_error(tmp_path: Path, tipo: Any) -> None:
    with pytest.raises(ValueError, match="unsupported grammar"):
        _carrega(tmp_path, _pacote_com(_gramatica(kind=tipo)))


@pytest.mark.parametrize("valor", [["half_cyan"], {"k": 1}, None, 1, True])
@pytest.mark.parametrize("campo", ["fill", "enclosure"])
def test_valor_nao_textual_recusa_com_value_error(tmp_path: Path, campo: str, valor: Any) -> None:
    with pytest.raises(ValueError, match=_MENSAGEM):
        _carrega(tmp_path, _pacote_com(_gramatica(**{campo: valor})))


def test_motor_nao_observa_split_triangle_mesmo_habilitado_e_desenhado(tmp_path: Path) -> None:
    """Triângulo e elipse desenhados: o motor antigo não os lê como nada."""
    pacote = _pacote_com(_gramatica(fill="outline", enclosure="ellipse"))
    pacote["variants"] = pacote["variants"][1:]
    pacotes = _carrega(tmp_path, pacote)
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=300)
        pagina.draw_polyline([(100, 120), (115, 95), (130, 120), (100, 120)], color=(0, 0, 0))
        pagina.draw_oval((90, 88, 140, 126), color=(0, 0, 0), width=0.5)
        resultado = observar_pacotes(
            pagina, documento_id="d", documento_sha256="0" * 64, pagina_numero=1, pacotes=pacotes
        )
    assert resultado.observacoes == ()
    assert resultado.perfil.classes_suportadas == ()
    assert len(_enabled(pacotes)) == 1
    assert variantes_do_motor(pacotes) == ()


def test_perfil_do_motor_nao_anuncia_split_triangle(tmp_path: Path) -> None:
    pacotes = _carrega(tmp_path, _pacote_com(_gramatica()))

    perfil = perfil_pacotes(pacotes)

    assert _CLASSE not in perfil.classes_suportadas
    assert ("enabled_variants", 1) in perfil.parametros


def test_perfil_do_modelo_nao_anuncia_classe_de_variante_pendente(tmp_path: Path) -> None:
    pacote = _pacote_com(_gramatica())
    pacote["variants"][1]["recognition"] = {
        "status": "pending",
        "reason": "ainda sem gramática curada",
        "negative_examples": ["triângulo sólido sem divisão"],
    }
    pacotes = _carrega(tmp_path, pacote)

    perfil = perfil_pacotes_modelo(pacotes, carregar_tabela_glifos())

    assert _CLASSE not in perfil.classes_suportadas
    assert ("enabled_variants", 1) in perfil.parametros


def test_perfil_do_modelo_anuncia_a_classe_uma_vez_com_duas_variantes(tmp_path: Path) -> None:
    pacote = _pacote_com(_gramatica())
    outra = copy.deepcopy(pacote["variants"][1])
    outra["id"] = "autoral-split-triangle-002"
    outra["recognition"]["grammar"] = _gramatica(fill="outline", enclosure="ellipse")
    pacote["variants"].append(outra)
    pacotes = _carrega(tmp_path, pacote)

    perfil = perfil_pacotes_modelo(pacotes, carregar_tabela_glifos())

    assert perfil.classes_suportadas.count(_CLASSE) == 1
    assert ("enabled_variants", 3) in perfil.parametros
    assert len(variantes_do_motor(pacotes)) == 1


def test_motor_com_split_triangle_e_moldura_observa_so_a_moldura(tmp_path: Path) -> None:
    pacotes = _carrega(tmp_path, _pacote_com(_gramatica()))
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=300)
        draw_symbol(pagina, _CASO_MOLDURA)
        resultado = observar_pacotes(
            pagina, documento_id="d", documento_sha256="0" * 64, pagina_numero=1, pacotes=pacotes
        )
    variantes = {dict(o.atributos).get("variante_inventario") for o in resultado.observacoes}
    assert variantes == {_CASO_MOLDURA.variant_id}


# Onda final da revisão (Minor 1): envolvente com marcador de retirada -----------------------------

_ANOTACOES = frozenset({"$comment", "description", "title"})


def _avalia(no: Any, valor: Any) -> bool:
    """Subconjunto estrito de JSON Schema para o ramo `split_triangle`: palavra desconhecida
    falha o teste em vez de aceitar em silêncio (sem biblioteca no ambiente)."""
    if no is True or no is False:
        return bool(no)
    assert isinstance(no, dict)
    for chave, regra in no.items():
        if chave in _ANOTACOES:
            continue
        if chave == "type":
            tipos = {"object": dict, "boolean": bool, "string": str}
            if regra == "number":
                if not _numero_json(valor):
                    return False
            elif not isinstance(valor, tipos[regra]):
                return False
        elif chave == "const":
            if type(valor) is not type(regra) or valor != regra:
                return False
        elif chave == "enum":
            if not any(type(valor) is type(item) and valor == item for item in regra):
                return False
        elif chave == "required":
            if not isinstance(valor, dict) or not set(regra) <= set(valor):
                return False
        elif chave == "properties":
            if isinstance(valor, dict) and not all(
                _avalia(sub, valor[campo]) for campo, sub in regra.items() if campo in valor
            ):
                return False
        elif chave == "additionalProperties":
            assert regra is False, regra
            if set(valor) - set(no.get("properties", {})):
                return False
        elif chave == "exclusiveMinimum":
            if not valor > regra:
                return False
        elif chave == "maximum":
            if not valor <= regra:
                return False
        elif chave == "not":
            if _avalia(regra, valor):
                return False
        elif chave == "allOf":
            if not all(_avalia(sub, valor) for sub in regra):
                return False
        elif chave == "anyOf":
            if not any(_avalia(sub, valor) for sub in regra):
                return False
        elif chave == "oneOf":
            if sum(_avalia(sub, valor) for sub in regra) != 1:
                return False
        elif chave == "if":
            ramo = no.get("then", True) if _avalia(regra, valor) else no.get("else", True)
            if not _avalia(ramo, valor):
                return False
        elif chave in ("then", "else"):
            continue
        else:
            raise AssertionError(f"palavra de JSON Schema não suportada pelo teste: {chave}")
    return True


_VALIDAS = [
    ("half_cyan", "none", False),
    ("half_cyan", "none", True),
    ("half_cyan", "ellipse", False),
    ("outline", "none", False),
    ("outline", "none", True),
    ("outline", "ellipse", False),
]


@pytest.mark.parametrize("fill", ["half_cyan", "outline"])
def test_envolvente_com_marcador_de_retirada_recusa_no_validador(tmp_path: Path, fill: str) -> None:
    """Revisão Minor 1: elipse com X não é grupo da R-1; `carregar_pacotes` recusa."""
    gramatica = _gramatica(fill=fill, enclosure="ellipse", removal_mark=True)
    with pytest.raises(ValueError):
        _carrega(tmp_path, _pacote_com(gramatica))


@pytest.mark.parametrize("fill", ["half_cyan", "outline"])
def test_envolvente_com_marcador_de_retirada_recusa_no_schema(fill: str) -> None:
    """Revisão Minor 1: o ramo `split_triangle` do schema recusa a mesma combinação."""
    gramatica = _gramatica(fill=fill, enclosure="ellipse", removal_mark=True)
    assert _avalia(_ramo(), gramatica) is False


@pytest.mark.parametrize(("fill", "enclosure", "removal_mark"), _VALIDAS)
def test_controle_schema_aceita_as_seis_combinacoes_da_r1(
    fill: str, enclosure: str, removal_mark: bool
) -> None:
    """Controle do avaliador: as seis combinações válidas passam no ramo do schema."""
    gramatica = _gramatica(fill=fill, enclosure=enclosure, removal_mark=removal_mark)
    assert _avalia(_ramo(), gramatica) is True
