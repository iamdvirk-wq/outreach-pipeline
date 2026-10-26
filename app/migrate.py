"""Run database migrations (Alembic) so the database matches the code.

This runs automatically every time the app starts, so you never need to run
it yourself. Developers: after changing app/models.py, create a migration with
    alembic revision --autogenerate -m "describe the change"
"""
from alembic import command
from alembic.config import Config

from app import config


def alembic_config() -> Config:
    cfg = Config(str(config.BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(config.BASE_DIR / "migrations"))
    return cfg


def upgrade_database() -> None:
    command.upgrade(alembic_config(), "head")
