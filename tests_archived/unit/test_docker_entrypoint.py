from pathlib import Path


def test_dockerfile_has_entrypoint():
    dockerfile = Path("docker/Dockerfile")
    assert dockerfile.exists()
    content = dockerfile.read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["./docker/entrypoint.sh"]' in content


def test_entrypoint_contains_commands():
    entrypoint = Path("docker/entrypoint.sh")
    assert entrypoint.exists()
    text = entrypoint.read_text(encoding="utf-8")
    assert "alembic upgrade head" in text
    assert "gunicorn" in text
