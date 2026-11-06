"""Apoio para testes que rodam um cenário Qt num subprocesso Python ou pytest.

O aborto de uma ``QThread`` destruída viva derruba o processo inteiro; no subprocesso ele vira
``returncode != 0`` com saída legível, em vez de um "worker crashed" do xdist.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def ambiente_subprocesso() -> dict[str, str]:
    """Herde o ambiente sem as variáveis do xdist, com Qt offscreen e o código deste checkout.

    O ``PYTHONPATH`` herdado vem primeiro: num worktree de tarefa ele aponta para o ``src`` da
    tarefa, que precisa ganhar do pacote editável instalado no venv de outro worktree.
    """
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_XDIST")}
    herdados = [c for c in ambiente.get("PYTHONPATH", "").split(os.pathsep) if c]
    caminhos = os.pathsep.join([*herdados, str(RAIZ), str(RAIZ / "src")])
    return ambiente | {"QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": caminhos}


def comando_pytest_cenario(cenario: Path, basetemp: Path, *opcoes: str) -> list[str]:
    """Monte o pytest serial do cenário com a configuração do projeto e sem cache."""
    return [
        *[sys.executable, "-m", "pytest", str(cenario), *opcoes, "-q", "-n", "0"],
        *["--rootdir", str(RAIZ), "-c", str(RAIZ / "pyproject.toml")],
        # Sem confcutdir a coleta lista cada pasta acima do cenário, inclusive o %TEMP%
        # compartilhado, onde outros testes criam e apagam pastas durante a listagem.
        *["--confcutdir", str(cenario.parent)],
        *["-p", "no:cacheprovider", "--basetemp", str(basetemp)],
    ]
