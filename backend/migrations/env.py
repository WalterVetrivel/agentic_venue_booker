from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, event

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.db import Base, engine

# Migrations get their own engine with foreign keys OFF. SQLite batch migrations copy a
# table, drop the original and rename the copy; with foreign keys ON, dropping the original
# would cascade-delete every child row (equipment, aliases, ...).
migration_engine = create_engine(engine.url)


@event.listens_for(migration_engine, "connect")
def _foreign_keys_off(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=OFF")
    cur.close()


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_name(name, type_, parent_names) -> bool:
    """FTS5 tables are created in raw SQL; autogenerate must not try to drop them."""
    return not (type_ == "table" and name and name.startswith("doc_chunks_fts"))


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with migration_engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
