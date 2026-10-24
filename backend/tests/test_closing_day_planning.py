from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_preview_api import setup_workspace
from test_planner_validate_api import edited_row

from accounts.models import User
from applications.models import Application
from ipos.models import GMPObservation
from ipos.planning_window import planning_window
from ipos.selection import resolve_ipo_choices
from planner.export_readiness import assert_exportable_plan
from planner.models import PlanRun
from planner.snapshot_builder import build_snapshot

INDIA = ZoneInfo("Asia/Kolkata")


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["CLOSED", "ALLOTMENT", "LISTED", "OPEN"])
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_manual_record_planning_has_no_midnight_or_age_limit(monkeypatch, status):
    owner, workspace, _, ipo, _ = setup_workspace()
    ipo.open_date = date(2026, 10, 1)
    ipo.close_date = date(2026, 10, 3)
    ipo.allotment_date = date(2026, 10, 9)
    ipo.status = status
    ipo.save()
    for instant in (
        datetime(2026, 10, 3, 23, 59, 59, tzinfo=INDIA),
        datetime(2026, 10, 4, 0, 0, tzinfo=INDIA),
        datetime(2027, 1, 10, 12, 0, tzinfo=INDIA),
    ):
        snapshot = build_snapshot(workspace=workspace, as_of=instant)
        assert len(snapshot.ipos) == 1
        assert snapshot.ipos[0].cutoff_at == datetime(2026, 10, 3, 17, tzinfo=INDIA)
        assert planning_window(status=status, close_date=ipo.close_date, now=instant) == (
            True,
            True,
        )
    monkeypatch.setattr("ipos.public_serializers.timezone.now", lambda: instant)
    client = APIClient()
    client.force_authenticate(owner)
    result = client.get(reverse("ipo-list"))
    row = next(item for item in result.data if item["id"] == str(ipo.pk))
    assert row["status"] == ("CLOSED" if status == "OPEN" else status)
    assert row["plan_available"] is True
    assert row["planning_only"] is True


@pytest.mark.parametrize("status", ["OPEN", "CLOSED", "ALLOTMENT", "LISTED"])
@pytest.mark.parametrize("day,hour", [(3, 17), (3, 23), (4, 0), (24, 12)])
def test_closed_ipo_is_never_automatically_selected_even_with_high_gmp(status, day, hour):
    values = {
        "status": status,
        "issue_type": "MAINBOARD",
        "open_date": date(2026, 10, 1),
        "close_date": date(2026, 10, 3),
        "allotment_date": date(2026, 10, 9),
    }
    result = resolve_ipo_choices(
        candidates=[("old-ipo", values, "DEFAULT", Decimal("90"))],
        threshold=Decimal("5"),
        issue_types=("MAINBOARD",),
        at=datetime(2026, 10, day, hour, tzinfo=INDIA),
    )
    assert result["old-ipo"] == (False, "IPO_NOT_OPEN")


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_old_closed_ipo_manual_api_flow_preview_validate_save_submit_and_scope(monkeypatch):
    owner, workspace, investor, ipo, decision = setup_workspace()
    now = datetime(2026, 10, 24, 12, tzinfo=INDIA)
    monkeypatch.setattr("django.utils.timezone.now", lambda: now)
    ipo.open_date = date(2026, 10, 1)
    ipo.close_date = date(2026, 10, 3)
    ipo.allotment_date = date(2026, 10, 9)
    ipo.status = "CLOSED"
    ipo.save()
    workspace.auto_select_enabled = True
    workspace.auto_select_gmp_percent = Decimal("5")
    workspace.save()
    decision.decision = "DEFAULT"
    decision.save()
    GMPObservation.objects.create(
        ipo=ipo, source_key="manual", value_per_share=Decimal("90"), observed_at=now
    )
    client = APIClient()
    client.force_authenticate(owner)
    preview_url = reverse("planner-preview", args=[workspace.pk])
    assert client.post(preview_url, {}, format="json").data["rows"] == []
    choice_url = reverse("workspace-ipo-decision-detail", args=[workspace.pk, ipo.pk])
    selected = client.patch(choice_url, {"decision": "APPLY"}, format="json")
    assert selected.status_code == 200
    assert selected.data["selected"] is True
    preview = client.post(preview_url, {}, format="json")
    assert preview.status_code == 200
    assert preview.data["status"] == "READY"
    assert preview.data["planning_only"] is True
    assert len(preview.data["rows"]) == 1
    payload = {"rows": [edited_row(investor, ipo)]}
    validated = client.post(
        reverse("planner-validate", args=[workspace.pk]), payload, format="json"
    )
    assert validated.status_code == 200
    assert validated.data["status"] == "READY"
    saved = client.post(reverse("planner-run-create", args=[workspace.pk]), payload, format="json")
    assert saved.status_code == 201, saved.data
    assert saved.data["planning_only"] is True
    run = PlanRun.objects.get()
    with pytest.raises(ValidationError, match="record keeping"):
        assert_exportable_plan(run)
    tracked = client.post(reverse("application-start-tracking", args=[workspace.pk, run.pk]), {})
    assert tracked.status_code == 201
    application = Application.objects.get()
    submitted = client.post(
        reverse("application-action", args=[workspace.pk, application.pk, "submit"]), {}
    )
    assert submitted.status_code == 200
    application.refresh_from_db()
    assert application.status == "SUBMITTED"
    outsider = User.objects.create_user(email="outsider@synthetic.test")
    client.force_authenticate(outsider)
    assert client.post(preview_url, {}, format="json").status_code in {403, 404}
    assert client.patch(choice_url, {"decision": "APPLY"}, format="json").status_code in {403, 404}


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
@pytest.mark.parametrize("status,publication", [("CANCELLED", "PUBLISHED"), ("CLOSED", "DRAFT")])
def test_cancelled_or_unpublished_ipo_stays_unavailable(status, publication):
    _, workspace, _, ipo, _ = setup_workspace()
    ipo.status = status
    ipo.publication_state = publication
    ipo.save()
    assert build_snapshot(workspace=workspace).ipos == ()
    with pytest.raises(ValidationError):
        build_snapshot(workspace=workspace, ipo_ids={str(ipo.pk)})
