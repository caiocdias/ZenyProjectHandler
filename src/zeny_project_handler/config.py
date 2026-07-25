"""Configurações locais da aplicação."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APPLICATION_NAME = "Zeny Project Handler"
ORGANIZATION_NAME = "Zeny"
DATA_DIR_ENVIRONMENT_VARIABLE = "ZENY_DATA_DIR"
LOG_LEVEL_ENVIRONMENT_VARIABLE = "ZENY_LOG_LEVEL"
PDF_RENDER_DPI_ENVIRONMENT_VARIABLE = "ZENY_PDF_RENDER_DPI"
DATABASE_FILE_NAME = "zeny-project-handler.sqlite3"
BACKUP_DIRECTORY_NAME = "backups"
ANALYSIS_CACHE_DIRECTORY_NAME = "cache/analysis"
VALID_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


def default_data_directory(environment: Mapping[str, str] | None = None) -> Path:
    """Retorne a pasta de dados adequada para o Windows, sem criá-la."""
    values = os.environ if environment is None else environment
    local_app_data = values.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "ZenyProjectHandler"
    return Path.home() / "AppData" / "Local" / "ZenyProjectHandler"


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Configuração imutável usada na composição da aplicação."""

    data_directory: Path
    log_level: str = "INFO"
    application_name: str = APPLICATION_NAME
    organization_name: str = ORGANIZATION_NAME
    pdf_render_dpi: int = 600

    def __post_init__(self) -> None:
        normalized_level = self.log_level.upper()
        if normalized_level not in VALID_LOG_LEVELS:
            allowed = ", ".join(sorted(VALID_LOG_LEVELS))
            raise ValueError(f"Nível de log inválido. Valores aceitos: {allowed}")
        if not 36 <= self.pdf_render_dpi <= 600:
            raise ValueError("DPI de renderização deve estar entre 36 e 600")
        object.__setattr__(self, "log_level", normalized_level)
        object.__setattr__(self, "data_directory", self.data_directory.expanduser().resolve())

    @property
    def database_path(self) -> Path:
        """Caminho canônico do banco local da aplicação."""
        return self.data_directory / DATABASE_FILE_NAME

    @property
    def backup_directory(self) -> Path:
        """Pasta reservada para snapshots atômicos do banco."""
        return self.data_directory / BACKUP_DIRECTORY_NAME

    @property
    def analysis_cache_directory(self) -> Path:
        """Cache derivado e descartável da extração nativa."""
        return self.data_directory / ANALYSIS_CACHE_DIRECTORY_NAME

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> AppSettings:
        """Carregue somente opções explicitamente suportadas do ambiente."""
        values = os.environ if environment is None else environment
        configured_data_directory = values.get(DATA_DIR_ENVIRONMENT_VARIABLE)
        data_directory = (
            Path(configured_data_directory)
            if configured_data_directory
            else default_data_directory(values)
        )
        return cls(
            data_directory=data_directory,
            log_level=values.get(LOG_LEVEL_ENVIRONMENT_VARIABLE, "INFO"),
            pdf_render_dpi=_pdf_render_dpi(values),
        )


def _pdf_render_dpi(values: Mapping[str, str]) -> int:
    raw_value = values.get(PDF_RENDER_DPI_ENVIRONMENT_VARIABLE, "600")
    try:
        return int(raw_value)
    except ValueError as error:
        raise ValueError("ZENY_PDF_RENDER_DPI deve ser um número inteiro") from error
