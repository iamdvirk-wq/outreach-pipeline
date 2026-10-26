"""Leads table, business detail, add/edit, CSV import and export."""
import csv
import io
from dataclasses import fields

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import dnc
from app.csv_import import import_csv, read_csv_text
from app.db import get_session
from app.export import export_zip, table_csv
from app.models import Business
from app.queries import LeadFilters, distinct_values, leads
from app.services import (
    ValidationError,
    apply_business_form,
    check_contact_email,
    last_contacted,
    set_contact_email,
    set_status,
)
from app.timeutil import local_now
from app.web import redirect, render

router = APIRouter()

# Statuses you can set by hand. The rest are set by the pipeline itself.
MANUAL_STATUSES = {"won", "lost", "disqualified", "qualified", "new"}


def _get(session: Session, business_id: int) -> Business:
    b = session.get(Business, business_id)
    if not b:
        raise HTTPException(404, "Business not found")
    return b


@router.get("/leads")
def leads_page(request: Request, session: Session = Depends(get_session)):
    params = request.query_params
    f = LeadFilters(**{fl.name: params.get(fl.name, fl.default) for fl in fields(LeadFilters)})
    rows = leads(session, f)
    ctx = {
        "rows": rows,
        "f": f,
        "industries": distinct_values(session, Business.industry),
        "suburbs": distinct_values(session, Business.suburb),
    }
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "leads-table":
        response = render(request, "_leads_table.html", **ctx)
        response.headers["HX-Push-Url"] = "/leads?" + f.query() if f.query() else "/leads"
        return response
    return render(request, "leads.html", **ctx)


@router.get("/leads/new")
def new_business_form(request: Request):
    return render(request, "business_form.html", b=None, form={})


@router.post("/leads/new")
async def create_business(request: Request, session: Session = Depends(get_session)):
    form = dict(await request.form())
    b = Business(source="manual", status="new")
    try:
        apply_business_form(session, b, form, is_new=True)
    except ValidationError as e:
        return render(request, "business_form.html", b=None, form=form, error=str(e))
    session.add(b)
    session.commit()
    return redirect(f"/leads/{b.id}", msg="Business added.")


@router.get("/leads/{business_id}")
def business_detail(request: Request, business_id: int, session: Session = Depends(get_session)):
    b = _get(session, business_id)
    timeline = sorted(
        [("email", e.sent_at or e.created_at, e) for e in b.emails]
        + [("reply", r.received_at, r) for r in b.replies]
        + [("status", c.changed_at, c) for c in b.status_changes],
        key=lambda t: t[1],
    )
    return render(
        request,
        "business_detail.html",
        b=b,
        blocked=dnc.is_business_blocked(session, b),
        last_contacted=last_contacted(b),
        timeline=timeline,
        research=b.research[0] if b.research else None,
        findings=sorted(b.findings, key=lambda f: (f.passed, {"high": 0, "medium": 1, "low": 2}.get(f.severity, 3))),
        manual_statuses=sorted(MANUAL_STATUSES),
    )


@router.get("/leads/{business_id}/edit")
def edit_business_form(request: Request, business_id: int, session: Session = Depends(get_session)):
    b = _get(session, business_id)
    form = {c: getattr(b, c) or "" for c in Business.__table__.columns.keys()}
    return render(request, "business_form.html", b=b, form=form)


@router.post("/leads/{business_id}/edit")
async def update_business(request: Request, business_id: int, session: Session = Depends(get_session)):
    b = _get(session, business_id)
    form = dict(await request.form())
    try:
        apply_business_form(session, b, form, is_new=False)
    except ValidationError as e:
        session.rollback()
        return render(request, "business_form.html", b=b, form=form, error=str(e))
    session.commit()
    return redirect(f"/leads/{b.id}", msg="Saved.")


@router.post("/leads/{business_id}/contact-email")
async def save_contact_email(request: Request, business_id: int, session: Session = Depends(get_session)):
    b = _get(session, business_id)
    form = dict(await request.form())
    try:
        email, confirmed = check_contact_email(session, b.domain, form)
    except ValidationError as e:
        return redirect(f"/leads/{b.id}#contact", err=str(e))
    set_contact_email(b, email, confirmed)
    b.contact_name = (form.get("contact_name") or "").strip() or None
    session.commit()
    return redirect(f"/leads/{b.id}#contact", msg="Contact saved." if email else "Contact saved (no email address).")


@router.post("/leads/{business_id}/notes")
async def save_notes(request: Request, business_id: int, session: Session = Depends(get_session)):
    b = _get(session, business_id)
    form = await request.form()
    b.notes = (form.get("notes") or "").strip() or None
    b.tags = ", ".join(t.strip() for t in (form.get("tags") or "").split(",") if t.strip()) or None
    session.commit()
    return redirect(f"/leads/{b.id}#notes", msg="Notes saved.")


@router.post("/leads/{business_id}/status")
async def change_status(request: Request, business_id: int, session: Session = Depends(get_session)):
    b = _get(session, business_id)
    form = await request.form()
    new_status = form.get("status", "")
    note = (form.get("note") or "").strip() or None
    if new_status not in MANUAL_STATUSES:
        return redirect(f"/leads/{b.id}", err="That status can't be set by hand.")
    if new_status == "disqualified" and not note:
        return redirect(f"/leads/{b.id}", err="Give a reason for disqualifying.")
    set_status(session, b, new_status, note=note)
    if new_status == "disqualified":
        b.disqualify_reason = note
    elif new_status in ("new", "qualified"):
        b.disqualify_reason = None
    session.commit()
    return redirect(f"/leads/{b.id}", msg=f"Marked as {new_status.replace('_', ' ')}.")


@router.post("/leads/{business_id}/do-not-contact")
async def add_to_dnc(request: Request, business_id: int, session: Session = Depends(get_session)):
    b = _get(session, business_id)
    form = await request.form()
    if not b.domain and not b.contact_email:
        return redirect(
            f"/leads/{b.id}",
            err="This business has no website domain or email to block. Add one first, or disqualify it instead.",
        )
    dnc.add_business(session, b, reason=(form.get("reason") or "").strip() or "Marked manually", kind="manual")
    if b.status not in ("won", "lost", "opted_out"):
        set_status(session, b, "disqualified", note="Added to do-not-contact list")
        b.disqualify_reason = "On do-not-contact list"
    session.commit()
    return redirect(f"/leads/{b.id}", msg="Added to the do-not-contact list.")


@router.post("/leads/{business_id}/delete")
def delete_business(business_id: int, session: Session = Depends(get_session)):
    b = _get(session, business_id)
    session.delete(b)
    session.commit()
    return redirect("/leads", msg=f"Deleted {b.name}. (Any do-not-contact entry for it is kept.)")


# ---- CSV import and export ---------------------------------------------------


@router.get("/import")
def import_page(request: Request):
    return render(request, "import.html", result=None)


@router.post("/import")
async def import_upload(request: Request, file: UploadFile = File(...), session: Session = Depends(get_session)):
    raw = await file.read()
    try:
        result = import_csv(session, read_csv_text(raw))
    except ValueError as e:
        session.rollback()
        return render(request, "import.html", result=None, error=str(e))
    return render(request, "import.html", result=result, filename=file.filename)


@router.get("/import/template.csv")
def import_template():
    buf = io.StringIO()
    csv.writer(buf).writerows(
        [
            ["name", "website", "phone", "industry", "suburb", "city", "rating", "review_count"],
            ["Example Physio", "examplephysio.com.au", "07 3000 0000", "Physiotherapist", "Chermside", "Brisbane", "4.7", "52"],
        ]
    )
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="import-template.csv"'},
    )


@router.get("/export/all.zip")
def export_all(session: Session = Depends(get_session)):
    stamp = local_now().strftime("%Y-%m-%d_%H%M")
    return Response(
        export_zip(session),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="outreach-export-{stamp}.zip"'},
    )


@router.get("/export/businesses.csv")
def export_businesses(session: Session = Depends(get_session)):
    stamp = local_now().strftime("%Y-%m-%d")
    return Response(
        "﻿" + table_csv(session, Business),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="businesses-{stamp}.csv"'},
    )
