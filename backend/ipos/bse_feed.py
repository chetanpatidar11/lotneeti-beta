"""Independent BSE public-issue discovery from a permissioned saved feed."""

import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ipos.feed_watch import _PRICE_PATTERN
from ipos.models import IPOFeedBatch, IPOFeedObservation


def normalize_bse_discovery_row(raw: dict) -> tuple[str, dict]:
    if not isinstance(raw, dict):
        raise ValidationError("BSE discovery row must be an object")
    symbol = str(raw.get("symbol") or raw.get("Symbol") or "").strip().upper()
    issuer = str(raw.get("company_name") or raw.get("Company Name") or "").strip()
    platform = str(raw.get("platform") or raw.get("Platform") or "").strip().upper()
    if not symbol or not issuer or platform not in {"MAINBOARD", "SME"}:
        raise ValidationError("BSE discovery needs symbol, issuer and listing platform")
    if len(symbol) > 40 or len(issuer) > 200:
        raise ValidationError("BSE issue identity is too long")
    result = {
        "symbol": symbol,
        "issuer_name": issuer,
        "issue_type": platform,
        "listing_platform": platform,
        "listing_exchanges": "BSE",
        "designated_exchange": "BSE",
        "source_market": "BSE_SME" if platform == "SME" else "BSE_MAINBOARD",
        "exchange_hint": "BSE",
        "status": str(raw.get("status") or raw.get("Status") or "").strip(),
    }
    for source, target in (("open_date", "open_date"), ("close_date", "close_date")):
        value = raw.get(source)
        if value:
            try:
                result[target] = datetime.fromisoformat(str(value)).date().isoformat()
            except ValueError as exc:
                raise ValidationError(f"BSE {source} is invalid") from exc
    band = raw.get("price_band") or raw.get("Price Band")
    if band:
        match = _PRICE_PATTERN.fullmatch(str(band).strip())
        if not match:
            raise ValidationError("BSE price band format is unknown")
        try:
            lower, upper = (Decimal(value.replace(",", "")) for value in match.groups())
        except InvalidOperation as exc:
            raise ValidationError("BSE price band is invalid") from exc
        if lower <= 0 or upper < lower:
            raise ValidationError("BSE price band is invalid")
        result.update(lower_price=str(lower), upper_price=str(upper))
    return f"{platform}:{symbol}", result


@transaction.atomic
def record_bse_discovery_rows(
    rows: list, *, source_url: str, observed_at: datetime
) -> tuple[int, int]:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname != "www.bseindia.com":
        raise ValidationError("BSE discovery needs an official HTTPS source")
    if timezone.is_naive(observed_at) or not isinstance(rows, list) or len(rows) > 500:
        raise ValidationError("BSE discovery needs a bounded timezone-aware response")
    prepared = []
    seen = set()
    for raw in rows:
        record_id, normalized = normalize_bse_discovery_row(raw)
        if record_id in seen:
            raise ValidationError("BSE discovery repeats a security identity")
        seen.add(record_id)
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
        prepared.append((record_id, raw, normalized, digest))
    batch_hash = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    IPOFeedBatch.objects.get_or_create(
        source_key="bse",
        payload_hash=batch_hash,
        observed_at=observed_at,
        defaults={
            "source_url": source_url,
            "row_keys": [
                {"record_id": record_id, "payload_hash": digest}
                for record_id, _, _, digest in prepared
            ],
        },
    )
    created = 0
    for record_id, raw, normalized, digest in prepared:
        _, is_new = IPOFeedObservation.objects.get_or_create(
            source_key="bse",
            source_record_id=record_id,
            payload_hash=digest,
            observed_at=observed_at,
            defaults={
                "source_url": source_url,
                "raw_payload": raw,
                "normalized_payload": normalized,
                "snapshot_created_at": timezone.now(),
            },
        )
        created += int(is_new)
    return created, len(prepared)


def current_bse_issues() -> list[dict]:
    batch = IPOFeedBatch.objects.filter(source_key="bse").first()
    if batch is None:
        return []
    wanted = {item["record_id"]: item["payload_hash"] for item in batch.row_keys}
    rows = []
    for observation in IPOFeedObservation.objects.filter(
        source_key="bse", observed_at=batch.observed_at, source_record_id__in=wanted
    ):
        if observation.payload_hash != wanted[observation.source_record_id]:
            continue
        _, normalized = normalize_bse_discovery_row(observation.raw_payload)
        rows.append(
            {
                **normalized,
                "source_key": "bse",
                "source_record_id": observation.source_record_id,
                "source_url": observation.source_url,
                "source_observed_at": observation.observed_at.isoformat(),
                "source_updated_at": observation.source_updated_at.isoformat()
                if observation.source_updated_at
                else None,
                "source_fetched_at": observation.fetched_at.isoformat(),
            }
        )
    from ipos.enrichment import enrich_current_feed_issues

    return enrich_current_feed_issues(sorted(rows, key=lambda item: item["symbol"]))
