"""Importing leads from a CSV file you collected yourself.

Expected columns (header names are matched loosely, case doesn't matter):
name, website, phone, industry, suburb, city, rating, review_count
Optional: state, address.

Any column that holds email addresses is ignored on purpose (rule 1 of the
brief: no harvested or imported address lists). Add addresses by hand on
each business's page after checking they are published on the business's
own website or listing.
"""
import csv
import io
import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app import dnc
from app.domains import normalise_domain, normalise_url
from app.models import Business
from app.services import find_duplicate

log = logging.getLogger(__name__)

COLUMN_ALIASES = {
    "name": ["name", "business name", "business", "company", "title"],
    "website": ["website", "website url", "url", "site", "web"],
    "phone": ["phone", "phone number", "telephone", "tel", "mobile"],
    "industry": ["industry", "category", "type", "categoryname"],
    "suburb": ["suburb", "locality", "neighbourhood", "neighborhood"],
    "city": ["city", "town"],
    "state": ["state", "region"],
    "address": ["address", "street address", "full address"],
    "rating": ["rating", "stars", "google rating", "totalscore"],
    "review_count": ["review_count", "review count", "reviews", "reviews count", "reviewscount", "number of reviews"],
}


@dataclass
class ImportResult:
    imported: int = 0
    skipped: list[tuple[int, str, str]] = field(default_factory=list)  # (row number, name, reason)
    ignored_email_columns: list[str] = field(default_factory=list)
    unknown_columns: list[str] = field(default_factory=list)


def _norm_header(h: str) -> str:
    return " ".join((h or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _is_email_column(header: str) -> bool:
    h = _norm_header(header).replace(" ", "")
    return "email" in h or "e-mail" in header.lower() or h in ("mail", "emails")


def _map_columns(headers: list[str]) -> tuple[dict[str, str], list[str], list[str]]:
    mapping: dict[str, str] = {}
    email_cols, unknown = [], []
    for h in headers:
        if _is_email_column(h):
            email_cols.append(h)
            continue
        nh = _norm_header(h)
        for key, aliases in COLUMN_ALIASES.items():
            if key not in mapping and (nh in aliases or nh.replace(" ", "") in [a.replace(" ", "") for a in aliases]):
                mapping[key] = h
                break
        else:
            unknown.append(h)
    return mapping, email_cols, unknown


def _num(v: str | None, cast):
    v = (v or "").strip().replace(",", "")
    if not v:
        return None
    try:
        return cast(float(v))
    except ValueError:
        return None


def read_csv_text(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Couldn't read the file. Save it as CSV (UTF-8) and try again.")


def import_csv(session: Session, text: str) -> ImportResult:
    result = ImportResult()
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("The file is empty or has no header row.")
    mapping, result.ignored_email_columns, result.unknown_columns = _map_columns(reader.fieldnames)
    if "name" not in mapping:
        raise ValueError("No 'name' column found. The first row must contain column headings.")
    if result.ignored_email_columns:
        log.info("CSV import: ignored email column(s) %s", result.ignored_email_columns)

    def get(row: dict, key: str) -> str | None:
        col = mapping.get(key)
        val = (row.get(col) or "").strip() if col else ""
        if "@" in val and key != "website":
            return None  # never take an address hidden in another column
        return val or None

    for i, row in enumerate(reader, start=2):  # row 1 is the header
        name = get(row, "name")
        if not name:
            result.skipped.append((i, "", "No business name"))
            continue
        website = normalise_url(get(row, "website"))
        if website and "@" in website:
            website = None
        domain = normalise_domain(website)
        suburb = get(row, "suburb")

        dup = find_duplicate(session, domain=domain, name=name, suburb=suburb)
        if dup:
            result.skipped.append((i, name, f"Already in the database as #{dup.id}"))
            continue
        blocked = dnc.is_blocked(session, domain=domain)
        if blocked:
            result.skipped.append((i, name, "On the do-not-contact list"))
            continue

        rating = _num(get(row, "rating"), float)
        if rating is not None and not 0 <= rating <= 5:
            rating = None
        b = Business(
            name=name,
            website_url=website,
            domain=domain,
            phone=get(row, "phone"),
            industry=get(row, "industry"),
            suburb=suburb,
            city=get(row, "city"),
            state=(get(row, "state") or "").upper() or None,
            address=get(row, "address"),
            rating=rating,
            review_count=_num(get(row, "review_count"), int),
            source="csv_import",
            status="new",
        )
        session.add(b)
        session.flush()  # so duplicates later in the same file are caught
        result.imported += 1

    session.commit()
    log.info("CSV import: %d imported, %d skipped", result.imported, len(result.skipped))
    return result
