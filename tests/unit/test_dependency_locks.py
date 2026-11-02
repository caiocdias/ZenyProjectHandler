"""Coerência entre locks e manifestos para dependências com versão corrigida de segurança."""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[2]
LOCKS = sorted(ROOT.glob("requirements*.lock"))
MANIFESTOS = [
    ROOT / "pyproject.toml",
    ROOT / "server" / "pyproject.toml",
    ROOT / "client" / "pyproject.toml",
]

VERSOES_CORRIGIDAS = {"pillow": "13.0.0", "mako": "1.4.2"}
VERSOES_VULNERAVEIS = {"pillow": "12.2.0", "mako": "1.3.12"}


def _pinos(lock: Path) -> dict[str, str]:
    """Leia os pinos ``nome==versão`` das linhas do próprio arquivo."""
    pinos: dict[str, str] = {}
    for linha in lock.read_text(encoding="utf-8").splitlines():
        texto = linha.split("#", 1)[0].strip()
        if not texto or texto.startswith("-"):
            continue
        requisito = Requirement(texto.rstrip("\\").strip().split(" --hash", 1)[0])
        for especificador in requisito.specifier:
            if especificador.operator == "==":
                pinos[canonicalize_name(requisito.name)] = especificador.version
    return pinos


def _requisitos_de_manifesto(pyproject: Path) -> list[Requirement]:
    """Liste requisitos de build, de runtime e de todos os extras de um manifesto."""
    dados = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    textos: list[str] = list(dados.get("build-system", {}).get("requires", []))
    projeto = dados.get("project", {})
    textos.extend(projeto.get("dependencies", []))
    for extras in projeto.get("optional-dependencies", {}).values():
        textos.extend(extras)
    return [Requirement(texto) for texto in textos]


def test_locks_nao_fixam_versao_abaixo_da_corrigida() -> None:
    for lock in LOCKS:
        for nome, versao in _pinos(lock).items():
            if nome in VERSOES_CORRIGIDAS:
                assert Version(versao) >= Version(VERSOES_CORRIGIDAS[nome]), (
                    f"{lock.name}: {nome}=={versao}"
                )


def test_pacote_corrigido_tem_a_mesma_versao_em_todos_os_locks() -> None:
    for nome in VERSOES_CORRIGIDAS:
        versoes = {_pinos(lock)[nome] for lock in LOCKS if nome in _pinos(lock)}
        assert len(versoes) <= 1, f"{nome}: versões divergentes {sorted(versoes)}"


def test_todo_pacote_corrigido_esta_em_algum_lock_ou_manifesto() -> None:
    for nome in VERSOES_CORRIGIDAS:
        em_locks = any(nome in _pinos(lock) for lock in LOCKS)
        em_manifestos = any(
            canonicalize_name(requisito.name) == nome
            for manifesto in MANIFESTOS
            if manifesto.exists()
            for requisito in _requisitos_de_manifesto(manifesto)
        )
        assert em_locks or em_manifestos, f"{nome} não aparece em lock nem manifesto"


def test_limites_dos_manifestos_admitem_a_corrigida_e_excluem_a_vulneravel() -> None:
    for manifesto in MANIFESTOS:
        if not manifesto.exists():
            continue
        for requisito in _requisitos_de_manifesto(manifesto):
            nome = canonicalize_name(requisito.name)
            if nome in VERSOES_CORRIGIDAS:
                assert requisito.specifier.contains(VERSOES_CORRIGIDAS[nome]), (
                    f"{manifesto.name}: {requisito}"
                )
                vulneravel = VERSOES_VULNERAVEIS.get(nome)
                if vulneravel is not None:
                    assert not requisito.specifier.contains(vulneravel), (
                        f"{manifesto.name}: {requisito}"
                    )
