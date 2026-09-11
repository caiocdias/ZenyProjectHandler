"""Lotes limitados de recortes, com retorno das caixas ao raster de cada ocorrência."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PIL import Image

from zeny_project_handler.ports.analysis import PaginaRasterOcr, TrechoTextoOcr

MAXIMUM_BATCH_REGIONS = 48
MAXIMUM_BATCH_PIXELS = 8_000_000


@dataclass(frozen=True, slots=True)
class OcrRowBatch:
    raster: PaginaRasterOcr
    boxes: tuple[tuple[int, int, int, int], ...]

    def locate(self, item: TrechoTextoOcr) -> tuple[int, TrechoTextoOcr] | None:
        """Rejeite texto que atravesse recortes; a ordem das linhas OCR é irrelevante."""
        left, top, right, bottom = item.caixa_normalizada
        width, height = self.raster.largura_pixels, self.raster.altura_pixels
        box = left * width, top * height, right * width, bottom * height
        if not item.texto.strip() or left >= right or top >= bottom:
            return None
        for index, (x0, y0, x1, y1) in enumerate(self.boxes):
            # TSV normaliza coordenadas inteiras: tolere apenas erro de ponto flutuante.
            if (
                box[0] >= x0 - 1e-6
                and box[1] >= y0 - 1e-6
                and box[2] <= x1 + 1e-6
                and box[3] <= y1 + 1e-6
            ):
                local = (
                    max(0.0, (box[0] - x0) / (x1 - x0)),
                    max(0.0, (box[1] - y0) / (y1 - y0)),
                    min(1.0, (box[2] - x0) / (x1 - x0)),
                    min(1.0, (box[3] - y0) / (y1 - y0)),
                )
                return index, replace(item, caixa_normalizada=local)
        return None


def pack_ocr_rows(regions: tuple[PaginaRasterOcr, ...]) -> OcrRowBatch | None:
    """Empacote um prefixo limitado, sem reamostrar nem juntar ocorrências vizinhas."""
    if not regions:
        return None
    first = regions[0]
    gap = max(20, first.dpi // 25)
    width, height = 0, gap
    selected: list[PaginaRasterOcr] = []
    for region in regions[:MAXIMUM_BATCH_REGIONS]:
        if region.dpi != first.dpi or region.pagina_numero != first.pagina_numero:
            raise ValueError("O lote OCR exige a mesma página e resolução")
        next_width = max(width, region.largura_pixels + 2 * gap)
        next_height = height + region.altura_pixels + gap
        if next_width * next_height > MAXIMUM_BATCH_PIXELS:
            break
        selected.append(region)
        width, height = next_width, next_height
    if not selected:
        return None
    picture = Image.new("RGB", (width, height), "white")
    boxes: list[tuple[int, int, int, int]] = []
    top = gap
    for region in selected:
        crop = Image.frombytes(
            "RGB",
            (region.largura_pixels, region.altura_pixels),
            region.dados_rgb,
            "raw",
            "RGB",
            region.stride,
        )
        picture.paste(crop, (gap, top))
        boxes.append((gap, top, gap + crop.width, top + crop.height))
        top += crop.height + gap
    return OcrRowBatch(
        raster=PaginaRasterOcr(
            pagina_numero=first.pagina_numero,
            largura_pixels=width,
            altura_pixels=height,
            stride=width * 3,
            dados_rgb=picture.tobytes(),
            dpi=first.dpi,
        ),
        boxes=tuple(boxes),
    )
