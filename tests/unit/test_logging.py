import json
import logging

from app.core.logging import configure_logging


def test_configure_logging_outputs_json(caplog):
    """Logs should be formatted as JSON containing level, name and message."""

    configure_logging()
    logging.getLogger().addHandler(caplog.handler)
    caplog.set_level(logging.INFO)
    logging.getLogger("test").info("hello")

    record = caplog.records[0]
    formatter = logging.getLogger().handlers[0].formatter
    log_line = formatter.format(record)
    data = json.loads(log_line)
    assert data["level"] == "INFO"
    assert data["name"] == "test"
    assert data["message"] == "hello"

