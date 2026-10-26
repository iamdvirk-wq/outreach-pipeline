from datetime import timedelta

from app import dnc
from app.audit import checks
from app.models import AuditFinding, Business, Email, ResearchSummary, utcnow
from app.qualify import qualify, score
from app.services import get_settings


def make(session, **kw):
    defaults = dict(name="Smith Plumbing", website_url="https://smith.com.au", domain="smith.com.au", rating=4.6, review_count=40)
    b = Business(**{**defaults, **kw})
    session.add(b)
    session.commit()
    return b


def fail(b, name, severity):
    b.findings.append(AuditFinding(check_name=name, passed=False, severity=severity, evidence="seen"))


def test_qualifies_with_two_medium_or_high_issues(session):
    b = make(session)
    fail(b, checks.VIEWPORT, "high")
    fail(b, checks.TAP_TO_CALL, "medium")
    fail(b, checks.COPYRIGHT, "low")
    q = qualify(session, b, get_settings(session))
    assert q.qualified and 0 < q.score <= 100


def test_low_issues_do_not_count(session):
    b = make(session)
    fail(b, checks.VIEWPORT, "high")
    fail(b, checks.COPYRIGHT, "low")
    q = qualify(session, b, get_settings(session))
    assert not q.qualified and "1 medium/high issue" in q.reason_text


def test_no_website_counts_as_enough_issues(session):
    b = make(session, website_url=None, domain=None)
    assert qualify(session, b, get_settings(session)).qualified
    fb = make(session, name="FB only", website_url="https://facebook.com/x", domain=None)
    assert qualify(session, fb, get_settings(session)).qualified


def test_rating_and_review_thresholds(session):
    s = get_settings(session)
    b = make(session, website_url=None, domain=None, rating=3.9, review_count=14)
    q = qualify(session, b, s)
    assert not q.qualified and "Rating 3.9" in q.reason_text and "14 reviews" in q.reason_text
    s.min_rating, s.min_review_count = 3.5, 10
    assert qualify(session, b, s).qualified
    unknown = make(session, name="No data", website_url=None, domain=None, rating=None, review_count=None)
    assert "No Google rating" in qualify(session, unknown, s).reason_text


def test_disqualifiers(session):
    s = get_settings(session)
    b = make(session, website_url=None, domain=None)
    b.research = [ResearchSummary(franchise_or_chain="yes", franchise_evidence="Part of Jim's group")]
    assert "franchise" in qualify(session, b, s).reason_text

    c = make(session, name="C", domain="c.com.au", website_url="https://c.com.au")
    fail(c, checks.VIEWPORT, "high")
    fail(c, checks.NO_SOLICITATION, "high")
    assert "not to be solicited" in qualify(session, c, s).reason_text

    d = make(session, name="D", website_url=None, domain=None, contact_email="d@d.com.au", email_confirmed_published=True)
    dnc.add(session, email="d@d.com.au", reason="opted out", kind="opt_out")
    assert "do-not-contact" in qualify(session, d, s).reason_text

    e = make(session, name="E", website_url=None, domain=None)
    e.emails.append(Email(subject="x", body="y", status="sent", sent_at=utcnow() - timedelta(days=30)))
    assert "Contacted in the last 180 days" in qualify(session, e, s).reason_text


def test_unchecked_website_is_not_qualified(session):
    b = make(session)
    assert "couldn't be checked" in qualify(session, b, get_settings(session)).reason_text


def test_score_orders_better_leads_higher(session):
    weak = make(session, name="Weak", domain="w.com.au", rating=4.0, review_count=15)
    fail(weak, checks.TAP_TO_CALL, "medium")
    strong = make(session, name="Strong", domain="s.com.au", rating=4.9, review_count=300)
    fail(strong, checks.VIEWPORT, "high")
    fail(strong, checks.CONTACT_FORM, "high")
    assert score(strong) > score(weak)
    assert score(strong) <= 100
