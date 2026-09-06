import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from avito_reviewer.config import DatabaseConfig
from avito_reviewer.db.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Логи alembic по `alembic.ini`. `disable_existing_loggers=False` обязателен:
# миграции прогоняются на старте приложения (`app/main.py`), к этому моменту
# логгеры всех модулей уже созданы импортом роутеров, и умолчание `fileConfig`
# гасило их все разом — приложение после старта молчало в журнал целиком.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# `DB_DSN` (env or `.env`), same source the app itself reads at startup —
# `alembic.ini`'s `sqlalchemy.url` is left as a placeholder on purpose so a
# migration run always targets whatever the app would connect to, not a URL
# that quietly drifts from it.
config.set_main_option("sqlalchemy.url", DatabaseConfig().dsn)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
