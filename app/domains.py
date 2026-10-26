"""Turning messy website addresses into one comparable domain.

"https://www.SmithPlumbing.com.au/contact?x=1" -> "smithplumbing.com.au"

Pages on shared platforms (Facebook, Instagram, Linktree ...) have no domain
of their own, so they get no domain; otherwise every Facebook-only business
would count as a duplicate of every other one.
"""
import re
from urllib.parse import urlsplit

SHARED_HOSTS = {
    "facebook.com",
    "fb.com",
    "m.facebook.com",
    "instagram.com",
    "linktr.ee",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "youtube.com",
    "google.com",
    "business.site",
    "sites.google.com",
    "yelp.com",
    "yelp.com.au",
    "truelocal.com.au",
    "yellowpages.com.au",
    "hipages.com.au",
    "oneflare.com.au",
}

# Mailbox providers. A gmail.com address says nothing about which business
# it belongs to, so these domains are never put on the do-not-contact list.
FREE_MAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "outlook.com.au",
    "hotmail.com",
    "hotmail.com.au",
    "live.com",
    "live.com.au",
    "msn.com",
    "yahoo.com",
    "yahoo.com.au",
    "icloud.com",
    "me.com",
    "mac.com",
    "bigpond.com",
    "bigpond.net.au",
    "optusnet.com.au",
    "iinet.net.au",
    "tpg.com.au",
    "internode.on.net",
    "aol.com",
    "protonmail.com",
    "proton.me",
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_url(url: str | None) -> str | None:
    """Return a clean https URL, or None when blank."""
    if not url or not url.strip():
        return None
    url = url.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url
    return url


def normalise_domain(value: str | None) -> str | None:
    """Domain for a URL or bare hostname. None for blanks and shared platforms."""
    url = normalise_url(value)
    if not url:
        return None
    host = (urlsplit(url).hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return None
    if is_shared_host(host):
        return None
    return host


def is_shared_host(host: str) -> bool:
    host = host.lower()
    return any(host == h or host.endswith("." + h) for h in SHARED_HOSTS)


def is_valid_email(email: str | None) -> bool:
    return bool(email and _EMAIL_RE.match(email.strip()))


def email_domain(email: str | None) -> str | None:
    if not is_valid_email(email):
        return None
    return email.strip().lower().rsplit("@", 1)[1]


def domain_matches(candidate: str | None, blocked: str | None) -> bool:
    """True if candidate is the blocked domain or one of its subdomains."""
    if not candidate or not blocked:
        return False
    candidate, blocked = candidate.lower(), blocked.lower()
    return candidate == blocked or candidate.endswith("." + blocked)
