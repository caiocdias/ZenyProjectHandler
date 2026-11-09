"""E07.1: flag ``--simbolos-modelo`` do benchmark por poste (runner de símbolos ligado).

Só fixtures sintéticas. O ``run_variant`` real roda sem o runner nos testes ponta a ponta; o
ramo com o runner é coberto em ``tests/integration/test_benchmark_runner_e07.py``.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import scripts.benchmark_ficha_poste as modulo
import scripts.curation_ficha as curation_ficha
from scripts.benchmark_ficha_poste import _gerador
from scripts.benchmark_network_pdf import run_variant as run_variant_real
from scripts.curation_ficha import baseline
from tests.pdf_fixtures import create_network_benchmark_pdf
from tests.unit.test_benchmark_ficha_poste import _referencia_sintetica
from tests.unit.test_curation_ficha_baseline import (  # noqa: F401  (fixture do pytest)
    _argv,
    _resumo,
    rodada_rede,
)
from tests.unit.test_curation_ficha_baseline_processos import _executor_sem_ficha

ASSINATURA = "a" * 64


def _variante(**extras: Any) -> dict[str, Any]:
    return {
        "analyzer": {"version": "1.0", "signature": "sig"},
        "interpreter_version": "2.0",
        "registry_signature": "reg",
        **extras,
    }


def test_gerador_sem_flag_nao_ganha_chave() -> None:
    assert "simbolos_modelo" not in _gerador(_variante(), native_only=True)


def test_gerador_com_assinatura_na_variante_registra_perfil_e_assinatura() -> None:
    gerador = _gerador(_variante(symbol_configuration_signature=ASSINATURA), native_only=True)

    assert gerador["simbolos_modelo"] == {"perfil": "vector-only", "assinatura": ASSINATURA}


def test_ponta_a_ponta_executar_grava_simbolos_no_gerador(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    recebido: dict[str, Any] = {}

    def run_variant_fake(source: Path, directory: Path, *, ocr: Any, **opcoes: Any) -> Any:
        recebido.update(opcoes)
        variante = run_variant_real(source, directory, ocr=None)
        return {**variante, "symbol_configuration_signature": ASSINATURA}

    monkeypatch.setattr(modulo, "run_variant", run_variant_fake)
    referencia = tmp_path / "ref.json"
    referencia.write_text(
        json.dumps(_referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())), encoding="utf-8"
    )

    modulo.executar(
        pdf,
        referencia,
        tmp_path / "saida",
        native_only=True,
        runtime_directory=tmp_path / "runtime",
        versao_extracao="propostas-v1",
        simbolos_modelo=True,
    )

    ficha = json.loads((tmp_path / "saida" / "ficha-predita.json").read_text(encoding="utf-8"))
    assert recebido == {"simbolos_modelo": True}
    assert ficha["gerador"]["simbolos_modelo"] == {
        "perfil": "vector-only",
        "assinatura": ASSINATURA,
    }


def test_simbolos_modelo_recusa_projeto_promovido(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="não usa símbolos"):
        modulo.executar(
            tmp_path / "x.pdf",
            tmp_path / "ref.json",
            tmp_path / "saida",
            native_only=True,
            runtime_directory=tmp_path,
            simbolos_modelo=True,
        )
    with pytest.raises(ValueError, match="não usa símbolos"):
        baseline(tmp_path, native_only=True, simbolos_modelo=True)


def test_cli_baseline_aceita_a_flag_e_propaga(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas: list[dict[str, Any]] = []

    def baseline_falso(rodada: Path, pdfs: Any, **opcoes: Any) -> dict[str, Any]:
        chamadas.append(opcoes)
        raise SystemExit(0)

    monkeypatch.setattr(curation_ficha, "baseline", baseline_falso)

    for argv in (
        [*_argv(tmp_path, "--versao-extracao", "propostas-v1", "--simbolos-modelo")],
        [*_argv(tmp_path)],
    ):
        with pytest.raises(SystemExit):
            curation_ficha.main(argv)

    assert chamadas[0]["simbolos_modelo"] is True
    assert "simbolos_modelo" not in chamadas[1]


def test_opcoes_do_resumo_so_mudam_com_a_flag(rodada_rede: tuple[Path, str]) -> None:  # noqa: F811
    rodada_dir, _ = rodada_rede

    baseline(rodada_dir, native_only=True, _executor=_executor_sem_ficha)
    baseline(
        rodada_dir,
        native_only=True,
        versao_extracao="propostas-v1",
        simbolos_modelo=True,
        _executor=_executor_sem_ficha,
    )

    assert "simbolos_modelo" not in _resumo(rodada_dir, "baseline-v001")["opcoes"]
    assert _resumo(rodada_dir, "baseline-v002")["opcoes"]["simbolos_modelo"] is True
