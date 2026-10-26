"""Do-not-contact list, settings and test-data clean-up."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, dnc
from app.db import get_session
from app.models import Business, DoNotContact
from app.services import clamp_send_cap, get_settings
from app.web import redirect, render

router = APIRouter()


@router.get("/do-not-contact")
def dnc_page(request: Request, session: Session = Depends(get_session)):
    entries = session.scalars(select(DoNotContact).order_by(DoNotContact.added_at.desc())).all()
    return render(request, "dnc.html", entries=entries, suppression_file=config.SUPPRESSION_FILE)


@router.post("/do-not-contact/add")
async def dnc_add(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    try:
        dnc.add(
            session,
            domain=form.get("domain"),
            email=form.get("email"),
            reason=form.get("reason") or "Added manually",
            kind="manual",
            business_name=(form.get("business_name") or "").strip() or None,
        )
    except ValueError as e:
        return redirect("/do-not-contact", err=str(e))
    return redirect("/do-not-contact", msg="Added.")


@router.post("/do-not-contact/{entry_id}/remove")
def dnc_remove(entry_id: int, session: Session = Depends(get_session)):
    entry = session.get(DoNotContact, entry_id)
    if not entry:
        raise HTTPException(404)
    try:
        dnc.remove(session, entry)
    except ValueError as e:
        return redirect("/do-not-contact", err=str(e))
    return redirect("/do-not-contact", msg="Removed.")


@router.get("/settings")
def settings_page(request: Request, session: Session = Depends(get_session)):
    return render(request, "settings.html", s=get_settings(session), max_cap=config.MAX_DAILY_SEND_CAP)


def _num(form, key: str, cast, default, lo=None, hi=None):
    try:
        v = cast(form.get(key))
    except (TypeError, ValueError):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


@router.post("/settings")
async def save_settings(request: Request, session: Session = Depends(get_session)):
    s = get_settings(session)
    form = await request.form()
    for key in ("sender_name", "business_name", "abn", "phone", "website", "signature", "opt_out_line",
                "target_industries", "target_locations", "claude_model"):
        setattr(s, key, (form.get(key) or "").strip())
    s.abn = " ".join(s.abn.split())
    if not s.opt_out_line:
        s.opt_out_line = "If you'd rather not hear from me, just reply 'no thanks' and I won't contact you again."
    if not s.claude_model:
        s.claude_model = config.DEFAULT_CLAUDE_MODEL

    requested_cap = _num(form, "daily_send_cap", int, s.daily_send_cap)
    s.daily_send_cap = clamp_send_cap(requested_cap)
    s.leads_per_run = _num(form, "leads_per_run", int, s.leads_per_run, 1, 200)
    s.min_rating = _num(form, "min_rating", float, s.min_rating, 0, 5)
    s.min_review_count = _num(form, "min_review_count", int, s.min_review_count, 0)
    s.min_medium_high_findings = _num(form, "min_medium_high_findings", int, s.min_medium_high_findings, 0)
    # Never allow re-contact sooner than the brief's 180 days, or follow-ups sooner than 5 business days.
    s.recontact_days = _num(form, "recontact_days", int, s.recontact_days, 180)
    s.followup_business_days = _num(form, "followup_business_days", int, s.followup_business_days, 5)

    turning_off_dry_run = s.dry_run and form.get("dry_run") != "on"
    if turning_off_dry_run and not s.sender_details_complete:
        session.rollback()
        return redirect("/settings", err="Fill in all sender details (name, business, ABN, phone, website) before turning off dry-run.")
    s.dry_run = form.get("dry_run") == "on"
    session.commit()
    msg = "Settings saved."
    if requested_cap != s.daily_send_cap:
        msg += f" Daily cap set to {s.daily_send_cap} (allowed range 1–{config.MAX_DAILY_SEND_CAP})."
    return redirect("/settings", msg=msg)


@router.post("/test-data/delete")
def delete_test_data(session: Session = Depends(get_session)):
    ids = session.scalars(select(Business.id).where(Business.is_test_data.is_(True))).all()
    for b in session.scalars(select(Business).where(Business.id.in_(ids))):
        session.delete(b)
    session.commit()
    return redirect("/", msg=f"Removed {len(ids)} test businesses.")
