"""OCR local via executável Tesseract, sem transmitir documentos para serviços externos."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from hashlib import sha256
from pathlib import Path

from zeny_project_handler.domain.analysis import DiagnosticoAnalise
from zeny_project_handler.domain.catalog import ExtraAttributes
from zeny_project_handler.ports.analysis import (
    CapacidadeMotorOcr,
    IdentidadeDadosTreinadosOcr,
    PaginaRasterOcr,
    ResultadoConsultaCapacidadeOcr,
    TrechoTextoOcr,
)

TESSERACT_PATH_ENVIRONMENT_VARIABLE = "ZENY_TESSERACT_PATH"
_DEFAULT_WINDOWS_PATHS = (
    Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
    Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
)
_PREFERRED_LANGUAGES = ("por", "eng")
_VERSION_PATTERN = re.compile(
    r"^\s*tesseract\s+v?([0-9][0-9a-z.+_-]*)",
    flags=re.IGNORECASE | re.MULTILINE,
)
_QUOTED_DIRECTORY_PATTERN = re.compile(r"[\"']([^\"']+)[\"']")
_GENERAL_PSM = 11
_IDENTIFIER_PSM = 10
_OPERATIONAL_LABEL_PSM = 7
_OPERATIONAL_BLOCK_PSM = 6
_IDENTIFIER_WHITELIST = "P0123456789"
_TECHNICAL_WHITELIST = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()-/".,:'


@dataclass(frozen=True, slots=True)
class _CapabilityInspection:
    result: ResultadoConsultaCapacidadeOcr
    tessdata_directory: Path | None = None


class TesseractCliOcr:
    """Reconhece linhas técnicas em uma página raster usando TSV do Tesseract."""

    nome = "tesseract-cli"

    def __init__(
        self,
        executable: Path,
        *,
        language: str | None = None,
        oem: int = 3,
        tessdata_directory: Path | None = None,
        capability_timeout_seconds: int = 15,
        recognition_timeout_seconds: int = 90,
    ) -> None:
        resolved = executable.expanduser().resolve(strict=True)
        if not resolved.is_file():
            raise ValueError("Executável Tesseract inválido")
        if oem not in range(4):
            raise ValueError("OEM do Tesseract deve estar entre 0 e 3")
        if capability_timeout_seconds < 1 or recognition_timeout_seconds < 1:
            raise ValueError("Timeouts do Tesseract devem ser positivos")
        self._executable = resolved
        self._requested_languages = _parse_requested_languages(language)
        self._oem = oem
        self._configured_tessdata_directory = _resolve_configured_tessdata_directory(
            tessdata_directory
        )
        self._capability_timeout_seconds = capability_timeout_seconds
        self._recognition_timeout_seconds = recognition_timeout_seconds

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
                try:
                    return cls(candidate)
                except (OSError, ValueError):
                    continue
        return None

    def consultar_capacidade(self) -> ResultadoConsultaCapacidadeOcr:
        """Consulte versão, idiomas e traineddata uma única vez nesta instância."""
        return self._inspection.result

    @cached_property
    def _inspection(self) -> _CapabilityInspection:
        try:
            version_process = self._run_metadata("--version")
            language_process = self._run_metadata(
                "--list-langs",
                *(
                    ("--tessdata-dir", str(self._configured_tessdata_directory))
                    if self._configured_tessdata_directory is not None
                    else ()
                ),
            )
        except subprocess.TimeoutExpired:
            return _failed_inspection(
                "analise.ocr_capacidade_timeout",
                "A consulta de capacidade do OCR excedeu o tempo limite; o OCR foi desativado.",
            )
        except (OSError, subprocess.SubprocessError):
            return _failed_inspection(
                "analise.ocr_capacidade_indisponivel",
                "A capacidade do motor OCR não pôde ser consultada; o OCR foi desativado.",
            )

        try:
            version = _normalize_version(_completed_stdout(version_process))
            language_output = _completed_stdout(language_process)
            available_languages = _parse_available_languages(language_output)
            selected_languages = _select_languages(
                self._requested_languages,
                available_languages,
            )
        except ValueError:
            return _failed_inspection(
                "analise.ocr_capacidade_invalida",
                "O motor OCR retornou uma capacidade inválida; o OCR foi desativado.",
            )

        try:
            tessdata_directory = _locate_tessdata_directory(
                language_output,
                configured=self._configured_tessdata_directory,
                executable=self._executable,
            )
            traineddata = _traineddata_identities(tessdata_directory, selected_languages)
        except (OSError, ValueError):
            return _failed_inspection(
                "analise.ocr_traineddata_indisponivel",
                "Os dados treinados selecionados não puderam ser identificados; "
                "o OCR foi desativado.",
            )

        capability = CapacidadeMotorOcr(
            implementacao=self.nome,
            versao=version,
            idiomas=selected_languages,
            dados_treinados=traineddata,
            parametros=self._semantic_parameters(),
        )
        return _CapabilityInspection(
            result=ResultadoConsultaCapacidadeOcr(capacidade=capability),
            tessdata_directory=tessdata_directory,
        )

    def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
        return self._recognize(pagina, page_segmentation_mode=_GENERAL_PSM)

    def reconhecer_identificador(
        self,
        pagina: PaginaRasterOcr,
    ) -> tuple[TrechoTextoOcr, ...]:
        return self._recognize(
            pagina,
            page_segmentation_mode=_IDENTIFIER_PSM,
            character_whitelist=_IDENTIFIER_WHITELIST,
        )

    def reconhecer_rotulo_operacional(
        self,
        pagina: PaginaRasterOcr,
    ) -> tuple[TrechoTextoOcr, ...]:
        return self._recognize(
            pagina,
            page_segmentation_mode=_OPERATIONAL_LABEL_PSM,
            character_whitelist=_TECHNICAL_WHITELIST,
        )

    def reconhecer_bloco_operacional(
        self,
        pagina: PaginaRasterOcr,
    ) -> tuple[TrechoTextoOcr, ...]:
        return self._recognize(
            pagina,
            page_segmentation_mode=_OPERATIONAL_BLOCK_PSM,
            character_whitelist=_TECHNICAL_WHITELIST,
        )

    def _recognize(
        self,
        pagina: PaginaRasterOcr,
        *,
        page_segmentation_mode: int,
        character_whitelist: str | None = None,
    ) -> tuple[TrechoTextoOcr, ...]:
        inspection = self._inspection
        capability = inspection.result.capacidade
        if capability is None or inspection.tessdata_directory is None:
            raise RuntimeError("Capacidade do motor OCR indisponível")
        arguments = [
            str(self._executable),
            "stdin",
            "stdout",
            "--tessdata-dir",
            str(inspection.tessdata_directory),
            "-l",
            "+".join(capability.idiomas),
            "--oem",
            str(self._oem),
            "--psm",
            str(page_segmentation_mode),
        ]
        if character_whitelist is not None:
            arguments.extend(("-c", f"tessedit_char_whitelist={character_whitelist}"))
        arguments.append("tsv")
        completed = subprocess.run(
            tuple(arguments),
            input=_ppm_bytes(pagina),
            capture_output=True,
            check=True,
            timeout=self._recognition_timeout_seconds,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return _parse_tsv(
            _completed_stdout(completed),
            width=pagina.largura_pixels,
            height=pagina.altura_pixels,
        )

    def _run_metadata(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (str(self._executable), *arguments),
            capture_output=True,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self._capability_timeout_seconds,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _semantic_parameters(self) -> ExtraAttributes:
        return (
            ("agregacao_tsv", "linhas-logicas-v1"),
            ("formato_saida", "tsv"),
            ("oem", self._oem),
            ("preprocessamento_raster", "ppm-p6-rgb-sem-alpha-v1"),
            ("psm_bloco_operacional", _OPERATIONAL_BLOCK_PSM),
            ("psm_geral", _GENERAL_PSM),
            ("psm_identificador", _IDENTIFIER_PSM),
            ("psm_rotulo_operacional", _OPERATIONAL_LABEL_PSM),
            ("timeout_reconhecimento_segundos", self._recognition_timeout_seconds),
            ("whitelist_identificador", _IDENTIFIER_WHITELIST),
            ("whitelist_tecnica", _TECHNICAL_WHITELIST),
        )


def _failed_inspection(code: str, message: str) -> _CapabilityInspection:
    return _CapabilityInspection(
        ResultadoConsultaCapacidadeOcr(
            capacidade=None,
            diagnosticos=(
                DiagnosticoAnalise(
                    codigo=code,
                    mensagem=message,
                    extrator="ocr-capacidade",
                ),
            ),
        )
    )


def _parse_requested_languages(language: str | None) -> tuple[str, ...] | None:
    if language is None:
        return None
    selected = tuple(item.strip() for item in language.split("+"))
    if not selected or any(not item for item in selected) or len(set(selected)) != len(selected):
        raise ValueError("Idiomas do Tesseract devem ser únicos e separados por '+'")
    return selected


def _normalize_version(output: str) -> str:
    match = _VERSION_PATTERN.search(output)
    if match is None:
        raise ValueError("Versão do Tesseract ausente")
    return match.group(1).lower()


def _parse_available_languages(output: str) -> frozenset[str]:
    languages = frozenset(
        line.strip()
        for line in output.splitlines()
        if line.strip() and not line.strip().lower().startswith("list of available languages")
    )
    if not languages:
        raise ValueError("Nenhum idioma disponível no Tesseract")
    return languages


def _select_languages(
    requested: tuple[str, ...] | None,
    available: frozenset[str],
) -> tuple[str, ...]:
    if requested is not None:
        if any(language not in available for language in requested):
            raise ValueError("Idioma solicitado não está disponível")
        return requested
    selected = tuple(language for language in _PREFERRED_LANGUAGES if language in available)
    if not selected:
        raise ValueError("Nenhum idioma preferencial está disponível")
    return selected


def _resolve_configured_tessdata_directory(directory: Path | None) -> Path | None:
    if directory is None:
        return None
    resolved = directory.expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("Diretório tessdata inválido")
    return resolved


def _locate_tessdata_directory(
    language_output: str,
    *,
    configured: Path | None,
    executable: Path,
) -> Path:
    if configured is not None:
        return configured
    for line in language_output.splitlines():
        if not line.strip().lower().startswith("list of available languages"):
            continue
        if match := _QUOTED_DIRECTORY_PATTERN.search(line):
            candidate = Path(match.group(1)).expanduser()
            if candidate.is_dir():
                return candidate.resolve()
    fallback = executable.parent / "tessdata"
    if fallback.is_dir():
        return fallback.resolve()
    raise ValueError("Diretório tessdata não identificado")


def _traineddata_identities(
    directory: Path,
    languages: tuple[str, ...],
) -> tuple[IdentidadeDadosTreinadosOcr, ...]:
    root = directory.resolve(strict=True)
    identities = []
    for language in languages:
        target = (root / f"{language}.traineddata").resolve(strict=True)
        target.relative_to(root)
        if not target.is_file():
            raise ValueError("traineddata inválido")
        digest = sha256()
        with target.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        identities.append(IdentidadeDadosTreinadosOcr(idioma=language, sha256=digest.hexdigest()))
    return tuple(identities)


def _completed_stdout(
    completed: subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes],
) -> str:
    output = completed.stdout
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return str(output or "")


def _best_available_language(executable: Path) -> str:
    """Compatibilidade: prefira português técnico e mantenha inglês quando disponível."""
    try:
        completed = subprocess.run(
            (str(executable), "--list-langs"),
            capture_output=True,
            check=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        available = _parse_available_languages(_completed_stdout(completed))
        selected = _select_languages(None, available)
    except (OSError, subprocess.SubprocessError, ValueError):
        return "eng"
    return "+".join(selected)


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
    lines = tsv.splitlines()
    if not lines:
        return ()
    header = lines[0].split("\t")
    for raw_line in lines[1:]:
        values = raw_line.split("\t", maxsplit=len(header) - 1)
        if len(values) != len(header):
            continue
        row = dict(zip(header, values, strict=True))
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

    recognized_lines = []
    for key in sorted(groups):
        words = groups[key]
        left = min(int(word["left"]) for word in words)
        top = min(int(word["top"]) for word in words)
        right = max(int(word["left"]) + int(word["width"]) for word in words)
        bottom = max(int(word["top"]) + int(word["height"]) for word in words)
        confidence = sum(float(word["conf"]) for word in words) / (100 * len(words))
        recognized_lines.append(
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
    return tuple(recognized_lines)
