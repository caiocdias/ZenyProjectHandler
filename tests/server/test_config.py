from __future__ import annotations

from pathlib import Path

import pytest

from zeny_project_handler_server.config import (
    PASSWORD_PLACEHOLDER,
    ServerSettings,
)


@pytest.mark.parametrize("password", ["", "   ", PASSWORD_PLACEHOLDER])
def test_server_refuses_missing_empty_or_placeholder_password(password: str) -> None:
    with pytest.raises(ValueError, match="ZENY_SERVER_PASSWORD"):
        ServerSettings.from_environment({"ZENY_SERVER_PASSWORD": password})


def test_server_settings_load_supported_runtime_values(tmp_path: Path) -> None:
    settings = ServerSettings.from_environment(
        {
            "ZENY_SERVER_PASSWORD": "senha longa de teste",
            "ZENY_SERVER_HOST": "127.0.0.1",
            "ZENY_SERVER_PORT": "9123",
            "ZENY_SERVER_DATA_DIR": str(tmp_path),
            "ZENY_SERVER_LOG_LEVEL": "warning",
            "ZENY_SERVER_UPLOAD_MAX_BYTES": "4096",
            "ZENY_SERVER_RENDER_DPI": "300",
            "ZENY_SERVER_RENDER_MAX_PIXELS": "12345",
            "ZENY_SERVER_RENDER_MAX_BYTES": "67890",
            "ZENY_SERVER_VIEWER_SESSION_TTL_SECONDS": "321",
            "ZENY_SERVER_VIEWER_MAX_FILES": "7",
            "ZENY_SERVER_JOB_RETENTION_SECONDS": "654",
            "ZENY_SERVER_JOB_MAX_RETAINED": "12",
        }
    )

    assert settings.host == "127.0.0.1"
    assert settings.port == 9123
    assert settings.data_directory == tmp_path.resolve()
    assert settings.log_level == "WARNING"
    assert settings.upload_max_bytes == 4096
    assert settings.render_dpi == 300
    assert settings.render_max_pixels == 12345
    assert settings.render_max_bytes == 67890
    assert settings.viewer_session_ttl_seconds == 321
    assert settings.viewer_max_files == 7
    assert settings.job_retention_seconds == 654
    assert settings.job_max_retained == 12
    assert "senha longa de teste" not in repr(settings)
    assert not hasattr(settings.core_settings(), "password")


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("ZENY_SERVER_HOST", "http://localhost", "HOST"),
        ("ZENY_SERVER_PORT", "0", "PORT"),
        ("ZENY_SERVER_PORT", "abc", "PORT"),
        ("ZENY_SERVER_LOG_LEVEL", "TRACE", "LOG_LEVEL"),
        ("ZENY_SERVER_UPLOAD_MAX_BYTES", "0", "UPLOAD_MAX_BYTES"),
        ("ZENY_SERVER_RENDER_DPI", "601", "RENDER_DPI"),
        ("ZENY_SERVER_RENDER_MAX_PIXELS", "-1", "RENDER_MAX_PIXELS"),
        ("ZENY_SERVER_RENDER_MAX_BYTES", "zero", "RENDER_MAX_BYTES"),
        ("ZENY_SERVER_VIEWER_SESSION_TTL_SECONDS", "0", "VIEWER_SESSION_TTL_SECONDS"),
        ("ZENY_SERVER_VIEWER_MAX_FILES", "-1", "VIEWER_MAX_FILES"),
        ("ZENY_SERVER_JOB_RETENTION_SECONDS", "0", "JOB_RETENTION_SECONDS"),
        ("ZENY_SERVER_JOB_MAX_RETAINED", "invalid", "JOB_MAX_RETAINED"),
    ],
)
def test_server_settings_reject_invalid_values(name: str, value: str, message: str) -> None:
    environment = {"ZENY_SERVER_PASSWORD": "senha válida de teste", name: value}

    with pytest.raises(ValueError, match=message):
        ServerSettings.from_environment(environment)
