from pathlib import Path


def test_entrypoint_uses_exec_for_gunicorn():
    p = Path("docker/entrypoint.sh")
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "alembic upgrade head" in text
    assert "exec gunicorn" in text
