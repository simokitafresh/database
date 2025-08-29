from app.core.config import Settings
from app.db.engine import create_engine_and_sessionmaker


def test_engine_uses_asyncpg_driver():
    settings = Settings()
    engine, _ = create_engine_and_sessionmaker(settings.DATABASE_URL)
    assert engine.url.drivername == "postgresql+asyncpg"
