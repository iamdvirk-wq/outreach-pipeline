"""Deciding whether a researched business is worth contacting.

A business qualifies when all of these hold (thresholds are in Settings):
- Google rating at least min_rating and at least min_review_count reviews
- at least min_medium_high_findings failed checks of medium or high severity,
  or no website of its own
- not a franchise or national chain
- not on the do-not-contact list, and not contacted in the last recontact_days
- the website doesn't ask not to be solicited

The score (0-100) ranks qualified leads: up to 40 points for website problems,
30 for rating and 30 for number of reviews.
"""
import math
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.orm import Session

from app import dnc
from app.audit.checks import NO_SOLICITATION
from app.models import Business, Settings, utcnow


@dataclass
class Qualification:
    qualified: bool
    score: float
    reasons: list[str] = field(default_factory=list)  # why it was disqualified

    @property
    def reason_text(self) -> str:
        return "; ".join(self.reasons)


def score(b: Business) -> float:
    if not b.has_own_website:
        issues = 35.0
    else:
        weights = {"high": 15, "medium": 8, "low": 2}
        issues = min(40.0, sum(weights.get(f.severity, 0) for f in b.findings if not f.passed))
    rating = 30 * min(1.0, max(0.0, ((b.rating or 0) - 3.5) / 1.5))
    reviews = 30 * min(1.0, math.log10((b.review_count or 0) + 1) / math.log10(201))
    return round(issues + rating + reviews, 1)


def qualify(session: Session, b: Business, settings: Settings) -> Qualification:
    reasons = []
    research = b.research[0] if b.research else None

    no_solicit = next((f for f in b.findings if f.check_name == NO_SOLICITATION and not f.passed), None)
    if no_solicit:
        reasons.append(f"Website asks not to be solicited ({no_solicit.evidence})")

    blocked = dnc.is_business_blocked(session, b)
    if blocked:
        reasons.append(f"On the do-not-contact list ({blocked.reason})")

    since = utcnow() - timedelta(days=settings.recontact_days)
    if any(e.sent_at and e.sent_at >= since for e in b.emails):
        reasons.append(f"Contacted in the last {settings.recontact_days} days")

    if b.rating is None:
        reasons.append("No Google rating recorded (add it with Edit details, then re-run research)")
    elif b.rating < settings.min_rating:
        reasons.append(f"Rating {b.rating} is below {settings.min_rating}")
    if b.review_count is None:
        reasons.append("Number of reviews not recorded")
    elif b.review_count < settings.min_review_count:
        reasons.append(f"Only {b.review_count} reviews (minimum {settings.min_review_count})")

    if b.has_own_website and not b.findings:
        reasons.append("Website couldn't be checked automatically")
    elif b.has_own_website:
        problems = [f for f in b.findings if not f.passed and f.severity in ("medium", "high")]
        if len(problems) < settings.min_medium_high_findings:
            reasons.append(
                f"Website has {len(problems)} medium/high issue{'s' if len(problems) != 1 else ''} "
                f"(minimum {settings.min_medium_high_findings})"
            )

    if research and research.franchise_or_chain == "yes":
        reasons.append(f"Looks like a franchise or chain ({research.franchise_evidence or 'see research'})")

    return Qualification(qualified=not reasons, score=score(b), reasons=reasons)
