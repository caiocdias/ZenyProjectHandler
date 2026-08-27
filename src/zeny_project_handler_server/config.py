"""Configuração fail-closed do processo servidor."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from zeny_project_handler.config import (
    DEFAULT_PDF_RENDER_MAX_BYTES,
    DEFAULT_PDF_RENDER_MAX_PIXELS,
    VALID_LOG_LEVELS,
    AppSettings,
)

PASSWORD_ENVIRONMENT_VARIABLE = "ZENY_SERVER_PASSWORD"
HOST_ENVIRONMENT_VARIABLE = "ZENY_SERVER_HOST"
PORT_ENVIRONMENT_VARIABLE = "ZENY_SERVER_PORT"
DATA_DIRECTORY_ENVIRONMENT_VARIABLE = "ZENY_SERVER_DATA_DIR"
LOG_LEVEL_ENVIRONMENT_VARIABLE = "ZENY_SERVER_LOG_LEVEL"
UPLOAD_MAX_BYTES_ENVIRONMENT_VARIABLE = "ZENY_SERVER_UPLOAD_MAX_BYTES"
RENDER_DPI_ENVIRONMENT_VARIABLE = "ZENY_SERVER_RENDER_DPI"
RENDER_MAX_PIXELS_ENVIRONMENT_VARIABLE = "ZENY_SERVER_RENDER_MAX_PIXELS"
RENDER_MAX_BYTES_ENVIRONMENT_VARIABLE = "ZENY_SERVER_RENDER_MAX_BYTES"
VIEWER_SESSION_TTL_ENVIRONMENT_VARIABLE = "ZENY_SERVER_VIEWER_SESSION_TTL_SECONDS"
VIEWER_MAX_FILES_ENVIRONMENT_VARIABLE = "ZENY_SERVER_VIEWER_MAX_FILES"
JOB_RETENTION_ENVIRONMENT_VARIABLE = "ZENY_SERVER_JOB_RETENTION_SECONDS"
JOB_MAX_RETAINED_ENVIRONMENT_VARIABLE = "ZENY_SERVER_JOB_MAX_RETAINED"
TRANSFER_TTL_ENVIRONMENT_VARIABLE = "ZENY_SERVER_TRANSFER_TTL_SECONDS"
MARKET_SQLSERVER_CONNECTION_STRING_ENVIRONMENT_VARIABLE = "ZENY_MARKET_SQLSERVER_CONNECTION_STRING"
MARKET_SQLSERVER_TIMEOUT_ENVIRONMENT_VARIABLE = "ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS"

PASSWORD_PLACEHOLDER = "troque-por-uma-senha-longa-e-aleatoria"
MARKET_SQLSERVER_CONNECTION_PLACEHOLDER = "troque-por-uma-string-de-conexao-sql-server"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_DATA_DIRECTORY = Path("/data")
DEFAULT_UPLOAD_MAX_BYTES = 256 * 1024 * 1024
DEFAULT_RENDER_DPI = 600
DEFAULT_VIEWER_SESSION_TTL_SECONDS = 15 * 60
DEFAULT_VIEWER_MAX_FILES = 20
DEFAULT_JOB_RETENTION_SECONDS = 24 * 60 * 60
DEFAULT_JOB_MAX_RETAINED = 100
DEFAULT_TRANSFER_TTL_SECONDS = 60 * 60
DEFAULT_MARKET_SQLSERVER_TIMEOUT_SECONDS = 15


@dataclass(frozen=True, slots=True)
class ServerSettings:
    """Valores imutáveis necessários para iniciar um único worker do servidor."""

    password: str = field(repr=False)
    market_sqlserver_connection_string: str = field(repr=False)
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    data_directory: Path = DEFAULT_DATA_DIRECTORY
    log_level: str = "INFO"
    upload_max_bytes: int = DEFAULT_UPLOAD_MAX_BYTES
    render_dpi: int = DEFAULT_RENDER_DPI
    render_max_pixels: int = DEFAULT_PDF_RENDER_MAX_PIXELS
    render_max_bytes: int = DEFAULT_PDF_RENDER_MAX_BYTES
    viewer_session_ttl_seconds: int = DEFAULT_VIEWER_SESSION_TTL_SECONDS
    viewer_max_files: int = DEFAULT_VIEWER_MAX_FILES
    job_retention_seconds: int = DEFAULT_JOB_RETENTION_SECONDS
    job_max_retained: int = DEFAULT_JOB_MAX_RETAINED
    transfer_ttl_seconds: int = DEFAULT_TRANSFER_TTL_SECONDS
    market_sqlserver_timeout_seconds: int = field(
        default=DEFAULT_MARKET_SQLSERVER_TIMEOUT_SECONDS,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not self.password.strip() or self.password.strip() == PASSWORD_PLACEHOLDER:
            raise ValueError(
                "ZENY_SERVER_PASSWORD é obrigatória e deve ser diferente do placeholder"
            )
        if (
            not self.market_sqlserver_connection_string.strip()
            or self.market_sqlserver_connection_string.strip()
            == MARKET_SQLSERVER_CONNECTION_PLACEHOLDER
        ):
            raise ValueError(
                "ZENY_MARKET_SQLSERVER_CONNECTION_STRING é obrigatória e deve ser "
                "diferente do placeholder"
            )
        normalized_host = self.host.strip()
        if not _valid_host(normalized_host):
            raise ValueError("ZENY_SERVER_HOST deve ser um host ou endereço IP sem esquema")
        if isinstance(self.port, bool) or not 1 <= self.port <= 65_535:
            raise ValueError("ZENY_SERVER_PORT deve estar entre 1 e 65535")
        normalized_level = self.log_level.strip().upper()
        if normalized_level not in VALID_LOG_LEVELS:
            allowed = ", ".join(sorted(VALID_LOG_LEVELS))
            raise ValueError(f"ZENY_SERVER_LOG_LEVEL inválido. Valores aceitos: {allowed}")
        if not 36 <= self.render_dpi <= 600:
            raise ValueError("ZENY_SERVER_RENDER_DPI deve estar entre 36 e 600")
        _require_positive(self.upload_max_bytes, UPLOAD_MAX_BYTES_ENVIRONMENT_VARIABLE)
        _require_positive(self.render_max_pixels, RENDER_MAX_PIXELS_ENVIRONMENT_VARIABLE)
        _require_positive(self.render_max_bytes, RENDER_MAX_BYTES_ENVIRONMENT_VARIABLE)
        _require_positive(
            self.viewer_session_ttl_seconds,
            VIEWER_SESSION_TTL_ENVIRONMENT_VARIABLE,
        )
        _require_positive(self.viewer_max_files, VIEWER_MAX_FILES_ENVIRONMENT_VARIABLE)
        _require_positive(self.job_retention_seconds, JOB_RETENTION_ENVIRONMENT_VARIABLE)
        _require_positive(self.job_max_retained, JOB_MAX_RETAINED_ENVIRONMENT_VARIABLE)
        _require_positive(self.transfer_ttl_seconds, TRANSFER_TTL_ENVIRONMENT_VARIABLE)
        _require_positive(
            self.market_sqlserver_timeout_seconds,
            MARKET_SQLSERVER_TIMEOUT_ENVIRONMENT_VARIABLE,
        )
        object.__setattr__(self, "host", normalized_host)
        object.__setattr__(self, "log_level", normalized_level)
        object.__setattr__(
            self,
            "data_directory",
            self.data_directory.expanduser().resolve(),
        )

    def core_settings(self) -> AppSettings:
        """Projete somente opções não sensíveis para a composição compartilhada."""
        return AppSettings(
            data_directory=self.data_directory,
            log_level=self.log_level,
            pdf_render_dpi=self.render_dpi,
            pdf_render_max_pixels=self.render_max_pixels,
            pdf_render_max_bytes=self.render_max_bytes,
        )

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> ServerSettings:
        """Leia apenas variáveis documentadas, recusando segredo ausente ou inseguro."""
        values = os.environ if environment is None else environment
        return cls(
            password=values.get(PASSWORD_ENVIRONMENT_VARIABLE, ""),
            market_sqlserver_connection_string=values.get(
                MARKET_SQLSERVER_CONNECTION_STRING_ENVIRONMENT_VARIABLE,
                "",
            ),
            host=values.get(HOST_ENVIRONMENT_VARIABLE, DEFAULT_HOST),
            port=_integer_setting(values, PORT_ENVIRONMENT_VARIABLE, DEFAULT_PORT),
            data_directory=Path(
                values.get(DATA_DIRECTORY_ENVIRONMENT_VARIABLE, str(DEFAULT_DATA_DIRECTORY))
            ),
            log_level=values.get(LOG_LEVEL_ENVIRONMENT_VARIABLE, "INFO"),
            upload_max_bytes=_integer_setting(
                values,
                UPLOAD_MAX_BYTES_ENVIRONMENT_VARIABLE,
                DEFAULT_UPLOAD_MAX_BYTES,
            ),
            render_dpi=_integer_setting(
                values,
                RENDER_DPI_ENVIRONMENT_VARIABLE,
                DEFAULT_RENDER_DPI,
            ),
            render_max_pixels=_integer_setting(
                values,
                RENDER_MAX_PIXELS_ENVIRONMENT_VARIABLE,
                DEFAULT_PDF_RENDER_MAX_PIXELS,
            ),
            render_max_bytes=_integer_setting(
                values,
                RENDER_MAX_BYTES_ENVIRONMENT_VARIABLE,
                DEFAULT_PDF_RENDER_MAX_BYTES,
            ),
            viewer_session_ttl_seconds=_integer_setting(
                values,
                VIEWER_SESSION_TTL_ENVIRONMENT_VARIABLE,
                DEFAULT_VIEWER_SESSION_TTL_SECONDS,
            ),
            viewer_max_files=_integer_setting(
                values,
                VIEWER_MAX_FILES_ENVIRONMENT_VARIABLE,
                DEFAULT_VIEWER_MAX_FILES,
            ),
            job_retention_seconds=_integer_setting(
                values,
                JOB_RETENTION_ENVIRONMENT_VARIABLE,
                DEFAULT_JOB_RETENTION_SECONDS,
            ),
            job_max_retained=_integer_setting(
                values,
                JOB_MAX_RETAINED_ENVIRONMENT_VARIABLE,
                DEFAULT_JOB_MAX_RETAINED,
            ),
            transfer_ttl_seconds=_integer_setting(
                values,
                TRANSFER_TTL_ENVIRONMENT_VARIABLE,
                DEFAULT_TRANSFER_TTL_SECONDS,
            ),
            market_sqlserver_timeout_seconds=_integer_setting(
                values,
                MARKET_SQLSERVER_TIMEOUT_ENVIRONMENT_VARIABLE,
                DEFAULT_MARKET_SQLSERVER_TIMEOUT_SECONDS,
            ),
        )


def _integer_setting(values: Mapping[str, str], name: str, default: int) -> int:
    raw_value = values.get(name, str(default))
    try:
        return int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} deve ser um número inteiro") from error


def _require_positive(value: int, name: str) -> None:
    if isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} deve ser um número inteiro positivo")


def _valid_host(value: str) -> bool:
    return bool(
        value
        and len(value) <= 253
        and "://" not in value
        and "/" not in value
        and "\\" not in value
        and not any(character.isspace() for character in value)
    )
