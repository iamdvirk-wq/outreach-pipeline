"""Add 5 fake example businesses so you can explore the dashboard.

    python -m scripts.seed

They are clearly marked as TEST data, use made-up ".example" web addresses
that can never belong to a real business, and can be removed with the
"Delete test data" button on the Overview page. Running this again does
nothing if test data already exists.
"""
from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.main import startup
from app.models import AuditFinding, Business, Email, Reply, ResearchSummary, StatusChange, utcnow

NOTE = "TEST DATA: fake example business created by the seed script."


def finding(name, passed, severity, evidence, ago):
    return AuditFinding(check_name=name, passed=passed, severity=severity, evidence=evidence, checked_at=ago)


def seed() -> int:
    startup()
    now = utcnow()
    with SessionLocal() as s:
        if s.scalar(select(Business).where(Business.is_test_data.is_(True))):
            print("Test data already exists. Nothing added.")
            return 0

        def biz(**kw):
            b = Business(is_test_data=True, notes=NOTE, source="manual", **kw)
            s.add(b)
            return b

        b1 = biz(
            name="[TEST] Northside Physio Example",
            industry="Physiotherapist",
            suburb="Chermside", city="Brisbane", state="QLD",
            phone="07 0000 0001",
            website_url="https://northside-physio.example", domain="northside-physio.example",
            rating=4.8, review_count=64, status="new", date_found=now - timedelta(days=1),
        )
        b2 = biz(
            name="[TEST] Harbour Plumbing Example",
            industry="Plumber",
            suburb="Balmain", city="Sydney", state="NSW",
            phone="02 0000 0002",
            website_url="https://harbour-plumbing.example", domain="harbour-plumbing.example",
            rating=4.6, review_count=38, status="draft_ready", qualification_score=82,
            contact_page_url="https://harbour-plumbing.example/contact", email_published_flag="yes",
            contact_email="hello@harbour-plumbing.example", email_confirmed_published=True,
            date_found=now - timedelta(days=4),
        )
        b3 = biz(
            name="[TEST] Corner Cafe Example",
            industry="Cafe",
            suburb="Fitzroy", city="Melbourne", state="VIC",
            phone="03 0000 0003",
            website_url=None, domain=None,
            rating=4.5, review_count=120, status="qualified", qualification_score=75,
            date_found=now - timedelta(days=6),
        )
        b4 = biz(
            name="[TEST] Bright Smile Dental Example",
            industry="Dentist",
            suburb="Subiaco", city="Perth", state="WA",
            phone="08 0000 0004",
            website_url="https://brightsmile-dental.example", domain="brightsmile-dental.example",
            rating=4.9, review_count=210, status="replied", qualification_score=88,
            contact_page_url="https://brightsmile-dental.example/contact-us", email_published_flag="yes",
            contact_email="reception@brightsmile-dental.example", email_confirmed_published=True,
            date_found=now - timedelta(days=12),
        )
        b5 = biz(
            name="[TEST] Hills Electrical Example",
            industry="Electrician",
            suburb="Castle Hill", city="Sydney", state="NSW",
            phone="02 0000 0005",
            website_url="https://hills-electrical.example", domain="hills-electrical.example",
            rating=4.2, review_count=19, status="disqualified",
            disqualify_reason="Website says \"No solicitations\" (test example).",
            date_found=now - timedelta(days=3),
        )
        s.flush()

        ago = now - timedelta(days=3)
        b2.findings = [
            finding("HTTPS", True, "low", "Homepage loads over HTTPS with a valid certificate.", ago),
            finding("Mobile viewport", False, "high", "No <meta name=\"viewport\"> tag in the homepage HTML.", ago),
            finding("Click-to-call link", False, "medium", "Phone number 02 0000 0002 appears as plain text; no tel: link found.", ago),
            finding("Copyright year", False, "low", "Footer reads \"© 2019\".", ago),
        ]
        b4.findings = [
            finding("Online booking", False, "medium", "No booking link or booking form found on homepage, contact or services pages.", ago),
            finding("PageSpeed mobile score", False, "high", "PageSpeed Insights mobile performance score: 31 (test value).", ago),
        ]
        b5.findings = [
            finding("No-solicitation wording", False, "high", "Contact page contains: \"No solicitations please\" (test value).", ago),
        ]
        b2.research = [ResearchSummary(
            what_they_sell="Residential plumbing, blocked drains and hot water repairs (test data).",
            likely_customers="Homeowners and renters in the inner west needing urgent repairs.",
            what_matters_in_this_industry="Being easy to call from a phone in an emergency.",
            positive_detail="Reviews often mention turning up on time (paraphrased, test data).",
            suggested_angle="Mobile callers: no viewport tag and no tap-to-call link.",
            created_at=ago,
        )]

        s.add(Email(
            business=b2, type="initial", status="draft",
            subject="Quick idea for Harbour Plumbing Example's website",
            body=(
                "Hi there,\n\n"
                "I noticed a lot of your reviews mention you turn up when you say you will, which is what people want from a plumber.\n\n"
                "I had a look at your website on my phone and found two things that might be costing you calls. "
                "The site isn't set up for mobile screens, so it shows up tiny and people have to pinch and zoom. "
                "And the phone number can't be tapped to call, which matters when someone has water on the floor.\n\n"
                "If it's useful, I can record a free 2-minute video walking through both fixes.\n\n"
                "Cheers,\n[Your name]\n[Business name] · ABN [ABN]\n[Phone] · [Website]\n\n"
                "If you'd rather not hear from me, just reply 'no thanks' and I won't contact you again.\n\n"
                "(TEST DATA: this draft was created by the seed script.)"
            ),
            created_at=now - timedelta(hours=5),
        ))
        sent = Email(
            business=b4, type="initial", status="sent", dry_run=True,
            subject="Quick idea for Bright Smile Dental Example's website",
            body="(TEST DATA) Example of a sent email. Nothing was really sent.",
            to_address=b4.contact_email,
            message_id="<seed-test-1@outreach.example>",
            approved_at=now - timedelta(days=8), sent_at=now - timedelta(days=8),
            created_at=now - timedelta(days=9),
        )
        s.add(sent)
        s.flush()
        s.add(Reply(
            business=b4, email_id=sent.id, from_address="reception@brightsmile-dental.example",
            received_at=now - timedelta(days=7),
            snippet="(TEST DATA) Hi, thanks for this. Yes, we've been meaning to sort out online bookings. Can you send the video?",
            classification="interested", handled=False, message_id="<seed-test-reply-1@outreach.example>",
        ))
        for b, steps in [
            (b2, [("new", "researched", 3), ("researched", "qualified", 3), ("qualified", "draft_ready", 0.2)]),
            (b3, [("new", "qualified", 5)]),
            (b4, [("new", "qualified", 10), ("qualified", "sent", 8), ("sent", "replied", 7)]),
            (b5, [("new", "disqualified", 2)]),
        ]:
            for frm, to, days in steps:
                s.add(StatusChange(business=b, from_status=frm, to_status=to, note="test data",
                                   changed_at=now - timedelta(days=days)))
        s.commit()
        print("Added 5 TEST businesses. Remove them any time with 'Delete test data' on the Overview page.")
        return 5


if __name__ == "__main__":
    seed()
