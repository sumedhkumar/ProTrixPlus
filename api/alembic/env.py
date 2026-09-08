"""Alembic environment.

Target metadata is the *shared* metadata from ``protrix_contracts.db`` - the
same object api and worker map against - so ``alembic check`` is a real
model/DB drift gate.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from protrix_contracts.db import metadata as target_metadata
from protrix_contracts.db.session import normalize_database_url
from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

_url = os.environ.get("PROTRIX_DATABASE_URL")
if _url:
    config.set_main_option("sqlalchemy.url", normalize_database_url(_url))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=False,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
