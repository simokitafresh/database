import importlib


def test_import_services_normalize():
    import app.services

    importlib.reload(app.services)
    from app.services import normalize

    assert hasattr(normalize, "normalize_symbol")
