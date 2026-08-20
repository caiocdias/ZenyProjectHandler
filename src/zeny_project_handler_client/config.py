"""Configuração exclusivamente visual e de rede do cliente."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APPLICATION_NAME = "Zeny Project Handler"
ORGANIZATION_NAME = "Zeny"
DATA_DIR_ENVIRONMENT_VARIABLE = "ZENY_DATA_DIR"
LOG_LEVEL_ENVIRONMENT_VARIABLE = "ZENY_LOG_LEVEL"
CLIENT_SERVER_URL_ENVIRONMENT_VARIABLE = "ZENY_CLIENT_SERVER_URL"
DEFAULT_CLIENT_SERVER_URL = "http://127.0.0.1:8000"
DEFAULT_PDF_TILE_CACHE_MAX_BYTES = 128 * 1024 * 1024
VALID_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


def default_data_directory(environment: Mapping[str, str] | None = None) -> Path:
    """Retorne a pasta local de preferências do cliente sem criá-la."""
    values = os.environ if environment is None else environment
    local_app_data = values.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "ZenyProjectHandler"
    return Path.home() / "AppData" / "Local" / "ZenyProjectHandler"


@dataclass(frozen=True, slots=True)
class ClientSettings:
    """Opções locais que não possuem estado de negócio."""

    data_directory: Path
    log_level: str = "INFO"
    application_name: str = APPLICATION_NAME
    organization_name: str = ORGANIZATION_NAME
    pdf_render_dpi: int = 600
    pdf_render_max_pixels: int = 8_000_000
    pdf_render_max_bytes: int = 64 * 1024 * 1024
    pdf_tile_cache_max_bytes: int = DEFAULT_PDF_TILE_CACHE_MAX_BYTES
    development_server_url: str = DEFAULT_CLIENT_SERVER_URL

    def __post_init__(self) -> None:
        normalized_level = self.log_level.upper()
        if normalized_level not in VALID_LOG_LEVELS:
            allowed = ", ".join(sorted(VALID_LOG_LEVELS))
            raise ValueError(f"Nível de log inválido. Valores aceitos: {allowed}")
        if not 36 <= self.pdf_render_dpi <= 600:
            raise ValueError("DPI de renderização deve estar entre 36 e 600")
        for value, message in (
            (self.pdf_render_max_pixels, "O orçamento de pixels deve ser positivo"),
            (self.pdf_render_max_bytes, "O orçamento de bytes deve ser positivo"),
            (self.pdf_tile_cache_max_bytes, "O limite do cache visual deve ser positivo"),
        ):
            if value <= 0:
                raise ValueError(message)
        object.__setattr__(self, "log_level", normalized_level)
        object.__setattr__(self, "data_directory", self.data_directory.expanduser().resolve())

    @property
    def ui_state_path(self) -> Path:
        return self.data_directory / "ui-state.ini"

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> ClientSettings:
        values = os.environ if environment is None else environment
        configured_data_directory = values.get(DATA_DIR_ENVIRONMENT_VARIABLE)
        return cls(
            data_directory=(
                Path(configured_data_directory)
                if configured_data_directory
                else default_data_directory(values)
            ),
            log_level=values.get(LOG_LEVEL_ENVIRONMENT_VARIABLE, "INFO"),
            pdf_render_dpi=_integer(values, "ZENY_PDF_RENDER_DPI", 600),
            pdf_render_max_pixels=_integer(values, "ZENY_PDF_RENDER_MAX_PIXELS", 8_000_000),
            pdf_render_max_bytes=_integer(values, "ZENY_PDF_RENDER_MAX_BYTES", 64 * 1024 * 1024),
            pdf_tile_cache_max_bytes=_integer(
                values,
                "ZENY_PDF_TILE_CACHE_MAX_BYTES",
                DEFAULT_PDF_TILE_CACHE_MAX_BYTES,
            ),
            development_server_url=values.get(
                CLIENT_SERVER_URL_ENVIRONMENT_VARIABLE,
                DEFAULT_CLIENT_SERVER_URL,
            ),
        )


@dataclass(frozen=True, slots=True)
class ClientRenderBudget:
    """Limites puramente visuais aplicados aos rasters recebidos."""

    limite_pixels: int
    limite_bytes: int

    def __post_init__(self) -> None:
        if self.limite_pixels <= 0 or self.limite_bytes <= 0:
            raise ValueError("O orçamento visual deve ser positivo")


def _integer(values: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(values.get(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} deve ser um número inteiro") from error
