from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings

from ipos.licensed_source_schedule import licensed_refresh_slot, reserve_refresh_slot
from ipos.models import IPO, GMPObservation
from ipos.tasks import _sync_nse, run_ipo_sync, sync_gmp_sources


def ist(hour, minute=0):
    return datetime(2026, 10, 1, hour, minute, tzinfo=ZoneInfo("Asia/Kolkata"))


def test_investorgain_schedule_matches_the_licensed_slots():
    schedule = settings.CELERY_BEAT_SCHEDULE
    assert schedule["sync-daily-ipo-data"]["task"] == "ipos.tasks.sync_daily_ipo_data"
    assert str(schedule["sync-daily-ipo-data"]["schedule"]) == "<crontab: 1 0 * * * (m/h/dM/MY/d)>"
    assert schedule["sync-hourly-investorgain-ipo-data"]["task"] == (
        "ipos.tasks.sync_hourly_investorgain_ipo_data"
    )
    assert str(schedule["sync-hourly-investorgain-ipo-data"]["schedule"]) == (
        "<crontab: 0 9-19 * * * (m/h/dM/MY/d)>"
    )
    assert "sync-gmp-midnight" not in schedule
    assert "sync-gmp-hourly" not in schedule
    assert "refresh-ipo-provider-health" not in schedule
    assert "sync-sebi-filings" not in schedule


def test_licensed_slots_include_daily_0001_and_hourly_0900_through_1900():
    assert licensed_refresh_slot(ist(0, 1)) == ist(0, 1)
    assert licensed_refresh_slot(ist(9)) == ist(9)
    assert licensed_refresh_slot(ist(19)) == ist(19)
    assert licensed_refresh_slot(ist(0)) is None
    assert licensed_refresh_slot(ist(8, 59)) is None
    assert licensed_refresh_slot(ist(9, 1)) is None
    assert licensed_refresh_slot(ist(19, 1)) is None
    assert licensed_refresh_slot(ist(20)) is None


@pytest.mark.django_db
def test_refresh_slot_reservation_blocks_duplicate_and_off_schedule_requests():
    error, _ = reserve_refresh_slot("nse", at=ist(9))
    assert error is None
    error, _ = reserve_refresh_slot("nse", at=ist(9))
    assert error["status"] == "RATE_LIMITED"
    error, _ = reserve_refresh_slot("nse", at=ist(10))
    assert error is None
    error, _ = reserve_refresh_slot("nse", at=ist(20))
    assert error["status"] == "OUTSIDE_SCHEDULE"


@pytest.mark.django_db
def test_investorgain_manual_sync_outside_the_window_does_not_fetch():
    make_gmp_ipo()
    with (
        patch("ipos.investorgain_gmp.timezone.now", return_value=ist(20)),
        patch("ipos.investorgain_gmp.fetch_payload") as fetch,
    ):
        result = sync_gmp_sources()
    assert result["status"] == "OUTSIDE_SCHEDULE"
    fetch.assert_not_called()


@pytest.mark.django_db
def test_nse_manual_sync_outside_the_window_does_not_fetch(monkeypatch):
    monkeypatch.setenv("LOTNEETI_NSE_SOURCE_RIGHTS_REFERENCE", "synthetic-rights-reference")
    monkeypatch.setenv("LOTNEETI_IPO_SOURCE_CACHE_DIR", "/private/tmp/synthetic-ipo-cache")
    with (
        patch("ipos.tasks.timezone.now", return_value=ist(20)),
        patch("ipos.tasks.call_command") as call_command,
    ):
        result = _sync_nse(refresh_discovery=True)
    assert result["status"] == "OUTSIDE_SCHEDULE"
    call_command.assert_not_called()


@pytest.mark.django_db
def test_founder_manual_nse_sync_bypasses_the_automatic_schedule(monkeypatch):
    monkeypatch.setenv("LOTNEETI_NSE_SOURCE_RIGHTS_REFERENCE", "synthetic-rights-reference")
    monkeypatch.setenv("LOTNEETI_IPO_SOURCE_CACHE_DIR", "/private/tmp/synthetic-ipo-cache")
    with (
        patch("ipos.tasks.timezone.now", return_value=ist(20)),
        patch("ipos.tasks.call_command") as call_command,
    ):
        result = _sync_nse(refresh_discovery=True, manual=True)
    assert result["status"] == "OK"
    call_command.assert_called_once()


@pytest.mark.django_db
def test_daily_sync_uses_only_investorgain():
    with patch("ipos.tasks.sync_gmp_sources", return_value={"status": "OK", "fetched": 2}):
        first = run_ipo_sync()
        second = run_ipo_sync()
    assert first == second
    assert first == {"investorgain": {"status": "OK", "fetched": 2}}


@pytest.mark.django_db
def investorgain_row():
    return {
        "~id": 321,
        "~ipo_name": "Orient Cables",
        "~ipo_status1": "O",
        "~ipo_category1": "MAINBOARD",
        "Price (₹)": "250-272",
        "Lot": "55",
        "Open": "1-Oct",
        "Close": "3-Oct",
        "BoA Dt": "6-Oct",
        "Listing": "8-Oct",
        "GMP": "&#8377;<b>76</b> (27.94%)",
        "Updated-On": "1-Oct 09:00",
        "~urlrewrite_folder_name": "/gmp/orient-cables-ipo/321/",
    }


def make_gmp_ipo(name="Orient Cables (India) Limited"):
    today = date.today()
    return IPO.objects.create(
        issuer_name=name,
        issue_type=IPO.IssueType.MAINBOARD,
        lower_price=Decimal("250.00"),
        upper_price=Decimal("272.00"),
        lot_size=55,
        open_date=today,
        close_date=today + timedelta(days=2),
        allotment_date=today + timedelta(days=5),
        status=IPO.Status.OPEN,
        publication_state=IPO.PublicationState.PUBLISHED,
        source_key="synthetic",
        source_record_id=f"synthetic-{name}",
    )


@pytest.mark.django_db
def test_daily_investorgain_sync_stores_an_observation_and_is_idempotent():
    payload = {"reportTableData": [investorgain_row()]}
    with patch(
        "ipos.investorgain_gmp.fetch_payload",
        return_value=("https://webnodejs.investorgain.com/example", payload),
    ) as fetch:
        with patch("ipos.investorgain_gmp.timezone.now", return_value=ist(9)):
            first = sync_gmp_sources()
            second = sync_gmp_sources()
        with patch("ipos.investorgain_gmp.timezone.now", return_value=ist(10)):
            third = sync_gmp_sources()
    assert first["status"] == "OK"
    assert first["requested"] == first["matched"] == first["created"] == 1
    assert second["status"] == "RATE_LIMITED"
    assert third["status"] == "OK"
    assert third["created"] == 0
    assert fetch.call_count == 2
    observation = GMPObservation.objects.get(source_key="investorgain")
    assert observation.value_per_share == Decimal("76")
    assert observation.source_record_id == "321"
    assert observation.source_url == "https://www.investorgain.com/gmp/orient-cables-ipo/321/"


@pytest.mark.django_db
def test_founder_manual_gmp_sync_bypasses_the_automatic_schedule():
    payload = {"reportTableData": [investorgain_row()]}
    with (
        patch("ipos.investorgain_gmp.timezone.now", return_value=ist(20)),
        patch(
            "ipos.investorgain_gmp.fetch_payload",
            return_value=("https://example.test", payload),
        ),
    ):
        result = sync_gmp_sources(manual=True)
    assert result["status"] == "OK"
    assert result["created"] == 1


@pytest.mark.django_db
def test_investorgain_skips_missing_gmp_instead_of_storing_zero():
    make_gmp_ipo("No GMP Limited")
    payload = {
        "reportTableData": [{"~id": 123, "~ipo_name": "No GMP", "GMP": "&#8377;<b>--</b> (0.00%)"}]
    }
    with (
        patch("ipos.investorgain_gmp.timezone.now", return_value=ist(9)),
        patch(
            "ipos.investorgain_gmp.fetch_payload",
            return_value=("https://webnodejs.investorgain.com/example", payload),
        ),
    ):
        result = sync_gmp_sources()
    assert result["matched"] == result["created"] == 0
    assert GMPObservation.objects.filter(source_key="investorgain").count() == 0


@pytest.mark.django_db
def test_daily_nse_pipeline_publishes_ready_issue_idempotently(monkeypatch, tmp_path):
    monkeypatch.setenv("LOTNEETI_NSE_SOURCE_RIGHTS_REFERENCE", "synthetic-rights-reference")
    monkeypatch.setenv("LOTNEETI_IPO_SOURCE_CACHE_DIR", str(tmp_path))
    ready = {
        "symbol": "SYNTH",
        "issuer_name": "Synthetic Limited",
        "issue_type": "MAINBOARD",
        "source_market": "NSE_MAINBOARD",
        "listing_exchanges": "NSE",
        "designated_exchange": "NSE",
        "lower_price": "100.00",
        "upper_price": "110.00",
        "lot_size": 100,
        "open_date": "2026-09-28",
        "close_date": "2026-09-30",
        "allotment_date": "2026-10-01",
        "status": "Active",
        "source_observed_at": "2026-09-28T00:00:00+00:00",
        "source_record_id": "EQ:SYNTH",
        "field_sources": {"lot_size": "NSE_DETAIL", "allotment_date": "NSE_RHP"},
        "enrichment_state": "READY",
        "missing_planning_fields": [],
    }
    with (
        patch("ipos.tasks.call_command"),
        patch("ipos.feed_watch.current_feed_issues", return_value=[ready]),
    ):
        with patch("ipos.tasks.timezone.now", return_value=ist(9)):
            first = _sync_nse(refresh_discovery=True)
        with patch("ipos.tasks.timezone.now", return_value=ist(10)):
            second = _sync_nse(refresh_discovery=True)
    assert first["status"] == second["status"] == "OK"
    assert first["changed"] == 1
    assert second["changed"] == 0
    assert IPO.objects.filter(symbol="SYNTH").count() == 1
