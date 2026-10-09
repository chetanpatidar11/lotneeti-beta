"""Founder-authorized InvestorGain IPO and GMP source adapter."""

import hashlib
import html
import json
import re
import ssl
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.request import Request, urlopen

import certifi
from django.db import transaction
from django.utils import timezone

from ipos.dto import IPORecord
from ipos.licensed_source_schedule import reserve_refresh_slot
from ipos.models import (
    IPO,
    GMPObservation,
    GMPProviderState,
    IPOProviderSyncState,
    IPOSourceLink,
    IPOSourceSnapshot,
)
from ipos.provider_health import record_provider_failure, record_provider_success

PROVIDER_KEY = "investorgain"
SOURCE_ORIGIN = "https://www.investorgain.com"
_NAME_NOISE = re.compile(r"\b(?:limited|ltd|india|industries|private)\b", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_GMP_VALUE = re.compile(r"<b>\s*([^<]+?)\s*</b>", re.IGNORECASE)


class InvestorGainError(RuntimeError):
    """The permissioned source could not be used for this run."""


def issuer_key(value: str) -> str:
    return _NON_ALNUM.sub("", _NAME_NOISE.sub(" ", value or "").lower())


def source_url(now) -> str:
    local = timezone.localtime(now)
    fiscal_start = local.year if local.month >= 4 else local.year - 1
    fiscal_year = f"{fiscal_start}-{str(fiscal_start + 1)[-2:]}"
    return (
        "https://webnodejs.investorgain.com/cloud/v2/report/data-read/331/"
        f"1/{local.month}/{local.year}/{fiscal_year}/0/all?search=&r2&v=15-18"
    )


def fetch_payload(now):
    """Make one transparent, bounded HTTPS request to the permitted endpoint."""
    url = source_url(now)
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Origin": SOURCE_ORIGIN,
            "Referer": f"{SOURCE_ORIGIN}/",
            "User-Agent": "LotNeeti-Beta/1.0 (founder-authorized IPO and GMP sync)",
        },
    )
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with urlopen(request, timeout=20, context=context) as response:  # nosec B310: fixed HTTPS URL
            body = response.read(1_000_001)
    except Exception as exc:
        raise InvestorGainError("InvestorGain request failed") from exc
    if len(body) > 1_000_000:
        raise InvestorGainError("InvestorGain response exceeded the size limit")
    try:
        payload = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise InvestorGainError("InvestorGain returned invalid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("reportTableData"), list):
        raise InvestorGainError("InvestorGain response has no IPO table")
    return url, payload


def _gmp_value(row: dict) -> Decimal | None:
    raw = html.unescape(str(row.get("GMP", "")))
    match = _GMP_VALUE.search(raw)
    if match is None or match.group(1).strip() in {"", "--", "-"}:
        return None
    try:
        return Decimal(match.group(1).strip().replace(",", ""))
    except InvalidOperation:
        return None


def _observed_at(row: dict, now):
    raw = html.unescape(str(row.get("Updated-On", "")))
    text = re.sub(r"<[^>]+>", "", raw).strip()
    try:
        parsed = datetime.strptime(text, "%d-%b %H:%M")
    except ValueError:
        return now
    local_now = timezone.localtime(now)
    candidate = timezone.make_aware(
        parsed.replace(year=local_now.year), timezone.get_current_timezone()
    )
    if candidate > local_now + timedelta(days=2):
        candidate = candidate.replace(year=candidate.year - 1)
    return candidate


def _text(value: object) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(str(value or ""))).strip()


def _price_range(value: object) -> tuple[Decimal, Decimal]:
    values = re.findall(r"\d+(?:\.\d+)?", _text(value).replace(",", ""))
    if not values:
        raise ValueError("InvestorGain price is missing")
    lower = Decimal(values[0])
    upper = Decimal(values[-1])
    if lower <= 0 or lower > upper:
        raise ValueError("InvestorGain price range is invalid")
    return lower, upper


def _lot_size(value: object) -> int:
    values = re.findall(r"\d+", _text(value).replace(",", ""))
    if not values or int(values[0]) <= 0:
        raise ValueError("InvestorGain lot size is missing")
    return int(values[0])


def _month_day(value: object) -> tuple[int, int]:
    parsed = datetime.strptime(_text(value), "%d-%b")
    return parsed.month, parsed.day


def _event_dates(row: dict, now) -> tuple[date, date, date, date | None]:
    open_month, open_day = _month_day(row.get("Open"))
    local_today = timezone.localdate(now)
    year = local_today.year + int(open_month < local_today.month and row.get("~ipo_status1") == "U")
    open_date = date(year, open_month, open_day)

    def after_open(column: str, previous: date) -> date:
        month, day = _month_day(row.get(column))
        candidate = date(previous.year, month, day)
        if candidate < previous:
            candidate = date(previous.year + 1, month, day)
        return candidate

    close_date = after_open("Close", open_date)
    allotment_date = after_open("BoA Dt", close_date)
    try:
        listing_date = after_open("Listing", allotment_date)
    except ValueError:
        listing_date = None
    return open_date, close_date, allotment_date, listing_date


def _record_from_row(row: dict, *, request_url: str, now) -> IPORecord:
    record_id = str(row.get("~id") or "").strip()
    issuer_name = _text(row.get("~ipo_name"))
    status_code = _text(row.get("~ipo_status1")).upper()
    if not record_id or not issuer_name or status_code not in {"U", "O"}:
        raise ValueError("InvestorGain row is not an active or upcoming IPO")
    lower_price, upper_price = _price_range(row.get("Price (₹)"))
    open_date, close_date, allotment_date, listing_date = _event_dates(row, now)
    detail_path = str(row.get("~urlrewrite_folder_name") or "")
    issue_type = "SME" if "SME" in _text(row.get("~ipo_category1")).upper() else "MAINBOARD"
    detail_url = f"{SOURCE_ORIGIN}{detail_path}" if detail_path.startswith("/") else request_url
    return IPORecord.from_mapping(
        {
            "issuer_name": issuer_name,
            "issue_type": issue_type,
            "lower_price": lower_price,
            "upper_price": upper_price,
            "lot_size": _lot_size(row.get("Lot")),
            "open_date": open_date,
            "close_date": close_date,
            "allotment_date": allotment_date,
            "listing_date": listing_date,
            "status": "OPEN" if status_code == "O" else "UPCOMING",
            "publication_state": "PUBLISHED",
            "source_url": detail_url,
        },
        source_key=PROVIDER_KEY,
        source_record_id=record_id,
        observed_at=_observed_at(row, now),
    )


@transaction.atomic
def _upsert_ipo(record: IPORecord, raw: dict) -> tuple[IPO, bool]:
    defaults = record.model_fields()
    ipo, created = IPO.objects.update_or_create(
        source_key=record.source_key,
        source_record_id=record.source_record_id,
        defaults=defaults,
    )
    link, _ = IPOSourceLink.objects.get_or_create(
        ipo=ipo, source_key=record.source_key, source_record_id=record.source_record_id
    )
    raw_hash = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    IPOSourceSnapshot.objects.get_or_create(
        link=link,
        payload_hash=raw_hash,
        observed_at=record.source_observed_at,
        defaults={"payload": {"normalized": record.payload(), "raw": raw}},
    )
    return ipo, created


def _rows_by_name(payload: dict):
    rows = {}
    for row in payload["reportTableData"]:
        if not isinstance(row, dict):
            continue
        name = row.get("~ipo_name")
        if not isinstance(name, str) or not issuer_key(name):
            continue
        rows.setdefault(issuer_key(name), row)
    return rows


def _match_row(ipo: IPO, rows: dict[str, dict]):
    key = issuer_key(ipo.issuer_name)
    if key in rows:
        return rows[key]
    candidates = [
        row
        for row_key, row in rows.items()
        if len(row_key) >= 8 and (key.startswith(row_key) or row_key.startswith(key))
    ]
    return candidates[0] if len(candidates) == 1 else None


def sync_investorgain_gmp(*, manual: bool = False) -> dict:
    state, _ = GMPProviderState.objects.get_or_create(provider_key=PROVIDER_KEY)
    if not state.enabled:
        return {"status": "DISABLED", "provider": PROVIDER_KEY, "requested": 0}

    now = timezone.now()
    if manual:
        sync_state, _ = IPOProviderSyncState.objects.get_or_create(source_key=PROVIDER_KEY)
        sync_state.last_status = "RUNNING"
        sync_state.last_safe_error = ""
        sync_state.save(update_fields=["last_status", "last_safe_error"])
    else:
        slot_error, sync_state = reserve_refresh_slot(PROVIDER_KEY, at=now)
        if slot_error:
            return slot_error
    try:
        request_url, payload = fetch_payload(now)
    except Exception as exc:
        record_provider_failure(provider_key=PROVIDER_KEY, error=exc, observed_at=now)
        sync_state.last_status = "ERROR"
        sync_state.last_safe_error = type(exc).__name__
        sync_state.save(update_fields=["last_status", "last_safe_error"])
        return {
            "status": "ERROR",
            "provider": PROVIDER_KEY,
            "requested": 1,
            "error": type(exc).__name__,
        }

    imported = skipped = 0
    for row in payload["reportTableData"]:
        if not isinstance(row, dict):
            skipped += 1
            continue
        try:
            record = _record_from_row(row, request_url=request_url, now=now)
            _, created_ipo = _upsert_ipo(record, row)
            imported += int(created_ipo)
        except (TypeError, ValueError, InvalidOperation):
            skipped += 1

    relevant = list(
        IPO.objects.filter(
            source_key=PROVIDER_KEY,
            publication_state=IPO.PublicationState.PUBLISHED,
            status__in=[IPO.Status.OPEN, IPO.Status.UPCOMING],
        )
    )
    rows = _rows_by_name(payload)
    created = matched = 0
    for ipo in relevant:
        row = _match_row(ipo, rows)
        if row is None:
            continue
        value = _gmp_value(row)
        if value is None:
            continue
        matched += 1
        payload_hash = hashlib.sha256(
            json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if GMPObservation.objects.filter(
            ipo=ipo, source_key=PROVIDER_KEY, source_payload_hash=payload_hash
        ).exists():
            continue
        detail_path = str(row.get("~urlrewrite_folder_name") or "")
        observation_url = (
            f"{SOURCE_ORIGIN}{detail_path}" if detail_path.startswith("/") else request_url
        )
        GMPObservation.objects.create(
            ipo=ipo,
            source_key=PROVIDER_KEY,
            source_record_id=str(row.get("~id") or issuer_key(ipo.issuer_name))[:160],
            value_per_share=value,
            observed_at=_observed_at(row, now),
            fetched_at=now,
            source_url=observation_url,
            source_payload_hash=payload_hash,
        )
        created += 1
    record_provider_success(provider_key=PROVIDER_KEY, observed_at=now)
    sync_state.last_status = "OK"
    sync_state.last_success_at = now
    sync_state.last_safe_error = ""
    sync_state.fetched_count = len(payload["reportTableData"])
    sync_state.updated_count = created
    sync_state.save(
        update_fields=[
            "last_status",
            "last_success_at",
            "last_safe_error",
            "fetched_count",
            "updated_count",
        ]
    )
    return {
        "status": "OK",
        "provider": PROVIDER_KEY,
        "requested": 1,
        "imported": imported,
        "skipped": skipped,
        "matched": matched,
        "created": created,
    }
