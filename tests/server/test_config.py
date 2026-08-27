from __future__ import annotations

from pathlib import Path

import pytest

from zeny_project_handler_server.config import (
    MARKET_SQLSERVER_CONNECTION_PLACEHOLDER,
    PASSWORD_PLACEHOLDER,
    ServerSettings,
)

MARKET_CONNECTION = "Driver=fake;Server=market.invalid;Uid=user;Pwd=secret"
ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize("password", ["", "   ", PASSWORD_PLACEHOLDER])
def test_server_refuses_missing_empty_or_placeholder_password(password: str) -> None:
    with pytest.raises(ValueError, match="ZENY_SERVER_PASSWORD"):
        ServerSettings.from_environment(
            {
                "ZENY_SERVER_PASSWORD": password,
                "ZENY_MARKET_SQLSERVER_CONNECTION_STRING": MARKET_CONNECTION,
            }
        )


@pytest.mark.parametrize("connection", ["", "   ", MARKET_SQLSERVER_CONNECTION_PLACEHOLDER])
def test_server_refuses_missing_empty_or_placeholder_market_connection(connection: str) -> None:
    with pytest.raises(ValueError, match="ZENY_MARKET_SQLSERVER_CONNECTION_STRING"):
        ServerSettings.from_environment(
            {
                "ZENY_SERVER_PASSWORD": "senha válida de teste",
                "ZENY_MARKET_SQLSERVER_CONNECTION_STRING": connection,
            }
        )


def test_server_settings_load_supported_runtime_values(tmp_path: Path) -> None:
    settings = ServerSettings.from_environment(
        {
            "ZENY_SERVER_PASSWORD": "senha longa de teste",
            "ZENY_MARKET_SQLSERVER_CONNECTION_STRING": MARKET_CONNECTION,
            "ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS": "7",
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
    assert settings.market_sqlserver_connection_string == MARKET_CONNECTION
    assert settings.market_sqlserver_timeout_seconds == 7
    assert "senha longa de teste" not in repr(settings)
    assert MARKET_CONNECTION not in repr(settings)
    assert "market_sqlserver_connection_string" not in repr(settings)
    assert "market_sqlserver_timeout_seconds" not in repr(settings)
    assert not hasattr(settings.core_settings(), "password")
    assert not hasattr(settings.core_settings(), "market_sqlserver_connection_string")
    assert not hasattr(settings.core_settings(), "market_sqlserver_timeout_seconds")


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
        ("ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS", "0", "MARKET_SQLSERVER_TIMEOUT_SECONDS"),
        ("ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS", "abc", "MARKET_SQLSERVER_TIMEOUT_SECONDS"),
    ],
)
def test_server_settings_reject_invalid_values(name: str, value: str, message: str) -> None:
    environment = {
        "ZENY_SERVER_PASSWORD": "senha válida de teste",
        "ZENY_MARKET_SQLSERVER_CONNECTION_STRING": MARKET_CONNECTION,
        name: value,
    }

    with pytest.raises(ValueError, match=message):
        ServerSettings.from_environment(environment)


def test_market_settings_are_propagated_to_every_compose_and_environment_example() -> None:
    compose_paths = (
        ROOT / "compose.yaml",
        ROOT / "compose.local.yaml",
        ROOT / "server" / "compose.release.yaml",
    )
    example_paths = (
        ROOT / ".env-example",
        ROOT / "server" / "env.release.example",
    )

    for path in compose_paths:
        content = path.read_text(encoding="utf-8")
        assert "${ZENY_MARKET_SQLSERVER_CONNECTION_STRING:?" in content
        assert "${ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS:-15}" in content
    for path in example_paths:
        content = path.read_text(encoding="utf-8")
        assert (
            f"ZENY_MARKET_SQLSERVER_CONNECTION_STRING={MARKET_SQLSERVER_CONNECTION_PLACEHOLDER}"
        ) in content
        assert "ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS=15" in content
