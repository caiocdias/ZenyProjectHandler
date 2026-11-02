"""Coerência entre locks e manifestos para dependências com versão corrigida de segurança."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
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

VERSOES_CORRIGIDAS = {
    "pillow": "13.0.0",
    "mako": "1.4.2",
    "httpx2": "2.12.0",
    "httpcore2": "2.12.0",
    "pytest": "9.0.3",
}
VERSOES_VULNERAVEIS = {"pillow": "12.2.0", "mako": "1.3.12", "httpx2": "2.10.0", "pytest": "8.4.2"}


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


def test_pywinauto_sem_uso_fora_do_ambiente() -> None:
    """pywinauto não é importado pelo projeto (E13); comtypes e pywin32 só entravam por ele."""
    for lock in LOCKS:
        assert "pywinauto" not in _pinos(lock)
    for manifesto in MANIFESTOS:
        assert all(
            canonicalize_name(r.name) != "pywinauto" for r in _requisitos_de_manifesto(manifesto)
        )


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


# --- Task 2 (E13): ferramentas de desenvolvimento, pywinauto e pytest 9 ---


def test_httpx2_e_httpcore2_tem_a_mesma_versao_em_todos_os_locks() -> None:
    """httpx2 exige ``httpcore2==<mesma versão>``: divergir quebra a instalação."""
    for lock in LOCKS:
        pinos = _pinos(lock)
        if "httpx2" in pinos or "httpcore2" in pinos:
            assert pinos.get("httpx2") == pinos.get("httpcore2"), (
                f"{lock.name}: httpx2={pinos.get('httpx2')} httpcore2={pinos.get('httpcore2')}"
            )


def test_httpcore2_corrigida_acompanha_a_httpx2_corrigida() -> None:
    assert VERSOES_CORRIGIDAS["httpcore2"] == VERSOES_CORRIGIDAS["httpx2"]


def test_lock_de_desenvolvimento_fixa_as_ferramentas_corrigidas() -> None:
    pinos = _pinos(ROOT / "requirements-development.lock")
    for nome in ("httpx2", "httpcore2", "pytest"):
        assert pinos.get(nome) == VERSOES_CORRIGIDAS[nome], nome


def test_extra_dev_do_manifesto_raiz_limita_httpx2_e_pytest_na_corrigida() -> None:
    dados = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requisitos = {
        str(canonicalize_name(r.name)): r
        for r in map(Requirement, dados["project"]["optional-dependencies"]["dev"])
    }
    for nome in ("httpx2", "pytest"):
        assert nome in requisitos, f"{nome} sumiu do extra dev"
        assert requisitos[nome].specifier.contains(VERSOES_CORRIGIDAS[nome])
        assert not requisitos[nome].specifier.contains(VERSOES_VULNERAVEIS[nome])


@pytest.mark.parametrize("nome", ["pywinauto", "comtypes", "pywin32"])
def test_pacotes_do_pywinauto_nao_aparecem_em_nenhum_lock_nem_nao_fixados(nome: str) -> None:
    """Varre o texto bruto: pega também linhas sem ``==`` que ``_pinos`` ignora."""
    for lock in LOCKS:
        for linha in lock.read_text(encoding="utf-8-sig").splitlines():
            texto = linha.split("#", 1)[0].strip()
            if not texto or texto.startswith("-"):
                continue
            assert canonicalize_name(re.split(r"[\s\[<>=!~;]", texto, maxsplit=1)[0]) != nome, (
                f"{lock.name}: {linha}"
            )


def test_pywinauto_nao_aparece_em_nenhuma_secao_de_nenhum_manifesto() -> None:
    """Olha o TOML inteiro (dependências, extras, build): qualquer string citando o pacote."""
    for manifesto in MANIFESTOS:
        if not manifesto.exists():
            continue
        dados = tomllib.loads(manifesto.read_text(encoding="utf-8"))
        textos = re.findall(r"pywinauto", repr(dados), flags=re.IGNORECASE)
        assert textos == [], f"{manifesto}: cita pywinauto"


def test_nome_de_pacote_pywin32_ctypes_nao_e_confundido_com_pywin32(tmp_path: Path) -> None:
    lock = _lock_sintetico(tmp_path, "pywin32-ctypes==0.2.3\n")

    assert "pywin32" not in _pinos(lock)


def test_pytest_instalado_no_ambiente_e_o_corrigido() -> None:
    assert Version(pytest.__version__) >= Version(VERSOES_CORRIGIDAS["pytest"])


def _rodar_pytest_com_a_config_do_projeto(
    tmp_path: Path,
    teste: str,
    *,
    sem_chaves: tuple[str, ...] = (),
    sem_flags_strict: bool = False,
    sem_filtros_de_marcador: bool = False,
    extras: dict[str, object] | None = None,
) -> tuple[int, str]:
    """Copie ``[tool.pytest.ini_options]`` real (menos ``testpaths``) e rode um teste isolado.

    Os parâmetros ``sem_*`` removem partes da configuração para provar que o mecanismo
    testado é de fato o que protege; ``extras`` acrescenta chaves ao ini.
    """
    dados = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    opcoes = dict(dados["tool"]["pytest"]["ini_options"])
    opcoes.pop("testpaths", None)
    for chave in sem_chaves:
        opcoes.pop(chave, None)
    if sem_flags_strict:
        opcoes["addopts"] = " ".join(
            a for a in opcoes["addopts"].split() if a not in {"--strict-markers", "--strict-config"}
        )
    if sem_filtros_de_marcador:
        opcoes["filterwarnings"] = [f for f in opcoes["filterwarnings"] if "UnknownMark" not in f]
    opcoes.update(extras or {})
    linhas = ["[tool.pytest.ini_options]"]
    linhas.extend(f"{chave} = {json.dumps(valor)}" for chave, valor in opcoes.items())
    (tmp_path / "pyproject.toml").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    (tmp_path / "test_alvo.py").write_text(teste, encoding="utf-8")
    ambiente = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    resultado = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "test_alvo.py"],
        cwd=tmp_path,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return resultado.returncode, resultado.stdout + resultado.stderr


def test_config_do_projeto_rejeita_marcador_nao_registrado_sob_o_pytest_atual(
    tmp_path: Path,
) -> None:
    codigo, saida = _rodar_pytest_com_a_config_do_projeto(
        tmp_path,
        "import pytest\n\n@pytest.mark.marcador_inexistente\ndef test_a():\n    pass\n",
    )

    assert codigo != 0, saida
    assert "marcador_inexistente" in saida


def test_config_do_projeto_transforma_resourcewarning_em_falha(tmp_path: Path) -> None:
    codigo, saida = _rodar_pytest_com_a_config_do_projeto(
        tmp_path,
        "import gc\n\n"
        "def test_a(tmp_path):\n"
        "    arquivo = open(tmp_path / 'x', 'w')\n"
        "    del arquivo\n"
        "    gc.collect()\n",
    )

    assert codigo != 0, saida
    assert "ResourceWarning" in saida


def test_config_do_projeto_transforma_excecao_nao_tratada_em_falha(tmp_path: Path) -> None:
    codigo, saida = _rodar_pytest_com_a_config_do_projeto(
        tmp_path,
        "import gc\n\n"
        "class Mau:\n"
        "    def __del__(self):\n"
        "        raise RuntimeError('boom no __del__')\n\n"
        "def test_a():\n"
        "    Mau()\n"
        "    gc.collect()\n",
    )

    assert codigo != 0, saida
    assert "PytestUnraisableExceptionWarning" in saida


def test_config_do_projeto_nao_emite_aviso_de_config_nem_de_depreciacao_do_pytest(
    tmp_path: Path,
) -> None:
    codigo, saida = _rodar_pytest_com_a_config_do_projeto(
        tmp_path, "def test_a():\n    assert True\n"
    )

    assert codigo == 0, saida
    assert "1 passed" in saida
    for aviso in ("PytestConfigWarning", "PytestRemovedIn", "PytestDeprecationWarning", "warnings"):
        assert aviso not in saida, saida


_TESTE_TRIVIAL = "def test_a():\n    pass\n"
_MARCADOR_DESCONHECIDO = "import pytest\n\n@pytest.mark.zzz\ndef test_a():\n    pass\n"


def test_strict_markers_do_ini_sozinho_rejeita_marcador_sem_flag_nem_filtro(
    tmp_path: Path,
) -> None:
    codigo, saida = _rodar_pytest_com_a_config_do_projeto(
        tmp_path, _MARCADOR_DESCONHECIDO, sem_flags_strict=True, sem_filtros_de_marcador=True
    )

    assert codigo != 0, saida
    assert "'zzz' not found" in saida


def test_filtro_de_marcador_sozinho_rejeita_marcador_sem_strict_markers(tmp_path: Path) -> None:
    codigo, saida = _rodar_pytest_com_a_config_do_projeto(
        tmp_path, _MARCADOR_DESCONHECIDO, sem_chaves=("strict_markers",), sem_flags_strict=True
    )

    assert codigo != 0, saida


def test_sem_strict_markers_flag_nem_filtro_marcador_desconhecido_so_avisa(
    tmp_path: Path,
) -> None:
    """Controle negativo: prova que os testes acima podem falhar."""
    codigo, saida = _rodar_pytest_com_a_config_do_projeto(
        tmp_path,
        _MARCADOR_DESCONHECIDO,
        sem_chaves=("strict_markers",),
        sem_flags_strict=True,
        sem_filtros_de_marcador=True,
    )

    assert codigo == 0, saida
    assert "PytestUnknownMarkWarning" in saida


def test_config_do_projeto_rejeita_chave_desconhecida_no_ini(tmp_path: Path) -> None:
    codigo, saida = _rodar_pytest_com_a_config_do_projeto(
        tmp_path, _TESTE_TRIVIAL, extras={"chave_inexistente_zzz": 1}
    )

    assert codigo != 0, saida
    assert "chave_inexistente_zzz" in saida


def test_strict_config_do_ini_sozinho_rejeita_chave_desconhecida(tmp_path: Path) -> None:
    codigo, saida = _rodar_pytest_com_a_config_do_projeto(
        tmp_path,
        _TESTE_TRIVIAL,
        sem_flags_strict=True,
        extras={"chave_inexistente_zzz": 1},
    )

    assert codigo != 0, saida


def test_sem_strict_config_chave_desconhecida_so_avisa(tmp_path: Path) -> None:
    """Controle negativo da guarda de ``strict_config``."""
    codigo, saida = _rodar_pytest_com_a_config_do_projeto(
        tmp_path,
        _TESTE_TRIVIAL,
        sem_chaves=("strict_config",),
        sem_flags_strict=True,
        extras={"chave_inexistente_zzz": 1},
    )

    assert codigo == 0, saida
