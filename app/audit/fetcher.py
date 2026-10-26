"""Polite website fetching (rule 10 of the brief).

- Checks robots.txt before every request and obeys it.
- Identifies itself with a clear user agent.
- Waits at least 2 seconds between requests to the same website.
- Retries temporary failures (timeouts, 5xx, 429) with growing waits.

It only ever reads pages (GET/HEAD); it never submits forms.
"""
import logging
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)

BOT_NAME = "OutreachPipelineAudit"
MIN_DELAY_SECONDS = 2.0


def user_agent(contact_website: str | None) -> str:
    contact = f"+{contact_website}" if contact_website else "website check by a local web designer"
    return f"{BOT_NAME}/1.0 ({contact})"


class BlockedByRobots(Exception):
    """robots.txt asks bots not to fetch this URL."""


@dataclass
class Page:
    url: str  # final URL after redirects
    status: int
    html: str


def is_ssl_error(exc: Exception) -> bool:
    """Any TLS/SSL failure (these aren't worth retrying)."""
    text = repr(exc).upper()
    return "SSL" in text or "CERTIFICATE" in text or "TLS" in text


def is_certificate_error(exc: Exception) -> bool:
    """The site has HTTPS but its certificate is invalid, expired or for another name."""
    text = repr(exc).upper()
    return "CERTIFICATE" in text or "HOSTNAME MISMATCH" in text or "CERT_" in text


class PoliteFetcher:
    def __init__(
        self,
        contact_website: str | None = None,
        *,
        delay: float = MIN_DELAY_SECONDS,
        timeout: float = 20.0,
        attempts: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
        verify: bool = True,
    ):
        self.ua = user_agent(contact_website)
        self.delay = max(delay, MIN_DELAY_SECONDS)
        self.attempts = attempts
        self._sleep = sleep
        self._transport = transport
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._lock = threading.Lock()
        self.requests_made = 0
        self.client = httpx.Client(
            headers={"User-Agent": self.ua, "Accept-Language": "en-AU,en;q=0.8"},
            follow_redirects=True,
            timeout=timeout,
            transport=transport,
            verify=verify,
        )

    def insecure_twin(self) -> "PoliteFetcher":
        """A fetcher that ignores certificate errors (to read a site whose certificate
        is broken), sharing this one's robots.txt cache and request timing."""
        twin = PoliteFetcher(transport=self._transport, sleep=self._sleep, verify=False)
        twin.ua, twin.delay, twin.attempts = self.ua, self.delay, self.attempts
        twin.client.headers["User-Agent"] = self.ua
        twin._last_request, twin._robots, twin._lock = self._last_request, self._robots, self._lock
        return twin

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- politeness -----------------------------------------------------

    def _wait_turn(self, host: str) -> None:
        with self._lock:
            last = self._last_request.get(host)
            if last is not None:
                wait = self.delay - (time.monotonic() - last)
                if wait > 0:
                    self._sleep(wait)
            self._last_request[host] = time.monotonic()
            self.requests_made += 1

    def _robots_for(self, url: str) -> RobotFileParser | None:
        """Parsed robots.txt for the URL's site. None means 'allow everything'."""
        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}"
        if key in self._robots:
            return self._robots[key]
        rp = RobotFileParser()
        robots_url = key + "/robots.txt"
        try:
            self._wait_turn(parts.netloc)
            r = self.client.get(robots_url)
            if r.status_code >= 500:
                rp.disallow_all = True  # site error: play safe, as the robots.txt standard says
            elif r.status_code >= 400:
                rp = None  # no robots.txt: everything allowed
            else:
                rp.parse(r.text.splitlines())
        except httpx.HTTPError:
            rp = None  # can't reach robots.txt; the page fetch itself will fail or succeed
        self._robots[key] = rp
        return rp

    def allowed(self, url: str) -> bool:
        rp = self._robots_for(url)
        return rp is None or rp.can_fetch(BOT_NAME, url)

    # ---- requests -------------------------------------------------------

    def _request(self, method: str, url: str) -> httpx.Response:
        if not self.allowed(url):
            raise BlockedByRobots(url)
        host = urlsplit(url).netloc
        last_exc: Exception | None = None
        for attempt in range(self.attempts):
            self._wait_turn(host)
            try:
                r = self.client.request(method, url)
                if r.status_code in (429, 500, 502, 503, 504) and attempt < self.attempts - 1:
                    self._sleep(2 ** (attempt + 1))
                    continue
                return r
            except httpx.TimeoutException as e:
                last_exc = e
            except httpx.ConnectError as e:
                if is_ssl_error(e):
                    raise  # certificate problems won't fix themselves on retry
                last_exc = e
            if attempt < self.attempts - 1:
                self._sleep(2 ** (attempt + 1))
        assert last_exc is not None
        raise last_exc

    def get_page(self, url: str) -> Page:
        r = self._request("GET", url)
        ctype = r.headers.get("content-type", "")
        html = r.text[:2_000_000] if ("html" in ctype or not ctype) else ""
        return Page(url=str(r.url), status=r.status_code, html=html)

    def link_status(self, url: str) -> int | None:
        """HTTP status for a link (HEAD, falling back to GET). None if it can't be reached."""
        try:
            r = self._request("HEAD", url)
            if r.status_code in (403, 405, 501):
                r = self._request("GET", url)
            return r.status_code
        except BlockedByRobots:
            return -1  # not checked
        except httpx.HTTPError:
            return None
