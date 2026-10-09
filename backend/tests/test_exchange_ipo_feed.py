from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from ipos.feed_ingest import NormalizedExchangeIPOProvider, record_exchange_snapshot
from ipos.models import IPO, IPOSourceLink, IPOSourceSnapshot


def issue_fields(*, upper_price="105.00"):
    return {
        "issuer_name": "Synthetic Industries",
        "symbol": "SYNTH",
        "issue_type": "MAINBOARD",
        "lower_price": "100.00",
        "upper_price": upper_price,
        "lot_size": 140,
        "open_date": "2026-10-01",
        "close_date": "2026-10-03",
        "allotment_date": "2026-10-08",
        "source_url": "https://example.test/issue/synthetic",
    }


def canonical_ipo(*, source_record_id="manual-synthetic-001"):
    return IPO.objects.create(
        issuer_name="Synthetic Industries",
        issue_type="MAINBOARD",
        lower_price=Decimal("100.00"),
        upper_price=Decimal("105.00"),
        lot_size=140,
        open_date=date(2026, 10, 1),
        close_date=date(2026, 10, 3),
        allotment_date=date(2026, 10, 8),
        publication_state=IPO.PublicationState.PUBLISHED,
        source_key="manual",
        source_record_id=source_record_id,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("source_key", ["nse", "bse", "sebi"])
def test_exchange_record_is_idempotent_and_keeps_canonical_public_value(source_key):
    ipo = canonical_ipo()
    observed_at = datetime(2026, 9, 28, 10, tzinfo=UTC)
    provider = NormalizedExchangeIPOProvider(source_key)
    record = provider.normalize(
        issue_fields(upper_price="110.00"),
        source_record_id=f"{source_key}-synthetic-001",
        observed_at=observed_at,
    )
    first = record_exchange_snapshot(ipo=ipo, record=record)
    second = record_exchange_snapshot(ipo=ipo, record=record)
    assert second.pk == first.pk
    assert IPOSourceLink.objects.count() == 1
    assert IPOSourceSnapshot.objects.count() == 1
    assert first.payload_hash == record.payload_hash
    assert first.payload["upper_price"] == "110.00"
    assert first.observed_at == observed_at

    ipo.refresh_from_db()
    assert ipo.upper_price == Decimal("105.00")
    user = User.objects.create_user(email=f"{source_key}@example.test")
    client = APIClient()
    client.force_authenticate(user)
    assert client.get(reverse("ipo-detail", args=[ipo.pk])).data["upper_price"] == "105.00"


@pytest.mark.django_db
def test_source_identity_cannot_be_silently_attached_to_another_ipo():
    first = canonical_ipo()
    second = canonical_ipo(source_record_id="manual-synthetic-002")
    record = NormalizedExchangeIPOProvider("nse").normalize(
        issue_fields(), source_record_id="nse-synthetic-001", observed_at=datetime.now(UTC)
    )
    record_exchange_snapshot(ipo=first, record=record)
    with pytest.raises(ValidationError, match="different IPO"):
        record_exchange_snapshot(ipo=second, record=record)
    assert IPOSourceSnapshot.objects.count() == 1


@pytest.mark.django_db
def test_changed_observation_preserves_history_and_rejects_invalid_facts():
    ipo = canonical_ipo()
    provider = NormalizedExchangeIPOProvider("bse")
    first_time = datetime(2026, 9, 28, 10, tzinfo=UTC)
    for price, observed_at in (
        ("105.00", first_time),
        ("110.00", first_time + timedelta(hours=1)),
    ):
        record = provider.normalize(
            issue_fields(upper_price=price),
            source_record_id="bse-synthetic-001",
            observed_at=observed_at,
        )
        record_exchange_snapshot(ipo=ipo, record=record)
    assert [item.payload["upper_price"] for item in IPOSourceSnapshot.objects.all()] == [
        "110.00",
        "105.00",
    ]
    snapshot = IPOSourceSnapshot.objects.first()
    snapshot.payload = issue_fields(upper_price="999.00")
    with pytest.raises(ValueError, match="cannot be changed"):
        snapshot.save()

    invalid = provider.normalize(
        issue_fields(upper_price="90.00"),
        source_record_id="bse-synthetic-001",
        observed_at=first_time + timedelta(hours=2),
    )
    with pytest.raises(ValidationError):
        record_exchange_snapshot(ipo=ipo, record=invalid)
    assert IPOSourceSnapshot.objects.count() == 2


def test_exchange_provider_requires_supported_key_and_aware_observation_time():
    with pytest.raises(ValueError, match="Unsupported"):
        NormalizedExchangeIPOProvider("unlicensed-example")
    with pytest.raises(ValueError, match="timezone"):
        NormalizedExchangeIPOProvider("sebi").normalize(
            issue_fields(),
            source_record_id="sebi-synthetic-001",
            observed_at=datetime(2026, 9, 28, 10),
        )


@pytest.mark.django_db
def test_exchange_record_requires_saved_canonical_ipo():
    record = NormalizedExchangeIPOProvider("sebi").normalize(
        issue_fields(),
        source_record_id="sebi-synthetic-001",
        observed_at=datetime.now(UTC),
    )
    with pytest.raises(ValidationError, match="saved canonical IPO"):
        record_exchange_snapshot(ipo=IPO(), record=record)
    assert IPOSourceLink.objects.count() == 0
