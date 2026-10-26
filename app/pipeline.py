"""Phase 2 pipeline: audit -> research -> qualify, for businesses with status "new".

Runs automatically every 10 minutes while the app is open (if "Research new
leads automatically" is on in Settings), or straight away from the Run now
button. Failures are recorded on the business and retried on later runs, up
to 3 attempts; nothing here can stop the scheduler.
"""
import logging
import os
import threading
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.audit.run import audit_website
from app.db import SessionLocal
from app.models import AuditFinding, Business, ResearchSummary, utcnow
from app.qualify import qualify
from app.research import ResearchError, model_name, write_research
from app.services import get_settings, set_status

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BATCH_SIZE = 10
RESEARCHABLE = ("new", "researched", "qualified", "disqualified")

_queue_lock = threading.Lock()
_state: dict = {"running": False, "current": None, "last_run_at": None, "last_summary": None}


def key_missing() -> bool:
    return not os.getenv("ANTHROPIC_API_KEY")


def _claim(session: Session, business_id: int) -> str | None:
    """Mark the business as being researched, unless something else got there first.
    Returns its previous status, or None if it can't be researched now."""
    b = session.get(Business, business_id)
    if not b or b.status not in RESEARCHABLE or b.is_test_data:
        return None
    previous = b.status
    claimed = session.execute(
        update(Business)
        .where(Business.id == business_id, Business.status == previous)
        .values(status="researching", last_error=None)
    ).rowcount
    session.commit()
    return previous if claimed else None


def claim(business_id: int) -> str | None:
    with SessionLocal() as session:
        return _claim(session, business_id)


def research_one(business_id: int, *, claimed_from: str | None = None, audit=audit_website, researcher=write_research) -> str:
    """Audit, research and qualify one business. Returns a one-line outcome.

    claimed_from: the business's status before claim() was called, when the
    caller has already marked it as researching."""
    with SessionLocal() as session:
        previous = claimed_from or _claim(session, business_id)
        if previous is None:
            return "skipped"
        b = session.get(Business, business_id)
        session.refresh(b)
        settings = get_settings(session)
        warnings: list[str] = []
        try:
            page_texts: list[tuple[str, str]] = []
            if b.has_own_website:
                result = audit(b.website_url, b.domain, b.industry, contact_website=settings.website or None)
                b.findings = [
                    AuditFinding(check_name=f.check_name, passed=f.passed, severity=f.severity, evidence=f.evidence)
                    for f in result.findings
                ]
                b.contact_page_url = result.contact_page_url
                b.email_published_flag = result.email_published
                warnings, page_texts = result.warnings, result.page_texts
            else:
                b.findings = []
            session.commit()  # keep the audit even if the research step fails

            out = researcher(b, b.findings, page_texts, settings)
            b.research = [
                ResearchSummary(
                    what_they_sell=out.what_they_sell,
                    likely_customers=out.likely_customers,
                    what_matters_in_this_industry=out.what_matters_in_this_industry,
                    positive_detail=out.positive_detail,
                    suggested_angle=out.suggested_angle,
                    franchise_or_chain=out.franchise_or_chain,
                    franchise_evidence=out.franchise_evidence,
                    model=model_name(settings),
                )
            ]
            session.flush()
            q = qualify(session, b, settings)
            b.status = previous
            b.qualification_score = q.score
            b.researched_at = utcnow()
            b.research_attempts = 0
            if q.qualified:
                set_status(session, b, "qualified", note=f"Score {q.score:.0f}")
                b.disqualify_reason = None
            else:
                set_status(session, b, "disqualified", note=q.reason_text)
                b.disqualify_reason = q.reason_text
            b.last_error = ("Some checks couldn't run: " + " ".join(warnings)) if warnings else None
            session.commit()
            outcome = "qualified" if q.qualified else "disqualified"
        except Exception as e:  # noqa: BLE001 - record any failure and carry on with the next business
            session.rollback()
            b = session.get(Business, business_id)
            b.status = "new"
            b.research_attempts = (b.research_attempts or 0) + 1
            message = str(e) if isinstance(e, ResearchError) else f"Unexpected error ({type(e).__name__}); see logs/app.log"
            if not isinstance(e, ResearchError):
                log.exception("Research failed for business %s", business_id)
            else:
                log.warning("Research failed for business %s: %s", business_id, message)
            if b.research_attempts >= MAX_ATTEMPTS:
                message += f" Gave up after {MAX_ATTEMPTS} attempts; press Re-run research to try again."
            b.last_error = message
            session.commit()
            outcome = "failed"
        log.info("Research for business %s: %s", business_id, outcome)
        return outcome


def waiting_ids(session: Session, limit: int | None = None) -> list[int]:
    q = (
        select(Business.id)
        .where(Business.status == "new", Business.research_attempts < MAX_ATTEMPTS, Business.is_test_data.is_(False))
        .order_by(Business.date_found, Business.id)
    )
    if limit:
        q = q.limit(limit)
    return list(session.scalars(q))


def run_queue(limit: int = BATCH_SIZE, *, only_if_auto: bool = False) -> str | None:
    """Research up to `limit` new businesses. Returns None if a run is already going."""
    if not _queue_lock.acquire(blocking=False):
        return None
    _state["running"] = True
    try:
        with SessionLocal() as session:
            if only_if_auto and not get_settings(session).auto_research:
                return "Automatic research is off"
            if key_missing():
                _state["last_summary"] = "Waiting for ANTHROPIC_API_KEY in .env"
                return _state["last_summary"]
            ids = waiting_ids(session, limit)
        if not ids:
            return "Nothing waiting"
        _state["last_run_at"] = utcnow()
        counts: dict[str, int] = {}
        for i, business_id in enumerate(ids, 1):
            with SessionLocal() as session:
                b = session.get(Business, business_id)
                _state["current"] = f"{b.name} ({i} of {len(ids)})" if b else None
            outcome = research_one(business_id)
            counts[outcome] = counts.get(outcome, 0) + 1
        summary = ", ".join(f"{n} {k}" for k, n in counts.items())
        _state["last_summary"] = f"Researched {len(ids)}: {summary}"
        log.info(_state["last_summary"])
        return _state["last_summary"]
    finally:
        _state.update(running=False, current=None)
        _queue_lock.release()


def in_background(fn, *args, **kwargs) -> None:
    threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()


def reset_interrupted() -> int:
    """Businesses left 'researching' when the app last stopped go back in the queue."""
    with SessionLocal() as session:
        n = session.execute(update(Business).where(Business.status == "researching").values(status="new")).rowcount
        session.commit()
        return n


def status(session: Session) -> dict:
    stuck = session.scalar(
        select(func.count(Business.id)).where(Business.status == "new", Business.research_attempts >= MAX_ATTEMPTS)
    ) or 0
    last_run_at: datetime | None = _state["last_run_at"]
    return {
        "running": _state["running"],
        "current": _state["current"],
        "last_run_at": last_run_at,
        "last_summary": _state["last_summary"],
        "waiting": len(waiting_ids(session)),
        "stuck": stuck,
        "key_missing": key_missing(),
        "pagespeed_key_missing": not os.getenv("GOOGLE_PAGESPEED_API_KEY"),
        "auto": get_settings(session).auto_research,
    }
