"""Database tables. See section 4 of BUILD_BRIEF.md.

Times are stored in UTC and converted to your local time zone for display.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    # SQLite has no time zone type, so store naive UTC consistently.
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Business.status values, in pipeline order.
STATUSES = [
    "new",
    "researching",
    "researched",
    "qualified",
    "disqualified",
    "draft_ready",
    "approved",
    "sent",
    "follow_up_sent",
    "replied",
    "won",
    "lost",
    "opted_out",
]
SOURCES = ["places_api", "csv_import", "manual"]
SEVERITIES = ["low", "medium", "high"]
EMAIL_TYPES = ["initial", "follow_up"]
EMAIL_STATUSES = ["draft", "approved", "sent", "failed"]
REPLY_CLASSIFICATIONS = [
    "interested",
    "question",
    "not_interested",
    "opt_out",
    "auto_reply",
    "bounce",
    "unclear",
]
DNC_KINDS = ["opt_out", "not_interested", "manual"]


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    industry: Mapped[str | None] = mapped_column(String(200))
    suburb: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(10))
    address: Mapped[str | None] = mapped_column(String(400))
    phone: Mapped[str | None] = mapped_column(String(60))
    website_url: Mapped[str | None] = mapped_column(String(500))
    # Normalised domain, e.g. "smithplumbing.com.au". Empty for businesses with
    # no website or only a social media page. Unique when set.
    domain: Mapped[str | None] = mapped_column(String(253), unique=True, index=True)
    google_place_id: Mapped[str | None] = mapped_column(String(300), unique=True)
    rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    date_found: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    contact_page_url: Mapped[str | None] = mapped_column(String(500))
    # "yes" / "no" / "unknown": whether an address APPEARS to be published.
    # The address itself is never recorded by the research step (rule 1).
    email_published_flag: Mapped[str] = mapped_column(String(10), default="unknown")

    contact_email: Mapped[str | None] = mapped_column(String(320))  # typed in by you only
    email_confirmed_published: Mapped[bool] = mapped_column(Boolean, default=False)
    email_bad: Mapped[bool] = mapped_column(Boolean, default=False)  # set when a send bounces
    contact_name: Mapped[str | None] = mapped_column(String(200))

    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    disqualify_reason: Mapped[str | None] = mapped_column(Text)
    qualification_score: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(String(500))  # comma separated
    last_error: Mapped[str | None] = mapped_column(Text)  # shown on the dashboard
    research_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    researched_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_test_data: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    findings: Mapped[list["AuditFinding"]] = relationship(
        back_populates="business", cascade="all, delete-orphan", order_by="AuditFinding.id"
    )
    research: Mapped[list["ResearchSummary"]] = relationship(
        back_populates="business",
        cascade="all, delete-orphan",
        order_by="ResearchSummary.created_at.desc()",
    )
    emails: Mapped[list["Email"]] = relationship(
        back_populates="business", cascade="all, delete-orphan", order_by="Email.id"
    )
    replies: Mapped[list["Reply"]] = relationship(
        back_populates="business", cascade="all, delete-orphan", order_by="Reply.received_at"
    )
    status_changes: Mapped[list["StatusChange"]] = relationship(
        back_populates="business",
        cascade="all, delete-orphan",
        order_by="StatusChange.changed_at",
    )

    @property
    def has_website(self) -> bool:
        return bool(self.website_url)

    @property
    def has_own_website(self) -> bool:
        """False for no website, or only a Facebook/Instagram-style page."""
        return bool(self.domain)

    @property
    def tag_list(self) -> list[str]:
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]


class AuditFinding(Base):
    __tablename__ = "audit_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    check_name: Mapped[str] = mapped_column(String(100))
    passed: Mapped[bool] = mapped_column(Boolean)
    severity: Mapped[str] = mapped_column(String(10), default="low")
    evidence: Mapped[str] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    business: Mapped[Business] = relationship(back_populates="findings")


class ResearchSummary(Base):
    __tablename__ = "research_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    what_they_sell: Mapped[str | None] = mapped_column(Text)
    likely_customers: Mapped[str | None] = mapped_column(Text)
    what_matters_in_this_industry: Mapped[str | None] = mapped_column(Text)
    positive_detail: Mapped[str | None] = mapped_column(Text)
    suggested_angle: Mapped[str | None] = mapped_column(Text)
    franchise_or_chain: Mapped[str] = mapped_column(String(10), default="uncertain", server_default="uncertain")
    franchise_evidence: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    business: Mapped[Business] = relationship(back_populates="research")


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20), default="initial")
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    message_id: Mapped[str | None] = mapped_column(String(300), index=True)
    to_address: Mapped[str | None] = mapped_column(String(320))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    edited_by_me: Mapped[bool] = mapped_column(Boolean, default=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)  # logged, not really sent
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    business: Mapped[Business] = relationship(back_populates="emails")


class Reply(Base):
    __tablename__ = "replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    email_id: Mapped[int | None] = mapped_column(ForeignKey("emails.id", ondelete="SET NULL"))
    from_address: Mapped[str] = mapped_column(String(320))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    snippet: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(20), default="unclear")
    handled: Mapped[bool] = mapped_column(Boolean, default=False)
    message_id: Mapped[str | None] = mapped_column(String(300), unique=True)

    business: Mapped[Business] = relationship(back_populates="replies")


class DoNotContact(Base):
    """Permanent suppression list. Mirrored to suppression/do_not_contact.csv."""

    __tablename__ = "do_not_contact"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str | None] = mapped_column(String(253), index=True)
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    reason: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="manual")
    business_name: Mapped[str | None] = mapped_column(String(300))
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StatusChange(Base):
    """History of status changes, shown on the business detail page."""

    __tablename__ = "status_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    business: Mapped[Business] = relationship(back_populates="status_changes")


class Settings(Base):
    """A single row (id = 1) holding everything editable on the Settings page."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    daily_send_cap: Mapped[int] = mapped_column(Integer, default=20)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)

    sender_name: Mapped[str] = mapped_column(String(200), default="")
    business_name: Mapped[str] = mapped_column(String(200), default="")
    abn: Mapped[str] = mapped_column(String(20), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    website: Mapped[str] = mapped_column(String(300), default="")
    signature: Mapped[str] = mapped_column(Text, default="")
    opt_out_line: Mapped[str] = mapped_column(
        Text,
        default="If you'd rather not hear from me, just reply 'no thanks' and I won't contact you again.",
    )

    target_industries: Mapped[str] = mapped_column(Text, default="")  # one per line
    target_locations: Mapped[str] = mapped_column(Text, default="")  # one per line
    leads_per_run: Mapped[int] = mapped_column(Integer, default=30)

    min_rating: Mapped[float] = mapped_column(Float, default=4.0)
    min_review_count: Mapped[int] = mapped_column(Integer, default=15)
    min_medium_high_findings: Mapped[int] = mapped_column(Integer, default=2)
    recontact_days: Mapped[int] = mapped_column(Integer, default=180)
    followup_business_days: Mapped[int] = mapped_column(Integer, default=5)

    claude_model: Mapped[str] = mapped_column(String(100), default="")
    auto_research: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    @staticmethod
    def _lines(text: str) -> list[str]:
        return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]

    @property
    def industries_list(self) -> list[str]:
        return self._lines(self.target_industries)

    @property
    def locations_list(self) -> list[str]:
        return self._lines(self.target_locations)

    @property
    def sender_details_complete(self) -> bool:
        return all([self.sender_name, self.business_name, self.abn, self.phone, self.website])
