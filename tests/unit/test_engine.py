from app.core.config import Settings
from app.db.engine import create_engine_and_sessionmaker


def test_engine_uses_asyncpg_driver():
    settings = Settings()
    engine, _ = create_engine_and_sessionmaker(settings.DATABASE_URL)
    assert engine.url.drivername == "postgresql+asyncpg"


def test_create_engine_called_without_future(mocker):
    mock_create_engine = mocker.patch("app.db.engine.create_async_engine", return_value=object())
    mock_sessionmaker = mocker.patch("app.db.engine.async_sessionmaker")

    create_engine_and_sessionmaker("postgresql+asyncpg://user:pass@localhost/db")

    # Check that create_async_engine was called with expected parameters
    mock_create_engine.assert_called_once()
    call_args = mock_create_engine.call_args
    assert call_args[0][0] == "postgresql+asyncpg://user:pass@localhost/db"
    
    # Verify key parameters are present
    kwargs = call_args.kwargs
    assert 'connect_args' in kwargs
    assert 'echo' in kwargs
    assert 'pool_pre_ping' in kwargs
    assert 'pool_recycle' in kwargs
    assert 'pool_size' in kwargs
    assert 'max_overflow' in kwargs
    
    mock_sessionmaker.assert_called_once()
