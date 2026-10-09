import hashlib
import json
from datetime import UTC, datetime
from io import StringIO

import pytest
from django.core.management import call_command

from ipos.detail_enrichment import (
    BSEIPOIssueDetailProvider,
    NSEIPOIssueDetailProvider,
    record_detail_observation,
)
from ipos.document_enrichment import (
    extract_listing_identity,
    extract_timetable,
    record_document_observation,
)
from ipos.enrichment import resolve_enriched_issue
from ipos.feed_watch import normalize_nse_current_row
from ipos.local_publication import publish_local_enriched_issue
from ipos.models import IPO, IPOEnrichmentObservation


def detail(symbol="SYNTH", lot=441):
    return {
        "issueInfo": {
            "symbol": symbol,
            "dataList": [
                {"title": "Symbol", "value": symbol},
                {"title": "Issue Period", "value": "24-Sep-2026 to 28-Sep-2026"},
                {"title": "Price Range", "value": "Rs. 32 to Rs. 34 per Equity Share"},
                {"title": "Bid Lot", "value": f"{lot} Equity Shares and in multiples thereof"},
                {"title": "Minimum Order Quantity", "value": f"{lot} Equity Shares"},
                {
                    "title": "Red Herring Prospectus",
                    "value": "https://nsearchives.nseindia.com/content/ipo/RHP_SYNTH.zip",
                },
            ],
        }
    }


def discovery():
    return normalize_nse_current_row(
        {
            "symbol": "SYNTH",
            "companyName": "Synthetic Limited",
            "series": "EQ",
            "status": "Active",
            "issuePrice": "Rs. 32 to Rs. 34",
            "issueStartDate": "24-Sep-2026",
            "issueEndDate": "28-Sep-2026",
        }
    )[1]


TIMETABLE = """An indicative timetable in respect of the Offer is set out below:
FINALISATION OF BASIS OF ALLOTMENT WITH THE
DESIGNATED STOCK EXCHANGE
On or about September 29, 2026
INITIATION OF REFUNDS FOR ANCHOR INVESTORS/
UNBLOCKING OF FUNDS FROM ASBA ACCOUNT*
On or about September 30, 2026
CREDIT OF EQUITY SHARES TO DEPOSITORY ACCOUNTS On or about September 30, 2026
COMMENCEMENT OF TRADING OF THE EQUITY SHARES ON
THE STOCK EXCHANGE
On or about October 1, 2026
"""


def make_observation(source, stage, facts, *, document_date=None, outcome="OK", fetched_hour=0):
    return IPOEnrichmentObservation(
        source_key=source,
        stage=stage,
        symbol="SYNTH",
        source_url="https://www.nseindia.com/market-data/issue-information",
        payload_hash=hashlib.sha256(f"{source}:{stage}:{fetched_hour}".encode()).hexdigest(),
        normalized_payload={"facts": facts, "document_type": "RHP", "document_date": document_date},
        fetched_at=datetime(2026, 9, 28, fetched_hour, tzinfo=UTC),
        outcome=outcome,
        safe_error="SOURCE_UNAVAILABLE" if outcome == "ERROR" else "",
    )


def test_nse_issue_detail_maps_bid_lot_for_moneyview_and_a_one_shapes():
    provider = NSEIPOIssueDetailProvider()
    assert (
        provider.normalize(detail(lot=441), symbol="SYNTH", series="EQ")["facts"]["lot_size"] == 441
    )
    assert (
        provider.normalize(detail(lot=37), symbol="SYNTH", series="EQ")["facts"]["lot_size"] == 37
    )
    assert (
        provider.normalize(detail(lot=441), symbol="SYNTH", series="EQ")["facts"]["upper_price"]
        == "34.00"
    )
    slash_price = detail()
    slash_price["issueInfo"]["dataList"][2]["value"] = "Rs. 159/- to Rs. 167/- per equity share"
    assert (
        provider.normalize(slash_price, symbol="SYNTH", series="EQ")["facts"]["upper_price"]
        == "167.00"
    )


def test_nse_sme_lot_size_and_bse_market_lot_are_distinct_detail_labels():
    raw = detail()
    raw["issueInfo"]["dataList"] = [
        {"title": "Lot Size", "value": "1200 Equity Shares"} if row["title"] == "Bid Lot" else row
        for row in raw["issueInfo"]["dataList"]
    ]
    assert (
        NSEIPOIssueDetailProvider().normalize(raw, symbol="SYNTH", series="SME")["facts"][
            "lot_size"
        ]
        == 1200
    )
    bse = BSEIPOIssueDetailProvider().normalize(
        "<table><tr><td>Symbol</td><td>SYNTH</td></tr><tr><td>Market Lot</td><td>441</td></tr>"
        "<tr><td>Minimum Bid Quantity</td><td>441</td></tr>"
        "<tr><td>Prospectus</td><td><a href='/docs/synthetic.pdf'>"
        "Open</a></td></tr></table>",
        symbol="SYNTH",
    )
    assert bse["links"]["prospectus_url"] == "https://www.bseindia.com/docs/synthetic.pdf"
    assert bse["facts"]["lot_size"] == 441
    assert bse["consistency_warnings"] == []


def test_document_timetable_extracts_only_explicit_dates():
    facts, evidence = extract_timetable(TIMETABLE)
    assert facts == {
        "allotment_date": "2026-09-29",
        "refund_or_unblock_date": "2026-09-30",
        "demat_credit_date": "2026-09-30",
        "listing_date": "2026-10-01",
    }
    assert "Finalisation" in evidence["allotment_date"].title()
    assert extract_timetable("The issue closes September 28, 2026. Allotment follows.")[0] == {}


def test_document_timetable_and_listing_identity_use_explicit_statements():
    text = (
        "Indicative timetable: Bid/Offer Opening Date September 24, 2026 "
        "Bid/Offer Closing Date September 28, 2026 "
        "The shares are proposed to be listed on BSE Limited and National Stock Exchange "
        "of India Limited. For the purpose of the Offer, BSE shall be the "
        "Designated Stock Exchange."
    )
    facts, _ = extract_timetable(text)
    assert facts["open_date"] == "2026-09-24"
    assert facts["close_date"] == "2026-09-28"
    identity = extract_listing_identity(text)
    assert identity["listing_exchanges"] == "NSE+BSE"
    assert identity["designated_exchange"] == "BSE"
    assert extract_listing_identity("Disclosure " * 600 + text)["designated_exchange"] == "BSE"
    assert (
        extract_listing_identity("Listed on the NSE EMERGE platform")["listing_platform"] == "SME"
    )


def test_timetable_variants_keep_explicit_about_and_before_dates():
    green = (
        "An indicative timetable in respect of the Offer is set out below: "
        "Event Indicative Date BID/OFFER CLOSING DATE Monday, September 28, 2026 "
        "FINALISATION OF BASIS OF ALLOTMENT WITH THE DESIGNATED STOCK EXCHANGE (T+1) "
        "On or about Tuesday, September 29, 2026"
    )
    compact = (
        "Bid/OfferClosingDate Tuesday,September29,2026 "
        "Finalization of Basis of Allotment with the Designated Stock Exchange "
        "On or before Wednesday, September30,2026"
    )
    issue = (
        "Bid/Issue closing date Wednesday, September 30, 2026 "
        "Finalisation of Basis of Allotment with the Designated Stock Exchange "
        "On or about Thursday, October 1, 2026"
    )
    assert extract_timetable(green)[0]["allotment_date"] == "2026-09-29"
    assert extract_timetable(compact)[0]["allotment_date"] == "2026-09-30"
    assert extract_timetable(issue)[0]["allotment_date"] == "2026-10-01"


def test_list_then_detail_then_document_becomes_complete():
    item = discovery()
    assert item["missing_planning_fields"] == ["lot_size", "allotment_date"]
    detail_item = make_observation("nse", "DETAIL", {"lot_size": 441})
    pending = resolve_enriched_issue(item, [detail_item])
    assert pending["lot_size"] == 441
    assert pending["pending_planning_fields"] == ["allotment_date"]
    assert pending["missing_planning_fields"] == []
    assert pending["enrichment_state"] == "ENRICHING"
    rhp = make_observation(
        "nse",
        "DOCUMENT",
        {"allotment_date": "2026-09-29"},
        document_date="2026-09-20",
        fetched_hour=1,
    )
    ready = resolve_enriched_issue(item, [detail_item, rhp])
    assert ready["missing_planning_fields"] == []
    assert ready["enrichment_state"] == "READY"
    assert ready["field_sources"]["lot_size"] == "NSE_DETAIL"
    assert ready["field_sources"]["allotment_date"] == "NSE_RHP"


def test_equal_and_conflicting_exchange_lots_preserve_source_comparison():
    nse = make_observation("nse", "DETAIL", {"lot_size": 441})
    bse_equal = make_observation("bse", "DETAIL", {"lot_size": 441})
    dual_listed = {**discovery(), "listing_exchanges": "NSE+BSE"}
    equal = resolve_enriched_issue(dual_listed, [nse, bse_equal])
    assert equal["verified_by_multiple_official_sources"] is True
    bse_conflict = make_observation("bse", "DETAIL", {"lot_size": 37})
    conflict = resolve_enriched_issue(dual_listed, [nse, bse_conflict])
    assert conflict["source_conflict_fields"] == ["lot_size"]
    assert conflict["enrichment_state"] == "REVIEW_REQUIRED"
    assert "lot_size" in conflict["missing_planning_fields"]


def test_nse_emerge_with_detail_and_rhp_is_ready_without_bse():
    item = {
        **discovery(),
        "issue_type": "SME",
        "listing_platform": "SME",
        "source_market": "NSE_EMERGE",
    }
    detail_item = make_observation("nse", "DETAIL", {"lot_size": 1200})
    rhp = make_observation("nse", "DOCUMENT", {"allotment_date": "2026-09-29"}, fetched_hour=1)
    ready = resolve_enriched_issue(item, [detail_item, rhp])
    assert ready["enrichment_state"] == "READY"
    assert ready["bse_state"] == "NOT_APPLICABLE"
    assert ready["listing_exchanges"] == "NSE"


def test_bse_sme_with_detail_and_prospectus_is_ready_without_nse():
    item = {
        **discovery(),
        "issue_type": "SME",
        "listing_platform": "SME",
        "source_market": "BSE_SME",
        "listing_exchanges": "BSE",
        "designated_exchange": "BSE",
    }
    detail_item = make_observation("bse", "DETAIL", {"lot_size": 1200})
    rhp = make_observation("bse", "DOCUMENT", {"allotment_date": "2026-09-29"}, fetched_hour=1)
    ready = resolve_enriched_issue(item, [detail_item, rhp])
    assert ready["enrichment_state"] == "READY"
    assert ready["nse_state"] == "NOT_APPLICABLE"
    assert ready["listing_exchanges"] == "BSE"


def test_provider_and_rhp_failure_leave_prior_valid_fact_and_show_review():
    item = {**discovery(), "lot_size": 441, "allotment_date": "2026-09-29"}
    failed_detail = make_observation("nse", "DETAIL", {}, outcome="ERROR")
    failed_rhp = make_observation("nse", "DOCUMENT", {}, outcome="ERROR", fetched_hour=1)
    result = resolve_enriched_issue(item, [failed_detail, failed_rhp])
    assert result["lot_size"] == 441
    assert result["allotment_date"] == "2026-09-29"
    assert result["enrichment_state"] == "REVIEW_REQUIRED"
    assert {error["source"] for error in result["enrichment_errors"]} == {
        "nse_detail",
        "nse_document",
    }


def test_later_corrigendum_replaces_only_its_explicit_timetable_field():
    rhp = make_observation(
        "nse",
        "DOCUMENT",
        {"allotment_date": "2026-09-29", "listing_date": "2026-10-01"},
        document_date="2026-09-20",
    )
    correction = make_observation(
        "sebi",
        "DOCUMENT",
        {"allotment_date": "2026-09-30"},
        document_date="2026-09-23",
        fetched_hour=1,
    )
    correction.normalized_payload["document_type"] = "CORRIGENDUM"
    result = resolve_enriched_issue(discovery(), [rhp, correction])
    assert result["allotment_date"] == "2026-09-30"
    assert result["listing_date"] == "2026-10-01"
    assert result["field_sources"]["allotment_date"] == "SEBI_CORRIGENDUM"


def test_new_extractor_missing_fact_keeps_older_valid_value():
    old = make_observation(
        "nse", "DOCUMENT", {"allotment_date": "2026-09-29"}, document_date="2026-09-20"
    )
    newer = make_observation(
        "nse", "DOCUMENT", {"open_date": "2026-09-24"}, document_date="2026-09-20"
    )
    newer.payload_hash = old.payload_hash
    newer.normalizer_version = old.normalizer_version + 1
    newer.fetched_at = datetime(2026, 9, 28, 1, tzinfo=UTC)
    detail_item = make_observation("nse", "DETAIL", {"lot_size": 441})
    result = resolve_enriched_issue(discovery(), [detail_item, old, newer])
    assert result["enrichment_state"] == "READY"
    assert result["allotment_date"] == "2026-09-29"


@pytest.mark.django_db
def test_reimporting_same_detail_and_document_is_idempotent():
    raw = detail()
    normalized = NSEIPOIssueDetailProvider().normalize(raw, symbol="SYNTH", series="EQ")
    first = record_detail_observation(
        source_key="nse",
        symbol="SYNTH",
        source_url="https://www.nseindia.com/api/ipo-detail",
        raw=raw,
        normalized=normalized,
    )
    second = record_detail_observation(
        source_key="nse",
        symbol="SYNTH",
        source_url="https://www.nseindia.com/api/ipo-detail",
        raw=json.loads(json.dumps(raw)),
        normalized=normalized,
    )
    assert first.pk == second.pk
    assert IPOEnrichmentObservation.objects.count() == 1
    pdf_blob = b"%PDF-synthetic-byte-fixture"
    document = {"facts": {"allotment_date": "2026-09-29"}, "document_type": "RHP"}
    first_doc = record_document_observation(
        source_key="nse",
        symbol="SYNTH",
        source_url="https://nsearchives.nseindia.com/rhp.pdf",
        blob=pdf_blob,
        normalized=document,
    )
    second_doc = record_document_observation(
        source_key="nse",
        symbol="SYNTH",
        source_url="https://nsearchives.nseindia.com/rhp.pdf",
        blob=pdf_blob,
        normalized=document,
    )
    assert first_doc.pk == second_doc.pk
    assert IPOEnrichmentObservation.objects.count() == 2


@pytest.mark.django_db
def test_complete_enrichment_publishes_one_local_canonical_ipo():
    item = {
        **discovery(),
        "source_observed_at": "2026-09-28T00:00:00+00:00",
    }
    detail_item = make_observation("nse", "DETAIL", {"lot_size": 441})
    rhp = make_observation(
        "nse",
        "DOCUMENT",
        {"allotment_date": "2026-09-29"},
        document_date="2026-09-20",
        fetched_hour=1,
    )
    ready = resolve_enriched_issue(item, [detail_item, rhp])
    ipo, changed = publish_local_enriched_issue(
        ready, rights_reference="founder-test-permission-reference"
    )
    assert changed is True
    assert ipo.lot_size == 441
    assert ipo.allotment_date.isoformat() == "2026-09-29"
    assert ipo.publication_state == IPO.PublicationState.PUBLISHED
    same, changed = publish_local_enriched_issue(
        ready, rights_reference="founder-test-permission-reference"
    )
    assert same.pk == ipo.pk
    assert changed is False
    assert IPO.objects.filter(symbol="SYNTH").count() == 1


@pytest.mark.django_db
def test_saved_bse_detail_import_supports_official_cross_check(tmp_path):
    path = tmp_path / "bse-detail.html"
    path.write_text(
        "<table><tr><td>Symbol</td><td>SYNTH</td></tr>"
        "<tr><td>Market Lot</td><td>441</td></tr>"
        "<tr><td>Minimum Bid Quantity</td><td>441</td></tr></table>"
    )
    out = StringIO()
    call_command(
        "import_bse_ipo_detail",
        symbol="SYNTH",
        file=str(path),
        source_url="https://www.bseindia.com/markets/publicIssues/DisplayIPO.aspx",
        stdout=out,
    )
    observation = IPOEnrichmentObservation.objects.get(source_key="bse")
    assert observation.normalized_payload["facts"]["lot_size"] == 441
    assert "Saved BSE detail" in out.getvalue()
