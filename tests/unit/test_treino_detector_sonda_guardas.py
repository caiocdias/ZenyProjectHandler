"""Ataques do testador à sonda de ambiente e às guardas de isolamento da E11 (Task 2)."""

from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest
from scripts.treino_detector import ambiente
from scripts.treino_detector.ambiente import Ambiente, coletar_ambiente

ROOT = Path(__file__).resolve().parents[2]
LOCK_DE_TREINO = ROOT / "requirements-treino.lock"
PACOTES_DE_TREINO = ("torch", "torchvision", "onnx", "onnxruntime")


def _importador(
    modulos: dict[str, object], chamados: list[str] | None = None
) -> Callable[[str], ModuleType]:
    def importar(nome: str) -> ModuleType:
        if chamados is not None:
            chamados.append(nome)
        if nome not in modulos:
            raise ModuleNotFoundError(f"No module named '{nome}'")
        return cast(ModuleType, modulos[nome])

    return importar


def _torch(cuda: object, **extra: object) -> object:
    base: dict[str, object] = {
        "__version__": "2.9.1",
        "version": SimpleNamespace(hip="7.1", cuda=None),
        "cuda": cuda,
    }
    base.update(extra)
    return SimpleNamespace(**base)


def _cuda(
    *,
    disponivel: Callable[[], bool] = lambda: True,
    nome: Callable[[int], object] = lambda i: "AMD Radeon RX 9070 XT",
    propriedades: Callable[[int], object] = lambda i: SimpleNamespace(gcnArchName="gfx1201"),
) -> object:
    return SimpleNamespace(
        is_available=disponivel, get_device_name=nome, get_device_properties=propriedades
    )


def _levanta(erro: Exception) -> Callable[..., object]:
    def f(*args: object) -> object:
        raise erro

    return f


def _sonda_sem_pacotes(monkeypatch: pytest.MonkeyPatch) -> None:
    original = ambiente.coletar_ambiente
    monkeypatch.setattr(ambiente, "coletar_ambiente", lambda: original(_importador({})))


# --------------------------------------------------------------------------- sonda


def test_gpu_sem_gcn_arch_name_mantem_gpu_e_arquitetura_none() -> None:
    cuda = _cuda(propriedades=lambda i: SimpleNamespace())

    r = coletar_ambiente(_importador({"torch": _torch(cuda)}))

    assert r.gpu_disponivel is True
    assert r.gpu_nome == "AMD Radeon RX 9070 XT"
    assert r.gpu_arquitetura is None
    assert r.motivo_sem_gpu is None


def test_get_device_name_levantando_vira_motivo_e_zera_campos_de_gpu() -> None:
    cuda = _cuda(nome=_levanta(RuntimeError("sem driver")))

    r = coletar_ambiente(_importador({"torch": _torch(cuda)}))

    assert r.gpu_disponivel is False
    assert (r.gpu_nome, r.gpu_arquitetura) == (None, None)
    assert r.motivo_sem_gpu == "RuntimeError: sem driver"


def test_get_device_properties_levantando_nao_deixa_gpu_meio_preenchida() -> None:
    cuda = _cuda(propriedades=_levanta(AssertionError("props")))

    r = coletar_ambiente(_importador({"torch": _torch(cuda)}))

    assert r.gpu_disponivel is False
    assert r.gpu_nome is None
    assert r.motivo_sem_gpu == "AssertionError: props"


def test_torch_sem_atributo_cuda_vira_motivo_sem_propagar() -> None:
    torch = SimpleNamespace(__version__="2.9.1", version=SimpleNamespace(hip=None, cuda=None))

    r = coletar_ambiente(_importador({"torch": torch}))

    assert r.torch == "2.9.1"
    assert r.gpu_disponivel is False
    assert r.motivo_sem_gpu is not None
    assert r.motivo_sem_gpu.startswith("AttributeError")


def test_torch_sem_version_deixa_hip_e_cuda_none() -> None:
    torch = SimpleNamespace(__version__="2.9.1", cuda=_cuda())

    r = coletar_ambiente(_importador({"torch": torch}))

    assert (r.hip, r.cuda) == (None, None)
    assert r.gpu_disponivel is True


def test_version_hip_e_cuda_ausentes_individualmente() -> None:
    torch = SimpleNamespace(__version__="2.9.1", version=SimpleNamespace(), cuda=_cuda())

    r = coletar_ambiente(_importador({"torch": torch}))

    assert (r.hip, r.cuda) == (None, None)


def test_torch_cuda_nvidia_preenche_cuda_e_deixa_hip_none() -> None:
    torch = _torch(_cuda(), version=SimpleNamespace(hip=None, cuda="12.1"))

    r = coletar_ambiente(_importador({"torch": torch}))

    assert r.cuda == "12.1"
    assert r.hip is None


def test_motivo_sem_gpu_so_existe_quando_nao_ha_gpu() -> None:
    com_gpu = coletar_ambiente(_importador({"torch": _torch(_cuda())}))
    sem_gpu = coletar_ambiente(_importador({"torch": _torch(_cuda(disponivel=lambda: False))}))

    assert (com_gpu.gpu_disponivel, com_gpu.motivo_sem_gpu) == (True, None)
    assert sem_gpu.gpu_disponivel is False
    assert sem_gpu.motivo_sem_gpu
    assert sem_gpu.gpu_nome is None


def test_torch_sem_dunder_version_ainda_consulta_gpu_e_versao_none() -> None:
    torch = SimpleNamespace(version=SimpleNamespace(hip="7.1", cuda=None), cuda=_cuda())

    r = coletar_ambiente(_importador({"torch": torch}))

    assert r.torch is None
    assert r.hip == "7.1"
    assert r.gpu_disponivel is True


def test_ausencia_de_um_pacote_nao_afeta_os_outros() -> None:
    modulos = {
        "torch": _torch(_cuda()),
        "torchvision": SimpleNamespace(__version__="0.24.1"),
        "onnxruntime": SimpleNamespace(__version__="1.31.1"),
    }

    r = coletar_ambiente(_importador(modulos))

    assert r.onnx is None
    assert (r.torch, r.torchvision, r.onnxruntime) == ("2.9.1", "0.24.1", "1.31.1")
    assert r.gpu_disponivel is True


def test_onnxruntime_com_dll_quebrada_vira_none_sem_propagar() -> None:
    def importar(nome: str) -> ModuleType:
        if nome == "onnxruntime":
            raise OSError("DLL load failed")
        if nome == "torch":
            return cast(ModuleType, _torch(_cuda()))
        raise ImportError(nome)

    r = coletar_ambiente(importar)

    assert r.onnxruntime is None
    assert r.torch == "2.9.1"
    assert r.gpu_disponivel is True


def test_importador_so_recebe_os_quatro_pacotes_de_treino() -> None:
    chamados: list[str] = []

    coletar_ambiente(_importador({}, chamados))

    assert sorted(chamados) == sorted(PACOTES_DE_TREINO)


def test_ambiente_e_imutavel_e_tem_os_doze_campos_do_contrato() -> None:
    r = coletar_ambiente(_importador({}))

    with pytest.raises(dataclasses.FrozenInstanceError):
        r.torch = "x"  # type: ignore[misc]
    assert [c.name for c in dataclasses.fields(Ambiente)] == [
        "python",
        "plataforma",
        "torch",
        "torchvision",
        "onnx",
        "onnxruntime",
        "hip",
        "cuda",
        "gpu_disponivel",
        "gpu_nome",
        "gpu_arquitetura",
        "motivo_sem_gpu",
    ]


def test_importador_padrao_e_importlib_import_module() -> None:
    padrao = inspect.signature(coletar_ambiente).parameters["importar"].default

    assert padrao is importlib.import_module


def test_main_sem_pacotes_grava_utf8_legivel_e_stdout_igual_ao_arquivo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _sonda_sem_pacotes(monkeypatch)
    saida = tmp_path / "a.json"

    assert ambiente.main(["--saida", str(saida)]) == 0

    bruto = saida.read_text(encoding="utf-8")
    assert "não importável" in bruto
    assert bruto.endswith("\n")
    dados = json.loads(bruto)
    assert dados["gpu_disponivel"] is False
    assert dados["torch"] is None
    assert json.loads(capsys.readouterr().out) == dados


def test_main_sem_saida_sai_com_erro_de_uso() -> None:
    with pytest.raises(SystemExit) as erro:
        ambiente.main([])

    assert erro.value.code == 2


def test_main_com_diretorio_inexistente_propaga_erro_de_arquivo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sonda_sem_pacotes(monkeypatch)

    with pytest.raises(FileNotFoundError):
        ambiente.main(["--saida", str(tmp_path / "nao-existe" / "a.json")])


def test_main_sobrescreve_arquivo_existente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sonda_sem_pacotes(monkeypatch)
    saida = tmp_path / "a.json"
    saida.write_text("lixo antigo " * 200, encoding="utf-8")

    ambiente.main(["--saida", str(saida)])

    assert json.loads(saida.read_text(encoding="utf-8"))["torch"] is None


# ------------------------------------------------------------------------ guardas

RAIZES_PROIBIDAS_EM_SRC = frozenset({"torch", "torchvision", "onnx", "scripts"})


def _importados(texto: str) -> Iterator[str]:
    for no in ast.walk(ast.parse(texto)):
        if isinstance(no, ast.Import):
            yield from (a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            yield no.module


def _proibidos(texto: str) -> list[str]:
    return [m for m in _importados(texto) if m.split(".")[0] in RAIZES_PROIBIDAS_EM_SRC]


def _percorrer_topo(no: ast.AST) -> Iterator[ast.AST]:
    for filho in ast.iter_child_nodes(no):
        if isinstance(filho, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        yield filho
        yield from _percorrer_topo(filho)


def _topo(texto: str) -> list[str]:
    """Imports de pacotes de treino executados na carga do módulo (fora de funções)."""
    achados: list[str] = []
    for no in _percorrer_topo(ast.parse(texto)):
        if isinstance(no, ast.Import):
            achados += [a.name for a in no.names]
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            achados.append(no.module)
    return [m for m in achados if m.split(".")[0] in PACOTES_DE_TREINO]


@pytest.mark.parametrize(
    "texto",
    [
        "import os, torch",
        "import a.b as c, onnx.helper as h",
        "from torch.utils.data import DataLoader",
        "from torch import (\n    nn,\n)",
        "from torchvision.ops import nms",
        "class A:\n    from onnx import helper\n",
        "async def f():\n    import torch\n",
        "if True:\n    import onnx\n",
        "try:\n    import torch\nexcept ImportError:\n    torch = None\n",
        "from scripts import treino_detector",
        "import scripts.treino_detector.metricas",
    ],
)
def test_guarda_de_src_pega_mais_grafias(texto: str) -> None:
    assert _proibidos(texto) != []


@pytest.mark.parametrize(
    "texto",
    [
        "import torchaudio",
        "import onnx_foo",
        "import onnxruntime",
        "import onnxruntime.capi",
        "from onnxruntime.capi import x",
        "from . import torch",
        "from .torch import x",
        "from .. import onnx",
        "import scriptsx",
        "from scripts_extra import y",
        "import torchx.torch",
        "x = 'import torch'",
        "# import torch\n",
    ],
)
def test_guarda_de_src_nao_acusa_nomes_parecidos_nem_relativos(texto: str) -> None:
    assert _proibidos(texto) == []


@pytest.mark.parametrize(
    "texto",
    [
        "class A:\n    import torch\n",
        "with open('x') as f:\n    import onnxruntime\n",
        "for _ in []:\n    from torchvision import ops\n",
        "import onnxruntime.capi",
        "match 1:\n    case 1:\n        import onnx\n",
    ],
)
def test_detector_de_topo_pega_imports_executados_na_carga(texto: str) -> None:
    assert _topo(texto) != []


@pytest.mark.parametrize(
    "texto",
    ["import torchaudio", "import onnx_foo", "from . import torch", "import numpy as np"],
)
def test_detector_de_topo_ignora_nomes_parecidos_e_relativos(texto: str) -> None:
    assert _topo(texto) == []


def test_src_nao_carrega_pacotes_de_treino_por_importlib_nem_dunder_import() -> None:
    violacoes: list[str] = []
    for fonte in sorted((ROOT / "src").rglob("*.py")):
        for no in ast.walk(ast.parse(fonte.read_text(encoding="utf-8"))):
            if not isinstance(no, ast.Call) or not no.args:
                continue
            alvo = no.args[0]
            if (
                ast.unparse(no.func).endswith(("import_module", "__import__"))
                and isinstance(alvo, ast.Constant)
                and isinstance(alvo.value, str)
                and alvo.value.split(".")[0] in RAIZES_PROIBIDAS_EM_SRC
            ):
                violacoes.append(f"{fonte.relative_to(ROOT)}: {alvo.value}")
    assert violacoes == []


def test_nenhum_script_nem_teste_fora_do_treino_importa_torch_no_topo() -> None:
    proprio = Path(__file__).resolve()
    arquivos = [
        f
        for pasta in ("scripts", "tests", "server", "client")
        for f in (ROOT / pasta).rglob("*.py")
        if "treino_detector" not in f.parts and f.resolve() != proprio
    ]
    assert arquivos
    violacoes = {
        str(f.relative_to(ROOT)): achados
        for f in arquivos
        if (achados := _topo(f.read_text(encoding="utf-8")))
    }
    assert violacoes == {}


def test_modulos_do_treino_nao_importam_pacotes_pesados_no_topo_nem_por_literal() -> None:
    violacoes: dict[str, list[str]] = {}
    for nome in ("dados_sinteticos", "metricas", "ambiente"):
        texto = (ROOT / "scripts" / "treino_detector" / f"{nome}.py").read_text(encoding="utf-8")
        achados = _topo(texto)
        achados += re.findall(r"""(?:import_module|__import__)\(\s*["'](torch\w*|onnx\w*)""", texto)
        if achados:
            violacoes[nome] = achados
    assert violacoes == {}


# --------------------------------------------------------------------------- lock

_SUFIXOS_TEXTO = {
    ".lock", ".txt", ".toml", ".yaml", ".yml", ".bat", ".cmd", ".py",
    ".cfg", ".ini", ".spec", ".in", ".sh", ".ps1",
}  # fmt: skip


def _arquivos_de_build() -> list[Path]:
    achados: list[Path] = []
    pastas = (ROOT, ROOT / "server", ROOT / "client", ROOT / "scripts", ROOT / "src")
    for pasta in (*pastas, ROOT / ".github"):
        if not pasta.exists():
            continue
        varredura = pasta.glob("*") if pasta == ROOT else pasta.rglob("*")
        for f in varredura:
            if not f.is_file() or f == LOCK_DE_TREINO or "treino_detector" in f.parts:
                continue
            if "__pycache__" in f.parts:
                continue
            if f.suffix.lower() in _SUFIXOS_TEXTO or f.name.lower().startswith("dockerfile"):
                achados.append(f)
    return achados


def test_nenhum_arquivo_de_build_ou_compose_cita_o_lock_de_treino() -> None:
    arquivos = _arquivos_de_build()
    assert any(f.name == "compose.yaml" for f in arquivos)
    assert any(f.name == "Dockerfile" for f in arquivos)
    citacoes = [
        str(f.relative_to(ROOT))
        for f in arquivos
        if "requirements-treino" in f.read_text(encoding="utf-8-sig", errors="replace")
    ]
    assert citacoes == []


def test_nenhum_lock_inclui_o_lock_de_treino_por_diretiva_r_ou_c() -> None:
    locks = list(ROOT.glob("requirements*.lock"))
    assert len(locks) >= 5
    inclusoes = [
        f"{lock.name}: {linha.strip()}"
        for lock in locks
        for linha in lock.read_text(encoding="utf-8-sig").splitlines()
        if re.match(r"\s*(-r|-c|--requirement|--constraint)\b.*requirements-treino", linha)
    ]
    assert inclusoes == []


def test_nenhum_outro_lock_fixa_torch_torchvision_ou_onnx() -> None:
    outros = [lock for lock in ROOT.glob("requirements*.lock") if lock != LOCK_DE_TREINO]
    assert len(outros) >= 4
    achados = [
        f"{lock.name}: {linha}"
        for lock in outros
        for linha in lock.read_text(encoding="utf-8-sig").splitlines()
        if re.match(r"\s*(torch|torchvision|onnx)\s*(==|>=|<=|~=|!=|<|>|\[|$)", linha, re.I)
    ]
    assert achados == []


def test_nenhum_lock_de_runtime_fixa_onnxruntime() -> None:
    runtime = [
        "requirements.lock",
        "requirements-server.lock",
        "requirements-client.lock",
        "requirements-client-build.lock",
        "requirements-development.lock",
    ]
    achados = [
        nome
        for nome in runtime
        if re.search(r"(?mi)^\s*onnxruntime\b", (ROOT / nome).read_text(encoding="utf-8-sig"))
    ]
    assert achados == []


def _linhas_do_lock() -> list[str]:
    return [
        t
        for linha in LOCK_DE_TREINO.read_text(encoding="utf-8").splitlines()
        if (t := linha.split("#", 1)[0].strip())
    ]


def test_lock_de_treino_so_tem_pinos_exatos_ou_opcoes_https_sem_duplicata() -> None:
    nomes: list[str] = []
    for linha in _linhas_do_lock():
        if linha.startswith("-"):
            assert re.fullmatch(r"--(find-links|index-url|extra-index-url) https://\S+", linha), (
                linha
            )
            continue
        m = re.fullmatch(r"([A-Za-z0-9._-]+)==([A-Za-z0-9._+!-]+)", linha)
        assert m, f"pino nao exato: {linha}"
        nomes.append(re.sub(r"[-_.]+", "-", m.group(1)).lower())
    assert len(nomes) == len(set(nomes))
    assert set(PACOTES_DE_TREINO) <= set(nomes)


def test_lock_de_treino_torch_e_torchvision_compartilham_variante_rocm_do_indice() -> None:
    texto = LOCK_DE_TREINO.read_text(encoding="utf-8")
    pinos = dict(re.findall(r"(?m)^(torch|torchvision|rocm)==(\S+)$", texto))
    assert set(pinos) == {"torch", "torchvision", "rocm"}
    variante = pinos["torch"].split("+", 1)[1]
    assert pinos["torchvision"].split("+", 1)[1] == variante
    assert variante == f"rocm{pinos['rocm']}"
    assert f"rocm-rel-{pinos['rocm']}" in texto


def test_lock_de_treino_declara_python_312_e_opt_in_no_cabecalho_sem_hash() -> None:
    texto = LOCK_DE_TREINO.read_text(encoding="utf-8")
    cabecalho = "\n".join(t for t in texto.splitlines() if t.startswith("#"))
    assert "3.12" in cabecalho
    assert "opt-in" in cabecalho
    assert "--hash" not in texto
