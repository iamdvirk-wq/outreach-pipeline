"""Audit -> research -> qualify, with the website and Claude replaced by fakes."""
from sqlalchemy import select, text

from app import pipeline
from app.audit import checks
from app.audit.checks import Finding
from app.audit.run import AuditResult
from app.models import Business, StatusChange
from app.research import ResearchError, ResearchOutput

GOOD_RESEARCH = ResearchOutput(
    what_they_sell="Emergency plumbing", likely_customers="Homeowners", what_matters_in_this_industry="Fast phone contact",
    positive_detail="Family owned (from their about page)", suggested_angle="Viewport and tap-to-call",
    franchise_or_chain="no", franchise_evidence="No sign",
)


def fake_audit(*args, **kwargs):
    return AuditResult(
        findings=[Finding(checks.VIEWPORT, False, "high", "No viewport tag"),
                  Finding(checks.TAP_TO_CALL, False, "medium", "Plain text phone"),
                  Finding(checks.HTTPS, True, "low", "OK")],
        contact_page_url="https://smith.com.au/contact", email_published="yes",
        page_texts=[("Homepage", "We fix pipes. Email [email]")], warnings=["PageSpeed check didn't run: HTTP 429."],
    )


def add(session, **kw):
    b = Business(**{**dict(name="Smith Plumbing", website_url="https://smith.com.au", domain="smith.com.au",
                           industry="Plumber", rating=4.7, review_count=50), **kw})
    session.add(b)
    session.commit()
    return b.id


def test_research_one_qualifies_and_saves_everything(session):
    seen = {}

    def researcher(b, findings, page_texts, settings):
        seen["texts"] = page_texts
        return GOOD_RESEARCH

    bid = add(session)
    assert pipeline.research_one(bid, audit=fake_audit, researcher=researcher) == "qualified"
    session.expire_all()
    b = session.get(Business, bid)
    assert b.status == "qualified" and b.qualification_score > 0
    assert len(b.findings) == 3 and b.research[0].positive_detail.startswith("Family")
    assert b.contact_page_url.endswith("/contact") and b.email_published_flag == "yes"
    assert b.contact_email is None  # never filled in automatically
    assert b.last_error.startswith("Some checks couldn't run")
    changes = session.scalars(select(StatusChange).where(StatusChange.business_id == bid)).all()
    assert [(c.from_status, c.to_status) for c in changes] == [("new", "qualified")]


def test_no_website_skips_the_audit(session):
    called = []
    bid = add(session, website_url=None, domain=None)
    pipeline.research_one(bid, audit=lambda *a, **k: called.append(1), researcher=lambda *a: GOOD_RESEARCH)
    session.expire_all()
    assert not called and session.get(Business, bid).status == "qualified"


def test_disqualified_reason_is_kept(session):
    bid = add(session, rating=3.2)
    pipeline.research_one(bid, audit=fake_audit, researcher=lambda *a: GOOD_RESEARCH)
    session.expire_all()
    b = session.get(Business, bid)
    assert b.status == "disqualified" and "Rating 3.2" in b.disqualify_reason


def test_failures_are_recorded_retried_then_given_up(session):
    def broken(*a):
        raise ResearchError("Anthropic rate limit or credit limit reached; will try again later.")

    bid = add(session)
    for attempt in range(1, pipeline.MAX_ATTEMPTS + 1):
        assert pipeline.research_one(bid, audit=fake_audit, researcher=broken) == "failed"
        session.expire_all()
        b = session.get(Business, bid)
        assert b.status == "new" and b.research_attempts == attempt and "rate limit" in b.last_error
    assert "Gave up" in b.last_error
    assert bid not in pipeline.waiting_ids(session)
    assert len(b.findings) == 3  # the audit is kept even though research failed


def test_unexpected_errors_do_not_escape(session):
    def crash(*a, **k):
        raise RuntimeError("boom")

    bid = add(session)
    assert pipeline.research_one(bid, audit=crash) == "failed"
    session.expire_all()
    assert "Unexpected error (RuntimeError)" in session.get(Business, bid).last_error


def test_a_business_is_not_researched_twice_at_once(session):
    bid = add(session)
    assert pipeline.claim(bid) == "new"
    assert pipeline.claim(bid) is None
    assert pipeline.research_one(bid, audit=fake_audit, researcher=lambda *a: GOOD_RESEARCH) == "skipped"


def test_contacted_businesses_cannot_be_rerun(session):
    bid = add(session, status="sent")
    assert pipeline.research_one(bid, audit=fake_audit, researcher=lambda *a: GOOD_RESEARCH) == "skipped"


def test_test_data_is_never_researched(session):
    bid = add(session, is_test_data=True)
    assert bid not in pipeline.waiting_ids(session)
    assert pipeline.claim(bid) is None


def test_interrupted_runs_go_back_in_the_queue(session):
    bid = add(session, status="researching")
    assert pipeline.reset_interrupted() == 1
    session.expire_all()
    assert session.get(Business, bid).status == "new"


def test_queue_waits_for_api_key(monkeypatch, session):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    add(session)
    assert "ANTHROPIC_API_KEY" in pipeline.run_queue()


def test_no_email_address_is_stored_anywhere(session):
    bid = add(session)
    pipeline.research_one(bid, audit=fake_audit, researcher=lambda *a: GOOD_RESEARCH)
    with session.connection() as conn:
        for table in ("businesses", "audit_findings", "research_summaries"):
            for row in conn.execute(text(f"select * from {table}")):
                assert not any(isinstance(v, str) and "@" in v for v in row), (table, row)
