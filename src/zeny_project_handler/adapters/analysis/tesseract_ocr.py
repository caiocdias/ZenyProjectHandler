"""OCR local via executável Tesseract, sem transmitir documentos para serviços externos."""

from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

from zeny_project_handler.ports.analysis import PaginaRasterOcr, TrechoTextoOcr

TESSERACT_PATH_ENVIRONMENT_VARIABLE = "ZENY_TESSERACT_PATH"
_DEFAULT_WINDOWS_PATHS = (
    Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
    Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
)


class TesseractCliOcr:
    """Reconhece linhas técnicas em uma página raster usando TSV do Tesseract."""

    nome = "tesseract-cli"
    versao = "5"

    def __init__(self, executable: Path, *, language: str = "eng") -> None:
        resolved = executable.expanduser().resolve(strict=True)
        if not resolved.is_file():
            raise ValueError("Executável Tesseract inválido")
        self._executable = resolved
        self._language = language

    @classmethod
    def descobrir(cls) -> TesseractCliOcr | None:
        configured = os.environ.get(TESSERACT_PATH_ENVIRONMENT_VARIABLE)
        candidates = (
            *((Path(configured),) if configured else ()),
            *((Path(found),) if (found := shutil.which("tesseract")) else ()),
            *_DEFAULT_WINDOWS_PATHS,
        )
        for candidate in candidates:
            if candidate.is_file():
                return cls(candidate)
        return None

    def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
        completed = subprocess.run(
            (
                str(self._executable),
                "stdin",
                "stdout",
                "-l",
                self._language,
                "--psm",
                "11",
                "tsv",
            ),
            input=_ppm_bytes(pagina),
            capture_output=True,
            check=True,
            timeout=90,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return _parse_tsv(
            completed.stdout.decode("utf-8", errors="replace"),
            width=pagina.largura_pixels,
            height=pagina.altura_pixels,
        )


def _ppm_bytes(page: PaginaRasterOcr) -> bytes:
    row_size = page.largura_pixels * 3
    expected_minimum = page.stride * page.altura_pixels
    if row_size > page.stride or len(page.dados_rgb) < expected_minimum:
        raise ValueError("Raster RGB inválido para OCR")
    pixels = b"".join(
        page.dados_rgb[offset : offset + row_size]
        for offset in range(0, expected_minimum, page.stride)
    )
    header = f"P6\n{page.largura_pixels} {page.altura_pixels}\n255\n".encode("ascii")
    return header + pixels


def _parse_tsv(tsv: str, *, width: int, height: int) -> tuple[TrechoTextoOcr, ...]:
    if width < 1 or height < 1:
        raise ValueError("Dimensões do raster devem ser positivas")
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
        text = (row.get("text") or "").strip()
        try:
            confidence = float(row.get("conf", "-1"))
        except ValueError:
            continue
        if text and confidence >= 0:
            key = (
                row.get("page_num") or "",
                row.get("block_num") or "",
                row.get("par_num") or "",
                row.get("line_num") or "",
            )
            groups[key].append(row)

    lines = []
    for key in sorted(groups):
        words = groups[key]
        left = min(int(word["left"]) for word in words)
        top = min(int(word["top"]) for word in words)
        right = max(int(word["left"]) + int(word["width"]) for word in words)
        bottom = max(int(word["top"]) + int(word["height"]) for word in words)
        confidence = sum(float(word["conf"]) for word in words) / (100 * len(words))
        lines.append(
            TrechoTextoOcr(
                texto=" ".join(word["text"].strip() for word in words),
                caixa_normalizada=(
                    max(0.0, min(1.0, left / width)),
                    max(0.0, min(1.0, top / height)),
                    max(0.0, min(1.0, right / width)),
                    max(0.0, min(1.0, bottom / height)),
                ),
                confianca=max(0.0, min(1.0, confidence)),
            )
        )
    return tuple(lines)
