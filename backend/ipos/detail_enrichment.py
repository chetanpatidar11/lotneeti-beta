"""Normalize official exchange issue information after list discovery."""

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ipos.models import IPOEnrichmentObservation

PRICE_BAND = re.compile(
    r"(?:Rs\.?|₹)?\s*([\d,]+(?:\.\d+)?)(?:\s*/-)?\s*(?:to|[-–])\s*"
    r"(?:Rs\.?|₹)?\s*([\d,]+(?:\.\d+)?)(?:\s*/-)?",
    re.I,
)
ISSUE_PERIOD = re.compile(r"(\d{1,2}-[A-Za-z]{3}-\d{4})\s+to\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", re.I)
INTEGER = re.compile(r"\b(\d[\d,]*)\b")
OFFICIAL_DOCUMENT_HOSTS = frozenset(
    {"nsearchives.nseindia.com", "archives.nseindia.com", "www.sebi.gov.in", "www.bseindia.com"}
)
DETAIL_NORMALIZER_VERSION = 2


def nse_issue_detail_url(symbol: str, series: str) -> str:
    if not re.fullmatch(r"[A-Z0-9_-]{1,40}", symbol) or series not in {"EQ", "SME"}:
        raise ValidationError("Unsupported NSE issue identity")
    return f"https://www.nseindia.com/api/ipo-detail?symbol={quote(symbol)}&series={series}"


def official_document_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme == "https" and parsed.hostname in OFFICIAL_DOCUMENT_HOSTS:
        return value.strip()
    return None


def _first_integer(value: object) -> int | None:
    match = INTEGER.search(str(value or ""))
    return int(match.group(1).replace(",", "")) if match else None


def _date(value: str) -> str:
    return datetime.strptime(value.title(), "%d-%b-%Y").date().isoformat()


def _explicit_date(value: object) -> str | None:
    raw = str(value or "").strip()
    for pattern in ("%d-%b-%Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.title(), pattern).date().isoformat()
        except ValueError:
            continue
    return None


def _common_facts(fields: dict[str, str], *, lot_label: str, price_labels: tuple[str, ...]) -> dict:
    facts = {}
    period = ISSUE_PERIOD.search(fields.get("Issue Period", ""))
    if period:
        facts["open_date"], facts["close_date"] = (_date(value) for value in period.groups())
    for label in price_labels:
        match = PRICE_BAND.search(fields.get(label, ""))
        if match:
            lower, upper = (Decimal(value.replace(",", "")) for value in match.groups())
            if lower <= 0 or upper < lower:
                raise ValidationError("Invalid official price band")
            facts["lower_price"], facts["upper_price"] = (f"{lower:.2f}", f"{upper:.2f}")
            break
    lot = _first_integer(fields.get(lot_label))
    if lot is not None:
        if lot <= 0:
            raise ValidationError("Invalid official lot size")
        facts["lot_size"] = lot
    for label in ("Allotment Date", "Basis of Allotment Date"):
        if value := _explicit_date(fields.get(label)):
            facts["allotment_date"] = value
            break
    return facts


class NSEIPOIssueDetailProvider:
    source_key = "nse"

    def normalize(self, raw: dict, *, symbol: str, series: str) -> dict:
        info = raw.get("issueInfo") if isinstance(raw, dict) else None
        rows = info.get("dataList") if isinstance(info, dict) else None
        if not isinstance(rows, list) or not rows:
            raise ValidationError("NSE issue detail has no information rows")
        fields = {
            str(row["title"]).strip(): str(row.get("value") or "").strip()
            for row in rows
            if isinstance(row, dict) and row.get("title")
        }
        actual_symbol = fields.get("Symbol") or info.get("symbol")
        if actual_symbol != symbol:
            raise ValidationError("NSE issue detail symbol does not match discovery")
        lot_label = "Lot Size" if series == "SME" else "Bid Lot"
        facts = _common_facts(
            fields, lot_label=lot_label, price_labels=("Price Range", "Issue Price")
        )
        minimum = _first_integer(fields.get("Minimum Order Quantity"))
        warnings = []
        if minimum and facts.get("lot_size") and minimum % facts["lot_size"]:
            warnings.append("minimum_order_quantity_differs_from_lot_multiple")
        issuer_name = next(
            (key for key, value in fields.items() if not value and key.lower().endswith("limited")),
            None,
        )
        links = {}
        for source_label, target in (
            ("Red Herring Prospectus", "rhp_url"),
            ("Price Band Advertisement", "price_band_document_url"),
            ("Security Parameters (Pre Anchor)", "security_parameters_url"),
            ("Anchor Allocation Report", "anchor_allocation_url"),
        ):
            url = official_document_url(fields.get(source_label))
            if url:
                links[target] = url
        return {
            "symbol": symbol,
            "series": series,
            "issuer_name": issuer_name,
            "facts": facts,
            "metadata": {
                "issue_size": fields.get("Issue Size"),
                "issue_type": fields.get("Issue Type"),
                "upi_mandate_cutoff": fields.get("Cut-off time for UPI Mandate Confirmation"),
                "minimum_order_quantity": minimum,
                "discount": fields.get("Discount"),
                "face_value": fields.get("Face Value"),
                "tick_size": fields.get("Tick Size"),
                "max_retail_subscription": fields.get(
                    "Maximum Subscription Amount for Retail Investor"
                ),
                "qib_limit": fields.get("Maximum Bid Quantity for QIB Investors"),
                "nib_limit": fields.get("Maximum Bid Quantity for NIB Investors"),
                "market_timings": fields.get("IPO Market Timings"),
                "brlm": fields.get("Book Running Lead Managers"),
                "sponsor_bank": fields.get("Sponsor Bank"),
                "categories": fields.get("Categories"),
                "registrar_name": fields.get("Name of the Registrar"),
                "registrar_contact": fields.get("Contact person name number and Email id"),
            },
            "links": links,
            "consistency_warnings": warnings,
            "source_fields": fields,
            # Demand-graph timestamps do not qualify as issue-fact updates.
            "source_updated_at": (raw.get("metaInfo") or {}).get("issueInfoUpdatedAt")
            if isinstance(raw.get("metaInfo"), dict)
            else None,
        }


class _TableCells(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None
        self.cell_href = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []
            self.cell_href = None
        elif tag == "a" and self.cell is not None:
            self.cell_href = dict(attrs).get("href")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            text = " ".join("".join(self.cell).split())
            self.row.append(self.cell_href if self.cell_href and len(self.row) == 1 else text)
            self.cell = None
            self.cell_href = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


class BSEIPOIssueDetailProvider:
    source_key = "bse"

    def normalize(self, raw: dict | str, *, symbol: str) -> dict:
        if isinstance(raw, str):
            parser = _TableCells()
            parser.feed(raw)
            fields = {row[0]: row[1] for row in parser.rows if len(row) >= 2}
        elif isinstance(raw, dict):
            rows = raw.get("dataList")
            fields = (
                {str(row["title"]): str(row.get("value") or "") for row in rows}
                if isinstance(rows, list)
                else {str(key): str(value) for key, value in raw.items()}
            )
        else:
            raise ValidationError("BSE issue detail is invalid")
        actual_symbol = fields.get("Symbol")
        if actual_symbol and actual_symbol != symbol:
            raise ValidationError("BSE issue detail symbol does not match discovery")
        facts = _common_facts(
            fields, lot_label="Market Lot", price_labels=("Price Band", "Price Range")
        )
        minimum = _first_integer(fields.get("Minimum Bid Quantity"))
        warnings = []
        if minimum and facts.get("lot_size") and minimum % facts["lot_size"]:
            warnings.append("minimum_bid_quantity_differs_from_market_lot_multiple")
        links = {
            key: url
            for label, key in (("Prospectus", "prospectus_url"), ("GID", "gid_url"))
            if fields.get(label)
            and (url := official_document_url(urljoin("https://www.bseindia.com", fields[label])))
        }
        return {
            "symbol": symbol,
            "facts": facts,
            "metadata": {
                "security_type": fields.get("Security Type"),
                "issue_size": fields.get("Issue Size"),
                "minimum_bid_quantity": minimum,
                "market_timings": fields.get("IPO Market Timings"),
                "upi_mandate_cutoff": fields.get("UPI cutoff"),
                "categories": fields.get("IPO Categories"),
                "face_value": fields.get("Face Value"),
                "tick_size": fields.get("Tick Size"),
                "brlm": fields.get("BRLM"),
                "sponsor_bank": fields.get("Sponsor Bank"),
                "registrar_name": fields.get("Registrar"),
            },
            "links": links,
            "consistency_warnings": warnings,
            "source_fields": fields,
            "source_updated_at": None,
        }


@transaction.atomic
def record_detail_observation(
    *,
    source_key: str,
    symbol: str,
    source_url: str,
    raw: dict | str,
    normalized: dict,
    fetched_at=None,
) -> IPOEnrichmentObservation:
    fetched_at = fetched_at or timezone.now()
    source_updated_at = normalized.get("source_updated_at")
    if source_updated_at:
        try:
            source_updated_at = datetime.fromisoformat(str(source_updated_at))
        except ValueError as exc:
            raise ValidationError("Invalid official source update timestamp") from exc
        if timezone.is_naive(source_updated_at):
            raise ValidationError("Official source update timestamp requires timezone")
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    observation, _ = IPOEnrichmentObservation.objects.get_or_create(
        source_key=source_key,
        stage="DETAIL",
        symbol=symbol,
        payload_hash=hashlib.sha256(encoded).hexdigest(),
        normalizer_version=DETAIL_NORMALIZER_VERSION,
        defaults={
            "source_url": source_url,
            "normalized_payload": normalized,
            "source_updated_at": source_updated_at,
            "fetched_at": fetched_at,
        },
    )
    return observation
