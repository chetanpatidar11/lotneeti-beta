from datetime import UTC, datetime

import pytest
from django.core.exceptions import ValidationError

from ipos.bse_feed import current_bse_issues, record_bse_discovery_rows
from ipos.local_publication import publish_local_enriched_issue
from ipos.models import IPO, IPOEnrichmentObservation

SOURCE = "https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx"


@pytest.mark.django_db
def test_independent_bse_mainboard_and_sme_discovery_is_idempotent():
    rows = [
        {
            "symbol": "SYNMAIN",
            "company_name": "Synthetic Main Limited",
            "platform": "MAINBOARD",
            "status": "Active",
            "price_band": "Rs. 100 to Rs. 110",
            "open_date": "2026-09-28",
            "close_date": "2026-09-30",
        },
        {
            "symbol": "SYNSME",
            "company_name": "Synthetic SME Limited",
            "platform": "SME",
            "status": "Forthcoming",
            "price_band": "Rs. 50 to Rs. 55",
            "open_date": "2026-09-29",
            "close_date": "2026-10-01",
        },
    ]
    at = datetime(2026, 9, 28, tzinfo=UTC)
    assert record_bse_discovery_rows(rows, source_url=SOURCE, observed_at=at) == (2, 2)
    assert record_bse_discovery_rows(rows, source_url=SOURCE, observed_at=at) == (0, 2)
    issues = {item["symbol"]: item for item in current_bse_issues()}
    assert issues["SYNMAIN"]["source_market"] == "BSE_MAINBOARD"
    assert issues["SYNSME"]["source_market"] == "BSE_SME"
    assert issues["SYNSME"]["nse_state"] == "NOT_APPLICABLE"

    IPOEnrichmentObservation.objects.create(
        source_key="bse",
        stage="DETAIL",
        symbol="SYNSME",
        source_url=SOURCE,
        payload_hash="a" * 64,
        normalized_payload={"facts": {"lot_size": 1000}},
        fetched_at=at,
    )
    IPOEnrichmentObservation.objects.create(
        source_key="bse",
        stage="DOCUMENT",
        symbol="SYNSME",
        source_url=SOURCE,
        payload_hash="b" * 64,
        normalized_payload={"facts": {"allotment_date": "2026-10-02"}, "document_type": "RHP"},
        fetched_at=at,
    )
    sme = {item["symbol"]: item for item in current_bse_issues()}["SYNSME"]
    assert sme["enrichment_state"] == "READY"
    assert sme["nse_state"] == "NOT_APPLICABLE"
    assert sme["field_sources"]["lot_size"] == "BSE_DETAIL"
    canonical, changed = publish_local_enriched_issue(
        sme, rights_reference="synthetic-permitted-fixture"
    )
    assert changed is True
    assert canonical.source_market == "BSE_SME"
    assert canonical.listing_exchanges == "BSE"
    assert IPO.objects.filter(symbol="SYNSME").count() == 1


@pytest.mark.django_db
def test_bse_discovery_rejects_non_official_source():
    with pytest.raises(ValidationError):
        record_bse_discovery_rows(
            [], source_url="https://example.com/feed", observed_at=datetime.now(UTC)
        )
