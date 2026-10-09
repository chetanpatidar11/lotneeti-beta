from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from ipos.models import IPO, GMPObservation


def make_ipo():
    return IPO.objects.create(
        issuer_name="Synthetic Industries",
        issue_type="MAINBOARD",
        lower_price=Decimal("100.00"),
        upper_price=Decimal("105.00"),
        lot_size=140,
        open_date=date(2026, 10, 1),
        close_date=date(2026, 10, 3),
        allotment_date=date(2026, 10, 8),
        source_key="synthetic-fixture",
        source_record_id="synthetic-001",
    )


@pytest.mark.django_db
def test_gmp_observations_keep_source_values_and_history():
    ipo = make_ipo()
    older = GMPObservation.objects.create(
        ipo=ipo,
        source_key="synthetic-manual",
        value_per_share=Decimal("20.00"),
        observed_at=datetime(2026, 9, 25, 10, 0, tzinfo=UTC),
        source_url="https://example.test/gmp/older",
        source_record_id="observation-001",
        source_payload_hash="a" * 64,
    )
    newer = GMPObservation.objects.create(
        ipo=ipo,
        source_key="synthetic-manual",
        value_per_share=Decimal("-5.00"),
        observed_at=datetime(2026, 9, 26, 10, 0, tzinfo=UTC),
    )
    assert list(ipo.gmp_observations.values_list("pk", flat=True)) == [newer.pk, older.pk]
    assert older.fetched_at is not None
    assert older.source_record_id == "observation-001"
    newer.value_per_share = Decimal("30.00")
    with pytest.raises(ValueError):
        newer.save()
    with pytest.raises(ValueError):
        older.delete()


@pytest.mark.django_db
def test_gmp_observation_requires_timezone_aware_time():
    with pytest.raises(ValidationError):
        GMPObservation.objects.create(
            ipo=make_ipo(),
            source_key="synthetic-manual",
            value_per_share=Decimal("20.00"),
            observed_at=datetime(2026, 9, 26, 10, 0),
        )
