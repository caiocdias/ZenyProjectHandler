# mypy: disable-error-code="no-untyped-call"
"""E07.1: ``run_variant`` com o runner de símbolos, sobre PDF sintético com moldura de CT."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from scripts.benchmark_network_pdf import _settings_benchmark, run_variant

pytestmark = pytest.mark.integration

_MOLDURA_CT = (101.0, 115.0, 169.0, 149.0)


def _pdf(caminho: Path) -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        pagina.draw_rect(pymupdf.Rect(_MOLDURA_CT), color=(0, 0, 0), width=1)
        pagina.insert_text((_MOLDURA_CT[0] + 6, _MOLDURA_CT[1] + 25), "CT", fontsize=11)
        documento.save(caminho)
    return caminho


def test_settings_do_benchmark_ligam_o_runner_vector_only(tmp_path: Path) -> None:
    settings = _settings_benchmark(tmp_path)

    assert settings.symbol_composition is True
    assert settings.symbol_profile == "vector-only"
    assert settings.symbol_model_path is None
    assert settings.data_directory == tmp_path / "dados-simbolos"
    assert settings.data_directory.is_dir()


def test_run_variant_com_simbolos_chama_runner(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "ct.pdf")
    diretorio = tmp_path / "execucao"
    diretorio.mkdir()

    variante = run_variant(pdf, diretorio, ocr=None, simbolos_modelo=True)

    parametros = dict(variante["semantic"].execucao.parametros)
    assert "semantica_simbolos_versao" in parametros
    assert variante["symbol_configuration_signature"]
    assert any(
        "origem_simbolo_ocorrencia_id" in dict(p.atributos_sugeridos)
        or "simbolo_classe" in dict(p.atributos_sugeridos)
        for p in variante["semantic"].elementos
    )


def test_run_variant_sem_flag_nao_traz_a_assinatura(tmp_path: Path) -> None:
    diretorio = tmp_path / "execucao"
    diretorio.mkdir()

    variante = run_variant(_pdf(tmp_path / "ct.pdf"), diretorio, ocr=None)

    assert "symbol_configuration_signature" not in variante


def test_run_variant_escolhe_o_interpretador_pela_flag(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    pdf = _pdf(tmp_path / "ct.pdf")

    com = run_variant(pdf, tmp_path / "a", ocr=None, simbolos_modelo=True)
    sem = run_variant(pdf, tmp_path / "b", ocr=None)

    assert com["semantic"].execucao.versao_metodo == "27.0"
    assert sem["semantic"].execucao.versao_metodo == "25.0"
