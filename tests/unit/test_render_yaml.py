from pathlib import Path
import yaml


def test_render_yaml_has_healthcheck_and_start_command():
    render = Path("render.yaml")
    assert render.exists()
    data = yaml.safe_load(render.read_text())
    service = data["services"][0]
    assert service["healthCheckPath"] == "/healthz"
    assert service["startCommand"] == "./docker/entrypoint.sh"
    assert service["env"] == "docker"
    assert service["type"] == "web"

