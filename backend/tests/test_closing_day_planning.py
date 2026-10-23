from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_preview_api import setup_workspace

from ipos.models import IPOUserDecision
from ipos.planning_window import planning_window
from planner.snapshot_builder import build_snapshot

INDIA = ZoneInfo("Asia/Kolkata")


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_closing_day_planning_keeps_closed_status_and_expires_at_midnight(monkeypatch):
    owner, workspace, _, ipo, decision = setup_workspace()
    late = datetime(2026, 10, 3, 23, 59, 59, tzinfo=INDIA)
    ipo.open_date = late.date()
    ipo.close_date = late.date()
    ipo.allotment_date = late.date().replace(day=9)
    ipo.status = "CLOSED"
    ipo.save()
    decision.decision = IPOUserDecision.Decision.APPLY
    decision.save()
    snapshot = build_snapshot(workspace=workspace, as_of=late)
    assert len(snapshot.ipos) == 1
    assert snapshot.ipos[0].cutoff_at.hour == 17
    midnight = datetime(2026, 10, 4, 0, 0, tzinfo=INDIA)
    assert build_snapshot(workspace=workspace, as_of=midnight).ipos == ()
    assert planning_window(status="CLOSED", close_date=ipo.close_date, now=late) == (True, True)
    assert planning_window(status="CLOSED", close_date=ipo.close_date, now=midnight) == (
        False,
        False,
    )
    monkeypatch.setattr("ipos.public_serializers.timezone.now", lambda: late)
    client = APIClient()
    client.force_authenticate(owner)
    result = client.get(reverse("ipo-list"))
    row = next(item for item in result.data if item["id"] == str(ipo.pk))
    assert row["status"] == "CLOSED"
    assert row["plan_available"] is True
