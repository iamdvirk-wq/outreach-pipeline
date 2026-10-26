"""The FastAPI app: wires up pages, startup tasks and the scheduler."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app import config, dnc, pipeline
from app.backup import run_backup
from app.db import SessionLocal
from app.logging_setup import setup_logging
from app.migrate import upgrade_database
from app.routes import admin, dashboard, leads, research
from app.services import get_settings
from app.timeutil import LOCAL_TZ

log = logging.getLogger(__name__)

ALLOWED_ORIGINS = {f"http://{h}:{config.PORT}" for h in ("127.0.0.1", "localhost")}


def startup() -> None:
    """Bring the database up to date and restore the do-not-contact list."""
    upgrade_database()
    with SessionLocal() as session:
        get_settings(session)
        dnc.sync_from_file(session)
    pipeline.reset_interrupted()


def research_new_leads() -> None:
    pipeline.run_queue(only_if_auto=True)


def _safe_job(fn):
    """Scheduled jobs log their errors instead of stopping the scheduler."""

    def wrapper():
        try:
            fn()
        except Exception:
            log.exception("Scheduled job %s failed", fn.__name__)

    wrapper.__name__ = fn.__name__
    return wrapper


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    startup()
    run_backup()
    scheduler = BackgroundScheduler(timezone=LOCAL_TZ)
    scheduler.add_job(_safe_job(run_backup), "cron", hour=2, minute=17, id="daily_backup", misfire_grace_time=3600)
    scheduler.add_job(
        _safe_job(research_new_leads), "interval", minutes=10, id="research",
        next_run_time=datetime.now(LOCAL_TZ) + timedelta(seconds=30), max_instances=1, coalesce=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    log.info("Outreach dashboard running at http://localhost:%s", config.PORT)
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Outreach Pipeline", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.middleware("http")
async def block_cross_site_posts(request: Request, call_next):
    """Refuse form posts that come from another website (cross-site request forgery).

    The dashboard has no login because it only listens on this computer, so this
    stops a web page you visit from quietly pressing buttons in it.
    """
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        referer = request.headers.get("referer", "")
        if origin:
            ok = origin in ALLOWED_ORIGINS
        else:
            ok = any(referer.startswith(o + "/") for o in ALLOWED_ORIGINS)
        if not ok:
            log.warning("Blocked cross-site %s %s (origin=%s)", request.method, request.url.path, origin)
            return PlainTextResponse("Blocked: this request did not come from the dashboard.", status_code=403)
    return await call_next(request)


app.mount("/static", StaticFiles(directory=config.BASE_DIR / "app" / "static"), name="static")
app.include_router(dashboard.router)
app.include_router(leads.router)
app.include_router(admin.router)
app.include_router(research.router)
