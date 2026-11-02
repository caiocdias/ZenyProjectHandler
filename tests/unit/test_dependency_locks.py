"""Coerência entre locks e manifestos para dependências com versão corrigida de segurança."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable
from pathlib import Path

import pytest
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
    """Leia os pinos ``nome==versão`` das linhas do próprio arquivo.

    Falha alto se o mesmo pacote for fixado em duas versões distintas no mesmo
    arquivo, para que um pino vulnerável não seja mascarado pelo seguinte.
    """
    pinos: dict[str, str] = {}
    for linha in lock.read_text(encoding="utf-8-sig").splitlines():
        texto = linha.split("#", 1)[0].strip()
        if not texto or texto.startswith("-"):
            continue
        sem_hash = re.split(r"\s--hash", texto.rstrip("\\").strip(), maxsplit=1)[0]
        requisito = Requirement(sem_hash)
        for especificador in requisito.specifier:
            if especificador.operator in {"==", "==="}:
                nome = canonicalize_name(requisito.name)
                anterior = pinos.setdefault(nome, especificador.version)
                if anterior != especificador.version:
                    raise ValueError(
                        f"{lock.name}: {nome} fixado em {anterior} e {especificador.version}"
                    )
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


def _pinos_abaixo_da_corrigida(locks: Iterable[Path]) -> list[str]:
    """Liste ``lock: nome==versão`` de todo pino abaixo da versão corrigida."""
    return [
        f"{lock.name}: {nome}=={versao}"
        for lock in locks
        for nome, versao in _pinos(lock).items()
        if nome in VERSOES_CORRIGIDAS and Version(versao) < Version(VERSOES_CORRIGIDAS[nome])
    ]


def _limites_invalidos(manifestos: Iterable[Path]) -> list[str]:
    """Liste requisitos que excluem a corrigida ou admitem a vulnerável."""
    problemas: list[str] = []
    for manifesto in manifestos:
        if not manifesto.exists():
            continue
        for requisito in _requisitos_de_manifesto(manifesto):
            nome = canonicalize_name(requisito.name)
            if nome not in VERSOES_CORRIGIDAS:
                continue
            if not requisito.specifier.contains(VERSOES_CORRIGIDAS[nome], prereleases=True):
                problemas.append(f"{manifesto.name}: {requisito} exclui a corrigida")
            vulneravel = VERSOES_VULNERAVEIS.get(nome)
            if vulneravel is not None and requisito.specifier.contains(
                vulneravel, prereleases=True
            ):
                problemas.append(f"{manifesto.name}: {requisito} admite a vulnerável")
    return problemas


def test_locks_nao_fixam_versao_abaixo_da_corrigida() -> None:
    assert _pinos_abaixo_da_corrigida(LOCKS) == []


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
    assert _limites_invalidos(MANIFESTOS) == []


# --- Guardas contra teste vazio e contra tabelas incoerentes ---


def test_descoberta_encontra_locks_e_manifestos_reais() -> None:
    assert LOCKS, "nenhum requirements*.lock encontrado: a guarda passaria vazia"
    assert sum(len(_pinos(lock)) for lock in LOCKS) > 0
    assert (ROOT / "pyproject.toml") in MANIFESTOS
    assert (ROOT / "pyproject.toml").exists()


def test_lock_do_servidor_fixa_cada_pacote_corrigido_ja_registrado() -> None:
    pinos = _pinos(ROOT / "requirements-server.lock")
    for nome in ("pillow", "mako"):
        assert pinos.get(nome) == VERSOES_CORRIGIDAS[nome]


def test_manifesto_raiz_declara_pillow_para_o_teste_de_limites_nao_ficar_vazio() -> None:
    nomes = {
        canonicalize_name(requisito.name)
        for requisito in _requisitos_de_manifesto(ROOT / "pyproject.toml")
    }
    assert "pillow" in nomes


def test_tabelas_de_versoes_sao_coerentes() -> None:
    assert set(VERSOES_VULNERAVEIS) <= set(VERSOES_CORRIGIDAS)
    for nome, vulneravel in VERSOES_VULNERAVEIS.items():
        assert Version(vulneravel) < Version(VERSOES_CORRIGIDAS[nome]), nome
    for nome in (*VERSOES_CORRIGIDAS, *VERSOES_VULNERAVEIS):
        assert nome == canonicalize_name(nome), f"{nome} não está na forma canônica"


# --- Ataques ao parser e às asserções com arquivos sintéticos ---


def _lock_sintetico(tmp_path: Path, conteudo: str) -> Path:
    lock = tmp_path / "requirements-sintetico.lock"
    lock.write_bytes(conteudo.encode("utf-8"))
    return lock


@pytest.mark.parametrize(
    "linha",
    [
        "pillow==12.2.0",
        "PILLOW==12.2.0",
        "Pillow == 12.2.0",
        "  Pillow==12.2.0   ",
        "Pillow==12.2.0  # CVE conhecida",
        'Pillow==12.2.0 ; python_version >= "3.11"',
        'Pillow==12.2.0; sys_platform == "win32"  # marcador e comentário',
        "Pillow[tests]==12.2.0",
        "Pillow===12.2.0",
        "Pillow==12.2.0 --hash=sha256:abc",
        "Pillow==12.2.0 \\\n    --hash=sha256:abc\n    --hash=sha256:def",
        "Pillow==12.2.0\t--hash=sha256:abc",
    ],
)
def test_guarda_pega_pillow_vulneravel_em_qualquer_grafia_de_pino(
    tmp_path: Path, linha: str
) -> None:
    lock = _lock_sintetico(tmp_path, f"alembic==1.18.5\n{linha}\nmako==1.4.2\n")

    assert _pinos(lock) == {"alembic": "1.18.5", "pillow": "12.2.0", "mako": "1.4.2"}
    assert _pinos_abaixo_da_corrigida([lock]) == [f"{lock.name}: pillow==12.2.0"]


def test_guarda_pega_pino_vulneravel_em_lock_com_bom_e_crlf(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-bom.lock"
    lock.write_bytes("﻿Mako==1.3.12\r\nPillow==13.0.0\r\n".encode())

    assert _pinos(lock) == {"mako": "1.3.12", "pillow": "13.0.0"}
    assert _pinos_abaixo_da_corrigida([lock]) == [f"{lock.name}: mako==1.3.12"]


def test_nome_com_underscore_ou_ponto_vira_forma_canonica(tmp_path: Path) -> None:
    lock = _lock_sintetico(tmp_path, "Py_MuPDF.x==1.0\n")

    assert _pinos(lock) == {"py-mupdf-x": "1.0"}


def test_pino_corrigido_ou_maior_nao_e_apontado(tmp_path: Path) -> None:
    lock = _lock_sintetico(tmp_path, "Pillow==13.0.0\nMako==1.4.3\n")

    assert _pinos_abaixo_da_corrigida([lock]) == []


def test_pino_duplicado_com_versoes_diferentes_nao_e_mascarado(tmp_path: Path) -> None:
    lock = _lock_sintetico(
        tmp_path,
        'Pillow==12.2.0 ; python_version < "3.12"\nPillow==13.0.0 ; python_version >= "3.12"\n',
    )

    with pytest.raises(ValueError, match="pillow"):
        _pinos(lock)


def test_pino_duplicado_com_a_mesma_versao_e_aceito(tmp_path: Path) -> None:
    lock = _lock_sintetico(tmp_path, "Pillow==13.0.0\nPillow==13.0.0\n")

    assert _pinos(lock) == {"pillow": "13.0.0"}


def test_pinos_ignoram_comentarios_branco_e_inclusoes(tmp_path: Path) -> None:
    lock = _lock_sintetico(
        tmp_path, "# Pillow==12.2.0\n\n-r outro.lock\n--index-url https://x\nmako==1.4.2\n"
    )

    assert _pinos(lock) == {"mako": "1.4.2"}


def test_pinos_de_lock_vazio_ou_so_com_comentarios_e_vazio(tmp_path: Path) -> None:
    assert _pinos(_lock_sintetico(tmp_path, "")) == {}
    assert _pinos(_lock_sintetico(tmp_path, "# nada\n\n")) == {}


def _manifesto_sintetico(
    tmp_path: Path, dependencias: str, extras: str = "", build: str = ""
) -> Path:
    manifesto = tmp_path / "pyproject.toml"
    manifesto.write_text(
        f"[build-system]\nrequires = [{build}]\n"
        f"[project]\nname = 'x'\nversion = '1'\ndependencies = [{dependencias}]\n"
        f"[project.optional-dependencies]\ng = [{extras}]\n",
        encoding="utf-8",
    )
    return manifesto


@pytest.mark.parametrize(
    "requisito",
    [
        "Pillow>=12.2,<13",
        "Pillow>=12.2",
        "Pillow>=12",
        "Pillow",
        "Pillow<14",
        "Pillow!=13.0.0",
        "pillow ~= 12.2",
        "Pillow>=12.2,<14",
        "Pillow==12.2.0",
    ],
)
def test_guarda_pega_limite_que_admite_a_vulneravel_ou_exclui_a_corrigida(
    tmp_path: Path, requisito: str
) -> None:
    manifesto = _manifesto_sintetico(tmp_path, f'"{requisito}"')

    assert _limites_invalidos([manifesto]) != []


@pytest.mark.parametrize(
    "requisito",
    ["Pillow>=13.0,<14", "pillow>=13.0.0,<14", "Pillow ==13.0.0", "Pillow>=13.0.0"],
)
def test_guarda_aceita_limite_correto(tmp_path: Path, requisito: str) -> None:
    manifesto = _manifesto_sintetico(tmp_path, f'"{requisito}"')

    assert _limites_invalidos([manifesto]) == []


def test_guarda_olha_extras_e_build_system_alem_das_dependencias(tmp_path: Path) -> None:
    extra = _manifesto_sintetico(tmp_path, '"outra>=1"', extras='"Pillow>=12.2,<13"')
    assert len(_limites_invalidos([extra])) == 2

    build = _manifesto_sintetico(tmp_path, "", build='"Mako<1.4"')
    assert len(_limites_invalidos([build])) == 2


def test_guarda_olha_requisito_com_marcador_de_ambiente(tmp_path: Path) -> None:
    manifesto = _manifesto_sintetico(tmp_path, "\"Pillow>=12.2,<13; sys_platform == 'win32'\"")

    assert len(_limites_invalidos([manifesto])) == 2


def test_guarda_ignora_pacote_fora_da_tabela_e_manifesto_ausente(tmp_path: Path) -> None:
    manifesto = _manifesto_sintetico(tmp_path, '"requests>=1"')

    assert _limites_invalidos([manifesto, tmp_path / "nao-existe.toml"]) == []


def test_requisitos_de_manifesto_lista_build_dependencias_e_todos_os_extras(
    tmp_path: Path,
) -> None:
    manifesto = tmp_path / "pyproject.toml"
    manifesto.write_text(
        "[build-system]\nrequires = ['setuptools>=1']\n"
        "[project]\nname = 'x'\nversion = '1'\ndependencies = ['a>=1']\n"
        "[project.optional-dependencies]\nd = ['b>=2']\ne = ['c>=3', 'd>=4']\n",
        encoding="utf-8",
    )

    nomes = [requisito.name for requisito in _requisitos_de_manifesto(manifesto)]

    assert sorted(nomes) == ["a", "b", "c", "d", "setuptools"]
