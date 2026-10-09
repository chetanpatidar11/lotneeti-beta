import json
from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from ipos.feed_watch import current_feed_issues, record_nse_current_rows
from ipos.models import IPO, IPOFeedBatch, IPOFeedObservation


def nse_row(**changes):
    return {
        "companyName": "Synthetic Industries Limited",
        "symbol": "SYNTH",
        "series": "EQ",
        "status": "Active",
        "issuePrice": "Rs.100 to Rs.105",
        "issueStartDate": "28-Sep-2026",
        "issueEndDate": "30-Sep-2026",
        **changes,
    }


@pytest.mark.django_db
def test_current_feed_preserves_raw_observations_and_does_not_publish_an_ipo():
    at = datetime(2026, 9, 28, tzinfo=UTC)
    created, total = record_nse_current_rows([nse_row()], observed_at=at)
    assert (created, total) == (1, 1)
    assert record_nse_current_rows([nse_row()], observed_at=at) == (0, 1)
    assert IPO.objects.count() == 0
    observation = IPOFeedObservation.objects.get()
    assert observation.raw_payload["issuePrice"] == "Rs.100 to Rs.105"
    assert observation.normalized_payload["upper_price"] == "105"
    assert observation.normalized_payload["missing_planning_fields"] == [
        "lot_size",
        "allotment_date",
    ]
    with pytest.raises(ValueError, match="cannot be changed"):
        observation.save()
    with pytest.raises(ValueError, match="cannot be deleted"):
        observation.delete()


@pytest.mark.django_db
def test_new_observation_supersedes_display_without_erasing_history():
    old = datetime(2026, 9, 28, tzinfo=UTC)
    new = datetime(2026, 9, 28, 1, tzinfo=UTC)
    record_nse_current_rows([nse_row(issuePrice="Rs.100 to Rs.105")], observed_at=old)
    record_nse_current_rows([nse_row(issuePrice="Rs.100 to Rs.110")], observed_at=new)
    assert IPOFeedObservation.objects.count() == 2
    assert IPOFeedBatch.objects.count() == 2
    assert current_feed_issues()[0]["upper_price"] == "110"


@pytest.mark.django_db
def test_watch_marks_old_observation_stale():
    record_nse_current_rows([nse_row()], observed_at=timezone.now() - timedelta(hours=25))
    assert current_feed_issues()[0]["fresh"] is False


@pytest.mark.django_db
def test_latest_complete_response_removes_issues_that_nse_no_longer_lists():
    old = datetime(2026, 9, 28, tzinfo=UTC)
    new = datetime(2026, 9, 28, 1, tzinfo=UTC)
    record_nse_current_rows(
        [nse_row(), nse_row(symbol="SECOND", companyName="Second Synthetic Limited")],
        observed_at=old,
    )
    record_nse_current_rows([nse_row()], observed_at=new)
    assert [item["symbol"] for item in current_feed_issues()] == ["SYNTH"]
    assert IPOFeedObservation.objects.count() == 3
    record_nse_current_rows([], observed_at=datetime(2026, 9, 28, 2, tzinfo=UTC))
    assert current_feed_issues() == []
    assert IPOFeedObservation.objects.count() == 3
    assert IPOFeedBatch.objects.count() == 3


@pytest.mark.django_db
def test_nse_emerge_discovery_is_not_blocked_by_isbse_flag():
    record_nse_current_rows(
        [nse_row(series="SME", isBse="1", issuePrice=None)],
        observed_at=datetime(2026, 9, 28, tzinfo=UTC),
    )
    issue = current_feed_issues()[0]
    assert issue["source_key"] == "nse"
    assert issue["exchange_hint"] == "NSE"
    assert issue["source_market"] == "NSE_EMERGE"
    assert issue["designated_exchange"] == "NSE"
    assert issue["bse_state"] == "NOT_APPLICABLE"
    assert issue["enrichment_state"] == "DISCOVERED"
    assert "upper_price" in issue["pending_planning_fields"]


@pytest.mark.django_db
def test_invalid_batch_is_atomic_and_cached_observations_survive():
    at = datetime(2026, 9, 28, tzinfo=UTC)
    record_nse_current_rows([nse_row()], observed_at=at)
    with pytest.raises(ValidationError):
        record_nse_current_rows(
            [nse_row(symbol="NEXT"), nse_row(symbol="BROKEN", issuePrice="unknown")],
            observed_at=at,
        )
    assert IPOFeedObservation.objects.count() == 1


@pytest.mark.django_db
def test_authenticated_watch_api_reads_saved_rows_without_any_network():
    record_nse_current_rows([nse_row()], observed_at=datetime(2026, 9, 28, tzinfo=UTC))
    client = APIClient()
    assert client.get(reverse("ipo-feed-watch")).status_code in {401, 403}
    user = User.objects.create_user(email="member@example.test")
    client.force_authenticate(user)
    response = client.get(reverse("ipo-feed-watch"))
    assert response.status_code == 200
    assert response.data[0]["issuer_name"] == "Synthetic Industries Limited"


@pytest.mark.django_db
def test_saved_official_response_import_command_is_idempotent(tmp_path):
    source = tmp_path / "nse.json"
    source.write_text(json.dumps([nse_row()]), encoding="utf-8")
    out = StringIO()
    args = (
        "refresh_nse_ipo_feed",
        "--file",
        str(source),
        "--observed-at",
        "2026-09-28T00:00:00+00:00",
    )
    call_command(*args, stdout=out)
    call_command(*args, stdout=out)
    assert IPOFeedObservation.objects.count() == 1
    assert "Saved 0 new" in out.getvalue()
