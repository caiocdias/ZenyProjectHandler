"""Ataque ao tipo `disc_mark` (R-E06.3.5-1): forma exata, tipos não hasheáveis e coerência."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests.unit import test_gramatica_disc_mark_tipo as base

from zeny_project_handler.adapters.analysis import declarative_symbols as ds
from zeny_project_handler.adapters.analysis.declarative_symbols import (
    GRAMATICAS_SO_MODELO,
    carregar_pacotes,
)

_MENSAGEM = "invalid grammar fields"
_NAO_HASHEAVEIS = [[], ["red"], {}, {"k": "red"}, [[]]]


def _carrega(tmp_path: Path, gramatica: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    return base._carrega(tmp_path, base._pacote_com(gramatica))


@pytest.mark.parametrize("valor", [*_NAO_HASHEAVEIS, None, 1, 1.5, True, "RED", "Red", " red", ""])
def test_fill_de_tipo_ou_valor_errado_recusa_sem_type_error(tmp_path: Path, valor: Any) -> None:
    with pytest.raises(ValueError, match=_MENSAGEM):
        _carrega(tmp_path, base._gramatica(fill=valor))


@pytest.mark.parametrize(
    "valor", [*_NAO_HASHEAVEIS, None, 1, True, "FUSE_CURVE", "fuse-curve", "", "double_box "]
)
def test_content_de_tipo_ou_valor_errado_recusa_sem_type_error(tmp_path: Path, valor: Any) -> None:
    with pytest.raises(ValueError, match=_MENSAGEM):
        _carrega(tmp_path, base._gramatica(content=valor))


@pytest.mark.parametrize("campo", ["min_span", "max_span"])
@pytest.mark.parametrize("valor", [None, [], [3], {}, {"v": 3}, "", "NaN", False, 0.0, -0.0, -1e-9])
def test_span_de_tipo_ou_valor_errado_recusa_sem_type_error(
    tmp_path: Path, campo: str, valor: Any
) -> None:
    gramatica = base._gramatica(**{campo: valor})
    if campo == "min_span":
        gramatica["max_span"] = 40
    with pytest.raises(ValueError, match=_MENSAGEM):
        _carrega(tmp_path, gramatica)


@pytest.mark.parametrize("cru", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("campo", ["min_span", "max_span"])
def test_span_nao_finito_no_json_recusa(tmp_path: Path, campo: str, cru: str) -> None:
    pacote = base._pacote_com(base._gramatica())
    texto = json.dumps(pacote)
    antigo = '"min_span": 3' if campo == "min_span" else '"max_span": 40'
    assert antigo in texto
    texto = texto.replace(antigo, f'"{campo}": {cru}')
    (tmp_path / "cru.json").write_text(texto, encoding="utf-8")
    with pytest.raises(ValueError, match=_MENSAGEM):
        carregar_pacotes(packages_dir=tmp_path)


@pytest.mark.parametrize(
    ("minimo", "maximo"),
    [(1e-9, 2), (0.001, 0.002), (71, 72), (71.999, 72), (1, 72.0), (3.0, 40.0), (2, 3)],
)
def test_limites_validos_de_span_carregam(tmp_path: Path, minimo: float, maximo: float) -> None:
    gramatica = base._gramatica(min_span=minimo, max_span=maximo)
    assert len(_carrega(tmp_path, gramatica)) == 1


@pytest.mark.parametrize(
    ("minimo", "maximo"),
    [
        (1, 72.0001),
        (1, 72.5),
        (1, 1e9),
        (1, float(2**70)),
        (72, 72),
        (72, 73),
        (5, 5.0),
        (5, 4.999),
    ],
)
def test_limites_invalidos_de_span_recusam(tmp_path: Path, minimo: float, maximo: float) -> None:
    gramatica = base._gramatica(min_span=minimo, max_span=maximo)
    with pytest.raises(ValueError, match=_MENSAGEM):
        _carrega(tmp_path, gramatica)


@pytest.mark.parametrize(
    "extra", ["terminal_line", "enclosure", "removal_mark", "label", "Kind", "min_span "]
)
def test_campo_extra_recusa(tmp_path: Path, extra: str) -> None:
    with pytest.raises(ValueError, match=_MENSAGEM):
        _carrega(tmp_path, {**base._BASE, extra: True})


def test_chave_com_espaco_no_lugar_de_campo_recusa(tmp_path: Path) -> None:
    gramatica = {("fill " if k == "fill" else k): v for k, v in base._BASE.items()}
    with pytest.raises(ValueError, match=_MENSAGEM):
        _carrega(tmp_path, gramatica)


@pytest.mark.parametrize("campo", ["fill", "content", "min_span", "max_span"])
def test_campo_ausente_recusa(tmp_path: Path, campo: str) -> None:
    gramatica = {k: v for k, v in base._BASE.items() if k != campo}
    with pytest.raises(ValueError, match=_MENSAGEM):
        _carrega(tmp_path, gramatica)


@pytest.mark.parametrize("kind", ["Disc_Mark", "disc-mark", "disc_mark ", "", None, ["disc_mark"]])
def test_kind_parecido_ou_de_tipo_errado_recusa(tmp_path: Path, kind: Any) -> None:
    with pytest.raises(ValueError, match="unsupported grammar"):
        _carrega(tmp_path, base._gramatica(kind=kind))


def test_validador_direto_nao_explode_com_tipos_nao_hasheaveis() -> None:
    for valor in _NAO_HASHEAVEIS:
        assert ds._disc_mark_grammar_ok(base._gramatica(fill=valor)) is False
        assert ds._disc_mark_grammar_ok(base._gramatica(content=valor)) is False
    assert ds._disc_mark_grammar_ok(base._gramatica()) is True


def test_validadores_e_gramaticas_coerentes_com_disc_mark() -> None:
    assert set(ds._GRAMMAR_FIELD_VALIDATORS) == ds._GRAMMARS
    assert "disc_mark" in ds._GRAMMARS
    assert ds.GRAMMAR_DISC_MARK == "disc_mark"
    assert ds._GRAMMAR_FIELD_VALIDATORS["disc_mark"] is ds._disc_mark_grammar_ok
    assert GRAMATICAS_SO_MODELO <= ds._GRAMMARS


def test_schema_enumera_todas_as_gramaticas_do_validador() -> None:
    schema = json.loads(base._SCHEMA.read_text(encoding="utf-8"))
    kinds = {
        r["properties"]["kind"]["const"]
        for r in schema["$defs"]["grammar"]["oneOf"]
        if "const" in r["properties"]["kind"]
    }
    assert ds.GRAMMAR_DISC_MARK in kinds
    assert kinds == ds._GRAMMARS


def test_disc_mark_nao_e_gramatica_do_motor_antigo() -> None:
    assert "disc_mark" in GRAMATICAS_SO_MODELO
    assert {"stem_bars", "rect_diagonal", "split_triangle", "forked_stem"} <= GRAMATICAS_SO_MODELO


def test_schema_e_validador_concordam_nos_limites() -> None:
    schema = json.loads(base._SCHEMA.read_text(encoding="utf-8"))
    ramo = next(
        r
        for r in schema["$defs"]["grammar"]["oneOf"]
        if r["properties"]["kind"].get("const") == "disc_mark"
    )
    for campo in ("min_span", "max_span"):
        assert "minimum" not in ramo["properties"][campo]
        assert ramo["properties"][campo]["exclusiveMinimum"] == 0
        assert ramo["properties"][campo]["maximum"] == 72
    assert ds._disc_mark_grammar_ok(base._gramatica(min_span=72, max_span=72)) is False
    assert ds._disc_mark_grammar_ok(base._gramatica(min_span=71, max_span=72)) is True
    assert ds._disc_mark_grammar_ok(base._gramatica(min_span=0, max_span=1)) is False
