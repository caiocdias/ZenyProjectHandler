"""Sonda do ambiente de treino do detector (spike E11).

Registra versões de Python, torch, torchvision, onnx e onnxruntime e se há GPU utilizável
pelo PyTorch (ROCm expõe a GPU AMD como ``torch.cuda`` e preenche ``torch.version.hip``).
Nunca levanta exceção: pacote ausente vira ``None`` e falha ao consultar a GPU vira
``gpu_disponivel=False`` com o motivo.

Uso, a partir da raiz do repositório, com o Python do venv de treino:

    python -m scripts.treino_detector.ambiente --saida tmp/treino-e11/ambiente-rocm.json
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import platform
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


@dataclass(frozen=True)
class Ambiente:
    python: str
    plataforma: str
    torch: str | None
    torchvision: str | None
    onnx: str | None
    onnxruntime: str | None
    hip: str | None
    cuda: str | None
    gpu_disponivel: bool
    gpu_nome: str | None
    gpu_arquitetura: str | None
    motivo_sem_gpu: str | None


def _descrever(erro: BaseException) -> str:
    return f"{type(erro).__name__}: {erro}"


def _texto_ou_none(valor: Any) -> str | None:
    return None if valor is None else str(valor)


def _consultar_gpu(torch: Any) -> tuple[bool, str | None, str | None, str | None]:
    """Devolva (disponível, nome, arquitetura, motivo sem GPU) sem propagar exceção."""
    try:
        if not torch.cuda.is_available():
            return False, None, None, "torch.cuda.is_available() == False"
        nome = _texto_ou_none(torch.cuda.get_device_name(0))
        propriedades = torch.cuda.get_device_properties(0)
        arquitetura = _texto_ou_none(getattr(propriedades, "gcnArchName", None))
    except Exception as erro:
        return False, None, None, _descrever(erro)
    return True, nome, arquitetura, None


def coletar_ambiente(
    importar: Callable[[str], ModuleType] = importlib.import_module,
) -> Ambiente:
    """Colete versões e disponibilidade de GPU usando o importador dado."""
    modulos: dict[str, ModuleType | None] = {}
    falhas: dict[str, str] = {}
    for nome in ("torch", "torchvision", "onnx", "onnxruntime"):
        try:
            modulos[nome] = importar(nome)
        except Exception as erro:  # ausente ou com DLL/biblioteca quebrada
            modulos[nome] = None
            falhas[nome] = _descrever(erro)
    versoes = {
        nome: None if modulo is None else _texto_ou_none(getattr(modulo, "__version__", None))
        for nome, modulo in modulos.items()
    }
    torch = modulos["torch"]
    gpu: tuple[bool, str | None, str | None, str | None]
    if torch is None:
        hip = cuda = None
        gpu = (False, None, None, f"torch não importável: {falhas['torch']}")
    else:
        versao = getattr(torch, "version", None)
        hip = _texto_ou_none(getattr(versao, "hip", None))
        cuda = _texto_ou_none(getattr(versao, "cuda", None))
        gpu = _consultar_gpu(torch)
    return Ambiente(
        python=platform.python_version(),
        plataforma=platform.platform(),
        torch=versoes["torch"],
        torchvision=versoes["torchvision"],
        onnx=versoes["onnx"],
        onnxruntime=versoes["onnxruntime"],
        hip=hip,
        cuda=cuda,
        gpu_disponivel=gpu[0],
        gpu_nome=gpu[1],
        gpu_arquitetura=gpu[2],
        motivo_sem_gpu=gpu[3],
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--saida", type=Path, required=True, help="arquivo JSON de saída")
    argumentos = parser.parse_args(argv)
    texto = json.dumps(dataclasses.asdict(coletar_ambiente()), ensure_ascii=False, indent=2)
    saida: Path = argumentos.saida
    saida.write_text(texto + "\n", encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
