"""Local DB/SVTR OCR, with lazy optional dependencies and explicit model identity."""

from __future__ import annotations

from hashlib import sha256
from importlib import import_module, metadata
from pathlib import Path
from time import perf_counter
from typing import Any

from zeny_project_handler.ports.analysis import (
    CapacidadeMotorOcr,
    IdentidadeDadosTreinadosOcr,
    PaginaRasterOcr,
    ResultadoConsultaCapacidadeOcr,
    TrechoTextoOcr,
)


def map_quad(
    quad: list[list[float]],
    *,
    raster_origin: tuple[int, int],
    scale: float,
    page_size: tuple[float, float],
) -> list[list[float]]:
    """Map actual integer pixmap origin, not the requested floating clip rectangle."""
    return [
        [
            min(1.0, max(0.0, (x + raster_origin[0]) / scale / page_size[0])),
            min(1.0, max(0.0, (y + raster_origin[1]) / scale / page_size[1])),
        ]
        for x, y in quad
    ]


class RapidLocalOcr:
    nome = "experimental-rapidocr-db-svtr"
    versao = "e12a-1"

    def __init__(self) -> None:
        rapid = import_module("rapidocr_onnxruntime")
        self._numpy = import_module("numpy")
        self._engine = rapid.RapidOCR(intra_op_num_threads=4, inter_op_num_threads=1)
        if rapid.__file__ is None:
            raise RuntimeError("Local RapidOCR package path unavailable")
        root = Path(rapid.__file__).parent
        self.models = {
            path.name: sha256(path.read_bytes()).hexdigest()
            for path in sorted((root / "models").glob("*.onnx"))
        }
        if len(self.models) != 3:
            raise RuntimeError("Expected three local detection/classification/recognition models")
        self.calls: list[dict[str, Any]] = []
        self.capability = CapacidadeMotorOcr(
            implementacao=self.nome,
            versao=metadata.version("rapidocr-onnxruntime"),
            idiomas=("ch+en",),
            dados_treinados=(
                IdentidadeDadosTreinadosOcr(
                    idioma="ch+en",
                    sha256=sha256(repr(sorted(self.models.items())).encode()).hexdigest(),
                ),
            ),
            parametros=(
                ("adapter", self.versao),
                ("onnxruntime", metadata.version("onnxruntime")),
                ("provider", "CPUExecutionProvider"),
                ("threads", 4),
            ),
        )

    def consultar_capacidade(self) -> ResultadoConsultaCapacidadeOcr:
        return ResultadoConsultaCapacidadeOcr(capacidade=self.capability)

    def recognize_quads(self, pagina: PaginaRasterOcr) -> list[dict[str, Any]]:
        width, height = pagina.largura_pixels, pagina.altura_pixels
        if width < 1 or height < 1 or width * height > 8_000_000:
            raise ValueError("Raster outside the experimental 8 MP memory budget")
        if pagina.stride < width * 3 or len(pagina.dados_rgb) != pagina.stride * height:
            raise ValueError("Invalid RGB stride or data length")
        started = perf_counter()
        call: dict[str, Any] = {"width": width, "height": height, "completed": False}
        try:
            raw = self._numpy.frombuffer(pagina.dados_rgb, dtype=self._numpy.uint8)
            rgb = raw.reshape(height, pagina.stride)[:, : width * 3].reshape(height, width, 3)
            # RapidOCR's numpy input is BGR; do not silently swap red and blue.
            result, _ = self._engine(rgb[:, :, ::-1].copy())
            rows = [
                {"quad": box, "text": text, "confidence": float(score)}
                for box, text, score in (result or [])
            ]
            call.update(completed=True, segments=len(rows))
            return rows
        except Exception as exc:
            call["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            call["seconds"] = perf_counter() - started
            self.calls.append(call)

    def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
        return tuple(
            TrechoTextoOcr(
                texto=row["text"],
                caixa_normalizada=(
                    min(p[0] for p in row["quad"]) / pagina.largura_pixels,
                    min(p[1] for p in row["quad"]) / pagina.altura_pixels,
                    max(p[0] for p in row["quad"]) / pagina.largura_pixels,
                    max(p[1] for p in row["quad"]) / pagina.altura_pixels,
                ),
                confianca=row["confidence"],
            )
            for row in self.recognize_quads(pagina)
        )
