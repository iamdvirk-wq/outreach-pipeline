"""Individual website checks. Each returns a Finding with the evidence seen.

These functions only look at HTML that has already been fetched; they make
no network requests themselves, which keeps them easy to test.
"""
import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

# Names used for AuditFinding.check_name (shown on the dashboard and to the drafter).
HTTPS = "HTTPS"
SITE_LOADS = "Website loads"
VIEWPORT = "Mobile viewport"
PAGESPEED = "PageSpeed mobile score"
TAP_TO_CALL = "Click-to-call link"
CONTACT_FORM = "Contact form or booking link"
COPYRIGHT = "Copyright year"
BROKEN_LINKS = "Broken links"
TITLE_META = "Page title and meta description"
ONLINE_BOOKING = "Online booking or quote request"
NO_SOLICITATION = "No-solicitation wording"


@dataclass
class Finding:
    check_name: str
    passed: bool
    severity: str  # low / medium / high
    evidence: str


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def _short(text: str, n: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


# ---- page text ---------------------------------------------------------------

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def visible_text(soup: BeautifulSoup) -> str:
    """Readable text of a page, without scripts, styles or email addresses."""
    soup = BeautifulSoup(str(soup), "html.parser")  # work on a copy
    for tag in soup(["script", "style", "noscript", "template", "svg", "iframe"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return EMAIL_RE.sub("[email]", text)  # rule 1: addresses never leave this function


# ---- individual checks -------------------------------------------------------


def check_viewport(soup: BeautifulSoup) -> Finding:
    tag = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
    if not tag:
        return Finding(VIEWPORT, False, "high", 'No <meta name="viewport"> tag in the homepage HTML, so phones show the desktop layout shrunk down.')
    content = (tag.get("content") or "").lower()
    if "width=device-width" not in content.replace(" ", ""):
        return Finding(VIEWPORT, False, "medium", f'Viewport tag is present but doesn\'t use width=device-width (content="{_short(content, 80)}").')
    return Finding(VIEWPORT, True, "low", f'Viewport tag present (content="{_short(content, 80)}").')


AU_PHONE_RE = re.compile(r"(?<!\d)(?:\+61\s?|\(?0)[2-478]\)?[\s-]?\d{4}[\s-]?\d{4}(?!\d)|(?<!\d)1[38]00[\s-]?\d{3}[\s-]?\d{3}(?!\d)|(?<!\d)13[\s-]?\d{2}[\s-]?\d{2}(?!\d)")


def check_tap_to_call(home: BeautifulSoup, other_pages: list[BeautifulSoup]) -> Finding:
    a = home.find("a", href=re.compile(r"^\s*tel:", re.I))
    if a:
        return Finding(TAP_TO_CALL, True, "low", f"Homepage has a tap-to-call link ({_short(a['href'], 40)}).")
    for page in other_pages:
        if page.find("a", href=re.compile(r"^\s*tel:", re.I)):
            return Finding(TAP_TO_CALL, False, "low", "Tap-to-call link only on an inner page; the homepage phone number can't be tapped to call.")
    m = AU_PHONE_RE.search(visible_text(home))
    if m:
        return Finding(TAP_TO_CALL, False, "medium", f"Phone number {m.group(0).strip()} appears as plain text on the homepage; no tel: link, so mobile visitors can't tap to call.")
    return Finding(TAP_TO_CALL, False, "medium", "No tap-to-call (tel:) link and no phone number found on the homepage.")


BOOKING_PROVIDERS = [
    "calendly.com", "cliniko.com", "halaxy.com", "nookal.com", "fresha.com", "timely.com.au", "gettimely.com",
    "mindbodyonline.com", "squareup.com/appointments", "square.site", "setmore.com", "simplybook", "acuityscheduling.com",
    "opentable.com", "resdiary.com", "sevenrooms.com", "bookeo.com", "hotdoc.com.au", "healthengine.com.au",
    "servicem8.com", "tradify", "jobber", "bookwell", "zenoti.com", "phorest.com", "booksy.com", "now-book-it",
    "obee.com.au", "nowbookit.com", "tablein.com", "quandoo", "dish.co", "appointfix", "housecallpro", "vagaro.com",
]
BOOKING_WORDS = re.compile(r"\b(book(ing)?s?( now| online| an? appointment)?|make an appointment|reserve|reservations?|get an? (free )?quote|request an? (free )?quote|free quote|instant quote|quote request|get a price|enquire now)\b", re.I)


def find_booking(soups: list[BeautifulSoup]) -> str | None:
    """Evidence of online booking or quote requests, or None."""
    for soup in soups:
        for tag in soup.find_all(["a", "iframe", "script", "form"]):
            target = (tag.get("href") or tag.get("src") or tag.get("action") or "").lower()
            for p in BOOKING_PROVIDERS:
                if p in target:
                    return f"Links to a booking system ({p})."
        for tag in soup.find_all(["a", "button"]):
            label = " ".join(tag.get_text(" ").split())
            if label and len(label) < 60 and BOOKING_WORDS.search(label):
                return f'Has a "{_short(label, 50)}" button or link.'
    return None


def _real_forms(soup: BeautifulSoup) -> list:
    forms = []
    for form in soup.find_all("form"):
        has_message = form.find("textarea") is not None
        has_contact = form.find("input", attrs={"type": re.compile("email|tel", re.I)}) is not None
        if has_message or has_contact:
            forms.append(form)
    return forms


def contact_forms(page_url: str, soup: BeautifulSoup) -> list[tuple[str, str | None]]:
    """(action URL or '' for same page, method) for each enquiry-style form."""
    out = []
    for form in _real_forms(soup):
        action = (form.get("action") or "").strip()
        out.append((urljoin(page_url, action) if action and not action.startswith(("#", "javascript:")) else "", (form.get("method") or "get").lower()))
    return out


def check_contact_form(forms: list[tuple[str, str | None]], broken_actions: list[tuple[str, str]], booking: str | None) -> Finding:
    if broken_actions:
        url, why = broken_actions[0]
        return Finding(CONTACT_FORM, False, "high", f"The enquiry form sends to {_short(url, 80)}, which {why}. Messages may not be arriving.")
    mailto = [a for a, _ in forms if a.lower().startswith("mailto:")]
    if forms and len(mailto) == len(forms):
        return Finding(CONTACT_FORM, False, "low", "The enquiry form uses a mailto: action, which only works if the visitor has an email app set up.")
    if forms:
        return Finding(CONTACT_FORM, True, "low", f"Found {len(forms)} enquiry form(s) on the homepage or contact page.")
    if booking:
        return Finding(CONTACT_FORM, True, "low", f"No enquiry form, but a booking link: {booking}")
    return Finding(CONTACT_FORM, False, "high", "No contact form or booking link found on the homepage or contact page.")


COPYRIGHT_RE = re.compile(r"(?:©|\(c\)|copyright)\s*(?:\D{0,20}?)((?:19|20)\d{2})(?:\s*[-–—]\s*((?:19|20)\d{2}))?", re.I)


def check_copyright(soup: BeautifulSoup, today: date | None = None) -> Finding | None:
    """None when no copyright year is shown (not a problem worth mentioning)."""
    today = today or date.today()
    footer = soup.find("footer")
    text = visible_text(footer) if footer else visible_text(soup)
    years = []
    for m in COPYRIGHT_RE.finditer(text):
        years.extend(int(y) for y in m.groups() if y)
    years = [y for y in years if y <= today.year]
    if not years:
        return None
    latest = max(years)
    age = today.year - latest
    if age >= 3:
        sev = "medium" if age >= 5 else "low"
        return Finding(COPYRIGHT, False, sev, f'Footer copyright year is {latest} ({age} years old), which can make the site look unmaintained.')
    return Finding(COPYRIGHT, True, "low", f"Footer copyright year is {latest}.")


def check_title_meta(soup: BeautifulSoup) -> Finding:
    title = " ".join((soup.title.get_text() if soup.title else "").split())
    desc_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    desc = " ".join((desc_tag.get("content") or "").split()) if desc_tag else ""
    if not title:
        return Finding(TITLE_META, False, "medium", "Homepage has no <title>, so Google shows a generic or missing heading in search results.")
    if not desc:
        return Finding(TITLE_META, False, "low", f'Homepage title is "{_short(title, 70)}" but there is no meta description for search results.')
    return Finding(TITLE_META, True, "low", f'Title "{_short(title, 60)}" and a meta description are present.')


BOOKING_RELEVANT = re.compile(
    r"physio|chiro|osteo|dent|doctor|gp\b|clinic|medical|health|massage|podiat|psycholog|counsel|optom|vet|beauty|salon|hair|barber|nail|spa|"
    r"cafe|café|restaurant|bar\b|bistro|hotel|motel|accommodation|bakery|catering|pub\b|"
    r"plumb|electric|builder|build|carpent|roof|paint|landscap|garden|clean|pest|locksmith|mechanic|auto|tyre|air ?con|hvac|fenc|tiling|tiler|concret|"
    r"gym|fitness|personal train|yoga|pilates|tutor|driving|photograph|groom|dog|pet|removal|storage|repair|service|trade",
    re.I,
)


def booking_relevant(industry: str | None) -> bool:
    return bool(industry and BOOKING_RELEVANT.search(industry))


def check_online_booking(booking: str | None, industry: str | None) -> Finding | None:
    if booking:
        return Finding(ONLINE_BOOKING, True, "low", booking)
    if booking_relevant(industry):
        return Finding(ONLINE_BOOKING, False, "medium", f"No online booking or quote request found on the pages checked, which customers of a {industry.lower()} often expect.")
    return None


NO_SOLICITATION_RE = re.compile(
    r"no (?:unsolicited |cold )?(?:solicitations?|soliciting|solicitors)|do not solicit|don'?t solicit|"
    r"no (?:unsolicited |cold )?(?:marketing|sales|seo|web design|advertising)\s*(?:emails?|calls?|enquiries|inquiries|offers|approaches|pitches)|"
    r"(?:we )?do not (?:accept|want|respond to) (?:unsolicited|marketing|sales|cold)|"
    r"unsolicited (?:emails?|offers|approaches|marketing|sales) (?:will not|won'?t) be (?:answered|responded|replied)|"
    r"no (?:agencies|marketers|marketing agencies)",
    re.I,
)


def check_no_solicitation(texts: list[tuple[str, str]]) -> Finding | None:
    """texts: (page url, visible text). Returns a failing finding if found."""
    for url, text in texts:
        m = NO_SOLICITATION_RE.search(text)
        if m:
            start = max(0, m.start() - 40)
            snippet = _short(text[start : m.end() + 40], 160)
            return Finding(NO_SOLICITATION, False, "high", f'{urlsplit(url).path or "/"} says: "…{snippet}…"')
    return None


def email_appears_published(soup: BeautifulSoup) -> bool:
    """Whether an email address seems to be on the page. The address itself is never returned."""
    if soup.find("a", href=re.compile(r"^\s*mailto:", re.I)):
        return True
    if soup.find(attrs={"class": re.compile("__cf_email__")}) or soup.find(attrs={"data-cfemail": True}):
        return True
    raw = soup.get_text(" ")
    return bool(EMAIL_RE.search(raw))


# ---- finding the key pages ---------------------------------------------------

KEY_PAGES = {
    "contact": re.compile(r"contact|get-in-touch|enquir|inquir|reach-us|find-us|location", re.I),
    "services": re.compile(r"services?|what-we-do|treatments?|menu|products?|our-work|pricing|prices|solutions", re.I),
    "about": re.compile(r"about|our-story|who-we-are|team|meet", re.I),
}


def same_site(url: str, domain: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host == domain or host.endswith("." + domain)


def internal_links(page_url: str, soup: BeautifulSoup, domain: str) -> list[tuple[str, str]]:
    """(absolute URL without fragment, link text) for same-site links, de-duplicated."""
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#", "sms:", "data:")):
            continue
        url = urljoin(page_url, href).split("#")[0]
        if not url.startswith(("http://", "https://")) or not same_site(url, domain) or url in seen:
            continue
        seen.add(url)
        out.append((url, " ".join(a.get_text(" ").split())))
    return out


def all_links(page_url: str, soup: BeautifulSoup) -> list[str]:
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#", "sms:", "data:")):
            continue
        url = urljoin(page_url, href).split("#")[0]
        if url.startswith(("http://", "https://")) and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def pick_key_pages(home_url: str, links: list[tuple[str, str]]) -> dict[str, str]:
    """Choose up to one contact, services and about page from the homepage links."""
    home_path = urlsplit(home_url).path.rstrip("/")
    chosen: dict[str, str] = {}
    for kind, pattern in KEY_PAGES.items():
        for url, text in links:
            path = urlsplit(url).path.rstrip("/")
            if path == home_path or url in chosen.values():
                continue
            if re.search(r"\.(pdf|jpe?g|png|gif|docx?|zip)$", path, re.I):
                continue
            if pattern.search(path) or pattern.search(text.replace(" ", "-")):
                chosen[kind] = url
                break
    return chosen
