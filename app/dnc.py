"""The do-not-contact (suppression) list. Rule 5 in BUILD_BRIEF.md.

The list lives in the database and is also mirrored to a CSV file
(suppression/do_not_contact.csv) every time it changes. When the app starts,
anything in the file that is missing from the database is put back, so
deleting or resetting the database never loses an opt-out.
"""
import csv
import logging
import os
import tempfile
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.domains import FREE_MAIL_DOMAINS, domain_matches, email_domain, normalise_domain
from app.models import DNC_KINDS, Business, DoNotContact, utcnow

log = logging.getLogger(__name__)

FILE_FIELDS = ["domain", "email", "reason", "kind", "business_name", "added_at"]


def _clean(domain: str | None, email: str | None) -> tuple[str | None, str | None]:
    email = (email or "").strip().lower() or None
    domain = normalise_domain(domain) if domain else None
    if domain in FREE_MAIL_DOMAINS:
        domain = None  # never block every Gmail user
    return domain, email


def _find_exact(session: Session, domain: str | None, email: str | None) -> DoNotContact | None:
    return session.scalar(
        select(DoNotContact).where(
            DoNotContact.domain.is_(None) if domain is None else DoNotContact.domain == domain,
            DoNotContact.email.is_(None) if email is None else DoNotContact.email == email,
        )
    )


def is_blocked(session: Session, domain: str | None = None, email: str | None = None) -> DoNotContact | None:
    """Return the matching suppression entry, or None if contact is allowed.

    Checks the business domain, the exact email address, and the domain of the
    email address (unless it is a free mailbox provider like gmail.com).
    """
    domain, email = _clean(domain, email)
    edomain = email_domain(email)
    if edomain in FREE_MAIL_DOMAINS:
        edomain = None
    for entry in session.scalars(select(DoNotContact)):
        if email and entry.email and entry.email.lower() == email:
            return entry
        if entry.domain and (domain_matches(domain, entry.domain) or domain_matches(edomain, entry.domain)):
            return entry
    return None


def is_business_blocked(session: Session, business: Business) -> DoNotContact | None:
    return is_blocked(session, business.domain, business.contact_email)


def add(
    session: Session,
    *,
    domain: str | None = None,
    email: str | None = None,
    reason: str,
    kind: str = "manual",
    business_name: str | None = None,
    added_at: datetime | None = None,
    write_file: bool = True,
) -> DoNotContact:
    """Add an entry (skips exact duplicates). Commits and rewrites the file."""
    domain, email = _clean(domain, email)
    if not domain and not email:
        raise ValueError("Enter a website domain or an email address.")
    existing = _find_exact(session, domain, email)
    if existing:
        return existing
    entry = DoNotContact(
        domain=domain,
        email=email,
        reason=reason.strip() or "No reason given",
        kind=kind,
        business_name=business_name,
        added_at=added_at or utcnow(),
    )
    session.add(entry)
    session.commit()
    log.info("Added to do-not-contact list: domain=%s email=%s kind=%s", domain, email, kind)
    if write_file:
        write_suppression_file(session)
    return entry


def add_business(session: Session, business: Business, reason: str, kind: str = "manual") -> DoNotContact:
    return add(
        session,
        domain=business.domain,
        email=business.contact_email,
        reason=reason,
        kind=kind,
        business_name=business.name,
    )


def remove(session: Session, entry: DoNotContact) -> None:
    """Only manual entries can be removed; opt-outs are permanent."""
    if entry.kind != "manual":
        raise ValueError("Opt-outs can't be removed. The person asked not to be contacted.")
    session.delete(entry)
    session.commit()
    log.info("Removed manual do-not-contact entry: domain=%s email=%s", entry.domain, entry.email)
    write_suppression_file(session)


def write_suppression_file(session: Session) -> None:
    """Rewrite the CSV mirror atomically (write a temp file, then swap it in)."""
    path = config.SUPPRESSION_FILE
    rows = session.scalars(select(DoNotContact).order_by(DoNotContact.added_at)).all()
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FILE_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "domain": r.domain or "",
                    "email": r.email or "",
                    "reason": r.reason,
                    "kind": r.kind,
                    "business_name": r.business_name or "",
                    "added_at": r.added_at.isoformat(timespec="seconds"),
                }
            )
    os.replace(tmp, path)


def sync_from_file(session: Session) -> int:
    """Restore entries from the CSV mirror that are missing in the database."""
    path = config.SUPPRESSION_FILE
    restored = 0
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                domain, email = _clean(row.get("domain"), row.get("email"))
                if not domain and not email:
                    continue
                if _find_exact(session, domain, email):
                    continue
                try:
                    added_at = datetime.fromisoformat(row.get("added_at") or "")
                except ValueError:
                    added_at = utcnow()
                session.add(
                    DoNotContact(
                        domain=domain,
                        email=email,
                        reason=row.get("reason") or "Restored from suppression file",
                        kind=row.get("kind") if row.get("kind") in DNC_KINDS else "manual",
                        business_name=row.get("business_name") or None,
                        added_at=added_at,
                    )
                )
                restored += 1
        session.commit()
    if restored:
        log.info("Restored %d do-not-contact entries from %s", restored, path.name)
    write_suppression_file(session)
    return restored
