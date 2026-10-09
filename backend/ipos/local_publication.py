"""Publish complete official issue facts with an explicit source-use reference."""

import hashlib
import json
import os
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from ipos.models import IPO


@transaction.atomic
def publish_local_enriched_issue(issue: dict, *, rights_reference: str) -> tuple[IPO, bool]:
    """Restrict the manual preview command to its isolated test database."""
    if os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings.test" or not settings.DATABASES[
        "default"
    ]["ENGINE"].endswith("sqlite3"):
        raise ValidationError("Local test database is required")
    return publish_enriched_issue(issue, rights_reference=rights_reference)


@transaction.atomic
def publish_enriched_issue(issue: dict, *, rights_reference: str) -> tuple[IPO, bool]:
    """Publish one READY issue; reject incomplete, conflicting, or duplicate identities."""

    if not rights_reference.strip():
        raise ValidationError("Founder source-use reference is required")
    if issue.get("enrichment_state") != "READY" or issue.get("missing_planning_fields"):
        raise ValidationError("Complete reviewed official issue facts are required")
    if issue.get("source_conflict_fields") or issue.get("blocking_enrichment_errors"):
        raise ValidationError("Official source conflict or failure requires review")
    if issue.get("source_market") not in {
        "NSE_MAINBOARD",
        "NSE_EMERGE",
        "BSE_MAINBOARD",
        "BSE_SME",
    }:
        raise ValidationError("Publication needs a verified source market")
    if issue.get("listing_exchanges") not in {"NSE", "BSE", "NSE+BSE"}:
        raise ValidationError("Listing exchange requires review")
    if issue.get("designated_exchange") not in {"NSE", "BSE"}:
        raise ValidationError("Designated exchange requires review")
    symbol = issue["symbol"]
    series = "SME" if issue["issue_type"] == "SME" else "EQ"
    exchange = "bse" if issue["source_market"].startswith("BSE_") else "nse"
    source_key = f"{exchange}_enriched"
    record_id = issue.get("source_record_id") or f"{series}:{symbol}"
    existing = list(IPO.objects.select_for_update().filter(symbol=symbol))
    if any(
        item.source_key != source_key or item.source_record_id != record_id for item in existing
    ):
        raise ValidationError("An existing IPO with this symbol needs Founder review")
    if len(existing) > 1:
        raise ValidationError("Duplicate canonical symbol needs Founder review")
    fields = {
        "issuer_name": issue["issuer_name"],
        "symbol": symbol,
        "issue_type": issue["issue_type"],
        "source_market": issue["source_market"],
        "listing_exchanges": issue["listing_exchanges"],
        "designated_exchange": issue["designated_exchange"],
        "lower_price": Decimal(str(issue["lower_price"])),
        "upper_price": Decimal(str(issue["upper_price"])),
        "lot_size": int(issue["lot_size"]),
        "open_date": date.fromisoformat(issue["open_date"]),
        "close_date": date.fromisoformat(issue["close_date"]),
        "allotment_date": date.fromisoformat(issue["allotment_date"]),
        "listing_date": date.fromisoformat(issue["listing_date"])
        if issue.get("listing_date")
        else None,
        "status": "OPEN" if issue["status"].lower() == "active" else "UPCOMING",
        "publication_state": IPO.PublicationState.PUBLISHED,
        "source_url": issue.get("source_url")
        or (
            "https://www.nseindia.com/market-data/issue-information"
            f"?series={series}&symbol={symbol}&type={issue['status']}"
            if exchange == "nse"
            else "https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx"
        ),
        "source_observed_at": datetime.fromisoformat(issue["source_observed_at"]),
    }
    fingerprint = {
        key: value.isoformat() if isinstance(value, date | datetime) else str(value)
        for key, value in fields.items()
    }
    fingerprint["field_sources"] = issue["field_sources"]
    fingerprint["rights_reference"] = rights_reference.strip()
    fields["source_payload_hash"] = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True).encode()
    ).hexdigest()
    if existing:
        ipo = existing[0]
        if ipo.source_payload_hash == fields["source_payload_hash"]:
            return ipo, False
        for key, value in fields.items():
            setattr(ipo, key, value)
        ipo.save()
        return ipo, True
    ipo = IPO.objects.create(source_key=source_key, source_record_id=record_id, **fields)
    return ipo, True
