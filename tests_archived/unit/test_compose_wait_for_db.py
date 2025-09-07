from pathlib import Path

import yaml


def test_compose_has_healthcheck_and_condition():
    compose = Path("docker-compose.yml")
    text = compose.read_text(encoding="utf-8")
    assert "services:" in text
    data = yaml.safe_load(text)
    # Postgres health check
    postgres = data["services"]["postgres"]
    assert "healthcheck" in postgres
    assert "pg_isready" in postgres["healthcheck"]["test"][1]
    # API depends on postgres service being healthy
    api_depends = data["services"]["api"]["depends_on"]["postgres"]
    assert api_depends["condition"] == "service_healthy"
