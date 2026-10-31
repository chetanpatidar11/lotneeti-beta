"""Shared public XAU/INR spot quote. No private holdings leave the server.

Provider contract/usage: https://gold-api.com/faqs and https://gold-api.com/terms
Troy ounce conversion: NIST Precious Metals Conversion Information (31.1034768 g).
"""

import http.client
import json
import re
import ssl
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import certifi
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

TROY_GRAMS = Decimal("31.1034768")
CENT = Decimal("0.01")
LATEST_KEY = "gold:xau-inr:v1:last"
REFRESH_KEY = "gold:xau-inr:v1:refresh"
MAX_AGE = timedelta(hours=72)
FRESH_AGE = timedelta(minutes=5)
SOURCE_URL = "https://gold-api.com/"
# Explicit hallmark combinations prevent a contradictory free-text purity being guessed.
HALLMARKS = {
    "24": {"999", "999.9"},
    "23": {"958"},
    "22": {"916"},
    "21": {"875"},
    "20": {"833"},
    "18": {"750"},
    "14": {"585"},
    "10": {"417"},
    "9": {"375"},
}


def purity_fraction(value):
    text = value.strip().upper()
    combined = re.fullmatch(r"(\d{1,2})\s*K(?:T)?\s*/\s*(\d{3}(?:\.\d)?)", text)
    if combined:
        karat, fine = combined.groups()
        return Decimal(fine) / 1000 if fine in HALLMARKS.get(karat, set()) else None
    if re.fullmatch(r"\d{3}(?:\.\d)?", text):
        fine = Decimal(text)
        return fine / 1000 if 100 <= fine < 1000 else None
    karat = re.fullmatch(r"(\d{1,2}(?:\.\d)?)\s*K(?:T|ARAT)?", text)
    if karat and 0 < Decimal(karat[1]) <= 24:
        return Decimal(karat[1]) / 24
    percent = re.fullmatch(r"(\d{1,2}(?:\.\d{1,2})?|100)\s*%", text)
    if percent and 0 < Decimal(percent[1]) <= 100:
        return Decimal(percent[1]) / 100
    return None


def fetch_quote():
    connection = http.client.HTTPSConnection(
        "api.gold-api.com", timeout=4, context=ssl.create_default_context(cafile=certifi.where())
    )
    try:
        connection.request(
            "GET",
            "/price/XAU/INR",
            headers={"Accept": "application/json", "User-Agent": "LotNeeti/1.0"},
        )
        response = connection.getresponse()
        if response.status != 200:  # No redirects, guessed currencies or fallback endpoints.
            raise ValueError("Gold feed unavailable")
        body = response.read(16385)
        if len(body) > 16384:
            raise ValueError("Gold feed response too large")
        return json.loads(body, parse_float=Decimal)
    finally:
        connection.close()


def validated_quote(data, now):
    if not isinstance(data, dict) or data.get("currency") != "INR" or data.get("symbol") != "XAU":
        raise ValueError("Unexpected gold feed")
    raw_price = data.get("price")
    if isinstance(raw_price, bool) or not isinstance(raw_price, str | int | Decimal):
        raise ValueError("Invalid gold price")
    price = Decimal(raw_price)
    if not price.is_finite() or not 0 < price < Decimal("1000000000"):
        raise ValueError("Invalid gold price")
    stamp = data.get("updatedAt")
    as_of = parse_datetime(stamp) if isinstance(stamp, str) else None
    if (
        as_of is None
        or timezone.is_naive(as_of)
        or not -timedelta(minutes=5) <= now - as_of <= MAX_AGE
    ):
        raise ValueError("Gold feed timestamp unavailable or expired")
    return price, as_of


def unavailable(state="UNAVAILABLE"):
    return {
        "state": state,
        "source": "Gold API",
        "source_url": SOURCE_URL,
        "as_of": None,
        "rates": {},
        "price_per_gram_24k": None,
    }


def market_quote():
    if not settings.GOLD_LIVE_PRICES_ENABLED:
        return unavailable("DISABLED")
    now = timezone.now()
    failed = False
    try:
        saved = cache.get(LATEST_KEY)
        # Atomic shared lock also provides a 60-second failure backoff across users/workers.
        if cache.add(REFRESH_KEY, True, timeout=60):
            try:
                data = fetch_quote()
                validated_quote(data, now)
                saved = {"data": data, "checked_at": now.isoformat()}
                cache.set(LATEST_KEY, saved, timeout=int(MAX_AGE.total_seconds()))
            except (OSError, http.client.HTTPException, ValueError, InvalidOperation):
                failed = True
        if not saved:
            return unavailable()
        price, as_of = validated_quote(saved["data"], now)
        checked = parse_datetime(saved["checked_at"])
        if checked is None or timezone.is_naive(checked):
            return unavailable()
        state = (
            "LIVE"
            if not failed and now - as_of <= FRESH_AGE and now - checked <= timedelta(seconds=60)
            else "STALE"
        )
        pure = price / TROY_GRAMS
        return {
            "state": state,
            "source": "Gold API",
            "source_url": SOURCE_URL,
            "as_of": as_of.isoformat(),
            "price_per_gram_24k": str(pure),
            "rates": {
                fine: str((pure * Decimal(fine) / 1000).quantize(CENT, rounding=ROUND_HALF_UP))
                for fine in ["999", "916", "750"]
            },
        }
    except Exception:
        # Cache failures must not break saved records or trigger request storms.
        return unavailable()


def item_price(item, market):
    if item.price_mode == "MANUAL":
        return item.current_price_per_gram, "MANUAL", item.price_updated_at
    fraction = purity_fraction(item.purity)
    if fraction is None:
        return None, "UNKNOWN_PURITY", None
    if market["state"] not in {"LIVE", "STALE"}:
        return None, "UNAVAILABLE", None
    price = (Decimal(market["price_per_gram_24k"]) * fraction).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    return price, market["state"], market["as_of"]
