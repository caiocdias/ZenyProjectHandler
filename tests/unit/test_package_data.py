from __future__ import annotations

import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _package_data(caminho: Path) -> dict[str, list[str]]:
    dados = tomllib.loads(caminho.read_text(encoding="utf-8"))
    return dict(dados["tool"]["setuptools"]["package-data"])


def test_package_data_do_servidor_cobre_o_da_raiz() -> None:
    raiz = _package_data(RAIZ / "pyproject.toml")
    servidor = _package_data(RAIZ / "server" / "pyproject.toml")
    esperados = {
        chave: padroes
        for chave, padroes in raiz.items()
        if chave.startswith("zeny_project_handler.")
    }
    assert esperados
    for chave, padroes in esperados.items():
        assert servidor.get(chave) == padroes, chave
    assert "zeny_project_handler.adapters.analysis.data" in servidor
    assert "zeny_project_handler.adapters.analysis.symbol_packages" in servidor
