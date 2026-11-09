"""A gramática de estai na identidade do runner opt-in (E06.3.4, Task 2), pelo testador."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.integration.test_model_symbols_runner import _settings

from zeny_project_handler_server import symbol_execution
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner


def test_mudanca_em_grammar_estai_muda_a_assinatura_do_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def assinatura(sal: str) -> str:
        def digest(modulo: Any) -> str:
            nome = str(modulo.__name__)
            return nome + (sal if nome.endswith(".grammar_estai") else "")

        monkeypatch.setattr(symbol_execution, "_module_digest", digest)
        return SymbolCompositionRunner(_settings(tmp_path / "dados")).signature

    assert assinatura("") == assinatura("")
    assert assinatura("") != assinatura("-mudou")
