"""Overview, review queue, replies and lead finder pages."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import pipeline
from app.db import get_session
from app.models import REPLY_CLASSIFICATIONS, Business, Email, Reply
from app.queries import overview
from app.services import get_settings, set_status
from app.web import redirect, render

router = APIRouter()


@router.get("/")
def overview_page(request: Request, session: Session = Depends(get_session)):
    return render(request, "overview.html", o=overview(session), r=pipeline.status(session))


# ---- Review queue ------------------------------------------------------------


def _drafts(session: Session) -> list[Email]:
    return list(
        session.scalars(
            select(Email)
            .where(Email.status == "draft")
            .options(selectinload(Email.business).selectinload(Business.findings))
            .order_by(Email.created_at, Email.id)
        )
    )


@router.get("/queue")
def review_queue(request: Request, id: int | None = None, session: Session = Depends(get_session)):
    drafts = _drafts(session)
    current = next((d for d in drafts if d.id == id), drafts[0] if drafts else None)
    position = drafts.index(current) + 1 if current else 0
    nxt = drafts[position] if current and position < len(drafts) else None
    return render(
        request,
        "queue.html",
        email=current,
        drafts=drafts,
        position=position,
        next_draft=nxt,
        settings=get_settings(session),
    )


def _get_draft(session: Session, email_id: int) -> Email:
    e = session.get(Email, email_id)
    if not e or e.status != "draft":
        raise HTTPException(404, "Draft not found (it may already have been sent or discarded).")
    return e


@router.post("/queue/{email_id}/save")
async def save_draft(request: Request, email_id: int, session: Session = Depends(get_session)):
    e = _get_draft(session, email_id)
    form = await request.form()
    subject, body = (form.get("subject") or "").strip(), (form.get("body") or "").strip()
    if not subject or not body:
        return redirect(f"/queue?id={e.id}", err="Subject and body can't be empty.")
    if subject != e.subject or body != e.body:
        e.subject, e.body, e.edited_by_me = subject, body, True
        session.commit()
    return redirect(f"/queue?id={e.id}", msg="Draft saved.")


@router.post("/queue/{email_id}/discard")
def discard_draft(email_id: int, session: Session = Depends(get_session)):
    e = _get_draft(session, email_id)
    b = e.business
    session.delete(e)
    if b.status == "draft_ready" and not any(x.status == "draft" for x in b.emails if x.id != email_id):
        set_status(session, b, "qualified", note="Draft discarded")
    session.commit()
    return redirect("/queue", msg=f"Draft for {b.name} discarded.")


# ---- Replies -----------------------------------------------------------------


@router.get("/replies")
def replies_page(request: Request, show: str = "all", session: Session = Depends(get_session)):
    q = select(Reply).options(selectinload(Reply.business)).order_by(Reply.received_at.desc())
    if show == "unhandled":
        q = q.where(Reply.handled.is_(False))
    return render(
        request, "replies.html", replies=list(session.scalars(q)), show=show, classifications=REPLY_CLASSIFICATIONS
    )


@router.post("/replies/{reply_id}/handled")
def toggle_handled(request: Request, reply_id: int, session: Session = Depends(get_session)):
    r = session.get(Reply, reply_id)
    if not r:
        raise HTTPException(404)
    r.handled = not r.handled
    session.commit()
    if request.headers.get("HX-Request"):
        return render(request, "_reply_row.html", r=r)
    return redirect("/replies")


# ---- Lead finder (Phase 5) ---------------------------------------------------


@router.get("/finder")
def finder_page(request: Request, session: Session = Depends(get_session)):
    return render(request, "finder.html", settings=get_settings(session))
