from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError

from ipos.models import IPO
from ipos.public_serializers import PublicIPOSerializer


def issue(**changes):
    values = {
        "issuer_name": "Synthetic Industries",
        "symbol": "SYNTH",
        "issue_type": IPO.IssueType.MAINBOARD,
        "lower_price": Decimal("100.00"),
        "upper_price": Decimal("105.00"),
        "lot_size": 140,
        "open_date": date(2026, 10, 1),
        "close_date": date(2026, 10, 3),
        "allotment_date": date(2026, 10, 8),
        "listing_date": date(2026, 10, 10),
        "source_key": "synthetic-manual",
        "source_record_id": "synthetic-ipo-001",
        "source_url": "https://example.test/ipo/synthetic-001",
    }
    values.update(changes)
    return IPO(**values)


@pytest.mark.django_db
def test_canonical_ipo_persists_issue_facts_status_and_provenance():
    ipo = issue()
    ipo.save()
    saved = IPO.objects.get(pk=ipo.pk)
    assert saved.upper_price == Decimal("105.00")
    assert saved.lot_size == 140
    assert saved.status == IPO.Status.UPCOMING
    assert saved.publication_state == IPO.PublicationState.DRAFT
    assert saved.source_key == "synthetic-manual"
    assert saved.source_record_id == "synthetic-ipo-001"
    assert saved.source_observed_at is not None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "change",
    [
        {"upper_price": Decimal("99.00")},
        {"lot_size": 0},
        {"close_date": date(2026, 9, 30)},
        {"allotment_date": date(2026, 10, 2)},
        {"listing_date": date(2026, 10, 7)},
        {"source_url": "invalid-url"},
    ],
)
def test_invalid_issue_facts_rejected(change):
    with pytest.raises(ValidationError):
        issue(**change).save()


@pytest.mark.django_db
def test_source_record_identity_is_unique():
    issue().save()
    with pytest.raises(ValidationError):
        issue(issuer_name="Another IPO").save()
    issue(source_record_id="synthetic-ipo-002").save()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("now", "expected_status"),
    [
        (datetime(2026, 10, 3, 16, 59, tzinfo=ZoneInfo("Asia/Kolkata")), IPO.Status.OPEN),
        (datetime(2026, 10, 3, 17, 0, tzinfo=ZoneInfo("Asia/Kolkata")), IPO.Status.CLOSED),
        (datetime(2026, 10, 4, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")), IPO.Status.CLOSED),
    ],
)
def test_public_ipo_status_closes_at_5pm_ist_on_close_date(now, expected_status):
    ipo = issue(status=IPO.Status.OPEN, publication_state=IPO.PublicationState.PUBLISHED)
    ipo.save()

    with patch("ipos.public_serializers.timezone.now", return_value=now):
        assert PublicIPOSerializer(ipo).data["status"] == expected_status
