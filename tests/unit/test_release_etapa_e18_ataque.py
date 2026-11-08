from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from scripts import build_release
from scripts.build_release import ReleaseBuildError, _render_server_environment, _validate_version

ROOT = Path(__file__).resolve().parents[2]
NOME = "ZENY_SERVER_SYMBOL_COMPOSITION"


def _versao_do_produto() -> str:
    dados = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(dados["project"]["version"])


def _texto(*partes: str) -> str:
    return (ROOT.joinpath(*partes)).read_text(encoding="utf-8")


def _padrao_compose(arquivo: Path) -> str:
    achado = re.search(
        rf'{NOME}:\s*"\$\{{{NOME}:-([^}}]*)\}}"', arquivo.read_text(encoding="utf-8")
    )
    assert achado is not None, f"{arquivo.name} não declara {NOME}"
    return achado.group(1)


@pytest.mark.parametrize(
    ("caminho", "padrao"),
    [
        (("src", "zeny_project_handler", "__init__.py"), r'__version__\s*=\s*"([^"]+)"'),
        (("src", "zeny_project_handler_client", "__init__.py"), r'__version__\s*=\s*"([^"]+)"'),
        (
            ("src", "zeny_project_handler_server", "composition.py"),
            r'except PackageNotFoundError:\s*return "([^"]+)"',
        ),
        (("Dockerfile",), r"ARG ZENY_RELEASE_VERSION=(\S+)"),
        (("scripts", "build_client.py"), r'DEFAULT_VERSION\s*=\s*"([^"]+)"'),
        (("README.md",), r"build_release\.py --version (\S+)"),
        (("CLAUDE.md",), r"build_release\.py --version (\S+)"),
        (("docs", "especificacao-funcional.md"), r"\| Pacote Python \| `([^`]+)`"),
    ],
    ids=lambda v: "/".join(v) if isinstance(v, tuple) else "padrao",
)
def test_versao_declarada_em_cada_ponto_e_a_do_pyproject(
    caminho: tuple[str, ...], padrao: str
) -> None:
    achado = re.search(padrao, _texto(*caminho))
    assert achado is not None, f"{'/'.join(caminho)} não declara a versão"
    assert achado.group(1) == _versao_do_produto()


def test_validate_version_aceita_a_versao_real_dos_tres_pyproject_sem_stub() -> None:
    _validate_version(_versao_do_produto())


def test_validate_version_recusa_versao_diferente_da_real() -> None:
    with pytest.raises(ReleaseBuildError, match="diverge dos manifestos"):
        _validate_version("9.9.9")


@pytest.mark.parametrize(
    "divergente", ["pyproject.toml", "client/pyproject.toml", "server/pyproject.toml"]
)
def test_validate_version_nomeia_o_manifesto_divergente(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, divergente: str
) -> None:
    for relativo in ("pyproject.toml", "client/pyproject.toml", "server/pyproject.toml"):
        alvo = tmp_path / relativo
        alvo.parent.mkdir(parents=True, exist_ok=True)
        versao = "0.5.0" if relativo == divergente else "0.6.0"
        alvo.write_text(f'[project]\nname = "x"\nversion = "{versao}"\n', encoding="utf-8")
    monkeypatch.setattr(build_release, "ROOT", tmp_path)
    with pytest.raises(ReleaseBuildError) as erro:
        _validate_version("0.6.0")
    mensagem = str(erro.value)
    assert Path(divergente).as_posix().replace("/", "\\") in mensagem or divergente in mensagem
    assert mensagem.count("=0.5.0") == 1


def test_ambiente_renderizado_do_kit_mantem_a_opcao_desligada_uma_vez(tmp_path: Path) -> None:
    destino = tmp_path / ".env-example"
    _render_server_environment("zeny-project-handler-server:0.6.0", destino)
    linhas = destino.read_text(encoding="utf-8").splitlines()
    assert linhas.count(f"{NOME}=false") == 1
    assert [linha for linha in linhas if linha.startswith(NOME)] == [f"{NOME}=false"]
    assert "@ZENY_SERVER_IMAGE@" not in "\n".join(linhas)


def test_ambiente_renderizado_nao_tem_retorno_de_carro(tmp_path: Path) -> None:
    destino = tmp_path / ".env-example"
    _render_server_environment("zeny-project-handler-server:0.6.0", destino)
    assert b"\r" not in destino.read_bytes()


def test_padrao_da_opcao_concorda_entre_compose_de_release_compose_do_repo_e_exemplo() -> None:
    exemplo = {
        linha.partition("=")[0]: linha.partition("=")[2]
        for linha in _texto("server", "env.release.example").splitlines()
        if "=" in linha and not linha.startswith("#")
    }
    assert exemplo[NOME] == "false"
    assert _padrao_compose(ROOT / "server" / "compose.release.yaml") == "false"
    assert _padrao_compose(ROOT / "compose.yaml") == "false"
    assert _padrao_compose(ROOT / "compose.local.yaml") == "false"


def test_valor_do_exemplo_e_aceito_pela_configuracao_do_servidor_como_desligado() -> None:
    from zeny_project_handler_server.config import _boolean_setting

    assert _boolean_setting({NOME: "false"}, NOME) is False


def test_guia_do_servidor_diz_o_mesmo_padrao_do_exemplo() -> None:
    guia = " ".join(_texto("server", "LEIA-ME-SERVIDOR.md").split())
    assert f"`{NOME}`" in guia
    assert "desligada por padrão (`false`)" in guia
