"""Store incomplete exchange issue-list rows without making them plannable."""

import hashlib
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ipos.models import IPOFeedBatch, IPOFeedObservation

NSE_CURRENT_URL = "https://www.nseindia.com/api/ipo-current-issue"
_PRICE_PATTERN = re.compile(
    r"(?:Rs\.?\s*)?([\d,]+(?:\.\d+)?)\s*(?:to|-|–)\s*(?:Rs\.?\s*)?([\d,]+(?:\.\d+)?)", re.I
)


def normalize_nse_current_row(raw: dict) -> tuple[str, dict]:
    """Copy only verified fields from the NSE current-issues response."""

    if not isinstance(raw, dict):
        raise ValidationError("NSE issue must be an object")
    symbol = str(raw.get("symbol") or "").strip()
    issuer = str(raw.get("companyName") or "").strip()
    series = str(raw.get("series") or "").strip().upper()
    if not symbol or not issuer or series not in {"EQ", "SME"}:
        raise ValidationError("NSE issue needs a symbol, issuer and supported series")
    if len(symbol) > 40 or len(issuer) > 200:
        raise ValidationError("NSE issue identity is too long")
    result = {
        "issuer_name": issuer,
        "symbol": symbol,
        "issue_type": "SME" if series == "SME" else "MAINBOARD",
        "status": str(raw.get("status") or "").strip(),
        # A row obtained from the NSE SME series is an NSE EMERGE discovery.
        # NSE's isBse flag is not proof of a BSE listing or requirement.
        "exchange_hint": "NSE",
        "source_market": "NSE_EMERGE" if series == "SME" else "NSE_MAINBOARD",
        "listing_platform": "SME" if series == "SME" else "MAINBOARD",
        "listing_exchanges": "NSE",
        "designated_exchange": "NSE",
    }
    for source, target in (("issueStartDate", "open_date"), ("issueEndDate", "close_date")):
        value = raw.get(source)
        if value:
            try:
                result[target] = datetime.strptime(str(value), "%d-%b-%Y").date().isoformat()
            except ValueError as exc:
                raise ValidationError(f"NSE {source} is invalid") from exc
    price = raw.get("issuePrice")
    if price:
        match = _PRICE_PATTERN.fullmatch(str(price).strip())
        if not match:
            raise ValidationError("NSE price band format is unknown")
        try:
            lower, upper = (Decimal(value.replace(",", "")) for value in match.groups())
        except InvalidOperation as exc:
            raise ValidationError("NSE price band is invalid") from exc
        if lower <= 0 or upper < lower:
            raise ValidationError("NSE price band is invalid")
        result["lower_price"] = str(lower)
        result["upper_price"] = str(upper)
    result["missing_planning_fields"] = [
        name
        for name in (
            "lower_price",
            "upper_price",
            "lot_size",
            "open_date",
            "close_date",
            "allotment_date",
        )
        if name not in result
    ]
    return f"{series}:{symbol}", result


@transaction.atomic
def record_nse_current_rows(rows: list, *, observed_at: datetime) -> tuple[int, int]:
    """Validate a bounded whole response before saving any immutable rows."""

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValidationError("Observation time must have a timezone")
    if not isinstance(rows, list) or len(rows) > 500:
        raise ValidationError("NSE response must be a list of at most 500 issues")
    prepared = []
    seen = set()
    for raw in rows:
        record_id, normalized = normalize_nse_current_row(raw)
        if record_id in seen:
            raise ValidationError("NSE response repeats an issue identity")
        seen.add(record_id)
        payload_hash = hashlib.sha256(
            json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        prepared.append((record_id, raw, normalized, payload_hash))
    response_hash = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    IPOFeedBatch.objects.get_or_create(
        source_key="nse",
        payload_hash=response_hash,
        observed_at=observed_at,
        defaults={
            "source_url": NSE_CURRENT_URL,
            "row_keys": [
                {"record_id": record_id, "payload_hash": payload_hash}
                for record_id, _, _, payload_hash in prepared
            ],
        },
    )
    created = 0
    for record_id, raw, normalized, payload_hash in prepared:
        _, was_created = IPOFeedObservation.objects.get_or_create(
            source_key="nse",
            source_record_id=record_id,
            payload_hash=payload_hash,
            observed_at=observed_at,
            defaults={
                "source_url": NSE_CURRENT_URL,
                "raw_payload": raw,
                "normalized_payload": normalized,
                "snapshot_created_at": timezone.now(),
            },
        )
        created += int(was_created)
    return created, len(prepared)


def current_feed_issues() -> list[dict]:
    """Read the most recent complete saved response; no customer-time network call."""

    batch = IPOFeedBatch.objects.filter(source_key="nse").first()
    if batch is None:
        return []
    wanted = {item["record_id"]: item["payload_hash"] for item in batch.row_keys}
    result = []
    now = timezone.now()
    for observation in IPOFeedObservation.objects.filter(
        source_key="nse", observed_at=batch.observed_at, source_record_id__in=wanted
    ):
        if observation.payload_hash == wanted[observation.source_record_id]:
            # Re-normalize the immutable source row so corrected market identity
            # applies to older saved snapshots without altering their history.
            _, normalized = normalize_nse_current_row(observation.raw_payload)
            result.append(
                {
                    **normalized,
                    "source_key": observation.source_key,
                    "source_record_id": observation.source_record_id,
                    "source_observed_at": observation.observed_at.isoformat(),
                    "source_updated_at": observation.source_updated_at.isoformat()
                    if observation.source_updated_at
                    else None,
                    "source_fetched_at": observation.fetched_at.isoformat(),
                    "snapshot_created_at": observation.snapshot_created_at.isoformat()
                    if observation.snapshot_created_at
                    else None,
                    "fresh": timedelta(0) <= now - observation.observed_at < timedelta(hours=24),
                }
            )
    from ipos.enrichment import enrich_current_feed_issues

    return enrich_current_feed_issues(
        sorted(result, key=lambda item: (item.get("close_date", ""), item["issuer_name"]))
    )
