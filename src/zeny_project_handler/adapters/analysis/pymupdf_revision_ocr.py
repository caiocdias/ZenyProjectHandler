"""Leituras literais por cor na aparência de uma revisão já detectada."""

from __future__ import annotations

from itertools import pairwise
from typing import Any

from PIL import Image, ImageChops, ImageOps

from zeny_project_handler.ports.analysis import (
    MotorOcrPort,
    MotorOcrRotuloOperacionalPort,
    PaginaRasterOcr,
)


def _color_mask(image: Image.Image, color: str) -> Image.Image:
    red, green, blue = image.convert("RGB").split()
    primary, other = (green, red) if color == "verde" else (red, green)

    def threshold(value: float) -> int:
        return 255 if value > 30 else 0

    return ImageChops.multiply(
        ImageChops.subtract(primary, other).point(threshold),
        ImageChops.subtract(primary, blue).point(threshold),
    )


def _bands(mask: Image.Image) -> list[tuple[int, int, int, int]]:
    """Separe linhas pela ausência de tinta; nunca una as duas cores."""
    result = []
    start = None
    for y in range(mask.height + 1):
        occupied = y < mask.height and mask.crop((0, y, mask.width, y + 1)).getbbox()
        if occupied and start is None:
            start = y
        if not occupied and start is not None:
            bounds = mask.crop((0, start, mask.width, y)).getbbox()
            if bounds is not None and y - start >= 5 and bounds[2] - bounds[0] >= 5:
                result.append((bounds[0], start, bounds[2], y))
            start = None
    return result


def _strike_rows(mask: Image.Image) -> list[int]:
    """Somente traços horizontais internos quase completos; molduras não são riscos."""
    rows = []
    for y in range(mask.height // 4, 3 * mask.height // 4):
        row = mask.crop((0, y, mask.width, y + 1))
        if row.histogram()[255] >= mask.width * 0.85:
            rows.append(y)
    return rows if len(rows) <= max(2, mask.height * 0.15) else []


def _cells(mask: Image.Image) -> list[tuple[int, int, int, int]]:
    columns = [
        x
        for x in range(mask.width)
        if mask.crop((x, 0, x + 1, mask.height)).histogram()[255] >= mask.height * 0.85
    ]
    runs: list[list[int]] = []
    for x in columns:
        if not runs or x > runs[-1][-1] + 1:
            runs.append([x])
        else:
            runs[-1].append(x)
    # Exige as duas bordas externas: um I ou uma haste isolada não delimita célula.
    if len(runs) < 2 or runs[0][0] > 2 or runs[-1][-1] < mask.width - 3:
        return [(0, 0, mask.width, mask.height)]
    return [
        (left[-1] + 1, 2, right[0], mask.height - 2)
        for left, right in pairwise(runs)
        if right[0] - left[-1] > 5
    ]


def _without_strike(mask: Image.Image, rows: list[int]) -> Image.Image:
    cleaned = mask.copy()
    # Interseção dos pixels acima/abaixo reconecta hastes, sem inventar o código.
    line = ImageChops.darker(
        mask.crop((0, min(rows) - 1, mask.width, min(rows))),
        mask.crop((0, max(rows) + 1, mask.width, max(rows) + 2)),
    )
    for y in rows:
        cleaned.paste(line, (0, y))
    return cleaned


def _read_crop(
    crop: Image.Image, number: int, dpi: int, engine: MotorOcrPort
) -> tuple[PaginaRasterOcr, Any]:
    picture = ImageOps.expand(ImageOps.invert(crop), border=20, fill=255).convert("RGB")
    raster = PaginaRasterOcr(
        pagina_numero=number,
        largura_pixels=picture.width,
        altura_pixels=picture.height,
        stride=picture.width * 3,
        dados_rgb=picture.tobytes(),
        dpi=dpi,
    )
    recognize = (
        engine.reconhecer_rotulo_operacional
        if isinstance(engine, MotorOcrRotuloOperacionalPort)
        else engine.reconhecer
    )
    return raster, recognize(raster)


def _reading_payload(
    item: Any,
    raster: PaginaRasterOcr,
    pixmap: Any,
    page: Any,
    bounds: tuple[int, int, int, int],
    color: str,
    rows: list[int],
    preprocessing: str,
) -> dict[str, Any] | None:
    left, top, right, bottom = item.caixa_normalizada
    box = (
        max(0, left * raster.largura_pixels - 20),
        max(0, top * raster.altura_pixels - 20),
        min(bounds[2] - bounds[0], right * raster.largura_pixels - 20),
        min(bounds[3] - bounds[1], bottom * raster.altura_pixels - 20),
    )
    if not item.texto.strip() or box[0] >= box[2] or box[1] >= box[3]:
        return None
    scale = raster.dpi / 72
    return {
        "text": item.texto,
        "confidence": item.confianca,
        "color": color,
        "horizontal_strike": bool(rows),
        "strike_rows_in_crop": rows,
        "preprocessing": preprocessing,
        "dpi": raster.dpi,
        "box": [
            (pixmap.x + bounds[0] + box[0]) / scale / page.rect.width,
            (pixmap.y + bounds[1] + box[1]) / scale / page.rect.height,
            (pixmap.x + bounds[0] + box[2]) / scale / page.rect.width,
            (pixmap.y + bounds[1] + box[3]) / scale / page.rect.height,
        ],
        "requires_review": True,
    }


def revision_color_readings(
    pixmap: Any, page: Any, number: int, dpi: int, engine: MotorOcrPort
) -> tuple[list[dict[str, Any]], bool]:
    """Preserve tentativas, caixas e risco; não atribua autoridade nem complete códigos."""
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    readings: list[dict[str, Any]] = []
    failed = False
    for color in ("verde", "vermelho"):
        mask = _color_mask(image, color)
        for band in _bands(mask):
            band_mask = mask.crop(band)
            cells = (
                _cells(band_mask)
                if color == "verde"
                else [(0, 0, band_mask.width, band_mask.height)]
            )
            for cell in cells:
                bounds = (
                    band[0] + cell[0],
                    band[1] + cell[1],
                    band[0] + cell[2],
                    band[1] + cell[3],
                )
                crop = mask.crop(bounds)
                if crop.getbbox() is None:
                    continue
                rows = _strike_rows(crop) if color == "vermelho" else []
                passes = [("cor_original", crop)]
                if rows:
                    passes.append(
                        ("cor_interpolacao_risco_horizontal", _without_strike(crop, rows))
                    )
                for preprocessing, selected in passes:
                    try:
                        raster, items = _read_crop(selected, number, dpi, engine)
                    except Exception:
                        failed = True
                        continue
                    for item in items:
                        payload = _reading_payload(
                            item, raster, pixmap, page, bounds, color, rows, preprocessing
                        )
                        if payload is not None:
                            readings.append(payload)
    return readings, failed
