from pathlib import Path

import pytest

from zeny_project_handler.config import AppSettings, default_data_directory


def test_settings_load_supported_environment_values(tmp_path: Path) -> None:
    settings = AppSettings.from_environment(
        {
            "ZENY_DATA_DIR": str(tmp_path),
            "ZENY_LOG_LEVEL": "debug",
            "ZENY_PDF_RENDER_DPI": "200",
        }
    )

    assert settings.data_directory == tmp_path.resolve()
    assert settings.log_level == "DEBUG"
    assert settings.database_path == tmp_path.resolve() / "zeny-project-handler.sqlite3"
    assert settings.backup_directory == tmp_path.resolve() / "backups"
    assert settings.analysis_cache_directory == tmp_path.resolve() / "cache" / "analysis"
    assert settings.pdf_render_dpi == 200


def test_default_data_directory_uses_local_app_data() -> None:
    result = default_data_directory({"LOCALAPPDATA": "C:/temporary/local"})

    assert result == Path("C:/temporary/local/ZenyProjectHandler")


def test_settings_reject_invalid_log_level(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Nível de log inválido"):
        AppSettings(data_directory=tmp_path, log_level="verbose")


@pytest.mark.parametrize("value", ["texto", "20", "601"])
def test_settings_reject_invalid_pdf_dpi(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError, match=r"DPI|inteiro"):
        AppSettings.from_environment({"ZENY_DATA_DIR": str(tmp_path), "ZENY_PDF_RENDER_DPI": value})
