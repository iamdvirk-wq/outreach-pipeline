from alembic import context

from app.db import Base, engine
from app import models  # noqa: F401  (registers the tables)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    connectable = context.config.attributes.get("connection") or engine
    with connectable.connect() as connection:
        # render_as_batch lets SQLite alter existing tables
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
