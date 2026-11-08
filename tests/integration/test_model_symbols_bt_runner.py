# mypy: disable-error-code="no-untyped-call"
"""E06.3.3.1, Task 4: PARA_RAIOS_BT desenhado no estilo clássico, no runner opt-in.

O legado (`_bt_arrester_matches`) e a gramática `rect_diagonal` do modelo leem o mesmo desenho
(`desenhar_bt_classico` satisfaz as duas regras nas quatro situações). A caixa do legado é a união
de haste, corpo e diagonal; a do modelo é o pictograma (R-E06.3.3.1-3). O teste afirma primeiro
que as duas assinaturas observaram PARA_RAIOS_BT na página e só então julga a fusão.

Resultado medido (R-E06.3.3.1-6): NÃO funde. `_same_occurrence` recusa o par por centro e tamanho
(a haste de ligação alarga a caixa do legado), então o runner opt-in mantém duas ocorrências até a
E09; o handoff "Para a E07" registra isso. Se um dia o par fundir, este teste falha de propósito.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.rect_diagonal import CASOS_RECT_DIAGONAL, desenhar_bt_classico
from tests.integration.test_model_symbols_runner import _METODO_NOVO, _fonte, _settings

from zeny_project_handler.application.symbol_reconciliation import _bounds, _same_occurrence
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

pytestmark = pytest.mark.integration

_CLASSE = "PARA_RAIOS_BT"
_SITUACOES = [identidade for identidade, _ in CASOS_RECT_DIAGONAL]


@pytest.mark.parametrize("situacao", _SITUACOES)
def test_bt_classico_no_runner_nao_funde_legado_e_modelo(tmp_path: Path, situacao: str) -> None:
    caminho = tmp_path / "bt.pdf"
    with pymupdf.open() as documento:
        desenhar_bt_classico(documento.new_page(width=300, height=300), situacao)
        documento.save(caminho)
    documento_projeto, fonte = _fonte(caminho)
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()
    legados = {p.assinatura() for p in runner._profiles if p.metodo_id != _METODO_NOVO}

    composto = runner.run(documento_projeto, fonte)

    de_bt = [
        o
        for occ in composto.occurrences
        for o in occ.observations
        if o.alternativas and str(o.alternativas[0].classe) == _CLASSE
    ]
    do_modelo = [o for o in de_bt if o.metodo_assinatura == novo]
    do_legado = [o for o in de_bt if o.metodo_assinatura in legados]
    # Primeiro: as duas assinaturas observaram PARA_RAIOS_BT na página.
    assert len(do_modelo) == 1, situacao
    assert len(do_legado) == 1, situacao
    modelo, legado = do_modelo[0], do_legado[0]

    # Só então o julgamento: o reconciliador não as funde, e a razão é o tamanho e o centro.
    assert not _same_occurrence(modelo, legado), situacao
    ocorrencias = [
        occ
        for occ in composto.occurrences
        if any(o.metodo_assinatura in {novo, *legados} and o in de_bt for o in occ.observations)
    ]
    assert len(ocorrencias) == 2, situacao
    assert all(len({o.metodo_assinatura for o in occ.observations}) == 1 for occ in ocorrencias)
    a, b = _bounds(modelo), _bounds(legado)
    largura_modelo, largura_legado = a[2] - a[0], b[2] - b[0]
    escala = min(max(largura_modelo, a[3] - a[1]), max(largura_legado, b[3] - b[1]))
    assert abs((a[0] + a[2] - b[0] - b[2]) / 2) > max(Decimal("0.001"), escala * Decimal("0.10"))
