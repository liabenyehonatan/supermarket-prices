# migrations/env.py

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from dotenv import load_dotenv

# Load .env so we can read DATABASE_URL
load_dotenv()

# This reads the alembic.ini config file
config = context.config

# Override the sqlalchemy.url with the one from .env
# This way your password is never hardcoded anywhere
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))

# Sets up logging so Alembic prints progress to your terminal
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# THIS IS THE CRITICAL LINE:
# We import our Base which knows about ALL our models.
# Alembic reads Base.metadata to discover every table
# we defined and generates the SQL to create them.
from app.db.base import Base
from app.db import models  # noqa: F401 — must import so models register themselves

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations without a live DB connection.
    Useful for generating SQL scripts to review.
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
    context.configure(
        connection=connection,
        target_metadata=target_metadata
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations with an async database connection.
    We need this because our engine is async.
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
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()