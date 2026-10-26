"""Export every table to CSV, bundled in one zip file."""
import csv
import io
import zipfile
from datetime import datetime

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models import AuditFinding, Business, DoNotContact, Email, Reply, ResearchSummary, Settings, StatusChange

TABLES = [
    ("businesses", Business),
    ("audit_findings", AuditFinding),
    ("research_summaries", ResearchSummary),
    ("emails", Email),
    ("replies", Reply),
    ("do_not_contact", DoNotContact),
    ("status_changes", StatusChange),
    ("settings", Settings),
]


def _cell(v):
    if isinstance(v, datetime):
        return v.isoformat(timespec="seconds")
    if v is None:
        return ""
    return v


def table_csv(session: Session, model) -> str:
    cols = [c.key for c in inspect(model).column_attrs]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for obj in session.scalars(select(model).order_by(model.id)):
        w.writerow([_cell(getattr(obj, c)) for c in cols])
    return buf.getvalue()


def export_zip(session: Session) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, model in TABLES:
            # BOM so Excel opens accented names correctly
            z.writestr(f"{name}.csv", "﻿" + table_csv(session, model))
    return buf.getvalue()
