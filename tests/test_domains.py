import pytest

from app.domains import domain_matches, email_domain, normalise_domain


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://www.SmithPlumbing.com.au/contact?x=1", "smithplumbing.com.au"),
        ("smithplumbing.com.au", "smithplumbing.com.au"),
        ("http://smithplumbing.com.au:8080/", "smithplumbing.com.au"),
        ("WWW.example.com", "example.com"),
        ("shop.example.com.au", "shop.example.com.au"),
        ("https://www.facebook.com/smithplumbing", None),
        ("instagram.com/smith", None),
        ("", None),
        (None, None),
        ("localhost", None),
    ],
)
def test_normalise_domain(raw, expected):
    assert normalise_domain(raw) == expected


def test_domain_matches_subdomains_only():
    assert domain_matches("shop.example.com", "example.com")
    assert domain_matches("example.com", "example.com")
    assert not domain_matches("notexample.com", "example.com")
    assert not domain_matches(None, "example.com")


def test_email_domain():
    assert email_domain("Bob@Example.com.au") == "example.com.au"
    assert email_domain("not an email") is None
