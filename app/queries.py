"""Read-only queries behind the Overview and Leads pages."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import STATUSES, Business, Email, Reply
from app.services import get_settings
from app.timeutil import local_date_start_utc, local_midnight_utc, local_week_start_utc


def sent_count_since(session: Session, since: datetime | None) -> int:
    q = select(func.count(Email.id)).where(Email.status == "sent")
    if since is not None:
        q = q.where(Email.sent_at >= since)
    return session.scalar(q) or 0


def sent_today(session: Session) -> int:
    return sent_count_since(session, local_midnight_utc())


def remaining_allowance(session: Session) -> int:
    return max(0, get_settings(session).daily_send_cap - sent_today(session))


def needs_reply(session: Session) -> list[Reply]:
    return list(
        session.scalars(
            select(Reply)
            .where(Reply.classification.in_(["interested", "question"]), Reply.handled.is_(False))
            .options(selectinload(Reply.business))
            .order_by(Reply.received_at.desc())
        )
    )


def overview(session: Session) -> dict:
    total_sent = sent_count_since(session, None)
    contacted = session.scalar(
        select(func.count(func.distinct(Email.business_id))).where(Email.status == "sent")
    ) or 0
    replied = session.scalar(
        select(func.count(func.distinct(Reply.business_id))).where(
            Reply.classification.notin_(["auto_reply", "bounce"])
        )
    ) or 0
    by_status = dict(session.execute(select(Business.status, func.count()).group_by(Business.status)).all())
    settings = get_settings(session)
    return {
        "sent_today": sent_today(session),
        "sent_week": sent_count_since(session, local_week_start_utc()),
        "sent_all": total_sent,
        "contacted": contacted,
        "replied": replied,
        "reply_rate": round(100 * replied / contacted) if contacted else None,
        "interested": session.scalar(select(func.count(Reply.id)).where(Reply.classification == "interested")) or 0,
        "won": by_status.get("won", 0),
        "by_status": [(s, by_status.get(s, 0)) for s in STATUSES],
        "total_leads": sum(by_status.values()),
        "cap": settings.daily_send_cap,
        "remaining": max(0, settings.daily_send_cap - sent_today(session)),
        "drafts": session.scalar(select(func.count(Email.id)).where(Email.status == "draft")) or 0,
        "needs_reply": needs_reply(session),
    }


# ---- Leads table -------------------------------------------------------------

SORTABLE = {
    "name": Business.name,
    "industry": Business.industry,
    "suburb": Business.suburb,
    "status": Business.status,
    "score": Business.qualification_score,
    "rating": Business.rating,
    "reviews": Business.review_count,
    "found": Business.date_found,
}


@dataclass
class LeadFilters:
    q: str = ""
    status: str = ""
    industry: str = ""
    suburb: str = ""
    min_score: str = ""
    found_from: str = ""  # YYYY-MM-DD
    found_to: str = ""
    contacted: str = ""  # "", "yes", "no"
    replied: str = ""  # "", "yes", "no"
    sort: str = "found"
    dir: str = "desc"

    def query(self, **overrides) -> str:
        """Query string for these filters, e.g. to build a sort link."""
        values = {**asdict(self), **overrides}
        return urlencode({k: v for k, v in values.items() if v})

    def sort_link(self, column: str) -> str:
        new_dir = "asc" if self.sort == column and self.dir == "desc" else "desc"
        return self.query(sort=column, dir=new_dir)


def _parse_date(v: str, plus_days: int = 0) -> datetime | None:
    """Local midnight of a YYYY-MM-DD date (plus some days), as naive UTC."""
    try:
        d = datetime.strptime(v, "%Y-%m-%d") if v else None
    except ValueError:
        return None
    return local_date_start_utc(d + timedelta(days=plus_days)) if d else None


def leads(session: Session, f: LeadFilters) -> list[tuple[Business, datetime | None, bool]]:
    """Rows of (business, last contacted, has replied) matching the filters."""
    last_sent = (
        select(Email.business_id, func.max(Email.sent_at).label("last_sent"))
        .where(Email.status == "sent")
        .group_by(Email.business_id)
        .subquery()
    )
    has_reply = exists().where(Reply.business_id == Business.id)
    q = select(Business, last_sent.c.last_sent, has_reply.label("has_reply")).outerjoin(
        last_sent, last_sent.c.business_id == Business.id
    )

    if f.q:
        like = f"%{f.q.strip()}%"
        q = q.where(
            or_(
                Business.name.ilike(like),
                Business.domain.ilike(like),
                Business.industry.ilike(like),
                Business.suburb.ilike(like),
                Business.city.ilike(like),
                Business.tags.ilike(like),
                Business.notes.ilike(like),
            )
        )
    if f.status:
        q = q.where(Business.status == f.status)
    if f.industry:
        q = q.where(Business.industry == f.industry)
    if f.suburb:
        q = q.where(Business.suburb == f.suburb)
    if f.min_score:
        try:
            q = q.where(Business.qualification_score >= float(f.min_score))
        except ValueError:
            pass
    if d := _parse_date(f.found_from):
        q = q.where(Business.date_found >= d)
    if d := _parse_date(f.found_to, plus_days=1):
        q = q.where(Business.date_found < d)
    if f.contacted == "yes":
        q = q.where(last_sent.c.last_sent.is_not(None))
    elif f.contacted == "no":
        q = q.where(last_sent.c.last_sent.is_(None))
    if f.replied == "yes":
        q = q.where(has_reply)
    elif f.replied == "no":
        q = q.where(~has_reply)

    col = last_sent.c.last_sent if f.sort == "contacted" else SORTABLE.get(f.sort, Business.date_found)
    order = col.desc() if f.dir == "desc" else col.asc()
    # put blanks last whichever way you sort
    q = q.order_by(col.is_(None).asc(), order, Business.id.desc())
    return [(b, ls, bool(r)) for b, ls, r in session.execute(q).all()]


def distinct_values(session: Session, column) -> list[str]:
    return [v for v in session.scalars(select(column).distinct().where(column.is_not(None)).order_by(column)) if v]
