"""Isolamento do spike de treino (E11): nada de treino entra em `src/` nem no runtime."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]
LOCK_DE_TREINO = ROOT / "requirements-treino.lock"
RAIZES_PROIBIDAS_EM_SRC = frozenset({"torch", "torchvision", "onnx", "scripts"})
RAIZES_DE_TREINO = frozenset({"torch", "torchvision", "onnx", "onnxruntime"})
MODULOS_PUROS = ("dados_sinteticos", "metricas", "ambiente")


def _modulos_importados(arvore: ast.AST) -> Iterator[str]:
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            yield from (alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            yield no.module


def _imports_proibidos_em_src(texto: str) -> list[str]:
    """Liste imports de treino (torch, torchvision, onnx, scripts) num fonte de `src/`."""
    return [
        nome
        for nome in _modulos_importados(ast.parse(texto))
        if nome.split(".")[0] in RAIZES_PROIBIDAS_EM_SRC
    ]


def _nos_de_topo(no: ast.AST) -> Iterator[ast.AST]:
    """Percorra o módulo sem descer em corpos de função ou lambda."""
    for filho in ast.iter_child_nodes(no):
        if isinstance(filho, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        yield filho
        yield from _nos_de_topo(filho)


def _imports_de_treino_no_topo(texto: str) -> list[str]:
    """Liste imports de torch/torchvision/onnx/onnxruntime fora de corpos de função."""
    return [
        modulo
        for no in _nos_de_topo(ast.parse(texto))
        if isinstance(no, ast.Import | ast.ImportFrom)
        for modulo in _modulos_importados(no)
        if modulo.split(".")[0] in RAIZES_DE_TREINO
    ]


def _pinos(lock: Path) -> dict[str, str]:
    pinos: dict[str, str] = {}
    for linha in lock.read_text(encoding="utf-8").splitlines():
        texto = linha.split("#", 1)[0].strip()
        if not texto or texto.startswith("-"):
            continue
        requisito = Requirement(texto)
        for especificador in requisito.specifier:
            if especificador.operator == "==":
                pinos[canonicalize_name(requisito.name)] = especificador.version
    return pinos


def test_src_nao_importa_treino_nem_torch_nem_onnx() -> None:
    fontes = sorted((ROOT / "src").rglob("*.py"))
    assert fontes, "nenhum fonte em src/: a guarda passaria vazia"
    violacoes = {
        str(fonte.relative_to(ROOT)): proibidos
        for fonte in fontes
        if (proibidos := _imports_proibidos_em_src(fonte.read_text(encoding="utf-8")))
    }
    assert violacoes == {}


@pytest.mark.parametrize(
    "texto",
    [
        "import torch",
        "import torch.nn as nn",
        "import torchvision",
        "from onnx import helper",
        "import scripts",
        "from scripts.treino_detector import ambiente",
        "from scripts.treino_detector.metricas import iou",
        "def f():\n    import torch\n",
    ],
)
def test_guarda_de_src_acusa_imports_de_treino(texto: str) -> None:
    assert _imports_proibidos_em_src(texto) != []


def test_guarda_de_src_permite_onnxruntime() -> None:
    assert _imports_proibidos_em_src("import onnxruntime") == []
    assert _imports_proibidos_em_src("from onnxruntime import InferenceSession") == []


def test_lock_de_treino_nao_entra_em_runtime_nem_build() -> None:
    outros_locks = [lock for lock in ROOT.glob("requirements*.lock") if lock != LOCK_DE_TREINO]
    assert outros_locks, "nenhum outro lock encontrado: a guarda passaria vazia"
    arquivos = [
        *outros_locks,
        ROOT / "Dockerfile",
        ROOT / "setup.bat",
        ROOT / "IniciarTestes.bat",
        ROOT / "pyproject.toml",
        ROOT / "server" / "pyproject.toml",
        ROOT / "client" / "pyproject.toml",
    ]
    citacoes = [
        str(arquivo.relative_to(ROOT))
        for arquivo in arquivos
        if "requirements-treino.lock" in arquivo.read_text(encoding="utf-8-sig")
    ]
    assert citacoes == []


def test_lock_de_treino_existe_e_fixa_torch_e_onnxruntime() -> None:
    pinos = _pinos(LOCK_DE_TREINO)
    assert set(pinos) >= RAIZES_DE_TREINO


def test_modulos_testados_nao_importam_torch_no_topo() -> None:
    violacoes = {
        nome: proibidos
        for nome in MODULOS_PUROS
        if (
            proibidos := _imports_de_treino_no_topo(
                (ROOT / "scripts" / "treino_detector" / f"{nome}.py").read_text(encoding="utf-8")
            )
        )
    }
    assert violacoes == {}


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("import torch", ["torch"]),
        ("from onnxruntime import InferenceSession", ["onnxruntime"]),
        ("if True:\n    import torchvision.ops\n", ["torchvision.ops"]),
        ("try:\n    import onnx\nexcept ImportError:\n    pass\n", ["onnx"]),
        ("def f():\n    import torch\n", []),
        ("class A:\n    def f(self):\n        import torch\n", []),
        ("import importlib", []),
    ],
)
def test_detector_de_topo_ve_blocos_mas_nao_corpos_de_funcao(
    texto: str, esperado: list[str]
) -> None:
    assert _imports_de_treino_no_topo(texto) == esperado
