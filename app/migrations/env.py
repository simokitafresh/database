import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# NOTE: app.db.base から Declarative Base を import（モデルの Metadata 集約）
try:
    from app.db.base import Base  # type: ignore
except Exception:
    # プロジェクト構成が異なる場合はここを調整
    from app.db.models import Base  # fallback

# Alembic Config オブジェクトは .ini を表す
config = context.config

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

    x_args = context.get_x_argument(asdict=True)
    if "db_url" in x_args and x_args["db_url"]:
        return x_args["db_url"]

    env_url = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    return config.get_main_option("sqlalchemy.url")


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

