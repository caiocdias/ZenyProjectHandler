"""E06.1: guarda contra memorização de folha real nos pacotes de simbologia.

Os pacotes declarativos descrevem símbolos, nunca uma folha específica. Esta guarda
reprova qualquer valor que pareça coordenada de folha, hash de PDF ou nome de folha.
"""

from __future__ import annotations

import ast
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

_PASTA_PACOTES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "zeny_project_handler"
    / "adapters"
    / "analysis"
    / "symbol_packages"
)

_CASAS_DECIMAIS_MAXIMAS = 4
# Separador `.` ou `,` com dígitos antes ou não (".123456", "0,123456"), ou notação científica
# com expoente <= -5 ("1e-05", "-1.5E-7").
_COORDENADA_NO_TEXTO = re.compile(
    rf"[.,]\d{{{_CASAS_DECIMAIS_MAXIMAS + 1},}}|\d[eE]-0*(?:[5-9]|[1-9]\d+)"
)
_ESPACOS = re.compile(r"\s+")
_HEXADECIMAL_64 = re.compile(r"[0-9a-fA-F]{64}")
# Montado por concatenação para o `git grep` do fechamento não achar este arquivo.
_NOME_DE_FOLHA = re.compile("PROJETO" + " DE REDE", re.IGNORECASE)


def _casas_decimais_excessivas(valor: float) -> bool:
    expoente = Decimal(repr(valor)).as_tuple().exponent
    return isinstance(expoente, int) and expoente < -_CASAS_DECIMAIS_MAXIMAS


def _violacoes_de_texto(texto: str, caminho: str) -> list[str]:
    violacoes: list[str] = []
    if _COORDENADA_NO_TEXTO.search(texto):
        violacoes.append(f"{caminho}: número com mais de 4 casas decimais no texto")
    if _HEXADECIMAL_64.search(texto):
        violacoes.append(f"{caminho}: hexadecimal de 64 caracteres (sha256 de PDF)")
    if ".pdf" in texto.lower():
        violacoes.append(f"{caminho}: referência a arquivo .pdf")
    if _NOME_DE_FOLHA.search(_ESPACOS.sub(" ", texto)):
        violacoes.append(f"{caminho}: nome de folha real")
    return violacoes


def verificar_pacote(dados: Any, caminho: str = "$") -> list[str]:
    """Devolve as violações de memorização encontradas em todo valor do pacote."""
    if isinstance(dados, dict):
        violacoes: list[str] = []
        for chave, valor in dados.items():
            violacoes.extend(_violacoes_de_texto(str(chave), f"{caminho}.<chave>"))
            violacoes.extend(verificar_pacote(valor, f"{caminho}.{chave}"))
        return violacoes
    if isinstance(dados, list):
        violacoes = []
        for indice, valor in enumerate(dados):
            violacoes.extend(verificar_pacote(valor, f"{caminho}[{indice}]"))
        return violacoes
    if isinstance(dados, str):
        return _violacoes_de_texto(dados, caminho)
    if isinstance(dados, float) and _casas_decimais_excessivas(dados):
        return [f"{caminho}: float com mais de 4 casas decimais"]
    return []


def test_pacotes_reais_passam_na_guarda() -> None:
    arquivos = sorted(_PASTA_PACOTES.glob("*.json"))
    assert arquivos, f"nenhum pacote encontrado em {_PASTA_PACOTES}"
    violacoes: list[str] = []
    for arquivo in arquivos:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        violacoes.extend(f"{arquivo.name} {item}" for item in verificar_pacote(dados))
    assert violacoes == []


@pytest.mark.parametrize(
    "dados",
    [
        pytest.param({"variants": [{"x": 0.123456}]}, id="float-com-6-casas"),
        pytest.param({"variants": [{"hash": "a1" * 32}]}, id="hexadecimal-de-64"),
        pytest.param(
            {"variants": [{"locator": "PROJETO" + " DE REDE NS 123"}]},
            id="nome-de-folha-por-concatenacao",
        ),
        pytest.param({"variants": [{"origem": "folha.pdf"}]}, id="arquivo-pdf"),
        pytest.param({"x": 1e-05}, id="float-em-notacao-cientifica"),
        pytest.param({"a1" * 32: 1}, id="hexadecimal-de-64-na-chave"),
        pytest.param({"nota": "0.123456,0.654321"}, id="coordenadas-no-texto"),
    ],
)
def test_guarda_reprova(dados: Any) -> None:
    assert len(verificar_pacote(dados)) == 1


@pytest.mark.parametrize(
    "dados",
    [
        pytest.param({"x": 0.1234, "y": 3.5, "z": 2}, id="ate-4-casas"),
        pytest.param({"x": 100.1234}, id="float-grande-sem-ruido-binario"),
        pytest.param({"x": 12.3456}, id="float-4-casas"),
        pytest.param({"x": "0.1234", "nota": "v1.2.3 e 0.1234,0.5"}, id="texto-numerico-curto"),
        pytest.param({"hash": "a1" * 31}, id="hexadecimal-curto"),
        pytest.param({"x": "1e-04", "y": "1.234.567,89", "z": ",1234"}, id="texto-numerico-ate-4"),
    ],
)
def test_guarda_aceita_valores_legitimos(dados: Any) -> None:
    assert verificar_pacote(dados) == []


_RAIZ = Path(__file__).resolve().parents[2]
_GRAMATICAS_NOVAS = (
    _RAIZ
    / "src"
    / "zeny_project_handler"
    / "adapters"
    / "analysis"
    / "drawing_model"
    / "grammar_stem.py",
    _RAIZ
    / "src"
    / "zeny_project_handler"
    / "adapters"
    / "analysis"
    / "drawing_model"
    / "grammar_marcas.py",
    _RAIZ
    / "src"
    / "zeny_project_handler"
    / "adapters"
    / "analysis"
    / "drawing_model"
    / "grammar_rect_diagonal.py",
    _RAIZ
    / "src"
    / "zeny_project_handler"
    / "adapters"
    / "analysis"
    / "drawing_model"
    / "grammar_triangulo.py",
    _RAIZ / "tests" / "fixtures" / "symbol_grammars" / "stem_bars.py",
    _RAIZ / "tests" / "fixtures" / "symbol_grammars" / "rect_diagonal.py",
    _RAIZ / "tests" / "fixtures" / "symbol_grammars" / "triangulo.py",
    _RAIZ / "tests" / "unit" / "test_grammar_marcas_envolvente.py",
    _RAIZ / "tests" / "unit" / "test_grammar_marcas_envolvente_ataque.py",
    _RAIZ / "tests" / "unit" / "test_grammar_marcas_x_contexto.py",
    _RAIZ / "tests" / "unit" / "test_grammar_marcas_x_contexto_ataque.py",
    _RAIZ / "tests" / "unit" / "test_grammar_marcas_costuras_etapa.py",
    _RAIZ / "tests" / "unit" / "test_grammar_marcas_elipse_inclinada.py",
    _RAIZ / "tests" / "unit" / "test_grammar_marcas_elipse_inclinada_ataque.py",
    _RAIZ / "tests" / "unit" / "test_grammar_rect_diagonal.py",
    _RAIZ / "tests" / "unit" / "test_grammar_rect_diagonal_ataque.py",
    _RAIZ / "tests" / "unit" / "test_grammar_rect_diagonal_herdados_ataque.py",
    _RAIZ / "tests" / "unit" / "test_grammar_triangulo.py",
    _RAIZ / "tests" / "unit" / "test_grammar_triangulo_ataque.py",
    _RAIZ / "tests" / "unit" / "test_gramatica_triangulo_tipo.py",
    _RAIZ / "tests" / "unit" / "test_model_symbols_formas_comuns.py",
    _RAIZ / "tests" / "unit" / "test_model_symbols_formas_comuns_ataque.py",
    _RAIZ / "tests" / "unit" / "test_grammar_triangulo_teto.py",
    _RAIZ / "tests" / "integration" / "test_model_symbols_trafo_runner.py",
    _RAIZ / "tests" / "integration" / "test_model_symbols_trafo_ataque.py",
    _RAIZ / "tests" / "integration" / "test_trafo_costuras_etapa_testador.py",
)


_EPSILON_MAXIMO = 1e-6
_COORDENADA_GRANDE = 1e5


def _numero_parece_coordenada(valor: float) -> bool:
    """Epsilon (|x| < 1e-6) passa; coordenada excede as casas da guarda JSON ou é grande."""
    modulo = abs(valor)
    if modulo < _EPSILON_MAXIMO:
        return False
    if _casas_decimais_excessivas(modulo):
        return True
    return modulo >= _COORDENADA_GRANDE and modulo != int(modulo)


def _violacoes_de_fonte(fonte: str, nome: str) -> list[str]:
    """Fonte Python: strings (docstrings inclusive) pela guarda textual; números por valor."""
    violacoes: list[str] = []
    for no in ast.walk(ast.parse(fonte)):
        if not isinstance(no, ast.Constant):
            continue
        local = f"{nome}:{no.lineno}"
        if isinstance(no.value, str):
            violacoes.extend(_violacoes_de_texto(no.value, local))
        elif isinstance(no.value, float) and _numero_parece_coordenada(no.value):
            violacoes.append(f"{local}: número que parece coordenada ({no.value!r})")
    return violacoes


@pytest.mark.parametrize("arquivo", _GRAMATICAS_NOVAS, ids=lambda a: a.name)
def test_gramaticas_novas_passam_na_guarda(arquivo: Path) -> None:
    texto = arquivo.read_text(encoding="utf-8")
    assert _violacoes_de_fonte(texto, arquivo.name) == []


@pytest.mark.parametrize(
    "fonte",
    [
        pytest.param("x = 612345.678\n", id="coordenada-grande"),
        pytest.param("x = 12.34567\n", id="muitas-casas"),
        pytest.param("x = 0.123456\n", id="normalizada-com-6-casas"),
        pytest.param('x = "origem: folha.pdf"\n', id="string-pdf"),
        pytest.param('def f():\n    """Veja folha.pdf."""\n', id="docstring-pdf"),
    ],
)
def test_guarda_de_fonte_reprova(fonte: str, tmp_path: Path) -> None:
    arquivo = tmp_path / "sintetico.py"
    arquivo.write_text(fonte, encoding="utf-8")
    assert len(_violacoes_de_fonte(arquivo.read_text(encoding="utf-8"), arquivo.name)) == 1


def test_guarda_de_fonte_aceita_epsilon_e_constantes_curtas() -> None:
    fonte = "a = 1e-9\nb = 1e-12\nc = 1.25\nd = 0.1234\n"
    assert _violacoes_de_fonte(fonte, "s.py") == []
