from app.core.config import Settings


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("API_MAX_SYMBOLS", "123")
    settings = Settings()
    assert settings.API_MAX_SYMBOLS == 123


def test_settings_contains_all_keys():
    settings = Settings()
    expected_keys = {
        "APP_ENV",
        "DATABASE_URL",
        "API_MAX_SYMBOLS",
        "API_MAX_ROWS",
        "YF_REFETCH_DAYS",
        "YF_REQ_CONCURRENCY",
        "FETCH_TIMEOUT_SECONDS",
        "REQUEST_TIMEOUT_SECONDS",
        "CORS_ALLOW_ORIGINS",
        "LOG_LEVEL",
    }
    assert expected_keys <= settings.model_dump().keys()
