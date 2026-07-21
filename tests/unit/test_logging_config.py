import json
import logging
from pathlib import Path

from zeny_project_handler.config import AppSettings
from zeny_project_handler.logging_config import JsonFormatter, configure_logging


def test_json_formatter_exposes_only_the_supported_fields() -> None:
    record = logging.LogRecord(
        name="zeny_project_handler.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="aplicação iniciada",
        args=(),
        exc_info=None,
    )
    record.password = "não-deve-aparecer"

    payload = json.loads(JsonFormatter().format(record))

    assert set(payload) == {"timestamp", "level", "logger", "event"}
    assert payload["event"] == "aplicação iniciada"
    assert "não-deve-aparecer" not in json.dumps(payload)


def test_configure_logging_can_skip_file_creation(tmp_path: Path) -> None:
    settings = AppSettings(data_directory=tmp_path)

    logger = configure_logging(settings, write_to_file=False)

    assert logger.name == "zeny_project_handler"
    assert len(logger.handlers) == 1
    assert not (tmp_path / "logs").exists()
