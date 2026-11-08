# mypy: disable-error-code="no-untyped-call"
"""Ataques a Task 4 no runner opt-in: versão na assinatura e BT só pelo modelo."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.rect_diagonal import CASOS_RECT_DIAGONAL, desenhar_positivo
from tests.integration.test_model_symbols_runner import _METODO_NOVO, _fonte, _settings

from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

pytestmark = pytest.mark.integration

_IDS = [identidade for identidade, _ in CASOS_RECT_DIAGONAL]


def test_runner_carrega_o_perfil_do_modelo_na_1_2_0_e_os_legados_em_outras_assinaturas(
    tmp_path: Path,
) -> None:
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    modelo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO)
    assert modelo.versao == "1.3.0"
    assert dict(modelo.parametros)["enabled_variants"] == 34
    assert "PARA_RAIOS_BT" in modelo.classes_suportadas
    assert modelo.assinatura() not in {
        p.assinatura() for p in runner._profiles if p.metodo_id != _METODO_NOVO
    }


@pytest.mark.parametrize("situacao", _IDS)
def test_desenho_exato_sem_haste_so_o_modelo_observa_bt_no_runner(
    tmp_path: Path, situacao: str
) -> None:
    caminho = tmp_path / "bt.pdf"
    with pymupdf.open() as documento:
        desenhar_positivo(documento.new_page(width=300, height=300), situacao)
        documento.save(caminho)
    documento_projeto, fonte = _fonte(caminho)
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()

    composto = runner.run(documento_projeto, fonte)

    de_bt = [
        o
        for occ in composto.occurrences
        for o in occ.observations
        if o.alternativas and str(o.alternativas[0].classe) == "PARA_RAIOS_BT"
    ]
    assert [o.metodo_assinatura for o in de_bt] == [novo], situacao
