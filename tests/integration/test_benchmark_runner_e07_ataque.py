# mypy: disable-error-code="no-untyped-call"
"""E07.2.1 (ataque): identidade da execução e importação tardia da subclasse no benchmark."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import pymupdf
import pytest
from scripts import benchmark_network_pdf
from scripts.benchmark_network_pdf import run_variant

from zeny_project_handler.adapters.interpretation import carregar_registro_regras_inicial
from zeny_project_handler.application.interpretation_pipeline import (
    ConfiguracaoInterpretacao,
    _execution_id,
)

pytestmark = pytest.mark.integration

_MODULO_SUBCLASSE = "zeny_project_handler.adapters.interpretation.ficha_poste"
_CHAVES_DE_SIMBOLO = (
    "simbolos_reconciliados_assinatura",
    "semantica_simbolos_versao",
    "configuracao_simbolos_assinatura",
)


def _pdf(caminho: Path) -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        pagina.draw_rect(pymupdf.Rect(101.0, 115.0, 169.0, 149.0), color=(0, 0, 0), width=1)
        pagina.insert_text((107.0, 140.0), "CT", fontsize=11)
        documento.save(caminho)
    return caminho


def _rodar(tmp_path: Path, nome: str, **opcoes: Any) -> dict[str, Any]:
    diretorio = tmp_path / nome
    diretorio.mkdir()
    base = tmp_path / "base.pdf"
    if not base.exists():
        _pdf(base)
    # Mesmos bytes em todas as execuções: a identidade do benchmark deriva do sha256.
    copia = diretorio / "ct.pdf"
    copia.write_bytes(base.read_bytes())
    return run_variant(copia, diretorio, ocr=None, **opcoes)


def test_sem_flag_nao_importa_a_subclasse_e_usa_o_padrao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delitem(sys.modules, _MODULO_SUBCLASSE, raising=False)
    monkeypatch.setattr(
        benchmark_network_pdf,
        "_interpretador_ficha_poste",
        lambda: pytest.fail("a subclasse não pode ser carregada sem a flag"),
    )

    variante = _rodar(tmp_path, "sem")

    assert variante["interpreter_version"] == "25.0"
    assert _MODULO_SUBCLASSE not in sys.modules


def test_com_flag_a_versao_26_chega_ao_resultado_do_benchmark(tmp_path: Path) -> None:
    com = _rodar(tmp_path, "com", simbolos_modelo=True)
    sem = _rodar(tmp_path, "sem")

    assert com["interpreter_version"] == "26.0"
    assert sem["interpreter_version"] == "25.0"


def test_sem_flag_identidade_nao_traz_chaves_de_simbolo_e_id_e_o_do_padrao(
    tmp_path: Path,
) -> None:
    variante = _rodar(tmp_path, "sem")
    execucao = variante["semantic"].execucao
    parametros = dict(execucao.parametros)
    registro = carregar_registro_regras_inicial()

    assert all(chave not in parametros for chave in _CHAVES_DE_SIMBOLO)
    assert execucao.versao_metodo == "25.0"
    assert execucao.id == _execution_id(
        execucao.projeto_id,
        UUID(parametros["execucao_extracao_id"]),
        registro,
        ConfiguracaoInterpretacao(),
        interpreter_name=execucao.metodo,
        interpreter_version="25.0",
    )


def test_sem_flag_o_id_e_estavel_entre_execucoes_independentes(tmp_path: Path) -> None:
    primeira = _rodar(tmp_path, "um")["semantic"].execucao
    segunda = _rodar(tmp_path, "dois")["semantic"].execucao

    assert primeira.id == segunda.id
    assert primeira.parametros == segunda.parametros


def test_com_flag_a_versao_26_entra_na_identidade_e_muda_o_id(tmp_path: Path) -> None:
    com = _rodar(tmp_path, "com", simbolos_modelo=True)
    sem = _rodar(tmp_path, "sem")
    execucao = com["semantic"].execucao
    parametros = dict(execucao.parametros)

    assert execucao.versao_metodo == "26.0"
    assert parametros["configuracao_simbolos_assinatura"] == com["symbol_configuration_signature"]
    assert all(chave in parametros for chave in _CHAVES_DE_SIMBOLO)
    assert execucao.id != sem["semantic"].execucao.id
    assert execucao.metodo == sem["semantic"].execucao.metodo


def test_com_flag_o_id_e_estavel_entre_execucoes_independentes(tmp_path: Path) -> None:
    primeira = _rodar(tmp_path, "um", simbolos_modelo=True)["semantic"].execucao
    segunda = _rodar(tmp_path, "dois", simbolos_modelo=True)["semantic"].execucao

    assert primeira.id == segunda.id
    assert primeira.versao_metodo == segunda.versao_metodo == "26.0"
