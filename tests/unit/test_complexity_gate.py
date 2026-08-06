from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parents[2]
_GATE = _PROJECT_ROOT / "scripts" / "complexity_gate.py"


def _function_source(name: str, branches: int) -> str:
    conditions = "\n".join(
        f"    if value == {index}:\n        value += {index + 1}" for index in range(branches)
    )
    return f"def {name}(value: int) -> int:\n{conditions}\n    return value\n"


def _run_gate(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (sys.executable, str(_GATE), str(path)),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
    )


def test_complexity_gate_allows_rank_d_and_reports_success(tmp_path: Path) -> None:
    fixture = tmp_path / "rank_d.py"
    fixture.write_text(_function_source("rank_d", 20), encoding="utf-8")

    completed = _run_gate(fixture)

    assert completed.returncode == 0
    assert "GATE DE COMPLEXIDADE E/F: APROVADO" in completed.stdout
    assert "Funções e métodos analisados: 1" in completed.stdout
    assert "rank E/F" in completed.stdout


def test_complexity_gate_blocks_controlled_rank_e_and_f_functions(tmp_path: Path) -> None:
    fixture = tmp_path / "rank_e_f.py"
    fixture.write_text(
        _function_source("rank_e", 30) + "\n" + _function_source("rank_f", 40),
        encoding="utf-8",
    )

    completed = _run_gate(fixture)

    assert completed.returncode == 1
    assert "GATE DE COMPLEXIDADE E/F: REPROVADO" in completed.stdout
    assert "E (31) rank_e" in completed.stdout
    assert "F (41) rank_f" in completed.stdout
    assert "Funções e métodos analisados: 2" in completed.stdout
