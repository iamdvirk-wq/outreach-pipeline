import pytest
from sqlalchemy import select

from app import dnc
from app.csv_import import import_csv
from app.models import Business


def test_email_columns_are_ignored(session):
    text = (
        "Business Name,Website,Email,E-mail address,Phone\n"
        "Good Physio,goodphysio.com.au,hello@goodphysio.com.au,x@goodphysio.com.au,07 1111 1111\n"
    )
    result = import_csv(session, text)
    assert result.imported == 1
    assert result.ignored_email_columns == ["Email", "E-mail address"]
    b = session.scalar(select(Business))
    assert b.contact_email is None
    assert not b.email_confirmed_published
    assert b.source == "csv_import"


def test_addresses_hidden_in_other_columns_are_dropped(session):
    import_csv(session, "name,website,phone\nSneaky,info@sneaky.com.au,info@sneaky.com.au\n")
    b = session.scalar(select(Business))
    assert b.website_url is None and b.phone is None
    assert b.contact_email is None


def test_column_aliases_and_numbers(session):
    text = "title,url,category,suburb,city,totalScore,reviewsCount\nCafe,cafe.com.au,Cafe,Kedron,Brisbane,4.6,\"1,204\"\n"
    import_csv(session, text)
    b = session.scalar(select(Business))
    assert (b.industry, b.suburb, b.city, b.rating, b.review_count) == ("Cafe", "Kedron", "Brisbane", 4.6, 1204)


def test_do_not_contact_rows_are_skipped(session):
    dnc.add(session, domain="blocked.com.au", reason="opted out", kind="opt_out")
    result = import_csv(session, "name,website\nBlocked,https://blocked.com.au\n")
    assert result.imported == 0
    assert result.skipped[0][2] == "On the do-not-contact list"


def test_missing_name_column_is_an_error(session):
    with pytest.raises(ValueError, match="name"):
        import_csv(session, "website,phone\nx.com,1\n")
