from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ipos.dto import IPOProvider, IPORecord
from ipos.providers import ManualIPOProvider


def raw_issue():
    return {
        "issuer_name": " Synthetic Industries ",
        "issue_type": "MAINBOARD",
        "lower_price": "100.00",
        "upper_price": "105.00",
        "lot_size": "140",
        "open_date": "2026-10-01",
        "close_date": "2026-10-03",
        "allotment_date": "2026-10-08",
    }


def test_manual_adapter_normalizes_into_deterministic_canonical_record():
    provider: IPOProvider = ManualIPOProvider()
    first = provider.normalize(
        raw_issue(),
        source_record_id="synthetic-001",
        observed_at=datetime(2026, 9, 26, 10, 0, tzinfo=UTC),
    )
    second = provider.normalize(
        raw_issue(),
        source_record_id="synthetic-001",
        observed_at=datetime(2026, 9, 27, 10, 0, tzinfo=UTC),
    )
    assert isinstance(first, IPORecord)
    assert first.issuer_name == "Synthetic Industries"
    assert first.lower_price == Decimal("100.00")
    assert first.lot_size == 140
    assert first.payload() == second.payload()
    assert first.payload_hash == second.payload_hash
    assert first.model_fields()["source_observed_at"] != second.model_fields()["source_observed_at"]


def test_adapter_rejects_missing_source_identity_or_naive_time():
    provider = ManualIPOProvider()
    with pytest.raises(ValueError):
        provider.normalize(raw_issue(), source_record_id="", observed_at=datetime.now(UTC))
    with pytest.raises(ValueError):
        provider.normalize(
            raw_issue(), source_record_id="synthetic-001", observed_at=datetime(2026, 9, 26)
        )
