"""Mapa visual conservador de conteúdo rasterizado para posicionar callouts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from uuid import UUID

from PIL import Image, ImageChops

_LIMIAR_BRANCO = 248
_LADO_CELULA_PIXELS = 4


@dataclass(frozen=True, slots=True, kw_only=True)
class MapaOcupacaoVisual:
    """Grade em que cada célula registra qualquer pixel que não seja branco."""

    pagina_id: UUID
    largura_pixels: int
    altura_pixels: int
    colunas: int
    linhas: int
    lado_celula_pixels: int
    celulas_ocupadas: bytes

    def __post_init__(self) -> None:
        if self.largura_pixels <= 0 or self.altura_pixels <= 0:
            raise ValueError("O mapa visual requer dimensões positivas")
        if self.colunas <= 0 or self.linhas <= 0 or self.lado_celula_pixels <= 0:
            raise ValueError("A grade visual requer dimensões positivas")
        if len(self.celulas_ocupadas) != self.colunas * self.linhas:
            raise ValueError("A grade visual não corresponde às dimensões informadas")

    def regiao_totalmente_branca(
        self,
        esquerda: float,
        topo: float,
        direita: float,
        base: float,
    ) -> bool:
        """Aceite somente regiões contidas cujas células não possuam nenhum traço."""
        if not 0.0 <= esquerda < direita <= 1.0 or not 0.0 <= topo < base <= 1.0:
            return False
        pixel_left = math.floor(esquerda * self.largura_pixels)
        pixel_top = math.floor(topo * self.altura_pixels)
        pixel_right = math.ceil(direita * self.largura_pixels)
        pixel_bottom = math.ceil(base * self.altura_pixels)
        column_start = max(0, pixel_left // self.lado_celula_pixels)
        row_start = max(0, pixel_top // self.lado_celula_pixels)
        column_end = min(
            self.colunas,
            math.ceil(pixel_right / self.lado_celula_pixels),
        )
        row_end = min(
            self.linhas,
            math.ceil(pixel_bottom / self.lado_celula_pixels),
        )
        for row in range(row_start, row_end):
            start = row * self.colunas + column_start
            end = row * self.colunas + column_end
            if any(self.celulas_ocupadas[start:end]):
                return False
        return True


def detectar_ocupacao_visual_rgb(
    pagina_id: UUID,
    *,
    largura_pixels: int,
    altura_pixels: int,
    stride: int,
    dados_rgb: memoryview,
) -> MapaOcupacaoVisual:
    """Converta os pixels reais da página em uma grade conservadora de ocupação."""
    if largura_pixels <= 0 or altura_pixels <= 0:
        raise ValueError("A rasterização deve possuir dimensões positivas")
    if stride < largura_pixels * 3:
        raise ValueError("O stride RGB é menor que a largura da rasterização")
    expected_size = stride * altura_pixels
    raw = dados_rgb.cast("B")
    if raw.nbytes < expected_size:
        raise ValueError("O buffer RGB é menor que as dimensões informadas")

    image = Image.frombytes(
        "RGB",
        (largura_pixels, altura_pixels),
        raw[:expected_size].tobytes(),
        "raw",
        "RGB",
        stride,
    )
    red, green, blue = image.split()
    darkest_channel = ImageChops.darker(ImageChops.darker(red, green), blue)
    occupied = darkest_channel.point(
        tuple(255 if value < _LIMIAR_BRANCO else 0 for value in range(256)),
        mode="L",
    )
    columns = math.ceil(largura_pixels / _LADO_CELULA_PIXELS)
    rows = math.ceil(altura_pixels / _LADO_CELULA_PIXELS)
    padded = Image.new(
        "L",
        (columns * _LADO_CELULA_PIXELS, rows * _LADO_CELULA_PIXELS),
        0,
    )
    padded.paste(occupied, (0, 0))
    pooled = padded.resize((columns, rows), resample=Image.Resampling.BOX)
    cells = pooled.point(
        tuple(1 if value else 0 for value in range(256)),
        mode="L",
    ).tobytes()
    return MapaOcupacaoVisual(
        pagina_id=pagina_id,
        largura_pixels=largura_pixels,
        altura_pixels=altura_pixels,
        colunas=columns,
        linhas=rows,
        lado_celula_pixels=_LADO_CELULA_PIXELS,
        celulas_ocupadas=cells,
    )
