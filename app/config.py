"""Settings that come from the .env file (secrets, paths, mailbox details).

Everything you can change from the dashboard lives in the database instead
(see the Settings page). Values here are read once when the app starts.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _path(name: str, default: str) -> Path:
    p = Path(os.getenv(name, default))
    return p if p.is_absolute() else BASE_DIR / p


DATA_DIR = _path("DATA_DIR", "data")
DATABASE_PATH = _path("DATABASE_PATH", "data/outreach.db")
BACKUP_DIR = _path("BACKUP_DIR", "data/backups")
# Kept outside the database on purpose so it survives a database reset.
SUPPRESSION_FILE = _path("SUPPRESSION_FILE", "suppression/do_not_contact.csv")
LOG_DIR = _path("LOG_DIR", "logs")

TIMEZONE = os.getenv("TIMEZONE", "Australia/Sydney")
HOST = "127.0.0.1"  # local only: the dashboard has no login, so never expose it
PORT = int(os.getenv("PORT", "8000"))

DEFAULT_CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
BACKUP_KEEP_DAYS = 14

# Hard limits from the compliance rules. These are not editable in Settings.
MAX_DAILY_SEND_CAP = 50
MIN_SECONDS_BETWEEN_SENDS = 180

# Names of .env values that must never appear in logs.
SECRET_ENV_NAMES = [
    "ANTHROPIC_API_KEY",
    "GOOGLE_PAGESPEED_API_KEY",
    "GOOGLE_PLACES_API_KEY",
    "SMTP_PASSWORD",
    "IMAP_PASSWORD",
]


def secret_values() -> list[str]:
    return [v for n in SECRET_ENV_NAMES if (v := os.getenv(n)) and len(v) >= 4]


for d in (DATA_DIR, BACKUP_DIR, SUPPRESSION_FILE.parent, LOG_DIR, DATABASE_PATH.parent):
    d.mkdir(parents=True, exist_ok=True)
