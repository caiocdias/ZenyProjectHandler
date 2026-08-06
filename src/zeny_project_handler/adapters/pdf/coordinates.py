"""Transformações reversíveis entre PDF, geometria normalizada, pixels e cena."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from zeny_project_handler.domain.documents import VALID_ROTATIONS, PaginaDocumento
from zeny_project_handler.domain.values import PontoNormalizado


@dataclass(frozen=True, slots=True)
class PontoPlano:
    x: float
    y: float


ORIGEM_CENA = PontoPlano(0, 0)


@dataclass(frozen=True, slots=True)
class TransformacaoAfin:
    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

    @classmethod
    def de_coeficientes(cls, values: tuple[Decimal, ...]) -> TransformacaoAfin:
        if len(values) != 6:
            raise ValueError("Uma transformação afim deve possuir seis coeficientes")
        return cls(*(float(value) for value in values))

    def aplicar(self, point: PontoPlano) -> PontoPlano:
        return PontoPlano(
            self.a * point.x + self.c * point.y + self.e,
            self.b * point.x + self.d * point.y + self.f,
        )

    def inversa(self) -> TransformacaoAfin:
        determinant = self.a * self.d - self.b * self.c
        if abs(determinant) < 1e-12:
            raise ValueError("A transformação afim não é inversível")
        return TransformacaoAfin(
            self.d / determinant,
            -self.b / determinant,
            -self.c / determinant,
            self.a / determinant,
            (self.c * self.f - self.d * self.e) / determinant,
            (self.b * self.e - self.a * self.f) / determinant,
        )


class TransformadorCoordenadasPagina:
    """Converte coordenadas usando as matrizes públicas registradas pelo leitor."""

    def __init__(
        self,
        pagina: PaginaDocumento,
        *,
        dpi: int,
        largura_pixels: int | None = None,
        altura_pixels: int | None = None,
        largura_pagina_pixels: int | None = None,
        altura_pagina_pixels: int | None = None,
        origem_x_pixels: int = 0,
        origem_y_pixels: int = 0,
        rotacao_adicional_graus: int = 0,
    ) -> None:
        if dpi <= 0:
            raise ValueError("DPI deve ser positivo")
        if rotacao_adicional_graus not in VALID_ROTATIONS:
            raise ValueError("Rotação adicional deve ser 0, 90, 180 ou 270 graus")
        self.pagina = pagina
        self.dpi = dpi
        self.rotacao_adicional_graus = rotacao_adicional_graus
        width = float(pagina.largura_pontos) * dpi / 72
        height = float(pagina.altura_pontos) * dpi / 72
        if rotacao_adicional_graus in {90, 270}:
            width, height = height, width
        self.largura_pagina_pixels = (
            largura_pagina_pixels if largura_pagina_pixels is not None else max(1, round(width))
        )
        self.altura_pagina_pixels = (
            altura_pagina_pixels if altura_pagina_pixels is not None else max(1, round(height))
        )
        self.largura_pixels = (
            largura_pixels if largura_pixels is not None else self.largura_pagina_pixels
        )
        self.altura_pixels = (
            altura_pixels if altura_pixels is not None else self.altura_pagina_pixels
        )
        self.origem_x_pixels = origem_x_pixels
        self.origem_y_pixels = origem_y_pixels
        if self.largura_pixels <= 0 or self.altura_pixels <= 0:
            raise ValueError("Dimensões raster devem ser positivas")
        if self.largura_pagina_pixels <= 0 or self.altura_pagina_pixels <= 0:
            raise ValueError("Dimensões da página raster devem ser positivas")
        if self.origem_x_pixels < 0 or self.origem_y_pixels < 0:
            raise ValueError("A origem do recorte deve estar dentro da página raster")
        if (
            self.origem_x_pixels + self.largura_pixels > self.largura_pagina_pixels
            or self.origem_y_pixels + self.altura_pixels > self.altura_pagina_pixels
        ):
            raise ValueError("O recorte raster deve estar dentro da página raster")

    def pdf_para_normalizado(self, point: PontoPlano) -> PontoNormalizado:
        visual = self._pdf_para_visual(point)
        return _normalized(
            visual.x / float(self.pagina.largura_pontos),
            visual.y / float(self.pagina.altura_pontos),
        )

    def normalizado_para_pdf(self, point: PontoNormalizado) -> PontoPlano:
        visual = PontoPlano(
            float(point.x) * float(self.pagina.largura_pontos),
            float(point.y) * float(self.pagina.altura_pontos),
        )
        return self._visual_para_pdf(visual)

    def normalizado_para_pixel(self, point: PontoNormalizado) -> PontoPlano:
        rotated = _rotate_normalized(point, self.rotacao_adicional_graus)
        return PontoPlano(
            float(rotated.x) * self.largura_pagina_pixels - self.origem_x_pixels,
            float(rotated.y) * self.altura_pagina_pixels - self.origem_y_pixels,
        )

    def pixel_para_normalizado(self, point: PontoPlano) -> PontoNormalizado:
        rendered = _normalized(
            (point.x + self.origem_x_pixels) / self.largura_pagina_pixels,
            (point.y + self.origem_y_pixels) / self.altura_pagina_pixels,
        )
        return _unrotate_normalized(rendered, self.rotacao_adicional_graus)

    def normalizado_para_cena(
        self,
        point: PontoNormalizado,
        *,
        origem: PontoPlano = ORIGEM_CENA,
        escala: float = 1,
    ) -> PontoPlano:
        if escala <= 0:
            raise ValueError("Escala de cena deve ser positiva")
        pixel = self.normalizado_para_pixel(point)
        return PontoPlano(origem.x + pixel.x * escala, origem.y + pixel.y * escala)

    def cena_para_normalizado(
        self,
        point: PontoPlano,
        *,
        origem: PontoPlano = ORIGEM_CENA,
        escala: float = 1,
    ) -> PontoNormalizado:
        if escala <= 0:
            raise ValueError("Escala de cena deve ser positiva")
        pixel = PontoPlano((point.x - origem.x) / escala, (point.y - origem.y) / escala)
        return self.pixel_para_normalizado(pixel)

    def _pdf_para_visual(self, point: PontoPlano) -> PontoPlano:
        if self.pagina.matriz_pdf_para_pagina and self.pagina.matriz_rotacao_pagina:
            unrotated = TransformacaoAfin.de_coeficientes(
                self.pagina.matriz_pdf_para_pagina
            ).aplicar(point)
            return TransformacaoAfin.de_coeficientes(self.pagina.matriz_rotacao_pagina).aplicar(
                unrotated
            )
        return self._pdf_para_visual_fallback(point)

    def _visual_para_pdf(self, point: PontoPlano) -> PontoPlano:
        if self.pagina.matriz_pdf_para_pagina and self.pagina.matriz_rotacao_pagina:
            unrotated = (
                TransformacaoAfin.de_coeficientes(self.pagina.matriz_rotacao_pagina)
                .inversa()
                .aplicar(point)
            )
            return (
                TransformacaoAfin.de_coeficientes(self.pagina.matriz_pdf_para_pagina)
                .inversa()
                .aplicar(unrotated)
            )
        return self._visual_para_pdf_fallback(point)

    def _pdf_para_visual_fallback(self, point: PontoPlano) -> PontoPlano:
        box = self.pagina.crop_box
        unrotated = PontoPlano(
            point.x - float(box.x_min),
            float(box.y_max) - point.y,
        )
        return _rotate_page_point(
            unrotated,
            float(box.largura),
            float(box.altura),
            self.pagina.rotacao_graus,
        )

    def _visual_para_pdf_fallback(self, point: PontoPlano) -> PontoPlano:
        box = self.pagina.crop_box
        unrotated = _unrotate_page_point(
            point,
            float(box.largura),
            float(box.altura),
            self.pagina.rotacao_graus,
        )
        return PontoPlano(
            unrotated.x + float(box.x_min),
            float(box.y_max) - unrotated.y,
        )


def _normalized(x: float, y: float) -> PontoNormalizado:
    tolerance = 1e-9
    if not -tolerance <= x <= 1 + tolerance or not -tolerance <= y <= 1 + tolerance:
        raise ValueError("Ponto está fora da página")
    return PontoNormalizado(
        Decimal(str(min(1.0, max(0.0, x)))), Decimal(str(min(1.0, max(0.0, y))))
    )


def _rotate_page_point(point: PontoPlano, width: float, height: float, rotation: int) -> PontoPlano:
    if rotation == 90:
        return PontoPlano(height - point.y, point.x)
    if rotation == 180:
        return PontoPlano(width - point.x, height - point.y)
    if rotation == 270:
        return PontoPlano(point.y, width - point.x)
    return point


def _unrotate_page_point(
    point: PontoPlano, width: float, height: float, rotation: int
) -> PontoPlano:
    if rotation == 90:
        return PontoPlano(point.y, height - point.x)
    if rotation == 180:
        return PontoPlano(width - point.x, height - point.y)
    if rotation == 270:
        return PontoPlano(width - point.y, point.x)
    return point


def _rotate_normalized(point: PontoNormalizado, rotation: int) -> PontoNormalizado:
    one = Decimal(1)
    if rotation == 90:
        return PontoNormalizado(one - point.y, point.x)
    if rotation == 180:
        return PontoNormalizado(one - point.x, one - point.y)
    if rotation == 270:
        return PontoNormalizado(point.y, one - point.x)
    return point


def _unrotate_normalized(point: PontoNormalizado, rotation: int) -> PontoNormalizado:
    one = Decimal(1)
    if rotation == 90:
        return PontoNormalizado(point.y, one - point.x)
    if rotation == 180:
        return PontoNormalizado(one - point.x, one - point.y)
    if rotation == 270:
        return PontoNormalizado(one - point.y, point.x)
    return point
