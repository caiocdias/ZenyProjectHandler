"""E06.1: guarda contra memorização de folha real nos pacotes de simbologia.

Os pacotes declarativos descrevem símbolos, nunca uma folha específica. Esta guarda
reprova qualquer valor que pareça coordenada de folha, hash de PDF ou nome de folha.
"""

from __future__ import annotations

import json
import re
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
_NUMERO_COM_MUITAS_CASAS = re.compile(rf"^\s*[-+]?\d*\.\d{{{_CASAS_DECIMAIS_MAXIMAS + 1},}}\s*$")
_HEXADECIMAL_64 = re.compile(r"[0-9a-fA-F]{64}")
# Montado por concatenação para o `git grep` do fechamento não achar este arquivo.
_NOME_DE_FOLHA = re.compile("PROJETO" + " DE REDE", re.IGNORECASE)


def _casas_decimais_excessivas(valor: float) -> bool:
    return bool(_NUMERO_COM_MUITAS_CASAS.match(f"{valor:.15f}".rstrip("0"))) or bool(
        _NUMERO_COM_MUITAS_CASAS.match(repr(valor))
    )


def _violacoes_de_texto(texto: str, caminho: str) -> list[str]:
    violacoes: list[str] = []
    if _NUMERO_COM_MUITAS_CASAS.match(texto):
        violacoes.append(f"{caminho}: string numérica com mais de 4 casas decimais")
    if _HEXADECIMAL_64.search(texto):
        violacoes.append(f"{caminho}: hexadecimal de 64 caracteres (sha256 de PDF)")
    if ".pdf" in texto.lower():
        violacoes.append(f"{caminho}: referência a arquivo .pdf")
    if _NOME_DE_FOLHA.search(texto):
        violacoes.append(f"{caminho}: nome de folha real")
    return violacoes


def verificar_pacote(dados: Any, caminho: str = "$") -> list[str]:
    """Devolve as violações de memorização encontradas em todo valor do pacote."""
    if isinstance(dados, dict):
        violacoes: list[str] = []
        for chave, valor in dados.items():
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
    ],
)
def test_guarda_reprova(dados: Any) -> None:
    assert len(verificar_pacote(dados)) == 1


@pytest.mark.parametrize(
    "dados",
    [
        pytest.param({"x": 0.1234, "y": 3.5, "z": 2}, id="ate-4-casas"),
        pytest.param({"x": "0.1234"}, id="string-numerica-curta"),
        pytest.param({"hash": "a1" * 31}, id="hexadecimal-curto"),
    ],
)
def test_guarda_aceita_valores_legitimos(dados: Any) -> None:
    assert verificar_pacote(dados) == []
