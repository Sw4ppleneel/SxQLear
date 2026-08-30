from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the backend package importable regardless of cwd (matches how
# uvicorn/pytest are invoked from the `backend/` directory).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from db import orm_models  # noqa: E402,F401 — registers models on Base.metadata
from db.session import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Use the same local-first SQLite path the app itself uses (~/.sxqlear/memory.db
# via settings.memory_db_path) rather than a separate hardcoded alembic.ini URL —
# there is only ever one memory.db, and it should not be possible for the two
# to drift.
config.set_main_option("sqlalchemy.url", f"sqlite:///{settings.memory_db_path}")


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
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
            render_as_batch=True,  # SQLite can't ALTER COLUMN directly; batch mode works around it
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
