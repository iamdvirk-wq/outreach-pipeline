"""Compliance rules enforced in Phase 1: manual email entry, send cap limits,
dry-run default, and cross-site form protection."""
import pytest

from app import config
from app.models import Business
from app.services import ValidationError, apply_business_form, clamp_send_cap, get_settings


def test_contact_email_requires_published_confirmation(session):
    with pytest.raises(ValidationError, match="Tick the box"):
        apply_business_form(session, Business(), {"name": "A", "contact_email": "a@a.com.au"}, is_new=True)
    b = Business()
    apply_business_form(
        session, b, {"name": "A", "contact_email": "A@a.com.au", "email_confirmed_published": "on"}, is_new=True
    )
    assert b.contact_email == "a@a.com.au" and b.email_confirmed_published


def test_invalid_email_rejected(session):
    with pytest.raises(ValidationError):
        apply_business_form(
            session, Business(), {"name": "A", "contact_email": "nope", "email_confirmed_published": "on"}, is_new=True
        )


@pytest.mark.parametrize("asked, got", [(20, 20), (0, 1), (-5, 1), (50, 50), (51, 50), (500, 50)])
def test_daily_cap_is_clamped(asked, got):
    assert clamp_send_cap(asked) == got


def test_defaults_are_safe(session):
    s = get_settings(session)
    assert s.dry_run is True
    assert s.daily_send_cap == 20
    assert s.recontact_days == 180
    assert s.followup_business_days == 5
    assert "no thanks" in s.opt_out_line


def test_settings_page_enforces_limits(client, session):
    r = client.post(
        "/settings",
        data={"daily_send_cap": "500", "recontact_days": "10", "followup_business_days": "1", "dry_run": "on"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    session.expire_all()
    s = get_settings(session)
    assert (s.daily_send_cap, s.recontact_days, s.followup_business_days) == (config.MAX_DAILY_SEND_CAP, 180, 5)


def test_dry_run_cannot_be_turned_off_without_sender_details(client, session):
    r = client.post("/settings", data={"daily_send_cap": "20"}, follow_redirects=False)
    assert "err=" in r.headers["location"]
    session.expire_all()
    assert get_settings(session).dry_run is True


def test_cross_site_posts_are_blocked(client):
    r = client.post("/settings", data={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/test-data/delete", headers={"Origin": ""})
    assert r.status_code == 403


def test_all_pages_load(client):
    from scripts.seed import seed

    seed()
    for path in ["/", "/leads", "/leads/1", "/leads/new", "/leads/1/edit", "/import", "/queue",
                 "/replies", "/finder", "/do-not-contact", "/settings", "/export/all.zip",
                 "/export/businesses.csv", "/leads?sort=contacted&dir=asc&replied=yes"]:
        assert client.get(path).status_code == 200, path
