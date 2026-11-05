"""Regra fixa de escolha do caminho de treino do detector (spike E11, só biblioteca padrão).

Lê os ``relatorio.json`` dos ensaios (``ensaio.py treino``) e aplica, nesta ordem: caminho
sem vazão medida é inviável; GPU (ROCm nativo, depois WSL2) com paridade de treino na 1ª
iteração, exportação e paridade ONNX e vazão ≥ 3x a CPU ou carga de referência em ≤ 12 h;
CPU com exportação e paridade ONNX e carga de referência em ≤ 12 h; senão GPU alugada.
A qualidade do ensaio curto e a trajetória de 30 iterações só entram no motivo.

Uso, a partir da raiz do repositório:

    python -m scripts.treino_detector.decisao --rocm tmp/treino-e11/ensaio-cuda/relatorio.json \
        --cpu tmp/treino-e11/ensaio-cpu/relatorio.json --saida tmp/treino-e11/decisao.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.treino_detector.metricas import ladrilhos_por_folha

# Premissas (registradas no ADR 0017 como premissas, não como especificação).
CARGA_REFERENCIA_LADRILHOS = 20_000
CARGA_REFERENCIA_EPOCAS = 30
LIMITE_HORAS_TREINO = 12.0
RAZAO_MINIMA_GPU_CPU = 3.0
FOLHA_REFERENCIA_PX = (9933, 7016)  # A1 a 300 dpi
ORCAMENTO_FOLHA_S = 60.0  # orçamento por folha da E12


def horas_estimadas_treino(
    imagens_por_segundo: float,
    ladrilhos: int = CARGA_REFERENCIA_LADRILHOS,
    epocas: int = CARGA_REFERENCIA_EPOCAS,
) -> float:
    """Horas para treinar `epocas` passadas sobre `ladrilhos` à vazão medida."""
    if imagens_por_segundo <= 0:
        raise ValueError("imagens_por_segundo deve ser positiva")
    return ladrilhos * epocas / imagens_por_segundo / 3600


def segundos_estimados_por_folha(
    mediana_ladrilho_s: float,
    largura_px: int = FOLHA_REFERENCIA_PX[0],
    altura_px: int = FOLHA_REFERENCIA_PX[1],
) -> float:
    """Teto de inferência por folha: todos os ladrilhos, sem restringir ao resíduo."""
    return mediana_ladrilho_s * ladrilhos_por_folha(largura_px, altura_px)


@dataclass(frozen=True)
class ResultadoCaminho:
    nome: str
    ensaiado: bool
    paridade_treino: bool
    exportacao_onnx: bool
    paridade_onnx: bool
    imagens_por_segundo: float | None
    qualidade_ok: bool | None
    trajetoria_ok: bool | None = None
    erro_fase: str | None = None
    motivo_nao_ensaiado: str | None = None


@dataclass(frozen=True)
class Decisao:
    caminho: str
    motivo: str
    descartados: tuple[tuple[str, str], ...]


def _vazao_valida(resultado: ResultadoCaminho) -> float | None:
    """Vazão utilizável na regra: medida, finita e positiva; o resto conta como inválida."""
    vazao = resultado.imagens_por_segundo
    return vazao if vazao is not None and math.isfinite(vazao) and vazao > 0 else None


def _falhas_comuns(resultado: ResultadoCaminho, exige_paridade_treino: bool) -> list[str]:
    falhas: list[str] = []
    if resultado.erro_fase is not None:
        falhas.append(f"erro na fase {resultado.erro_fase}")
    if resultado.imagens_por_segundo is None:
        falhas.append("sem vazão de treino medida após o aquecimento")
    elif _vazao_valida(resultado) is None:
        falhas.append(f"vazão de treino inválida ({resultado.imagens_por_segundo:g} img/s)")
    if exige_paridade_treino and not resultado.paridade_treino:
        falhas.append("paridade de treino CPU x GPU na 1ª iteração não comprovada")
    if not resultado.exportacao_onnx:
        falhas.append("exportação ONNX não concluída")
    if not resultado.paridade_onnx:
        falhas.append("paridade ONNX contra o PyTorch em CPU não comprovada")
    return falhas


def _falhas_gpu(gpu: ResultadoCaminho, vazao_cpu: float | None) -> list[str]:
    if not gpu.ensaiado:
        return [f"não ensaiado: {gpu.motivo_nao_ensaiado}"]
    falhas = _falhas_comuns(gpu, exige_paridade_treino=True)
    vazao = _vazao_valida(gpu)
    if vazao is not None:
        horas = horas_estimadas_treino(vazao)
        rapida = vazao_cpu is not None and vazao >= RAZAO_MINIMA_GPU_CPU * vazao_cpu
        if not rapida and horas > LIMITE_HORAS_TREINO:
            falhas.append(
                f"{vazao:.1f} img/s abaixo de {RAZAO_MINIMA_GPU_CPU:g}x a CPU"
                f" e {horas:.1f} h > {LIMITE_HORAS_TREINO:g} h na carga de referência"
            )
    return falhas


def _falhas_cpu(cpu: ResultadoCaminho) -> list[str]:
    if not cpu.ensaiado:
        return [f"não ensaiado: {cpu.motivo_nao_ensaiado}"]
    falhas = _falhas_comuns(cpu, exige_paridade_treino=False)
    vazao = _vazao_valida(cpu)
    if vazao is not None:
        horas = horas_estimadas_treino(vazao)
        if horas > LIMITE_HORAS_TREINO:
            falhas.append(f"{horas:.1f} h > {LIMITE_HORAS_TREINO:g} h na carga de referência")
    return falhas


def _ressalvas(resultado: ResultadoCaminho) -> list[str]:
    observacoes: list[str] = []
    if resultado.qualidade_ok is True:
        observacoes.append("qualidade confirmada (recall e precisão ≥ 0,80)")
    elif resultado.qualidade_ok is False:
        observacoes.append("ressalva: qualidade abaixo de 0,80 no ensaio curto")
    else:
        observacoes.append("qualidade não medida")
    if resultado.trajetoria_ok is False:
        observacoes.append(
            "ressalva: trajetória de loss CPUxGPU divergiu além da tolerância (1ª iteração ok)"
        )
    return observacoes


def _motivo_escolha(resultado: ResultadoCaminho, vazao_cpu: float | None) -> str:
    assert resultado.imagens_por_segundo is not None
    partes = [
        "paridade ONNX ok",
        f"{resultado.imagens_por_segundo:.1f} img/s",
        f"{horas_estimadas_treino(resultado.imagens_por_segundo):.1f} h na carga de referência",
    ]
    if resultado.paridade_treino:
        partes.insert(0, "paridade de treino na 1ª iteração ok")
    if vazao_cpu and resultado.nome != "cpu":
        partes.append(f"{resultado.imagens_por_segundo / vazao_cpu:.1f}x a CPU")
    return "; ".join([*partes, *_ressalvas(resultado)])


def decidir_caminho(
    rocm: ResultadoCaminho, wsl2: ResultadoCaminho, cpu: ResultadoCaminho
) -> Decisao:
    """Aplique a regra fixa da E11 e devolva o caminho com os descartados e seus motivos."""
    vazao_cpu = _vazao_valida(cpu) if cpu.ensaiado else None
    candidatos = (
        (
            "rocm-nativo",
            dataclasses.replace(rocm, nome="rocm-nativo"),
            _falhas_gpu(rocm, vazao_cpu),
        ),
        ("wsl2", dataclasses.replace(wsl2, nome="wsl2"), _falhas_gpu(wsl2, vazao_cpu)),
        ("cpu", dataclasses.replace(cpu, nome="cpu"), _falhas_cpu(cpu)),
    )
    escolhido: str | None = None
    motivo = ""
    descartados: list[tuple[str, str]] = []
    for nome, resultado, falhas in candidatos:
        if escolhido is None and not falhas:
            escolhido, motivo = nome, _motivo_escolha(resultado, vazao_cpu)
        elif falhas:
            descartados.append((nome, "; ".join(falhas)))
        else:
            descartados.append((nome, f"viável, mas preterido por {escolhido}"))
    if escolhido is None:
        escolhido = "gpu-alugada"
        motivo = "nenhum caminho local viável: propor GPU alugada ao usuário (D1)"
    return Decisao(caminho=escolhido, motivo=motivo, descartados=tuple(descartados))


def _fase_do_erro(erro: Any) -> str | None:
    """Fase do erro do relatório; erro em qualquer forma conta, e sem fase vira "desconhecida"."""
    if erro is None:
        return None
    fase = erro.get("fase") if isinstance(erro, dict) else None
    return str(fase) if fase else "desconhecida"


def _ok(bloco: Any) -> bool:
    return isinstance(bloco, dict) and bloco.get("ok") is True


def resultado_de_relatorio(nome: str, relatorio: Path | None) -> ResultadoCaminho:
    """Leia o `relatorio.json` de um ensaio; ausente vira caminho não ensaiado."""
    if relatorio is None or not relatorio.is_file():
        motivo = "relatório não fornecido" if relatorio is None else f"{relatorio} ausente"
        return ResultadoCaminho(
            nome=nome,
            ensaiado=False,
            paridade_treino=False,
            exportacao_onnx=False,
            paridade_onnx=False,
            imagens_por_segundo=None,
            qualidade_ok=None,
            motivo_nao_ensaiado=motivo,
        )
    dados = json.loads(relatorio.read_text(encoding="utf-8"))
    paridade = dados.get("paridade_treino")
    erro = dados.get("erro")
    vazao = dados.get("imagens_por_segundo_treino")
    return ResultadoCaminho(
        nome=nome,
        ensaiado=True,
        paridade_treino=isinstance(paridade, dict)
        and paridade.get("paridade_primeira_iteracao") is True,
        exportacao_onnx=_ok(dados.get("exportacao_onnx")),
        paridade_onnx=_ok(dados.get("paridade_onnx")),
        imagens_por_segundo=None if vazao is None else float(vazao),
        qualidade_ok=dados.get("qualidade_ok"),
        trajetoria_ok=paridade.get("trajetoria_equivalente")
        if isinstance(paridade, dict)
        else None,
        erro_fase=_fase_do_erro(erro),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--rocm", type=Path, help="relatorio.json do ensaio GPU com ROCm nativo")
    parser.add_argument("--cpu", type=Path, help="relatorio.json do ensaio em CPU")
    parser.add_argument("--wsl2", type=Path, help="relatorio.json do ensaio GPU no WSL2")
    parser.add_argument("--motivo-wsl2", help="por que o WSL2 não foi ensaiado")
    parser.add_argument("--saida", type=Path, required=True, help="arquivo decisao.json")
    argumentos = parser.parse_args(argv)

    wsl2 = resultado_de_relatorio("wsl2", argumentos.wsl2)
    if not wsl2.ensaiado and argumentos.motivo_wsl2:
        wsl2 = dataclasses.replace(wsl2, motivo_nao_ensaiado=argumentos.motivo_wsl2)
    decisao = decidir_caminho(
        resultado_de_relatorio("rocm-nativo", argumentos.rocm),
        wsl2,
        resultado_de_relatorio("cpu", argumentos.cpu),
    )
    texto = json.dumps(dataclasses.asdict(decisao), ensure_ascii=False, indent=2)
    argumentos.saida.parent.mkdir(parents=True, exist_ok=True)
    argumentos.saida.write_text(texto + "\n", encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
