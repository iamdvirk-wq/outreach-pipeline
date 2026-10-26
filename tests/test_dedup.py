import pytest

from app.csv_import import import_csv
from app.models import Business
from app.services import ValidationError, apply_business_form, find_duplicate


def add(session, **kw):
    b = Business(source="manual", **kw)
    session.add(b)
    session.commit()
    return b


def test_duplicate_by_domain(session):
    existing = add(session, name="Smith Plumbing", website_url="https://smithplumbing.com.au", domain="smithplumbing.com.au")
    assert find_duplicate(session, domain="smithplumbing.com.au", name="Different Name") == existing


def test_duplicate_by_place_id(session):
    existing = add(session, name="A", google_place_id="ChIJ123")
    assert find_duplicate(session, domain=None, place_id="ChIJ123", name="B") == existing


def test_no_website_matches_name_and_suburb_ignoring_case(session):
    existing = add(session, name="Corner Cafe", suburb="Fitzroy")
    assert find_duplicate(session, domain=None, name="corner cafe ", suburb="FITZROY") == existing
    assert find_duplicate(session, domain=None, name="Corner Cafe", suburb="Carlton") is None


def test_social_pages_are_not_duplicates_of_each_other(session):
    form = {"name": "One", "website_url": "https://facebook.com/one"}
    b1 = Business()
    apply_business_form(session, b1, form, is_new=True)
    session.add(b1)
    session.commit()
    b2 = Business()
    apply_business_form(session, b2, {"name": "Two", "website_url": "https://facebook.com/two"}, is_new=True)


def test_manual_add_rejects_duplicate(session):
    add(session, name="Smith Plumbing", domain="smithplumbing.com.au")
    with pytest.raises(ValidationError, match="duplicate"):
        apply_business_form(session, Business(), {"name": "X", "website_url": "www.smithplumbing.com.au/about"}, is_new=True)


def test_editing_a_business_is_not_a_duplicate_of_itself(session):
    b = add(session, name="Smith Plumbing", domain="smithplumbing.com.au", website_url="https://smithplumbing.com.au")
    apply_business_form(session, b, {"name": "Smith Plumbing Pty Ltd", "website_url": "smithplumbing.com.au"}, is_new=False)


def test_csv_import_dedupes_within_file_and_against_db(session):
    add(session, name="Existing", domain="existing.com.au")
    text = (
        "name,website\n"
        "Existing again,https://www.existing.com.au\n"
        "New One,newone.com.au\n"
        "New One copy,http://newone.com.au/\n"
    )
    result = import_csv(session, text)
    assert result.imported == 1
    assert [r[1] for r in result.skipped] == ["Existing again", "New One copy"]
