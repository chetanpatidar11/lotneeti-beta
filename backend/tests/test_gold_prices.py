from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest
from django.core.cache import cache

from portfolio import gold_prices as prices

NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


def quote(**changes):
    return {
        "symbol": "XAU",
        "currency": "INR",
        "price": Decimal("311034.768"),
        "updatedAt": NOW.isoformat(),
        **changes,
    }


@pytest.fixture
def live(settings, monkeypatch):
    settings.GOLD_LIVE_PRICES_ENABLED = True
    cache.clear()
    monkeypatch.setattr(prices.timezone, "now", lambda: NOW)
    fetch = Mock(return_value=quote())
    monkeypatch.setattr(prices, "fetch_quote", fetch)
    yield fetch
    cache.clear()


@pytest.mark.parametrize(
    ("purity", "fraction"),
    [
        ("24K / 999", "0.999"),
        ("22K/916", "0.916"),
        ("18K / 750", "0.75"),
        ("999.9", "0.9999"),
        ("995", "0.995"),
        ("91.6%", "0.916"),
        ("24K", "1"),
        ("18kt", "0.75"),
        ("18 karat", "0.75"),
        ("22K", str(Decimal(22) / 24)),
        ("24K / 750", None),
        ("22K / 999", None),
        ("mystery", None),
        ("0K", None),
        ("25K", None),
        ("1000", None),
        ("0%", None),
        ("999 / 750", None),
    ],
)
def test_gold_purity_uses_explicit_fineness_and_never_guesses_contradictions(purity, fraction):
    assert prices.purity_fraction(purity) == (Decimal(fraction) if fraction else None)


def test_inr_troy_quote_is_shared_and_converts_exactly_to_grams(live):
    first = prices.market_quote()
    assert first["state"] == "LIVE"
    assert Decimal(first["price_per_gram_24k"]) == 10000
    assert first["rates"] == {"999": "9990.00", "916": "9160.00", "750": "7500.00"}
    assert prices.market_quote() == first
    assert live.call_count == 1


@pytest.mark.parametrize(
    "changed",
    [
        {"symbol": "XAG"},
        {"currency": "USD"},
        {"price": "NaN"},
        {"price": "Infinity"},
        {"price": 0},
        {"price": -1},
        {"price": True},
        {"price": "bad"},
        {"updatedAt": None},
        {"updatedAt": "2026-10-31T12:00:00"},
        {"updatedAt": (NOW + timedelta(minutes=6)).isoformat()},
        {"updatedAt": (NOW - timedelta(hours=73)).isoformat()},
    ],
)
def test_invalid_currency_price_and_time_cannot_become_a_gold_valuation(live, changed):
    live.return_value = quote(**changed)
    result = prices.market_quote()
    assert result["state"] == "UNAVAILABLE" and result["rates"] == {}
    assert cache.get(prices.LATEST_KEY) is None


def test_quote_outage_retains_labelled_last_value_with_backoff_then_expires(live, monkeypatch):
    assert prices.market_quote()["state"] == "LIVE"
    cache.delete(prices.REFRESH_KEY)  # Emulate the shared 60-second cache lock expiring.
    monkeypatch.setattr(prices.timezone, "now", lambda: NOW + timedelta(seconds=61))
    live.side_effect = TimeoutError("synthetic feed timeout")
    result = prices.market_quote()
    assert result["state"] == "STALE" and result["rates"]["999"] == "9990.00"
    assert result["as_of"] == NOW.isoformat()
    assert prices.market_quote()["state"] == "STALE"
    assert live.call_count == 2
    monkeypatch.setattr(prices.timezone, "now", lambda: NOW + timedelta(hours=73))
    assert prices.market_quote()["state"] == "UNAVAILABLE"


def test_weekend_or_old_provider_timestamp_is_not_labelled_live(live):
    live.return_value = quote(updatedAt=(NOW - timedelta(days=1)).isoformat())
    result = prices.market_quote()
    assert result["state"] == "STALE" and result["rates"]["916"] == "9160.00"


def test_cache_outage_never_starts_uncached_requests(live, monkeypatch):
    monkeypatch.setattr(prices.cache, "get", Mock(side_effect=ConnectionError("cache down")))
    assert prices.market_quote()["state"] == "UNAVAILABLE"
    live.assert_not_called()


def test_public_feed_uses_fixed_path_verified_tls_and_a_bounded_body(monkeypatch):
    response = Mock(status=200)
    response.read.return_value = b'{"symbol":"XAU","currency":"INR","price":311034.768}'
    connection = Mock()
    connection.getresponse.return_value = response
    constructor = Mock(return_value=connection)
    monkeypatch.setattr(prices.http.client, "HTTPSConnection", constructor)
    assert prices.fetch_quote()["price"] == Decimal("311034.768")
    args, kwargs = constructor.call_args
    assert args == ("api.gold-api.com",) and kwargs["timeout"] == 4
    assert kwargs["context"].check_hostname
    connection.request.assert_called_once_with(
        "GET",
        "/price/XAU/INR",
        headers={"Accept": "application/json", "User-Agent": "LotNeeti/1.0"},
    )
    response.read.assert_called_once_with(16385)
    connection.close.assert_called_once()
    response.status = 302
    with pytest.raises(ValueError):
        prices.fetch_quote()
    response.status = 200
    response.read.return_value = b"x" * 16385
    with pytest.raises(ValueError):
        prices.fetch_quote()
