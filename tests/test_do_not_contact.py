import csv

import pytest

from app import config, dnc
from app.models import Business, DoNotContact
from app.services import ValidationError, apply_business_form


def test_blocked_by_domain_and_subdomain(session):
    dnc.add(session, domain="https://www.smith.com.au/contact", reason="asked")
    assert dnc.is_blocked(session, domain="smith.com.au")
    assert dnc.is_blocked(session, domain="shop.smith.com.au")
    assert not dnc.is_blocked(session, domain="smithy.com.au")


def test_blocked_by_email_and_by_email_domain(session):
    dnc.add(session, email="Bob@Jones.com.au", reason="asked")
    dnc.add(session, domain="smith.com.au", reason="asked")
    assert dnc.is_blocked(session, email="bob@jones.com.au")
    assert not dnc.is_blocked(session, email="alice@jones.com.au")
    assert dnc.is_blocked(session, email="anyone@smith.com.au")


def test_free_mail_domains_are_never_blocked_wholesale(session):
    with pytest.raises(ValueError):
        dnc.add(session, domain="gmail.com", reason="oops")
    dnc.add(session, email="tradie@gmail.com", reason="opted out", kind="opt_out")
    assert dnc.is_blocked(session, email="tradie@gmail.com")
    assert not dnc.is_blocked(session, email="someoneelse@gmail.com")


def test_opt_outs_cannot_be_removed_but_manual_entries_can(session):
    opt = dnc.add(session, domain="a.com.au", reason="no thanks", kind="opt_out")
    manual = dnc.add(session, domain="b.com.au", reason="mistake")
    with pytest.raises(ValueError):
        dnc.remove(session, opt)
    dnc.remove(session, manual)
    assert dnc.is_blocked(session, domain="a.com.au")
    assert not dnc.is_blocked(session, domain="b.com.au")


def test_list_is_mirrored_to_file_and_survives_database_reset(session):
    dnc.add(session, domain="keep.com.au", email="x@keep.com.au", reason="opted out", kind="opt_out")
    with config.SUPPRESSION_FILE.open() as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["domain"] == "keep.com.au" and rows[0]["kind"] == "opt_out"

    # simulate a wiped database
    session.query(DoNotContact).delete()
    session.commit()
    assert not dnc.is_blocked(session, domain="keep.com.au")

    assert dnc.sync_from_file(session) == 1
    entry = dnc.is_blocked(session, domain="keep.com.au")
    assert entry and entry.kind == "opt_out" and entry.email == "x@keep.com.au"
    assert dnc.sync_from_file(session) == 0  # no duplicates on the next start


def test_cannot_add_or_email_a_blocked_business(session):
    dnc.add(session, domain="blocked.com.au", reason="opted out", kind="opt_out")
    with pytest.raises(ValidationError, match="do-not-contact"):
        apply_business_form(session, Business(), {"name": "B", "website_url": "blocked.com.au"}, is_new=True)
    with pytest.raises(ValidationError, match="do-not-contact"):
        apply_business_form(
            session,
            Business(),
            {"name": "C", "contact_email": "me@blocked.com.au", "email_confirmed_published": "on"},
            is_new=True,
        )
