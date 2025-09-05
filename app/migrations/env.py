import os
import sys
from logging.config import fileConfig
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
def _normalize_sync_dsn(url: str) -> str:
    """Normalize DSN for Alembic (sync driver required).

    - Convert asyncpg DSN to psycopg
    - Convert plain postgresql scheme to psycopg driver
    """
    if not url:
        return url
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


env_url = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")
if env_url:
    env_url = _normalize_sync_dsn(env_url)
    # Avoid ConfigParser interpolation by escaping % as %%
    env_url_escaped = env_url.replace('%', '%%')
    config.set_main_option("sqlalchemy.url", env_url_escaped)

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

    new_url = _normalize_sync_dsn(url)
    if new_url != url:
        # Avoid ConfigParser interpolation by escaping % as %% when setting option
        url_escaped = new_url.replace('%', '%%')
        config.set_main_option("sqlalchemy.url", url_escaped)
        url = new_url

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
    
    # Supabase 接続の最適化
    config_section = config.get_section(config.config_ini_section) or {}
    
    # Supabase用の接続設定
    if "supabase.com" in url:
        config_section.update({
            "sqlalchemy.connect_args": {
                "connect_timeout": 30,
                "command_timeout": 30,
                "server_settings": {
                    "application_name": "alembic-migration",
                    "jit": "off"
                }
            }
        })
    
    connectable = engine_from_config(
        config_section,
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
