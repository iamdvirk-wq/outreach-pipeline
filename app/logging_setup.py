"""Log to logs/app.log (rotated) and the console, with secrets masked."""
import logging
from logging.handlers import RotatingFileHandler

from app import config


class RedactSecrets(logging.Filter):
    """Replace any API key or password from .env with ***** before it is written."""

    def filter(self, record: logging.LogRecord) -> bool:
        secrets = config.secret_values()
        if secrets:
            msg = record.getMessage()
            for s in secrets:
                msg = msg.replace(s, "*****")
            record.msg, record.args = msg, None
        return True


def setup_logging() -> None:
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(config.LOG_DIR / "app.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    console = logging.StreamHandler()
    for h in (file_handler, console):
        h.setFormatter(fmt)
        h.addFilter(RedactSecrets())
        root.addHandler(h)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
