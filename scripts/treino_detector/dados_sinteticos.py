"""Dados sintéticos do ensaio de treino do detector (só numpy e Pillow)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy
from PIL import Image, ImageDraw

CLASSES: tuple[str, ...] = ("circulo", "triangulo", "quadrado", "cruz")

LADO_MINIMO_SIMBOLO = 32
LADO_MAXIMO_SIMBOLO = 96
TENTATIVAS_POR_SIMBOLO = 50
ESPESSURA_CONTORNO = 3


@dataclass(frozen=True)
class Anotacao:
    caixa: tuple[float, float, float, float]
    rotulo: int


@dataclass(frozen=True)
class AmostraSintetica:
    imagem: numpy.ndarray
    anotacoes: tuple[Anotacao, ...]


def _desenhar_fundo(desenho: ImageDraw.ImageDraw, lado: int, rng: numpy.random.Generator) -> None:
    for _ in range(int(rng.integers(6, 14))):
        x0, y0, x1, y1 = (int(v) for v in rng.integers(0, lado, size=4))
        tom = int(rng.integers(130, 200))
        desenho.line((x0, y0, x1, y1), fill=(tom, tom, tom), width=1)


def _desenhar_simbolo(
    desenho: ImageDraw.ImageDraw, rotulo: int, x0: int, y0: int, tamanho: int
) -> None:
    x1, y1 = x0 + tamanho - 1, y0 + tamanho - 1
    preto = (0, 0, 0)
    if rotulo == 1:
        desenho.ellipse((x0, y0, x1, y1), outline=preto, width=ESPESSURA_CONTORNO)
    elif rotulo == 2:
        desenho.polygon(
            [(x0 + tamanho // 2, y0), (x1, y1), (x0, y1)],
            outline=preto,
            width=ESPESSURA_CONTORNO,
        )
    elif rotulo == 3:
        desenho.rectangle((x0, y0, x1, y1), outline=preto, width=ESPESSURA_CONTORNO)
    else:
        meio_x, meio_y = x0 + tamanho // 2, y0 + tamanho // 2
        desenho.line((meio_x, y0, meio_x, y1), fill=preto, width=ESPESSURA_CONTORNO)
        desenho.line((x0, meio_y, x1, meio_y), fill=preto, width=ESPESSURA_CONTORNO)


def _sem_sobreposicao(
    caixa: tuple[int, int, int, int], ocupadas: list[tuple[int, int, int, int]]
) -> bool:
    return all(
        caixa[2] <= o[0] or o[2] <= caixa[0] or caixa[3] <= o[1] or o[3] <= caixa[1]
        for o in ocupadas
    )


def gerar_amostra(semente: int, lado: int = 320, max_simbolos: int = 4) -> AmostraSintetica:
    """Imagem clara com ruído, linhas finas e de 1 a `max_simbolos` símbolos sem sobreposição."""
    if lado < LADO_MINIMO_SIMBOLO:
        raise ValueError(f"lado deve ser ao menos {LADO_MINIMO_SIMBOLO}")
    rng = numpy.random.default_rng(semente)
    fundo = rng.integers(225, 256, size=(lado, lado, 3), dtype=numpy.uint8)
    imagem = Image.fromarray(fundo, "RGB")
    try:
        desenho = ImageDraw.Draw(imagem)
        _desenhar_fundo(desenho, lado, rng)
        maximo = min(LADO_MAXIMO_SIMBOLO, lado)
        quantidade = int(rng.integers(1, max_simbolos + 1))
        ocupadas: list[tuple[int, int, int, int]] = []
        anotacoes: list[Anotacao] = []
        for _ in range(quantidade):
            for _tentativa in range(TENTATIVAS_POR_SIMBOLO):
                tamanho = int(rng.integers(LADO_MINIMO_SIMBOLO, maximo + 1))
                x0 = int(rng.integers(0, lado - tamanho + 1))
                y0 = int(rng.integers(0, lado - tamanho + 1))
                caixa = (x0, y0, x0 + tamanho, y0 + tamanho)
                if not _sem_sobreposicao(caixa, ocupadas):
                    continue
                rotulo = int(rng.integers(1, len(CLASSES) + 1))
                _desenhar_simbolo(desenho, rotulo, x0, y0, tamanho)
                ocupadas.append(caixa)
                anotacoes.append(Anotacao(tuple(float(v) for v in caixa), rotulo))  # type: ignore[arg-type]
                break
        pixels = numpy.asarray(imagem, dtype=numpy.uint8).copy()
    finally:
        imagem.close()
    return AmostraSintetica(imagem=pixels, anotacoes=tuple(anotacoes))


def gerar_conjunto(semente: int, quantidade: int, lado: int = 320) -> list[AmostraSintetica]:
    """Conjunto determinístico; a amostra `i` usa a semente `semente * 1_000_003 + i`."""
    return [gerar_amostra(semente * 1_000_003 + i, lado) for i in range(quantidade)]
