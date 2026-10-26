"""Shared business rules used by the dashboard pages and scripts."""
import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.domains import is_valid_email, normalise_domain, normalise_url
from app.models import STATUSES, Business, Settings, StatusChange

log = logging.getLogger(__name__)


class ValidationError(ValueError):
    """A problem with what was typed into a form; the message is shown to you."""


def get_settings(session: Session) -> Settings:
    s = session.get(Settings, 1)
    if s is None:
        s = Settings(id=1, claude_model=config.DEFAULT_CLAUDE_MODEL)
        session.add(s)
        session.commit()
    return s


def clamp_send_cap(value: int) -> int:
    return max(1, min(int(value), config.MAX_DAILY_SEND_CAP))


def set_status(session: Session, business: Business, new_status: str, note: str | None = None) -> None:
    if new_status not in STATUSES:
        raise ValidationError(f"Unknown status {new_status!r}")
    if business.status == new_status:
        return
    session.add(StatusChange(business=business, from_status=business.status, to_status=new_status, note=note))
    log.info("Business %s status %s -> %s", business.id, business.status, new_status)
    business.status = new_status


def find_duplicate(
    session: Session,
    *,
    domain: str | None,
    place_id: str | None = None,
    name: str | None = None,
    suburb: str | None = None,
    exclude_id: int | None = None,
) -> Business | None:
    """Existing business with the same place_id or domain.

    Businesses without a domain (no website, or Facebook-only) are matched on
    name + suburb instead, ignoring case.
    """
    candidates = []
    if place_id:
        candidates.append(select(Business).where(Business.google_place_id == place_id))
    if domain:
        candidates.append(select(Business).where(Business.domain == domain))
    elif name:
        candidates.append(
            select(Business).where(
                func.lower(Business.name) == name.strip().lower(),
                func.lower(Business.suburb) == suburb.strip().lower() if suburb else Business.suburb.is_(None),
            )
        )
    for q in candidates:
        if exclude_id is not None:
            q = q.where(Business.id != exclude_id)
        found = session.scalars(q).first()
        if found:
            return found
    return None


def _opt_float(v: str | None, label: str) -> float | None:
    v = (v or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        raise ValidationError(f"{label} must be a number (got {v!r}).") from None


def _opt_int(v: str | None, label: str) -> int | None:
    f = _opt_float(v, label)
    return None if f is None else int(f)


def _opt_str(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def apply_business_form(session: Session, b: Business, form: dict, *, is_new: bool) -> None:
    """Validate form fields and copy them onto b. Raises ValidationError."""
    name = _opt_str(form.get("name"))
    if not name:
        raise ValidationError("Business name is required.")
    rating = _opt_float(form.get("rating"), "Rating")
    if rating is not None and not 0 <= rating <= 5:
        raise ValidationError("Rating must be between 0 and 5.")
    review_count = _opt_int(form.get("review_count"), "Review count")
    if review_count is not None and review_count < 0:
        raise ValidationError("Review count can't be negative.")

    website = normalise_url(form.get("website_url"))
    domain = normalise_domain(website)
    dup = find_duplicate(
        session, domain=domain, name=name, suburb=_opt_str(form.get("suburb")), exclude_id=None if is_new else b.id
    )
    if dup:
        raise ValidationError(f"This looks like a duplicate of “{dup.name}” (#{dup.id}).")

    email, confirmed = check_contact_email(session, domain, form)

    b.name = name
    for field in ("industry", "suburb", "city", "address", "phone", "contact_name", "notes"):
        setattr(b, field, _opt_str(form.get(field)))
    b.state = (_opt_str(form.get("state")) or "").upper() or None
    b.tags = ", ".join(t.strip() for t in (form.get("tags") or "").split(",") if t.strip()) or None
    b.website_url = website
    b.domain = domain
    b.rating = rating
    b.review_count = review_count
    set_contact_email(b, email, confirmed)


def check_contact_email(session: Session, domain: str | None, form: dict) -> tuple[str | None, bool]:
    """Validate the contact email fields (rule 1) and the do-not-contact list."""
    from app import dnc  # avoid an import cycle

    email = _opt_str(form.get("contact_email"))
    confirmed = form.get("email_confirmed_published") in ("on", "true", "1", True)
    if email:
        email = email.lower()
        if not is_valid_email(email):
            raise ValidationError(f"{email!r} doesn't look like an email address.")
        if not confirmed:
            raise ValidationError(
                "Tick the box confirming you found this address published on the business's own "
                "website or listing. Addresses must not come from scrapers or bought lists."
            )
    blocked = dnc.is_blocked(session, domain, email)
    if blocked:
        raise ValidationError(
            f"This business is on the do-not-contact list ({blocked.domain or blocked.email}: {blocked.reason})."
        )
    return email, confirmed


def set_contact_email(b: Business, email: str | None, confirmed: bool) -> None:
    if b.contact_email != email:
        b.email_bad = False
    b.contact_email = email
    b.email_confirmed_published = bool(email) and confirmed


def last_contacted(b: Business) -> datetime | None:
    sent = [e.sent_at for e in b.emails if e.sent_at]
    return max(sent) if sent else None
