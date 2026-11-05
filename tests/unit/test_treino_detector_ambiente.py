"""Sonda de ambiente de treino do detector (spike E11) com importador falso."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest
from scripts.treino_detector import ambiente
from scripts.treino_detector.ambiente import Ambiente, coletar_ambiente


def _importador(modulos: dict[str, object]) -> Callable[[str], ModuleType]:
    def importar(nome: str) -> ModuleType:
        if nome not in modulos:
            raise ModuleNotFoundError(f"No module named '{nome}'")
        return cast(ModuleType, modulos[nome])

    return importar


def _torch(*, hip: str | None, cuda: object) -> object:
    return SimpleNamespace(
        __version__="2.9.1",
        version=SimpleNamespace(hip=hip, cuda=None),
        cuda=cuda,
    )


def _cuda_com_gpu() -> object:
    return SimpleNamespace(
        is_available=lambda: True,
        get_device_name=lambda indice: "AMD Radeon RX 9070 XT",
        get_device_properties=lambda indice: SimpleNamespace(gcnArchName="gfx1201"),
    )


def test_sem_torch_tudo_none_e_sem_gpu() -> None:
    resultado = coletar_ambiente(_importador({}))

    assert resultado.python
    assert resultado.plataforma
    assert (resultado.torch, resultado.torchvision, resultado.onnx, resultado.onnxruntime) == (
        None,
        None,
        None,
        None,
    )
    assert (resultado.hip, resultado.cuda) == (None, None)
    assert resultado.gpu_disponivel is False
    assert (resultado.gpu_nome, resultado.gpu_arquitetura) == (None, None)
    assert resultado.motivo_sem_gpu is not None
    assert "torch" in resultado.motivo_sem_gpu


def test_torch_rocm_com_gpu() -> None:
    resultado = coletar_ambiente(
        _importador(
            {
                "torch": _torch(hip="7.1", cuda=_cuda_com_gpu()),
                "torchvision": SimpleNamespace(__version__="0.24.1"),
                "onnx": SimpleNamespace(__version__="1.19.1"),
                "onnxruntime": SimpleNamespace(__version__="1.23.2"),
            }
        )
    )

    assert resultado.torch == "2.9.1"
    assert resultado.torchvision == "0.24.1"
    assert resultado.onnx == "1.19.1"
    assert resultado.onnxruntime == "1.23.2"
    assert resultado.hip == "7.1"
    assert resultado.cuda is None
    assert resultado.gpu_disponivel is True
    assert resultado.gpu_nome == "AMD Radeon RX 9070 XT"
    assert resultado.gpu_arquitetura == "gfx1201"
    assert resultado.motivo_sem_gpu is None


def test_torch_cpu_sem_gpu_tem_motivo() -> None:
    cuda = SimpleNamespace(is_available=lambda: False)

    resultado = coletar_ambiente(_importador({"torch": _torch(hip=None, cuda=cuda)}))

    assert resultado.torch == "2.9.1"
    assert resultado.hip is None
    assert resultado.gpu_disponivel is False
    assert resultado.gpu_nome is None
    assert resultado.motivo_sem_gpu == "torch.cuda.is_available() == False"


def test_excecao_ao_consultar_gpu_vira_motivo_sem_propagar() -> None:
    def falha() -> bool:
        raise RuntimeError("hipErrorNoBinaryForGpu")

    cuda = SimpleNamespace(is_available=falha)

    resultado = coletar_ambiente(_importador({"torch": _torch(hip="7.1", cuda=cuda)}))

    assert resultado.hip == "7.1"
    assert resultado.gpu_disponivel is False
    assert (resultado.gpu_nome, resultado.gpu_arquitetura) == (None, None)
    assert resultado.motivo_sem_gpu == "RuntimeError: hipErrorNoBinaryForGpu"


def test_falha_ao_carregar_torch_vira_motivo_sem_propagar() -> None:
    def importar(nome: str) -> ModuleType:
        raise OSError("[WinError 126] amdhip64_7.dll")

    resultado = coletar_ambiente(importar)

    assert resultado.torch is None
    assert resultado.gpu_disponivel is False
    assert resultado.motivo_sem_gpu is not None
    assert "torch" in resultado.motivo_sem_gpu
    assert "OSError: [WinError 126] amdhip64_7.dll" in resultado.motivo_sem_gpu


def test_main_grava_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    coletar_original = ambiente.coletar_ambiente
    importar = _importador({"torch": _torch(hip="7.1", cuda=_cuda_com_gpu())})
    monkeypatch.setattr(ambiente, "coletar_ambiente", lambda: coletar_original(importar))
    saida = tmp_path / "ambiente.json"

    codigo = ambiente.main(["--saida", str(saida)])

    assert codigo == 0
    dados = json.loads(saida.read_text(encoding="utf-8"))
    assert set(dados) == {campo.name for campo in dataclasses.fields(Ambiente)}
    assert dados["gpu_arquitetura"] == "gfx1201"
    assert json.loads(capsys.readouterr().out) == dados
