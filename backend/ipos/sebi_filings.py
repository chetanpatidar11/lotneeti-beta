"""Conservative index of official SEBI public-issue documents.

The index contains filing facts and links only. Offer terms are deliberately
left for reviewed deterministic extraction from the actual document.
"""

import re
import subprocess
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ipos.models import SEBIFiling

INDEX_URL = "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&sm=&ssid=15"
MAX_BYTES = 1_000_000
USER_AGENT = "LotNeeti-FilingIndex/1.0 (contact: founder@lotneeti.local)"
DOCUMENT_TYPES = (
    ("CORRIGENDUM", re.compile(r"corrigendum|addendum", re.I)),
    ("PROSPECTUS", re.compile(r"prospectus", re.I)),
    ("RHP", re.compile(r"\brhp\b|red herring", re.I)),
    ("DRHP", re.compile(r"\bdrhp\b|draft red herring", re.I)),
    ("UDRHP", re.compile(r"\budrhp\b", re.I)),
)


class _FilingIndexParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.in_row = False
        self.in_cell = False
        self.cell_number = 0
        self.date_text = ""
        self.title_text = ""
        self.url = ""
        self.in_title = False
        self.title_done = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr" and attrs.get("role") == "row":
            self.in_row = True
            self.cell_number = 0
            self.date_text = self.title_text = self.url = ""
            self.title_done = False
        elif self.in_row and tag == "td":
            self.in_cell = True
            self.cell_number += 1
        elif self.in_row and self.cell_number == 2 and tag == "a" and not self.url:
            self.url = attrs.get("href", "")
            self.in_title = True
        elif self.in_title and tag == "br":
            self.title_done = True

    def handle_data(self, data):
        if self.in_cell and self.cell_number == 1:
            self.date_text += data
        elif self.in_title and not self.title_done:
            self.title_text += data

    def handle_endtag(self, tag):
        if tag == "td":
            self.in_cell = False
            self.in_title = False
        elif tag == "tr" and self.in_row:
            if self.url and self.date_text.strip() and self.title_text.strip():
                self.rows.append((self.date_text.strip(), self.title_text.strip(), self.url))
            self.in_row = False


def parse_filing_index(html: str) -> list[dict]:
    parser = _FilingIndexParser()
    parser.feed(html)
    records = []
    seen = set()
    for raw_date, raw_title, raw_url in parser.rows:
        url = urljoin(INDEX_URL, unescape(raw_url))
        if urlparse(url).hostname != "www.sebi.gov.in" or "/filings/public-issues/" not in url:
            continue
        title = " ".join(unescape(raw_title).split())
        match = re.search(
            r"\s+[-–]\s+(?=(?:U?DRHP|RHP|Prospectus|Corrigendum|Addendum)\b)", title, re.I
        )
        issuer = title[: match.start()].strip() if match else title
        issuer = issuer[:200]
        document_type = next(
            (name for name, pattern in DOCUMENT_TYPES if pattern.search(title)), "OTHER"
        )
        try:
            filing_date = datetime.strptime(raw_date, "%b %d, %Y").date()
        except ValueError as exc:
            raise ValidationError("SEBI filing date changed format") from exc
        if url not in seen:
            records.append(
                {
                    "source_url": url,
                    "issuer_name": issuer,
                    "document_type": document_type,
                    "filing_date": filing_date,
                }
            )
            seen.add(url)
    if not records:
        raise ValidationError("SEBI filing index had no recognized public issues")
    return records


def search_issuer_filings(issuer_name: str, html: str) -> list[dict]:
    """Keep exact issuer matches from SEBI's own title/keyword search results."""

    key = re.sub(r"[^a-z0-9]", "", issuer_name.lower()).removesuffix("limited")
    if not key:
        raise ValidationError("Issuer name is required")
    try:
        records = parse_filing_index(html)
    except ValidationError:
        return []
    return [
        record
        for record in records
        if re.sub(r"[^a-z0-9]", "", record["issuer_name"].lower()).removesuffix("limited") == key
    ]


def document_pdf_url(html: str) -> str:
    """Read the official PDF URL from the filing's iframe, never a third-party link."""
    match = re.search(r"<iframe\b[^>]*\bsrc\s*=\s*['\"]([^'\"]+)", html, re.I)
    if not match:
        return ""
    iframe_url = urljoin("https://www.sebi.gov.in/", unescape(match.group(1)))
    candidate = parse_qs(urlparse(iframe_url).query).get("file", [""])[0]
    parsed = urlparse(candidate)
    return (
        candidate
        if parsed.scheme == "https"
        and parsed.hostname == "www.sebi.gov.in"
        and parsed.path.lower().endswith(".pdf")
        else ""
    )


def _read_html(url: str) -> str:
    if urlparse(url).scheme != "https" or urlparse(url).hostname != "www.sebi.gov.in":
        raise ValidationError("Only official SEBI HTTPS links are accepted")
    try:
        result = subprocess.run(
            [
                "curl",
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--proto",
                "=https",
                "--proto-redir",
                "=https",
                "--max-redirs",
                "2",
                "--max-time",
                "15",
                "--max-filesize",
                str(MAX_BYTES),
                "--user-agent",
                USER_AGENT,
                url,
            ],
            capture_output=True,
            check=True,
            timeout=20,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise OSError("Official SEBI fetch failed") from exc
    body = result.stdout
    if len(body) > MAX_BYTES:
        raise ValidationError("SEBI response exceeded the size limit")
    return body.decode("utf-8", errors="replace")


@transaction.atomic
def save_filing_index(records: list[dict], *, fetched_at=None) -> tuple[int, int]:
    if not records or len(records) > 100:
        raise ValidationError("SEBI index must contain 1 to 100 filings")
    now = fetched_at or timezone.now()
    created = 0
    for record in records:
        _, is_new = SEBIFiling.objects.update_or_create(
            source_url=record["source_url"],
            defaults={**record, "fetched_at": now},
        )
        created += int(is_new)
    return created, len(records)


def sync_sebi_index(*, html=None, fetch_documents=True) -> tuple[int, int]:
    records = parse_filing_index(html if html is not None else _read_html(INDEX_URL))
    if fetch_documents:
        for record in records:
            try:
                document_url = document_pdf_url(_read_html(record["source_url"]))
                if document_url:
                    record["document_url"] = document_url
            except (OSError, ValidationError):
                # Keep a previously verified PDF link if this detail request fails.
                pass
    return save_filing_index(records)
