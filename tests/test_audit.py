"""The audit against a fake website (no real network requests)."""
import httpx
import pytest

from app.audit import checks
from app.audit.checks import Finding
from app.audit.fetcher import BOT_NAME, PoliteFetcher
from app.audit.pagespeed import PageSpeedError, run_pagespeed
from app.audit.run import audit_website

HOME = """<html><head><title>Smith Plumbing</title></head><body>
<nav><a href="/contact-us">Contact</a> <a href="/services">Services</a> <a href="/about">About</a>
<a href="/private/secret">Staff</a> <a href="/old-page">Old</a> <a href="https://gone.example/x">Partner</a>
<a href="https://www.facebook.com/smith">Facebook</a></nav>
<p>Call 07 3000 0000 for emergencies. Email boss@smithplumbing.com.au</p>
<footer>&copy; 2019 Smith Plumbing</footer></body></html>"""
CONTACT = """<html><body><h1>Contact</h1><p>Write to hello@smithplumbing.com.au</p>
<form action="/send.php" method="post"><input type="email" name="e"><textarea></textarea></form></body></html>"""


class FakeSite:
    def __init__(self, robots="User-agent: *\nDisallow: /private/\n", https_ok=True):
        self.robots, self.https_ok, self.requests = robots, https_ok, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, str(request.url), request.headers.get("user-agent")))
        url = request.url
        if url.host == "gone.example":
            raise httpx.ConnectError("Name or service not known")
        if url.scheme == "https" and not self.https_ok:
            raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        pages = {"/robots.txt": (200, self.robots, "text/plain"), "/": (200, HOME, "text/html"),
                 "/contact-us": (200, CONTACT, "text/html"), "/services": (200, "<p>Hot water</p>", "text/html"),
                 "/about": (200, "<p>Family owned since 1990</p>", "text/html")}
        status, body, ctype = pages.get(url.path, (404, "not found", "text/html"))
        return httpx.Response(status, text=body, headers={"content-type": ctype})


def no_pagespeed(url):
    raise PageSpeedError("skipped in tests")


def run(site, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return audit_website("smithplumbing.com.au", "smithplumbing.com.au", "Plumber",
                         contact_website="https://mydesign.example", transport=httpx.MockTransport(site),
                         sleep=sleeps.append, pagespeed=no_pagespeed)


def by_name(result):
    return {f.check_name: f for f in result.findings}


def test_full_audit_records_evidence():
    site = FakeSite()
    result = run(site)
    f = by_name(result)
    assert f[checks.HTTPS].passed
    assert not f[checks.VIEWPORT].passed and f[checks.VIEWPORT].severity == "high"
    assert "07 3000 0000" in f[checks.TAP_TO_CALL].evidence
    assert not f[checks.COPYRIGHT].passed
    assert not f[checks.TITLE_META].passed  # no meta description
    assert not f[checks.CONTACT_FORM].passed and "send.php" in f[checks.CONTACT_FORM].evidence
    assert not f[checks.ONLINE_BOOKING].passed
    assert not f[checks.BROKEN_LINKS].passed
    assert "old-page" in f[checks.BROKEN_LINKS].evidence and "gone.example" in f[checks.BROKEN_LINKS].evidence
    assert checks.NO_SOLICITATION not in f
    assert result.contact_page_url.endswith("/contact-us")
    assert result.email_published == "yes"
    assert any("PageSpeed" in w for w in result.warnings)


def test_robots_txt_is_obeyed_and_bot_identifies_itself():
    site = FakeSite()
    run(site)
    assert not any("/private/" in url for _, url, _ in site.requests)
    assert all(ua.startswith(BOT_NAME) and "mydesign.example" in ua for _, _, ua in site.requests)
    assert all(m in ("GET", "HEAD") for m, _, _ in site.requests)


def test_only_homepage_and_three_key_pages_are_fetched():
    site = FakeSite()
    run(site)
    page_gets = {url for m, url, _ in site.requests if m == "GET" and "robots.txt" not in url and "smithplumbing" in url}
    assert page_gets <= {"https://smithplumbing.com.au/", "https://smithplumbing.com.au/contact-us",
                         "https://smithplumbing.com.au/services", "https://smithplumbing.com.au/about",
                         "https://smithplumbing.com.au/old-page", "https://smithplumbing.com.au/send.php"}


def test_waits_at_least_two_seconds_between_requests_to_a_site():
    sleeps = []
    run(FakeSite(), sleeps)
    assert sleeps and all(s > 0 for s in sleeps)
    assert max(sleeps) >= 1.9  # back-to-back requests wait out the 2 second gap


def test_email_addresses_never_leave_the_audit():
    result = run(FakeSite())
    blob = repr(result)
    assert "boss@smithplumbing.com.au" not in blob and "hello@smithplumbing.com.au" not in blob


def test_robots_blocking_everything_skips_checks():
    result = run(FakeSite(robots="User-agent: *\nDisallow: /\n"))
    assert result.findings == [] and "robots.txt" in result.warnings[0]


def test_certificate_error_is_a_high_finding_and_http_is_used():
    result = run(FakeSite(https_ok=False))
    f = by_name(result)
    assert not f[checks.HTTPS].passed and f[checks.HTTPS].severity == "high" and "certificate" in f[checks.HTTPS].evidence
    assert checks.VIEWPORT in f  # the rest of the audit still ran over http


def test_unreachable_site():
    def down(request):
        raise httpx.ConnectError("Name or service not known")
    result = audit_website("dead.example", "dead.example", "Plumber", transport=httpx.MockTransport(down),
                           sleep=lambda s: None, pagespeed=no_pagespeed)
    assert [f.check_name for f in result.findings] == [checks.SITE_LOADS]


def test_fetcher_never_waits_less_than_two_seconds():
    assert PoliteFetcher(delay=0.1).delay == 2.0


@pytest.mark.parametrize("score, passed, severity", [(0.31, False, "medium"), (0.12, False, "high"), (0.9, True, "low")])
def test_pagespeed(score, passed, severity):
    def api(request):
        return httpx.Response(200, json={"lighthouseResult": {"categories": {"performance": {"score": score}},
                                                              "audits": {"largest-contentful-paint": {"displayValue": "6.1 s"}}}})
    f = run_pagespeed("https://a.com/", transport=httpx.MockTransport(api), sleep=lambda s: None)
    assert (f.passed, f.severity) == (passed, severity) and str(round(score * 100)) in f.evidence


def test_pagespeed_retries_then_gives_up():
    calls = []
    def api(request):
        calls.append(1)
        return httpx.Response(429)
    with pytest.raises(PageSpeedError):
        run_pagespeed("https://a.com/", transport=httpx.MockTransport(api), sleep=lambda s: None)
    assert len(calls) == 3


def test_finding_dataclass():
    assert Finding("x", True, "low", "e").passed
