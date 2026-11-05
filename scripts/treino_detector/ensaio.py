"""Ensaio treino → ONNX → CPU do detector (spike E11; precisa de torch, torchvision, onnx e
onnxruntime, por isso nunca é importado por teste nem por `src/`).

Uso, a partir da raiz do repositório, com o Python do venv de treino:

    python -m scripts.treino_detector.ensaio paridade --saida tmp/treino-e11/paridade-treino
    python -m scripts.treino_detector.ensaio treino --dispositivo cuda --minutos-max 30 \
        --paridade-treino tmp/treino-e11/paridade-treino/relatorio.json \
        --saida tmp/treino-e11/ensaio-cuda
    python -m scripts.treino_detector.ensaio treino --dispositivo cpu --epocas 3 \
        --minutos-max 15 --saida tmp/treino-e11/ensaio-cpu

Cada subcomando grava `relatorio.json` e `log.txt` em `--saida` (o treino grava também
`modelo.onnx`). Exceção em qualquer fase vai para o campo `erro` e o processo sai com 1.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import math
import os
import time
import traceback
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy
import onnxruntime
import torch
import torchvision
from torch import nn

from scripts.treino_detector.ambiente import coletar_ambiente
from scripts.treino_detector.dados_sinteticos import CLASSES, AmostraSintetica, gerar_conjunto
from scripts.treino_detector.decisao import horas_estimadas_treino, segundos_estimados_por_folha
from scripts.treino_detector.metricas import (
    Deteccao,
    avaliar,
    deteccoes_equivalentes,
    perdas_equivalentes,
    resumir_tempos,
)

LADO = 320
LOTES_AQUECIMENTO = 10
OPSET = 18
IMAGENS_PARIDADE_ONNX = 20
EXECUCOES_INFERENCIA = 100
AQUECIMENTO_INFERENCIA = 5
OTIMIZADOR = {
    "tipo": "SGD",
    "lr": 0.01,
    "momentum": 0.9,
    "weight_decay": 4e-5,
    "aquecimento_lr": "linear de 0,1x a 1x nos primeiros 100 lotes",
}
MODELOS: dict[str, Callable[..., nn.Module]] = {
    "ssdlite320_mobilenet_v3_large": torchvision.models.detection.ssdlite320_mobilenet_v3_large,
    "fasterrcnn_mobilenet_v3_large_320_fpn": (
        torchvision.models.detection.fasterrcnn_mobilenet_v3_large_320_fpn
    ),
}


class Registro:
    """Escreve cada linha no terminal e em `log.txt`."""

    def __init__(self, pasta: Path) -> None:
        pasta.mkdir(parents=True, exist_ok=True)
        self._arquivo = (pasta / "log.txt").open("w", encoding="utf-8")

    def __call__(self, texto: str) -> None:
        linha = f"[{time.strftime('%H:%M:%S')}] {texto}"
        print(linha, flush=True)
        self._arquivo.write(linha + "\n")
        self._arquivo.flush()

    def fechar(self) -> None:
        self._arquivo.close()


def _construir_modelo(nome: str) -> nn.Module:
    return MODELOS[nome](weights=None, weights_backbone=None, num_classes=len(CLASSES) + 1)


def _imagem(amostra: AmostraSintetica, dispositivo: torch.device) -> torch.Tensor:
    tensor = torch.from_numpy(amostra.imagem).permute(2, 0, 1)
    return tensor.to(dispositivo).float().div_(255.0)


def _alvo(amostra: AmostraSintetica, dispositivo: torch.device) -> dict[str, torch.Tensor]:
    caixas = [a.caixa for a in amostra.anotacoes]
    return {
        "boxes": torch.tensor(caixas, dtype=torch.float32, device=dispositivo).reshape(-1, 4),
        "labels": torch.tensor(
            [a.rotulo for a in amostra.anotacoes], dtype=torch.int64, device=dispositivo
        ),
    }


def _sincronizar(dispositivo: torch.device) -> None:
    if dispositivo.type == "cuda":
        torch.cuda.synchronize()


def _otimizador(modelo: nn.Module) -> torch.optim.SGD:
    return torch.optim.SGD(
        modelo.parameters(),
        lr=float(OTIMIZADOR["lr"]),  # type: ignore[arg-type]
        momentum=float(OTIMIZADOR["momentum"]),  # type: ignore[arg-type]
        weight_decay=float(OTIMIZADOR["weight_decay"]),  # type: ignore[arg-type]
    )


def _passo(
    modelo: nn.Module,
    otimizador: torch.optim.Optimizer,
    lote: Sequence[AmostraSintetica],
    dispositivo: torch.device,
) -> float:
    imagens = [_imagem(a, dispositivo) for a in lote]
    alvos = [_alvo(a, dispositivo) for a in lote]
    perdas = modelo(imagens, alvos)
    perda = sum(perdas.values())
    otimizador.zero_grad(set_to_none=True)
    perda.backward()
    otimizador.step()
    valor = float(perda.detach().item())
    if not math.isfinite(valor):
        raise FloatingPointError(f"loss não finita: {valor}")
    return valor


# ---------------------------------------------------------------- paridade de treino


def _curva(
    estado: dict[str, torch.Tensor],
    nome_modelo: str,
    lotes: Sequence[Sequence[AmostraSintetica]],
    dispositivo: torch.device,
    registrar: Registro,
) -> list[float]:
    modelo = _construir_modelo(nome_modelo)
    modelo.load_state_dict(copy.deepcopy(estado))
    modelo.to(dispositivo).train()
    otimizador = _otimizador(modelo)
    perdas = []
    for indice, lote in enumerate(lotes):
        perdas.append(_passo(modelo, otimizador, lote, dispositivo))
        registrar(f"{dispositivo.type} iteração {indice}: loss {perdas[-1]:.6f}")
    return perdas


def _paridade(argumentos: argparse.Namespace) -> int:
    pasta: Path = argumentos.saida
    registrar = Registro(pasta)
    relatorio: dict[str, Any] = {
        "ambiente": dataclasses.asdict(coletar_ambiente()),
        "nucleos": os.cpu_count(),
        "torch_threads": torch.get_num_threads(),
        "modelo": argumentos.modelo,
        "iteracoes": argumentos.iteracoes,
        "lote": argumentos.lote,
        "semente": argumentos.semente,
        "tolerancia": argumentos.tolerancia,
        "tolerancia_primeira_iteracao": 1e-3,
        "otimizador": {k: v for k, v in OTIMIZADOR.items() if k != "aquecimento_lr"},
        "aumento_de_dados": None,
        "erro": None,
    }
    fase = "dados"
    try:
        amostras = gerar_conjunto(argumentos.semente, argumentos.iteracoes * argumentos.lote)
        lotes = [
            amostras[i : i + argumentos.lote] for i in range(0, len(amostras), argumentos.lote)
        ]
        fase = "modelo"
        torch.manual_seed(argumentos.semente)
        estado = _construir_modelo(argumentos.modelo).state_dict()
        fase = "treino-cpu"
        cpu = _curva(estado, argumentos.modelo, lotes, torch.device("cpu"), registrar)
        relatorio["perdas_cpu"] = cpu
        fase = "treino-gpu"
        gpu = _curva(estado, argumentos.modelo, lotes, torch.device("cuda"), registrar)
        fora = [
            i
            for i, (r, c) in enumerate(zip(cpu, gpu, strict=True))
            if not perdas_equivalentes([r], [c], argumentos.tolerancia)
        ]
        relatorio.update(
            perdas_cpu=cpu,
            perdas_gpu=gpu,
            paridade_primeira_iteracao=perdas_equivalentes(cpu[:1], gpu[:1], 1e-3),
            trajetoria_equivalente=perdas_equivalentes(cpu, gpu, argumentos.tolerancia),
            primeira_divergencia=fora[0] if fora else None,
        )
    except Exception as erro:
        relatorio["erro"] = {"fase": fase, "mensagem": f"{type(erro).__name__}: {erro}"}
        registrar(traceback.format_exc())
    _gravar(pasta, relatorio, registrar)
    return 1 if relatorio["erro"] else 0


# ---------------------------------------------------------------- ensaio de treino


def _deteccoes(saida: dict[str, Any]) -> list[Deteccao]:
    caixas = numpy.asarray(saida["boxes"], dtype=float).reshape(-1, 4)
    rotulos = numpy.asarray(saida["labels"]).reshape(-1)
    scores = numpy.asarray(saida["scores"], dtype=float).reshape(-1)
    return [
        Deteccao(
            caixa=(float(c[0]), float(c[1]), float(c[2]), float(c[3])),
            rotulo=int(r),
            score=float(s),
        )
        for c, r, s in zip(caixas, rotulos, scores, strict=True)
    ]


def _prever_torch(
    modelo: nn.Module, amostras: Sequence[AmostraSintetica], dispositivo: torch.device
) -> list[list[Deteccao]]:
    modelo.eval()
    resultado: list[list[Deteccao]] = []
    with torch.no_grad():
        for inicio in range(0, len(amostras), 16):
            saidas = modelo([_imagem(a, dispositivo) for a in amostras[inicio : inicio + 16]])
            resultado.extend(
                _deteccoes({k: v.cpu().numpy() for k, v in saida.items()}) for saida in saidas
            )
    return resultado


class _ParaOnnx(nn.Module):
    """Entrada fixa 1x3x320x320 e saídas (boxes, scores, labels) de uma imagem."""

    def __init__(self, modelo: nn.Module) -> None:
        super().__init__()
        self.modelo = modelo

    def forward(self, imagem: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        saida = self.modelo([imagem[0]])[0]
        return saida["boxes"], saida["scores"], saida["labels"]


def _exportar(modelo: nn.Module, destino: Path, registrar: Registro) -> dict[str, Any]:
    envoltorio = _ParaOnnx(modelo).eval()
    exemplo = torch.zeros(1, 3, LADO, LADO)
    tentativas: list[dict[str, Any]] = []
    for exportador, dynamo in (("dynamo", True), ("torchscript", False)):
        inicio = time.perf_counter()
        try:
            with torch.no_grad():
                torch.onnx.export(
                    envoltorio,
                    (exemplo,),
                    str(destino),
                    opset_version=OPSET,
                    input_names=["imagem"],
                    output_names=["boxes", "scores", "labels"],
                    dynamo=dynamo,
                )
            import onnx  # só para validar o grafo exportado

            onnx.checker.check_model(str(destino))
        except Exception as erro:
            mensagem = f"{type(erro).__name__}: {erro}"
            registrar(f"exportação {exportador} falhou: {mensagem}")
            tentativas.append({"exportador": exportador, "ok": False, "erro": mensagem[:2000]})
            continue
        segundos = time.perf_counter() - inicio
        registrar(f"exportação {exportador} ok em {segundos:.1f} s")
        return {
            "ok": True,
            "exportador": exportador,
            "opset": OPSET,
            "segundos": segundos,
            "erro": None,
            "tentativas": tentativas,
        }
    return {
        "ok": False,
        "exportador": None,
        "opset": OPSET,
        "segundos": None,
        "erro": tentativas[-1]["erro"],
        "tentativas": tentativas,
    }


def _sessao_onnx(arquivo: Path, threads: int) -> onnxruntime.InferenceSession:
    opcoes = onnxruntime.SessionOptions()
    opcoes.intra_op_num_threads = threads
    return onnxruntime.InferenceSession(
        str(arquivo), sess_options=opcoes, providers=["CPUExecutionProvider"]
    )


def _entrada_onnx(amostra: AmostraSintetica) -> numpy.ndarray:
    return (amostra.imagem.transpose(2, 0, 1)[None].astype(numpy.float32) / 255.0).copy()


def _prever_onnx(sessao: onnxruntime.InferenceSession, amostra: AmostraSintetica) -> list[Deteccao]:
    caixas, scores, rotulos = sessao.run(None, {"imagem": _entrada_onnx(amostra)})
    return _deteccoes({"boxes": caixas, "scores": scores, "labels": rotulos})


def _treinar(
    modelo: nn.Module,
    treino: Sequence[AmostraSintetica],
    argumentos: argparse.Namespace,
    dispositivo: torch.device,
    registrar: Registro,
) -> dict[str, Any]:
    otimizador = _otimizador(modelo)
    gerador = numpy.random.default_rng(argumentos.semente)
    lote = argumentos.lote
    limite_s = argumentos.minutos_max * 60
    modelo.to(dispositivo).train()
    lotes_feitos = 0
    imagens_apos = 0
    tempo_apos = 0.0
    aquecimento_s = 0.0
    segundos_por_epoca: list[float] = []
    epocas_feitas = 0
    parou_por_tempo = False
    _sincronizar(dispositivo)
    inicio_total = time.perf_counter()
    for epoca in range(argumentos.epocas):
        ordem = gerador.permutation(len(treino))
        inicio_epoca = time.perf_counter()
        perdas: list[float] = []
        for inicio in range(0, len(ordem) - lote + 1, lote):
            for grupo in otimizador.param_groups:
                grupo["lr"] = float(OTIMIZADOR["lr"]) * min(1.0, 0.1 + 0.9 * lotes_feitos / 100)  # type: ignore[arg-type]
            antes = time.perf_counter()
            perdas.append(
                _passo(
                    modelo,
                    otimizador,
                    [treino[i] for i in ordem[inicio : inicio + lote]],
                    dispositivo,
                )
            )
            _sincronizar(dispositivo)
            depois = time.perf_counter()
            lotes_feitos += 1
            if lotes_feitos <= LOTES_AQUECIMENTO:
                aquecimento_s += depois - antes
            else:
                imagens_apos += lote
                tempo_apos += depois - antes
            if depois - inicio_total >= limite_s:
                parou_por_tempo = True
                break
        if parou_por_tempo:
            registrar(f"época {epoca} interrompida por --minutos-max após {lotes_feitos} lotes")
            break
        segundos_por_epoca.append(time.perf_counter() - inicio_epoca)
        epocas_feitas += 1
        registrar(
            f"época {epoca}: {segundos_por_epoca[-1]:.1f} s, loss média "
            f"{sum(perdas) / len(perdas):.4f}, {lotes_feitos} lotes"
        )
    return {
        "epocas_feitas": epocas_feitas,
        "lotes_feitos": lotes_feitos,
        "parou_por_tempo": parou_por_tempo,
        "aquecimento_s": aquecimento_s,
        "imagens_por_segundo_treino": imagens_apos / tempo_apos if imagens_apos else None,
        "medida_vazao": "lotes-apos-10",
        "segundos_por_epoca": segundos_por_epoca,
        "treino_total_s": time.perf_counter() - inicio_total,
    }


def _medir_inferencia(
    sessao: onnxruntime.InferenceSession, amostra: AmostraSintetica, threads: int
) -> dict[str, Any]:
    entrada = {"imagem": _entrada_onnx(amostra)}
    for _ in range(AQUECIMENTO_INFERENCIA):
        sessao.run(None, entrada)
    tempos = []
    for _ in range(EXECUCOES_INFERENCIA):
        inicio = time.perf_counter()
        sessao.run(None, entrada)
        tempos.append(time.perf_counter() - inicio)
    return {
        **dataclasses.asdict(resumir_tempos(tempos)),
        "aquecimento": AQUECIMENTO_INFERENCIA,
        "intra_op_num_threads": threads,
        "ladrilho_px": LADO,
    }


def _ensaio(argumentos: argparse.Namespace) -> int:
    pasta: Path = argumentos.saida
    registrar = Registro(pasta)
    dispositivo = torch.device(argumentos.dispositivo)
    paridade_treino = (
        json.loads(argumentos.paridade_treino.read_text(encoding="utf-8"))
        if argumentos.paridade_treino
        else None
    )
    relatorio: dict[str, Any] = {
        "ambiente": dataclasses.asdict(coletar_ambiente()),
        "nucleos": os.cpu_count(),
        "torch_threads": torch.get_num_threads(),
        "modelo": argumentos.modelo,
        "dispositivo": argumentos.dispositivo,
        "parametros": {
            "treino": argumentos.treino,
            "validacao": argumentos.validacao,
            "epocas": argumentos.epocas,
            "lote": argumentos.lote,
            "minutos_max": argumentos.minutos_max,
            "semente": argumentos.semente,
        },
        "otimizador": OTIMIZADOR,
        "epocas_feitas": 0,
        "aquecimento_s": None,
        "imagens_por_segundo_treino": None,
        "medida_vazao": "lotes-apos-10",
        "segundos_por_epoca": [],
        "qualidade": None,
        "qualidade_ok": None,
        "paridade_treino": paridade_treino,
        "exportacao_onnx": None,
        "paridade_onnx": None,
        "inferencia_cpu_onnxruntime": None,
        "segundos_estimados_por_folha": None,
        "horas_estimadas_treino_referencia": None,
        "erro": None,
    }
    fase = "dados"
    try:
        treino = gerar_conjunto(argumentos.semente, argumentos.treino)
        validacao = gerar_conjunto(argumentos.semente + 1, argumentos.validacao)
        registrar(f"conjuntos gerados: {len(treino)} treino, {len(validacao)} validação")
        fase = "modelo"
        torch.manual_seed(argumentos.semente)
        modelo = _construir_modelo(argumentos.modelo)
        fase = "treino"
        relatorio.update(_treinar(modelo, treino, argumentos, dispositivo, registrar))
        vazao = relatorio["imagens_por_segundo_treino"]
        if vazao:
            relatorio["horas_estimadas_treino_referencia"] = horas_estimadas_treino(vazao)
        registrar(f"vazão {vazao} img/s, aquecimento {relatorio['aquecimento_s']:.1f} s")
        fase = "qualidade"
        resultado = avaliar(
            _prever_torch(modelo, validacao, dispositivo), [a.anotacoes for a in validacao]
        )
        relatorio["qualidade"] = {
            "precisao": resultado.precisao,
            "recall": resultado.recall,
            "verdadeiros": resultado.verdadeiros,
            "falsos_positivos": resultado.falsos_positivos,
            "falsos_negativos": resultado.falsos_negativos,
            "iou_minimo": 0.5,
            "score_minimo": 0.5,
        }
        relatorio["qualidade_ok"] = resultado.recall >= 0.80 and resultado.precisao >= 0.80
        registrar(f"qualidade: {relatorio['qualidade']}")
        fase = "exportacao"
        modelo_cpu = modelo.to(torch.device("cpu")).eval()
        arquivo_onnx = pasta / "modelo.onnx"
        relatorio["exportacao_onnx"] = _exportar(modelo_cpu, arquivo_onnx, registrar)
        if not relatorio["exportacao_onnx"]["ok"]:
            raise RuntimeError(f"exportação ONNX falhou: {relatorio['exportacao_onnx']['erro']}")
        fase = "paridade_onnx"
        threads = torch.get_num_threads()
        sessao = _sessao_onnx(arquivo_onnx, threads)
        amostras = validacao[:IMAGENS_PARIDADE_ONNX]
        referencia = _prever_torch(modelo_cpu, amostras, torch.device("cpu"))
        divergentes = [
            i
            for i, (amostra, ref) in enumerate(zip(amostras, referencia, strict=True))
            if not deteccoes_equivalentes(ref, _prever_onnx(sessao, amostra))
        ]
        relatorio["paridade_onnx"] = {
            "ok": not divergentes,
            "imagens": len(amostras),
            "divergentes": divergentes,
            "deteccoes_referencia_acima_de_0_25": sum(
                1 for ref in referencia for d in ref if d.score >= 0.25
            ),
        }
        registrar(f"paridade ONNX: {relatorio['paridade_onnx']}")
        fase = "inferencia"
        inferencia = _medir_inferencia(sessao, validacao[0], threads)
        relatorio["inferencia_cpu_onnxruntime"] = inferencia
        relatorio["segundos_estimados_por_folha"] = segundos_estimados_por_folha(
            inferencia["mediana_s"]
        )
        registrar(f"inferência ONNX Runtime: {inferencia}")
    except Exception as erro:
        relatorio["erro"] = {"fase": fase, "mensagem": f"{type(erro).__name__}: {erro}"[:4000]}
        registrar(traceback.format_exc())
    _gravar(pasta, relatorio, registrar)
    return 1 if relatorio["erro"] else 0


def _gravar(pasta: Path, relatorio: dict[str, Any], registrar: Registro) -> None:
    (pasta / "relatorio.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    registrar(f"relatório gravado em {pasta / 'relatorio.json'}")
    registrar.fechar()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ensaio de treino do detector (spike E11)")
    sub = parser.add_subparsers(dest="comando", required=True)
    paridade = sub.add_parser("paridade", help="paridade numérica de treino CPU x GPU")
    paridade.add_argument("--saida", type=Path, required=True)
    paridade.add_argument("--iteracoes", type=int, default=30)
    paridade.add_argument("--lote", type=int, default=16)
    paridade.add_argument("--semente", type=int, default=0)
    paridade.add_argument("--tolerancia", type=float, default=0.05)
    paridade.add_argument(
        "--modelo", choices=sorted(MODELOS), default="ssdlite320_mobilenet_v3_large"
    )
    treino = sub.add_parser("treino", help="treino, exportação ONNX e inferência em CPU")
    treino.add_argument("--dispositivo", choices=("cuda", "cpu"), required=True)
    treino.add_argument("--saida", type=Path, required=True)
    treino.add_argument("--treino", type=int, default=2000)
    treino.add_argument("--validacao", type=int, default=200)
    treino.add_argument("--epocas", type=int, default=20)
    treino.add_argument("--lote", type=int, default=16)
    treino.add_argument("--minutos-max", type=float, default=30)
    treino.add_argument("--semente", type=int, default=0)
    treino.add_argument("--paridade-treino", type=Path)
    treino.add_argument(
        "--modelo", choices=sorted(MODELOS), default="ssdlite320_mobilenet_v3_large"
    )
    argumentos = parser.parse_args(argv)
    return _paridade(argumentos) if argumentos.comando == "paridade" else _ensaio(argumentos)


if __name__ == "__main__":
    raise SystemExit(main())
