import os
from logging.config import fileConfig
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure repo root is importable: migrations -> app -> <repo root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# NOTE: app.db.base から Declarative Base を import（モデルの Metadata 集約）
try:
    from app.db.base import Base  # preferred
except (ModuleNotFoundError, ImportError):
    # プロジェクト構成が異なる場合はここを調整
    from app.db.models import Base  # fallback if Base is defined here

# Alembic Config オブジェクトは .ini を表す
config = context.config
# --- inject DB URL from env (prefer ALEMBIC_DATABASE_URL, fallback to DATABASE_URL) ---
env_url = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")
if env_url:
    if env_url.startswith("postgresql+asyncpg://"):
        env_url = env_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    config.set_main_option("sqlalchemy.url", env_url)

# ログ設定
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_db_url() -> str:
    """
    優先順位:
      1) -x db_url=...（CLI からの上書き）
      2) 環境変数 ALEMBIC_DATABASE_URL
      3) 環境変数 DATABASE_URL
      4) alembic.ini の sqlalchemy.url
    """

    x_args = context.get_x_argument(as_dictionary=True)
    if "db_url" in x_args and x_args["db_url"]:
        url = x_args["db_url"]
    else:
        env_url = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")
        if env_url:
            url = env_url
        else:
            url = config.get_main_option("sqlalchemy.url")

    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        config.set_main_option("sqlalchemy.url", url)

    return url


def run_migrations_offline() -> None:
    url = _get_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _get_db_url()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=url,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
