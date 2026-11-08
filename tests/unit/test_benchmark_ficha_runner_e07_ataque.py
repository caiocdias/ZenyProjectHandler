"""E07.1 (testador): ataques a flag ``--simbolos-modelo`` do benchmark da ficha do poste.

So fixtures sinteticas. Os executores usados com ``processos`` sao de nivel de modulo (spawn).
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import scripts.benchmark_ficha_poste as modulo
import scripts.benchmark_network_pdf as rede
import scripts.curation_ficha as curation_ficha
from scripts.benchmark_network_pdf import run_variant as run_variant_real
from scripts.curation_ficha import _medir_pdf, baseline
from scripts.ficha_poste import validar_ficha
from scripts.ficha_predita_propostas import ficha_predita_propostas
from tests.pdf_fixtures import create_network_benchmark_pdf
from tests.unit.test_benchmark_ficha_poste import _referencia_sintetica
from tests.unit.test_curation_ficha_baseline import _resumo
from tests.unit.test_curation_ficha_baseline_processos import (
    _executor_sintetico,
    _montar,
)

ASSINATURA = "b" * 64
Registro = dict[str, Any]


def _executor_falha_beta_so_com_simbolos(
    pdf: Path, referencia: Path, saida: Path, **opcoes: Any
) -> Registro:
    if opcoes.get("simbolos_modelo") and pdf.stem == "beta-secreto":
        raise RuntimeError(f"runner de simbolos falhou em {pdf}")
    return _executor_sintetico(
        pdf,
        referencia,
        saida,
        native_only=opcoes["native_only"],
        runtime_directory=opcoes["runtime_directory"],
        versao_extracao=opcoes["versao_extracao"],
    )


def _executor_estrito(
    pdf: Path,
    referencia: Path,
    saida: Path,
    *,
    native_only: bool,
    runtime_directory: Path,
    versao_extracao: str,
) -> Registro:
    return _executor_sintetico(
        pdf,
        referencia,
        saida,
        native_only=native_only,
        runtime_directory=runtime_directory,
        versao_extracao=versao_extracao,
    )


def _preparar(tmp_path: Path) -> tuple[Path, Path]:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    referencia = tmp_path / "ref.json"
    referencia.write_text(
        json.dumps(_referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())), encoding="utf-8"
    )
    return pdf, referencia


def test_executar_sem_flag_nao_repassa_nada_ao_run_variant_nem_registra_simbolos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf, referencia = _preparar(tmp_path)
    recebido: list[dict[str, Any]] = []

    def espiao(source: Path, directory: Path, *, ocr: Any) -> Any:  # assinatura estrita
        recebido.append({})
        return run_variant_real(source, directory, ocr=None)

    monkeypatch.setattr(modulo, "run_variant", espiao)
    for versao in ("projeto-promovido-v1", "propostas-v1"):
        saida = tmp_path / f"saida-{versao}"
        modulo.executar(
            pdf,
            referencia,
            saida,
            native_only=True,
            runtime_directory=tmp_path / "rt",
            versao_extracao=versao,
        )
        ficha = json.loads((saida / "ficha-predita.json").read_text(encoding="utf-8"))
        assert "simbolos_modelo" not in ficha["gerador"]
    assert len(recebido) == 2


def test_fichas_preditas_reais_registram_simbolos_so_com_a_chave_na_variante(
    tmp_path: Path,
) -> None:
    pdf, _ = _preparar(tmp_path)
    diretorio = tmp_path / "v"
    diretorio.mkdir()
    variante = run_variant_real(pdf, diretorio, ocr=None)
    sha = sha256(pdf.read_bytes()).hexdigest()
    ligada = {**variante, "symbol_configuration_signature": ASSINATURA}

    sem = modulo.ficha_predita(variante, sha, native_only=True)
    com = modulo.ficha_predita(ligada, sha, native_only=True)
    propostas = ficha_predita_propostas(ligada, sha, native_only=True)
    propostas_sem = ficha_predita_propostas(variante, sha, native_only=True)

    esperado = {"perfil": "vector-only", "assinatura": ASSINATURA}
    assert "simbolos_modelo" not in sem["gerador"]
    assert "simbolos_modelo" not in propostas_sem["gerador"]
    assert com["gerador"]["simbolos_modelo"] == esperado
    assert propostas["gerador"]["simbolos_modelo"] == esperado
    assert validar_ficha(propostas) == []


def test_medir_pdf_so_repassa_a_flag_quando_ligada(tmp_path: Path) -> None:
    rodada_dir, ids = _montar(tmp_path, "rodada")
    ref = rodada_dir / "x.json"
    chamadas: list[dict[str, Any]] = []

    def espiao(pdf: Path, referencia: Path, saida: Path, **opcoes: Any) -> Registro:
        chamadas.append(opcoes)
        return {}

    base: dict[str, Any] = {"native_only": True, "runtime_directory": tmp_path, "executor": espiao}
    _medir_pdf(rodada_dir, ids[0], ref, tmp_path / "s", **base)
    _medir_pdf(rodada_dir, ids[0], ref, tmp_path / "s", simbolos_modelo=True, **base)

    assert "simbolos_modelo" not in chamadas[0]
    assert chamadas[1]["simbolos_modelo"] is True


def test_baseline_sem_flag_com_executor_estrito_continua_funcionando(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, "rodada")

    resumo = baseline(rodada_dir, native_only=True, processos=2, _executor=_executor_estrito)

    assert "simbolos_modelo" not in resumo["opcoes"]


@pytest.mark.parametrize("processos", [1, 3], ids=["serial", "pool"])
def test_falha_do_runner_numa_folha_nao_derruba_as_outras(tmp_path: Path, processos: int) -> None:
    rodada_dir, ids = _montar(tmp_path, "rodada")

    baseline(
        rodada_dir,
        native_only=True,
        versao_extracao="propostas-v1",
        simbolos_modelo=True,
        processos=processos,
        _executor=_executor_falha_beta_so_com_simbolos,
    )

    resumo = _resumo(rodada_dir, "baseline-v001")
    falhas = [i for i in ids if resumo["por_pdf"][i].get("situacao") == "falha"]
    assert len(falhas) == 1
    assert "runner de simbolos falhou" in resumo["por_pdf"][falhas[0]]["erro"]
    assert str(tmp_path) not in json.dumps(resumo)
    assert "beta-secreto" not in json.dumps(resumo)
    assert resumo["opcoes"]["simbolos_modelo"] is True
    assert resumo["total"]["postes"]["tp"] > 0


def test_recusa_do_projeto_promovido_nao_cria_nada_nem_roda_executor(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, "rodada")
    antes = sorted(p.relative_to(rodada_dir) for p in rodada_dir.rglob("*"))

    def nao_deve_rodar(*_: Any, **__: Any) -> Registro:
        raise AssertionError("executor nao devia rodar")

    with pytest.raises(ValueError, match="não usa símbolos"):
        baseline(
            rodada_dir,
            native_only=True,
            versao_extracao="projeto-promovido-v1",
            simbolos_modelo=True,
            _executor=nao_deve_rodar,
        )

    assert sorted(p.relative_to(rodada_dir) for p in rodada_dir.rglob("*")) == antes


def test_executar_recusa_projeto_promovido_antes_de_tocar_a_saida(tmp_path: Path) -> None:
    pdf, referencia = _preparar(tmp_path)
    saida = tmp_path / "saida"

    with pytest.raises(ValueError, match="não usa símbolos"):
        modulo.executar(
            pdf,
            referencia,
            saida,
            native_only=True,
            runtime_directory=tmp_path / "rt",
            versao_extracao="projeto-promovido-v1",
            simbolos_modelo=True,
        )

    assert not saida.exists()


def test_cli_do_benchmark_recusa_flag_com_projeto_promovido(tmp_path: Path) -> None:
    pdf, referencia = _preparar(tmp_path)
    argv = [
        str(pdf),
        "--referencia",
        str(referencia),
        "--saida",
        str(tmp_path / "s"),
        "--native-only",
        "--runtime-directory",
        str(tmp_path / "rt"),
        "--simbolos-modelo",
    ]

    with pytest.raises(ValueError, match="não usa símbolos"):
        modulo.main(argv)


def test_cli_do_benchmark_propaga_a_flag_so_quando_ligada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas: list[dict[str, Any]] = []

    def executar_falso(*args: Any, **opcoes: Any) -> dict[str, Any]:
        chamadas.append(opcoes)
        return {}

    monkeypatch.setattr(modulo, "executar", executar_falso)
    base = [str(tmp_path / "a.pdf"), "--referencia", "r", "--saida", "s", "--native-only"]
    modulo.main([*base, "--versao-extracao", "propostas-v1", "--simbolos-modelo"])
    modulo.main(base)

    assert chamadas[0]["simbolos_modelo"] is True
    assert "simbolos_modelo" not in chamadas[1]


def test_cli_baseline_com_flag_e_projeto_promovido_sai_com_1_sem_medir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, _ = _montar(tmp_path, "rodada")

    codigo = curation_ficha.main(
        ["baseline", "--rodada", str(rodada_dir), "--native-only", "--simbolos-modelo"]
    )

    assert codigo == 1
    assert "não usa símbolos" in capsys.readouterr().err
    assert not list((rodada_dir / "fichas").glob("baseline-v*"))


def test_falha_do_runner_dentro_do_executar_real_propaga_e_nao_deixa_temporario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

    def quebra(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("modelo indisponivel")

    monkeypatch.setattr(SymbolCompositionRunner, "run", quebra)
    pdf, referencia = _preparar(tmp_path)
    saida = tmp_path / "saida"

    with pytest.raises(RuntimeError, match="modelo indisponivel"):
        modulo.executar(
            pdf,
            referencia,
            saida,
            native_only=True,
            runtime_directory=tmp_path / "rt",
            versao_extracao="propostas-v1",
            simbolos_modelo=True,
        )

    assert not (saida / "ficha-predita.json").exists()
    assert list(saida.glob("ficha-poste-*")) == []


def test_run_variant_com_flag_mantem_banco_e_dados_dentro_do_diretorio_da_variante(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf, _ = _preparar(tmp_path)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    diretorio = tmp_path / "variante"
    diretorio.mkdir()
    configuracoes: list[Any] = []
    original = rede._settings_benchmark

    def espia(directory: Path) -> Any:
        settings = original(directory)
        configuracoes.append(settings)
        return settings

    monkeypatch.setattr(rede, "_settings_benchmark", espia)

    run_variant_real(pdf, diretorio, ocr=None, simbolos_modelo=True)

    assert len(configuracoes) == 1
    assert configuracoes[0].data_directory.resolve().is_relative_to(diretorio.resolve())
    assert (diretorio / "benchmark.sqlite3").is_file()
    assert list(cwd.iterdir()) == []  # nada vazou para o cwd (ex.: tmp/ real)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        ["cwd", "variante", "rede.pdf", "ref.json"]
    )


def test_dois_run_variant_com_flag_nao_compartilham_dados(tmp_path: Path) -> None:
    pdf, _ = _preparar(tmp_path)
    pastas = []
    for nome in ("a", "b"):
        pasta = tmp_path / nome
        pasta.mkdir()
        run_variant_real(pdf, pasta, ocr=None, simbolos_modelo=True)
        pastas.append(pasta)

    assert all((p / "dados-simbolos").is_dir() for p in pastas)
    assert not (tmp_path / "dados-simbolos").exists()
