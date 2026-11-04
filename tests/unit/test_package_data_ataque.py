from __future__ import annotations

import tomllib
from importlib.resources import files
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SRC = RAIZ / "src"
PREFIXO = "zeny_project_handler."


def _package_data(caminho: Path) -> dict[str, list[str]]:
    dados = tomllib.loads(caminho.read_text(encoding="utf-8"))
    return dict(dados["tool"]["setuptools"]["package-data"])


def _pacotes_do_nucleo(package_data: dict[str, list[str]]) -> list[str]:
    return [chave for chave in package_data if chave.startswith(PREFIXO)]


def test_servidor_nao_declara_pacote_do_nucleo_ausente_na_raiz() -> None:
    raiz = _package_data(RAIZ / "pyproject.toml")
    servidor = _package_data(RAIZ / "server" / "pyproject.toml")
    assert sorted(_pacotes_do_nucleo(servidor)) == sorted(_pacotes_do_nucleo(raiz))


@pytest.mark.parametrize("pyproject", ["pyproject.toml", "server/pyproject.toml"])
def test_cada_entrada_de_package_data_aponta_para_pacote_real_com_arquivos(
    pyproject: str,
) -> None:
    for chave, padroes in _package_data(RAIZ / pyproject).items():
        if chave.startswith("zeny_project_handler_client"):
            continue
        pasta = SRC.joinpath(*chave.split("."))
        assert (pasta / "__init__.py").is_file(), f"{chave} não é pacote (falta __init__.py)"
        for padrao in padroes:
            assert list(pasta.glob(padrao)), f"{chave}: padrão {padrao!r} não casa arquivo algum"


@pytest.mark.parametrize("pyproject", ["pyproject.toml", "server/pyproject.toml"])
def test_toda_pasta_de_pacote_com_json_esta_declarada_no_package_data(pyproject: str) -> None:
    declarados = set(_package_data(RAIZ / pyproject))
    sem_declaracao = []
    for arquivo in (SRC / "zeny_project_handler").rglob("*.json"):
        if "__pycache__" in arquivo.parts:
            continue
        pacote = ".".join(arquivo.parent.relative_to(SRC).parts)
        if pacote not in declarados:
            sem_declaracao.append(f"{pacote}/{arquivo.name}")
    assert not sem_declaracao, sem_declaracao


def test_tabela_de_glifos_e_declarada_nos_dois_pyproject_com_padrao_json() -> None:
    chave = "zeny_project_handler.adapters.analysis.data"
    for pyproject in ("pyproject.toml", "server/pyproject.toml"):
        padroes = _package_data(RAIZ / pyproject)[chave]
        pasta = SRC.joinpath(*chave.split("."))
        casados = {p.name for padrao in padroes for p in pasta.glob(padrao)}
        assert "tabela-glifos-v1.json" in casados, pyproject


def test_pacote_de_dados_dos_glifos_e_encontrado_como_recurso() -> None:
    recurso = files("zeny_project_handler.adapters.analysis.data").joinpath("tabela-glifos-v1.json")
    assert recurso.is_file()
