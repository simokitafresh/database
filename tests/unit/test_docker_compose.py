from pathlib import Path
import yaml


def test_docker_compose_build_context():
    compose = Path("docker-compose.yml")
    assert compose.exists()
    data = yaml.safe_load(compose.read_text())
    assert data["services"]["api"]["build"]["context"] == "./"
