"""Test setup: point the whole app at a throwaway folder before it is imported,
so tests can never touch your real database or do-not-contact list."""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="outreach-tests-"))
os.environ.update(
    DATA_DIR=str(_tmp / "data"),
    DATABASE_PATH=str(_tmp / "data" / "test.db"),
    BACKUP_DIR=str(_tmp / "data" / "backups"),
    SUPPRESSION_FILE=str(_tmp / "suppression" / "do_not_contact.csv"),
    LOG_DIR=str(_tmp / "logs"),
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app, startup  # noqa: E402

startup()


@pytest.fixture(autouse=True)
def clean_db():
    """Empty every table and the suppression file before each test."""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    config.SUPPRESSION_FILE.unlink(missing_ok=True)
    yield


@pytest.fixture
def session():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    with TestClient(app, base_url=f"http://localhost:{config.PORT}") as c:
        c.headers["Origin"] = f"http://localhost:{config.PORT}"
        yield c
