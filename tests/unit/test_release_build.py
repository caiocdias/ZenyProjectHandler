from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from scripts import build_release
from scripts.build_client import _pyinstaller_environment
from scripts.build_release import (
    ReleaseBuildError,
    _commit_de_origem,
    _fatos_do_produto,
    _FatosProduto,
    _render_server_environment,
    _validate_version,
    _write_release_notes,
    _write_sha256s,
)
from scripts.release_artifact_gate import _validate_sha256s

from zeny_project_handler.adapters.analysis.pymupdf_analyzer import PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.interpretation.rule_based import InterpretadorRegrasExplicitas
from zeny_project_handler.application.compliance_analysis import VERSAO_METODO_CONFORMIDADE
from zeny_project_handler_contracts.versioning import API_VERSION, MIN_COMPATIBLE_API_VERSION

ROOT = Path(__file__).resolve().parents[2]
SEED = Path("src/zeny_project_handler/adapters/compliance/data/regras_conformidade_v1.json")
FATOS = _FatosProduto("9.8.7", "6.5", "4", "registro-x", 3)
COMMIT = "a" * 40


def _notas(tmp_path: Path) -> str:
    destination = tmp_path / "RELEASE_NOTES.md"
    _write_release_notes(destination, "0.6.0", "zeny-server:0.6.0", "sha256:fixture", COMMIT, FATOS)
    return " ".join(destination.read_text(encoding="utf-8").split())


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repositorio(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Teste")
    _git(path, "config", "user.email", "teste@example.com")
    (path / "a.txt").write_text("a", encoding="utf-8")
    _git(path, "add", "a.txt")
    _git(path, "commit", "-q", "-m", "inicial")
    return path


def test_release_notes_declare_current_api_and_acceptance_limits(tmp_path: Path) -> None:
    notes = _notas(tmp_path)
    assert f"API: `{API_VERSION}`" in notes
    assert f"faixa compatível `{MIN_COMPATIBLE_API_VERSION}`" in notes
    assert "ainda não está homologado" in notes


def test_notas_citam_commit_e_versoes_recebidas(tmp_path: Path) -> None:
    notes = _notas(tmp_path)
    assert COMMIT in notes
    assert "9.8.7" in notes
    assert "6.5" in notes
    assert "método de conformidade 4" in notes
    assert "registro-x" in notes
    assert "3 regras habilitadas" in notes


def test_notas_dizem_que_a_leitura_vetorial_vem_desligada(tmp_path: Path) -> None:
    notes = _notas(tmp_path)
    assert "ZENY_SERVER_SYMBOL_COMPOSITION" in notes
    assert "desligada por padrão" in notes


def test_notas_nao_trazem_numero_de_versao_escrito_a_mao(tmp_path: Path) -> None:
    notes = _notas(tmp_path)
    for antigo in ("1.18.0", "25.0", "42 regras"):
        assert antigo not in notes


def test_fatos_do_produto_leem_as_versoes_do_codigo() -> None:
    fatos = _fatos_do_produto()
    assert fatos.versao_extracao == PyMuPdfDocumentAnalyzer.versao
    assert fatos.versao_interpretacao == InterpretadorRegrasExplicitas.versao
    assert fatos.metodo_conformidade == VERSAO_METODO_CONFORMIDADE


def test_fatos_contam_so_regras_habilitadas(tmp_path: Path) -> None:
    payload = json.loads((ROOT / SEED).read_text(encoding="utf-8"))
    total = len(payload["rules"])
    payload["rules"][0]["enabled"] = False
    copia = tmp_path / SEED
    copia.parent.mkdir(parents=True)
    copia.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    fatos = _fatos_do_produto(tmp_path)

    assert fatos.regras_habilitadas == total - 1
    assert fatos.registro_conformidade == payload["registry"]["version"]


def test_commit_de_origem_recusa_arvore_suja(tmp_path: Path) -> None:
    repo = _repositorio(tmp_path / "repo")
    (repo / "novo.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ReleaseBuildError, match="árvore suja"):
        _commit_de_origem(repo)


def test_commit_de_origem_devolve_head_do_root_e_nao_do_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primeiro = _repositorio(tmp_path / "primeiro")
    segundo = _repositorio(tmp_path / "segundo")
    (segundo / "b.txt").write_text("b", encoding="utf-8")
    _git(segundo, "add", "b.txt")
    _git(segundo, "commit", "-q", "-m", "segundo")
    monkeypatch.chdir(segundo)

    assert _commit_de_origem(primeiro) == _git(primeiro, "rev-parse", "HEAD")


def test_commit_de_origem_sem_repositorio_da_erro_acionavel(tmp_path: Path) -> None:
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    with pytest.raises(ReleaseBuildError, match="não foi possível obter o commit"):
        _commit_de_origem(vazio)


def test_commit_de_origem_sem_git_instalado_da_erro_acionavel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def sem_git(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", sem_git)
    with pytest.raises(ReleaseBuildError, match="não foi possível obter o commit"):
        _commit_de_origem(tmp_path)


def test_build_recusa_arvore_suja_antes_de_gastar_build(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def suja(root: Path = ROOT) -> str:
        raise ReleaseBuildError("árvore suja")

    def nao_deve_rodar(*args: object, **kwargs: object) -> None:
        pytest.fail("o build não pode começar com a árvore suja")

    monkeypatch.setattr(build_release, "_commit_de_origem", suja)
    monkeypatch.setattr(build_release, "_reset_directory", nao_deve_rodar)
    monkeypatch.setattr(build_release, "_run", nao_deve_rodar)
    monkeypatch.setattr(sys, "argv", ["build_release.py", "--version", "0.6.0"])

    assert build_release.main() == 1
    assert "BUILD DE RELEASE: REPROVADO" in capsys.readouterr().out


def _prepara_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, commits: object
) -> tuple[Path, Path]:
    """Isola build_release em tmp_path; devolve (output_root, sentinela do destino)."""
    version = "0.6.0"
    monkeypatch.setattr(build_release, "ROOT", tmp_path)
    monkeypatch.setattr(build_release, "_validate_version", lambda _version: None)
    monkeypatch.setattr(build_release, "_garantir_pacote_do_checkout", lambda: None)
    monkeypatch.setattr(build_release, "_commit_de_origem", commits)
    monkeypatch.setattr(build_release, "_fatos_do_produto", lambda root=tmp_path: FATOS)
    monkeypatch.setattr(build_release, "_reset_directory", lambda path: None)
    monkeypatch.setattr(build_release, "_run", lambda *command: None)
    monkeypatch.setattr(build_release, "_image_metadata", lambda image, v: {"Id": "sha256:x"})
    monkeypatch.setattr(build_release, "_render_server_environment", lambda *args: None)
    monkeypatch.setattr(build_release, "_render_server_guide", lambda *args: None)
    monkeypatch.setattr(build_release, "_server_sbom", lambda *args: {})
    monkeypatch.setattr(shutil, "copy2", lambda *args, **kwargs: None)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    wheel = tmp_path / "build" / "release" / version / "client-artifacts" / version / "wheel"
    wheel.mkdir(parents=True)
    (wheel / "zeny_project_handler_client-0.6.0-py3-none-any.whl").write_bytes(b"")
    saida = tmp_path / "saida"
    sentinela = saida / version / "sentinela.txt"
    sentinela.parent.mkdir(parents=True)
    sentinela.write_text("fica", encoding="utf-8")
    return saida, sentinela


def _executa_build(saida: Path) -> None:
    build_release.build_release("0.6.0", output_root=saida, image_repository="zeny")


def test_build_reprova_se_o_head_muda_durante_o_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shas = iter(["a" * 40, "b" * 40])
    saida, sentinela = _prepara_build(tmp_path, monkeypatch, lambda root=tmp_path: next(shas))

    with pytest.raises(ReleaseBuildError, match="mudou durante o build"):
        _executa_build(saida)

    assert sentinela.read_text(encoding="utf-8") == "fica"


def test_build_reprova_se_a_arvore_suja_na_segunda_conferencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas: list[int] = []

    def commit(root: Path = tmp_path) -> str:
        chamadas.append(1)
        if len(chamadas) > 1:
            raise ReleaseBuildError("árvore suja")
        return "a" * 40

    saida, sentinela = _prepara_build(tmp_path, monkeypatch, commit)

    with pytest.raises(ReleaseBuildError, match="árvore suja"):
        _executa_build(saida)

    assert sentinela.read_text(encoding="utf-8") == "fica"


def test_troca_do_destino_restaura_o_anterior_se_o_move_falha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saida, sentinela = _prepara_build(tmp_path, monkeypatch, lambda root=tmp_path: "a" * 40)

    def move_falha(origem: str, destino: str) -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr(shutil, "move", move_falha)

    with pytest.raises(ReleaseBuildError):
        _executa_build(saida)

    assert sentinela.read_text(encoding="utf-8") == "fica"
    assert not (saida / "0.6.0.anterior").exists()


def test_troca_do_destino_com_sucesso_nao_deixa_anterior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saida, sentinela = _prepara_build(tmp_path, monkeypatch, lambda root=tmp_path: "a" * 40)
    (saida / "0.6.0.anterior").mkdir()

    _executa_build(saida)

    assert not (saida / "0.6.0.anterior").exists()
    assert not sentinela.exists()
    assert (saida / "0.6.0" / "release-manifest.json").is_file()


def test_build_recusa_pacote_fora_do_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def nao_deve_rodar(*args: object, **kwargs: object) -> None:
        pytest.fail("o build não pode começar com o pacote fora do checkout")

    monkeypatch.setattr(build_release, "ROOT", tmp_path)
    monkeypatch.setattr(build_release, "_validate_version", lambda _version: None)
    monkeypatch.setattr(build_release, "_reset_directory", nao_deve_rodar)
    monkeypatch.setattr(sys, "argv", ["build_release.py", "--version", "0.6.0"])

    with pytest.raises(ReleaseBuildError, match="fora do checkout"):
        _executa_build(tmp_path / "saida")
    assert build_release.main() == 1
    assert "fora do checkout" in capsys.readouterr().out


def test_notas_nao_trazem_afirmacoes_sem_prova(tmp_path: Path) -> None:
    notes = _notas(tmp_path)
    assert "a leitura de símbolos é a mesma" not in notes
    assert "o método novo não é executado" in notes
    assert "sem vulnerabilidade corrigível conhecida" not in notes
    assert "não têm vulnerabilidade conhecida na varredura desta release" in notes


def test_titulo_das_mudancas_usa_a_versao_anterior(tmp_path: Path) -> None:
    assert f"O que mudou desde a {build_release.VERSAO_ANTERIOR}" in _notas(tmp_path)


def test_versao_anterior_difere_da_versao_do_produto() -> None:
    declarada = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    assert declarada != build_release.VERSAO_ANTERIOR


def test_pyinstaller_build_environment_excludes_external_dll_and_qt_paths() -> None:
    environment = _pyinstaller_environment(
        {
            "SYSTEMROOT": "C:/Windows",
            "PATH": "C:/runtime/poppler;C:/runtime/ffmpeg",
            "PYTHONHOME": "C:/external-python",
            "PYTHONPATH": "C:/external-modules",
            "QML2_IMPORT_PATH": "C:/external-qml",
            "QT_PLUGIN_PATH": "C:/external-qt",
            "PRESERVED": "yes",
        }
    )

    assert environment["PATH"].split(";") == [
        "C:\\Windows\\System32",
        "C:\\Windows",
        "C:\\Windows\\System32\\Wbem",
    ]
    assert environment["PRESERVED"] == "yes"
    for name in ("PYTHONHOME", "PYTHONPATH", "QML2_IMPORT_PATH", "QT_PLUGIN_PATH"):
        assert name not in environment


def test_release_version_must_be_stable_semver_and_match_all_packages() -> None:
    _validate_version("0.6.0")

    for invalid in ("1", "1.0", "01.0.0", "1.0.0-rc.1", "v1.0.0", "0.4.1"):
        with pytest.raises(ReleaseBuildError):
            _validate_version(invalid)


def test_release_compose_is_image_only_and_server_environment_is_separate(tmp_path: Path) -> None:
    compose = (ROOT / "server" / "compose.release.yaml").read_text(encoding="utf-8")
    assert "image:" in compose
    assert "build:" not in compose
    assert "zeny-data:/data" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose

    destination = tmp_path / ".env-example"
    _render_server_environment("zeny-project-handler-server:0.1.0", destination)
    environment = destination.read_text(encoding="utf-8")
    assert "ZENY_SERVER_IMAGE=zeny-project-handler-server:0.1.0" in environment
    assert "ZENY_SERVER_PASSWORD=troque-por-uma-senha-longa-e-aleatoria" in environment
    assert (
        "ZENY_MARKET_SQLSERVER_CONNECTION_STRING=troque-por-uma-string-de-conexao-sql-server"
    ) in environment
    assert "ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS=15" in environment
    assert "ZENY_CLIENT" not in environment
    assert "@ZENY_SERVER_IMAGE@" not in environment


def test_release_sources_document_load_lifecycle_backup_and_rollback() -> None:
    guide = (ROOT / "server" / "LEIA-ME-SERVIDOR.md").read_text(encoding="utf-8").casefold()
    for requirement in (
        "docker load",
        "--no-build",
        "health",
        "firewall",
        "down -v",
        "backup",
        "atualizar",
        "rollback",
        "trocar a senha",
        "zeny_market_sqlserver_connection_string",
        "trustservercertificate=no",
        "select",
    ):
        assert requirement in guide
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "org.opencontainers.image.version" in dockerfile
    assert "ZENY_RELEASE_VERSION" in dockerfile


def test_sha256_index_covers_every_distributed_file_except_itself(tmp_path: Path) -> None:
    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "artifact.zip").write_bytes(b"cliente")
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(json.dumps({"release": "fixture"}), encoding="utf-8")

    _write_sha256s(tmp_path)
    actual = {
        path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file()
    }
    _validate_sha256s(tmp_path, actual)
    entries = (tmp_path / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert hashlib.sha256(b"cliente").hexdigest() in entries
    assert "client/artifact.zip" in entries
    assert "release-manifest.json" in entries
    assert "SHA256SUMS.txt" not in entries


def test_commit_de_origem_devolve_sha_completo_de_repositorio_limpo(tmp_path: Path) -> None:
    repo = _repositorio(tmp_path / "repo")
    commit = _commit_de_origem(repo)
    assert len(commit) == 40
    assert commit == _git(repo, "rev-parse", "HEAD")


def test_commit_de_origem_recusa_arquivo_rastreado_modificado(tmp_path: Path) -> None:
    repo = _repositorio(tmp_path / "repo")
    (repo / "a.txt").write_text("alterado", encoding="utf-8")
    with pytest.raises(ReleaseBuildError, match="árvore suja"):
        _commit_de_origem(repo)


def test_commit_de_origem_recusa_mudanca_so_no_indice(tmp_path: Path) -> None:
    repo = _repositorio(tmp_path / "repo")
    (repo / "b.txt").write_text("b", encoding="utf-8")
    _git(repo, "add", "b.txt")
    with pytest.raises(ReleaseBuildError, match="árvore suja"):
        _commit_de_origem(repo)


def test_commit_de_origem_em_repositorio_sem_commits_da_erro_acionavel(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    with pytest.raises(ReleaseBuildError, match="não foi possível obter o commit"):
        _commit_de_origem(repo)


def test_commit_de_origem_falha_do_git_no_status_vira_erro_acionavel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = subprocess.run

    def status_falha(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[1] == "status":
            return subprocess.CompletedProcess(command, 128, "", "fatal: índice corrompido")
        return real(command, **kwargs)  # type: ignore[no-any-return, call-overload]

    repo = _repositorio(tmp_path / "repo")
    monkeypatch.setattr(subprocess, "run", status_falha)
    with pytest.raises(ReleaseBuildError, match="não foi possível obter o commit"):
        _commit_de_origem(repo)


def test_commit_de_origem_executa_os_dois_comandos_git_no_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas: list[tuple[list[str], object]] = []
    real = subprocess.run

    def espiao(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        chamadas.append((command, kwargs.get("cwd")))
        return real(command, **kwargs)  # type: ignore[no-any-return, call-overload]

    repo = _repositorio(tmp_path / "repo")
    monkeypatch.setattr(subprocess, "run", espiao)
    _commit_de_origem(repo)
    assert len(chamadas) == 2
    assert all(Path(str(cwd)) == repo for _comando, cwd in chamadas)


@pytest.mark.parametrize(
    "conteudo",
    [
        "{ nao e json",
        "[]",
        "{}",
        '{"registry": {}, "rules": []}',
        '{"registry": {"version": 1}, "rules": "x"}',
        '{"registry": {"version": "v"}, "rules": [1, 2]}',
        '{"registry": {"version": "v"}, "rules": [{}]}',
    ],
    ids=[
        "json-quebrado",
        "lista",
        "vazio",
        "registro-vazio",
        "regras-texto",
        "regras-inteiros",
        "regra-vazia",
    ],
)
def test_fatos_com_seed_invalido_viram_release_build_error(tmp_path: Path, conteudo: str) -> None:
    copia = tmp_path / SEED
    copia.parent.mkdir(parents=True)
    copia.write_text(conteudo, encoding="utf-8")
    with pytest.raises(ReleaseBuildError):
        _fatos_do_produto(tmp_path)


def test_fatos_sem_arquivo_de_seed_viram_release_build_error(tmp_path: Path) -> None:
    with pytest.raises(ReleaseBuildError):
        _fatos_do_produto(tmp_path)


def test_fatos_contam_so_ativas_quando_varias_estao_desabilitadas(tmp_path: Path) -> None:
    payload = json.loads((ROOT / SEED).read_text(encoding="utf-8"))
    total = len(payload["rules"])
    for regra in payload["rules"][:5]:
        regra["enabled"] = False
    copia = tmp_path / SEED
    copia.parent.mkdir(parents=True)
    copia.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert _fatos_do_produto(tmp_path).regras_habilitadas == total - 5


def test_build_com_seed_invalido_reprova_antes_de_gastar_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def nao_deve_rodar(*args: object, **kwargs: object) -> None:
        pytest.fail("o build não pode começar com o seed inválido")

    copia = tmp_path / SEED
    copia.parent.mkdir(parents=True)
    copia.write_text("{ nao e json", encoding="utf-8")
    monkeypatch.setattr(build_release, "ROOT", tmp_path)
    monkeypatch.setattr(build_release, "_commit_de_origem", lambda root=tmp_path: COMMIT)
    monkeypatch.setattr(
        build_release,
        "_fatos_do_produto",
        lambda root=tmp_path: _fatos_do_produto(root),
    )
    monkeypatch.setattr(build_release, "_reset_directory", nao_deve_rodar)
    monkeypatch.setattr(build_release, "_run", nao_deve_rodar)
    monkeypatch.setattr(sys, "argv", ["build_release.py", "--version", "0.6.0"])

    assert build_release.main() == 1
    assert "BUILD DE RELEASE: REPROVADO" in capsys.readouterr().out


def test_build_com_git_ausente_reprova_sem_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def sem_git(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    def nao_deve_rodar(*args: object, **kwargs: object) -> None:
        pytest.fail("o build não pode começar sem git")

    monkeypatch.setattr(subprocess, "run", sem_git)
    monkeypatch.setattr(build_release, "_reset_directory", nao_deve_rodar)
    monkeypatch.setattr(build_release, "_run", nao_deve_rodar)
    monkeypatch.setattr(sys, "argv", ["build_release.py", "--version", "0.6.0"])

    assert build_release.main() == 1
    assert "não foi possível obter o commit" in capsys.readouterr().out


def test_notas_trazem_a_origem_na_lista_de_fatos(tmp_path: Path) -> None:
    assert f"- Origem: commit `{COMMIT}`." in _notas(tmp_path)
