"""Template setup and small helpers shared by the page routes."""
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import config
from app.db import SessionLocal
from app.services import get_settings
from app.timeutil import fmt

STATUS_LABELS = {
    "new": "New",
    "researching": "Researching",
    "researched": "Researched",
    "qualified": "Qualified",
    "disqualified": "Disqualified",
    "draft_ready": "Draft ready",
    "approved": "Approved",
    "sent": "Sent",
    "follow_up_sent": "Follow-up sent",
    "replied": "Replied",
    "won": "Won",
    "lost": "Lost",
    "opted_out": "Opted out",
}


def _globals(request: Request) -> dict:
    with SessionLocal() as s:
        settings = get_settings(s)
        return {
            "dry_run": settings.dry_run,
            "sender_ok": settings.sender_details_complete,
            "flash_msg": request.query_params.get("msg"),
            "flash_err": request.query_params.get("err"),
            "nav": request.url.path,
        }


templates = Jinja2Templates(directory=config.BASE_DIR / "app" / "templates", context_processors=[_globals])
templates.env.filters["dt"] = fmt
templates.env.filters["d"] = lambda v: fmt(v, with_time=False)
templates.env.filters["status_label"] = lambda s: STATUS_LABELS.get(s, s)
templates.env.globals["STATUS_LABELS"] = STATUS_LABELS


def redirect(url: str, msg: str | None = None, err: str | None = None) -> RedirectResponse:
    """Redirect after a form post, carrying a one-line message to show."""
    url, _, fragment = url.partition("#")
    params = {k: v for k, v in (("msg", msg), ("err", err)) if v}
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    if fragment:
        url += "#" + fragment
    return RedirectResponse(url, status_code=303)


def render(request: Request, name: str, **ctx):
    return templates.TemplateResponse(request, name, ctx)
