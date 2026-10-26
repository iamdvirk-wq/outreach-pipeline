"""Buttons that start the website audit and research (Phase 2)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import pipeline
from app.db import get_session
from app.models import Business
from app.web import redirect

router = APIRouter()


@router.post("/research/run")
def run_now(request: Request):
    if pipeline.key_missing():
        return redirect("/", err="Add your ANTHROPIC_API_KEY to the .env file and restart the app first.")
    pipeline.in_background(pipeline.run_queue)
    return redirect("/", msg="Research started. This page refreshes while it runs; each business takes about a minute.")


@router.post("/leads/{business_id}/research")
def rerun(business_id: int, session: Session = Depends(get_session)):
    b = session.get(Business, business_id)
    if not b:
        raise HTTPException(404)
    if b.status not in pipeline.RESEARCHABLE:
        return redirect(f"/leads/{b.id}", err="Research can't be re-run once a draft or email exists for this business.")
    if pipeline.key_missing():
        return redirect(f"/leads/{b.id}", err="Add your ANTHROPIC_API_KEY to the .env file and restart the app first.")
    b.research_attempts = 0
    session.commit()
    previous = pipeline.claim(b.id)
    if previous is None:
        return redirect(f"/leads/{b.id}", err="Research is already running for this business.")
    pipeline.in_background(pipeline.research_one, b.id, claimed_from=previous)
    return redirect(f"/leads/{b.id}", msg="Research started. This page refreshes until it's done (usually about a minute).")
