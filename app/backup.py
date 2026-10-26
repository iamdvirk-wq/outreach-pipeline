"""Daily backups of the database and the do-not-contact file.

Backups go to data/backups/<date>/ and the newest 14 days are kept.
"""
import logging
import shutil
import sqlite3
from datetime import date

from app import config

log = logging.getLogger(__name__)


def run_backup(force: bool = False) -> str | None:
    """Back up today's data unless a backup for today already exists."""
    folder = config.BACKUP_DIR / date.today().isoformat()
    if folder.exists() and not force:
        return None
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if config.DATABASE_PATH.exists():
            # sqlite's backup API gives a consistent copy even while the app is running
            src = sqlite3.connect(config.DATABASE_PATH)
            dst = sqlite3.connect(folder / config.DATABASE_PATH.name)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
        if config.SUPPRESSION_FILE.exists():
            shutil.copy2(config.SUPPRESSION_FILE, folder / config.SUPPRESSION_FILE.name)
        prune_old_backups()
        log.info("Backup written to %s", folder)
        return str(folder)
    except Exception:
        log.exception("Backup failed")
        return None


def prune_old_backups() -> None:
    folders = sorted(p for p in config.BACKUP_DIR.iterdir() if p.is_dir())
    for old in folders[: -config.BACKUP_KEEP_DAYS]:
        shutil.rmtree(old, ignore_errors=True)
