from datetime import date

from app.audit import checks
from app.audit.checks import soup_of


def test_viewport():
    assert not checks.check_viewport(soup_of("<head></head>")).passed
    f = checks.check_viewport(soup_of('<meta name="viewport" content="width=1024">'))
    assert not f.passed and f.severity == "medium"
    assert checks.check_viewport(soup_of('<meta name="Viewport" content="width=device-width, initial-scale=1">')).passed


def test_tap_to_call():
    assert checks.check_tap_to_call(soup_of('<a href="tel:0730000000">Call</a>'), []).passed
    f = checks.check_tap_to_call(soup_of("<p>Call us on 07 3000 0000</p>"), [])
    assert not f.passed and "07 3000 0000" in f.evidence and f.severity == "medium"
    f = checks.check_tap_to_call(soup_of("<p>Call us</p>"), [soup_of('<a href="tel:1300123456">x</a>')])
    assert not f.passed and f.severity == "low"
    assert "1300 123 456" in checks.check_tap_to_call(soup_of("<p>1300 123 456</p>"), []).evidence


def test_copyright_age():
    today = date(2026, 10, 26)
    old = checks.check_copyright(soup_of("<footer>© 2019 Smith Plumbing</footer>"), today)
    assert not old.passed and old.severity == "medium" and "2019" in old.evidence
    assert checks.check_copyright(soup_of("<footer>Copyright 2022</footer>"), today).severity == "low"
    assert checks.check_copyright(soup_of("<footer>&copy; 2015 - 2026 Acme</footer>"), today).passed
    assert checks.check_copyright(soup_of("<footer>Made with love</footer>"), today) is None


def test_title_and_meta():
    assert not checks.check_title_meta(soup_of("<head></head>")).passed
    f = checks.check_title_meta(soup_of("<title>Acme</title>"))
    assert not f.passed and f.severity == "low"
    assert checks.check_title_meta(soup_of('<title>Acme</title><meta name="description" content="Plumbing">')).passed


def test_no_solicitation():
    for text in ["Please, no solicitations.", "NO SOLICITING", "No marketing emails please", "We do not accept unsolicited offers", "No SEO calls"]:
        assert checks.check_no_solicitation([("https://a.com/contact", text)]), text
    for text in ["We solicit feedback from customers", "Solicitors in Brisbane", "Marketing emails are sent monthly"]:
        assert checks.check_no_solicitation([("https://a.com/", text)]) is None, text


def test_booking():
    assert checks.find_booking([soup_of('<a href="https://bookings.cliniko.com/x">Appointments</a>')])
    assert checks.find_booking([soup_of("<button>Book now</button>")])
    assert checks.find_booking([soup_of('<a href="/quote">Get a free quote</a>')])
    assert checks.find_booking([soup_of("<p>Our book club meets on Tuesday and the bookshelf is full</p>")]) is None
    assert checks.check_online_booking(None, "Physiotherapist").severity == "medium"
    assert checks.check_online_booking(None, "Accountant") is None


def test_email_published_never_returns_the_address():
    assert checks.email_appears_published(soup_of('<a href="mailto:hi@a.com.au">Email us</a>')) is True
    assert checks.email_appears_published(soup_of('<span class="__cf_email__" data-cfemail="abc">[email protected]</span>')) is True
    assert checks.email_appears_published(soup_of("<p>Use the form below</p>")) is False
    assert "hi@a.com.au" not in checks.visible_text(soup_of("<p>Write to hi@a.com.au</p>"))


def test_pick_key_pages():
    links = [("https://a.com/", "Home"), ("https://a.com/our-services/", "Services"), ("https://a.com/contact-us", "Contact"),
             ("https://a.com/about", "About"), ("https://a.com/brochure.pdf", "Contact PDF")]
    assert checks.pick_key_pages("https://a.com/", links) == {
        "contact": "https://a.com/contact-us", "services": "https://a.com/our-services/", "about": "https://a.com/about"}
