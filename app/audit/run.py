"""Run every website check for one business.

Fetches the homepage plus up to 3 key pages (contact, services, about), then
samples up to 20 homepage links (HEAD requests) to look for broken ones.
"""
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.audit import checks
from app.audit.checks import Finding
from app.audit.fetcher import BlockedByRobots, Page, PoliteFetcher, is_certificate_error
from app.audit.pagespeed import PageSpeedError, run_pagespeed
from app.domains import is_shared_host, normalise_url

log = logging.getLogger(__name__)

MAX_KEY_PAGES = 3
MAX_LINKS_CHECKED = 20
MAX_TEXT_PER_PAGE = 6000  # characters of page text passed on to the research step


@dataclass
class AuditResult:
    findings: list[Finding] = field(default_factory=list)
    contact_page_url: str | None = None
    email_published: str = "unknown"  # yes / no / unknown; never the address itself
    page_texts: list[tuple[str, str]] = field(default_factory=list)  # (page label, text)
    warnings: list[str] = field(default_factory=list)  # checks that couldn't run
    final_url: str | None = None

    def add(self, finding: Finding | None) -> None:
        if finding:
            self.findings.append(finding)


def _with_scheme(url: str, scheme: str) -> str:
    p = urlsplit(normalise_url(url))
    return urlunsplit((scheme, p.netloc, p.path or "/", p.query, ""))


def _load_homepage(website_url: str, fetcher: PoliteFetcher, insecure: PoliteFetcher, result: AuditResult) -> Page | None:
    """Fetch the homepage, recording the HTTPS / site-loads findings on the way."""
    https_url = _with_scheme(website_url, "https")
    http_url = _with_scheme(website_url, "http")
    host = urlsplit(https_url).netloc
    try:
        page = fetcher.get_page(https_url)
        if page.url.startswith("http://"):
            result.add(Finding(checks.HTTPS, False, "medium", f"https://{host} redirects visitors to the insecure http:// version ({page.url})."))
        else:
            result.add(Finding(checks.HTTPS, True, "low", f"Homepage loads over HTTPS with a valid certificate ({page.url})."))
        return page
    except BlockedByRobots:
        raise
    except httpx.HTTPError as e:
        if is_certificate_error(e):
            result.add(Finding(checks.HTTPS, False, "high", f"https://{host} has a security certificate error, so browsers show a 'Not secure' warning."))
            try:
                return insecure.get_page(https_url)  # read the page anyway, just to audit it
            except httpx.HTTPError:
                pass
        try:
            page = fetcher.get_page(http_url)
        except httpx.HTTPError as e2:
            result.add(Finding(checks.SITE_LOADS, False, "high", f"The website {website_url} couldn't be loaded ({type(e2).__name__}) after 3 attempts."))
            return None
        if not any(f.check_name == checks.HTTPS for f in result.findings):
            result.add(Finding(checks.HTTPS, False, "high", f"https://{host} doesn't load; the site only works over insecure http://."))
        return page


def audit_website(
    website_url: str,
    domain: str,
    industry: str | None,
    *,
    contact_website: str | None = None,
    transport: httpx.BaseTransport | None = None,
    sleep=time.sleep,
    pagespeed=run_pagespeed,
) -> AuditResult:
    result = AuditResult()
    with PoliteFetcher(contact_website, transport=transport, sleep=sleep) as fetcher, fetcher.insecure_twin() as insecure:
        try:
            home = _load_homepage(website_url, fetcher, insecure, result)
        except BlockedByRobots:
            result.warnings.append("The site's robots.txt asks bots not to visit, so no site checks were run.")
            return result
        if home is None:
            return result
        if home.status in (401, 403, 429):
            result.warnings.append(f"The site refused our check (HTTP {home.status}); it may block automated visitors. No site checks were run.")
            result.findings = []
            return result
        if home.status >= 400:
            result.add(Finding(checks.SITE_LOADS, False, "high", f"The homepage {home.url} returned an error (HTTP {home.status})."))
            return result

        result.final_url = home.url
        home_soup = checks.soup_of(home.html)
        texts = [("Homepage", checks.visible_text(home_soup))]

        # Key pages
        links = checks.internal_links(home.url, home_soup, domain)
        key_pages = checks.pick_key_pages(home.url, links)
        page_soups: dict[str, tuple[str, object]] = {}
        for kind, url in list(key_pages.items())[:MAX_KEY_PAGES]:
            try:
                p = fetcher.get_page(url)
            except BlockedByRobots:
                continue
            except httpx.HTTPError as e:
                result.warnings.append(f"Couldn't load the {kind} page ({type(e).__name__}).")
                continue
            if p.status >= 400:
                continue
            soup = checks.soup_of(p.html)
            page_soups[kind] = (p.url, soup)
            texts.append((f"{kind.capitalize()} page", checks.visible_text(soup)))
        others = [s for _, s in page_soups.values()]

        # Page checks
        result.add(checks.check_viewport(home_soup))
        result.add(checks.check_title_meta(home_soup))
        result.add(checks.check_tap_to_call(home_soup, others))
        result.add(checks.check_copyright(home_soup))

        booking = checks.find_booking([home_soup, *others])
        forms = checks.contact_forms(home.url, home_soup)
        if "contact" in page_soups:
            forms += checks.contact_forms(*page_soups["contact"])
        broken_actions = []
        for action, _method in forms[:3]:
            if not action or action.lower().startswith("mailto:"):
                continue
            status = fetcher.link_status(action)  # HEAD only: forms are never submitted
            if status is None:
                broken_actions.append((action, "couldn't be reached"))
            elif status in (404, 410):
                broken_actions.append((action, f"returns 'page not found' (HTTP {status})"))
        result.add(checks.check_contact_form(forms, broken_actions, booking))
        result.add(checks.check_online_booking(booking, industry))
        result.add(checks.check_no_solicitation([(home.url, texts[0][1])] + [(u, checks.visible_text(s)) for u, s in page_soups.values()]))

        # Contact page and whether an email address appears on it (yes/no only)
        if "contact" in page_soups:
            result.contact_page_url, contact_soup = page_soups["contact"]
        else:
            contact_soup = home_soup
        result.email_published = "yes" if checks.email_appears_published(contact_soup) else "no"

        # Broken links: internal links first, skipping pages already loaded and social sites
        loaded = {home.url, *(u for u, _ in page_soups.values()), *key_pages.values()}
        candidates = [u for u in checks.all_links(home.url, home_soup) if u not in loaded and not is_shared_host(urlsplit(u).hostname or "")]
        candidates.sort(key=lambda u: not checks.same_site(u, domain))
        checked, broken = [], []
        for url in candidates[:MAX_LINKS_CHECKED]:
            status = fetcher.link_status(url)
            if status == -1:
                continue  # robots.txt asked us not to check this one
            checked.append(url)
            if status in (404, 410) or status is None:
                broken.append(f"{url} ({'HTTP ' + str(status) if status else 'unreachable'})")
        if checked:
            if not broken:
                result.add(Finding(checks.BROKEN_LINKS, True, "low", f"Checked {len(checked)} homepage links; none were broken."))
            else:
                shown = "; ".join(broken[:5]) + (f"; and {len(broken) - 5} more" if len(broken) > 5 else "")
                result.add(Finding(checks.BROKEN_LINKS, False, "medium" if len(broken) >= 2 else "low", f"{len(broken)} of {len(checked)} homepage links checked are broken: {shown}."))

        result.page_texts = [(label, text[:MAX_TEXT_PER_PAGE]) for label, text in texts]
        log.info("Audited %s: %d requests, %d findings", domain, fetcher.requests_made, len(result.findings))

    # PageSpeed runs on Google's servers, not ours
    try:
        result.add(pagespeed(result.final_url))
    except PageSpeedError as e:
        result.warnings.append(f"PageSpeed check didn't run: {e}.")
    return result
