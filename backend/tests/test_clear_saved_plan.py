from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User, WorkspaceMembership
from applications.services import cancel_application, start_tracking_plan
from core.models import AuditEvent
from planner.export_readiness import assert_exportable_plan
from planner.models import PlanRun
from planner.persistence import create_plan_run


@pytest.mark.django_db
def test_clearing_saved_plan_releases_untracked_funds_and_keeps_history():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    capital_url = reverse("workspace-capital", args=[workspace.pk])
    assert client.get(capital_url).data["planned"] == "15000.00"

    response = client.post(reverse("planner-run-clear", args=[workspace.pk, run.pk]))

    assert response.status_code == 200
    assert response.data["status"] == "CLEARED"
    assert client.get(capital_url).data == {
        "balance": "50000.00",
        "blocked": "0.00",
        "planned": "0.00",
        "available": "50000.00",
        "by_bank": {
            run.rows.first().bank_ref: {
                "balance": "50000.00",
                "blocked": "0.00",
                "planned": "0.00",
                "available": "50000.00",
            }
        },
    }
    run.refresh_from_db()
    assert run.status == PlanRun.Status.CLEARED
    assert run.planned_total == Decimal("15000.00")
    assert run.rows.count() == 1
    assert (
        AuditEvent.objects.filter(action="planner.run.cleared", object_id=str(run.pk)).count() == 1
    )
    assert client.post(reverse("planner-run-clear", args=[workspace.pk, run.pk])).status_code == 200
    assert (
        AuditEvent.objects.filter(action="planner.run.cleared", object_id=str(run.pk)).count() == 1
    )
    with pytest.raises(ValidationError):
        assert_exportable_plan(run)
    assert (
        client.post(reverse("application-start-tracking", args=[workspace.pk, run.pk])).status_code
        == 409
    )


@pytest.mark.django_db
def test_clear_requires_editor_and_latest_plan_in_same_workspace():
    owner, workspace, snapshot = setup_plan()
    older = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    newer = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    assert (
        client.post(reverse("planner-run-clear", args=[workspace.pk, older.pk])).status_code == 409
    )

    viewer = User.objects.create_user(email="plan-clear-viewer@example.test")
    WorkspaceMembership.objects.create(
        workspace=workspace, user=viewer, role=WorkspaceMembership.Role.VIEWER
    )
    client.force_authenticate(viewer)
    assert (
        client.post(reverse("planner-run-clear", args=[workspace.pk, newer.pk])).status_code == 403
    )
    outsider = User.objects.create_user(email="plan-clear-outsider@example.test")
    client.force_authenticate(outsider)
    assert (
        client.post(reverse("planner-run-clear", args=[workspace.pk, newer.pk])).status_code == 403
    )
    newer.refresh_from_db()
    assert newer.status == PlanRun.Status.READY


@pytest.mark.django_db
def test_clearing_latest_plan_keeps_active_application_reservations_from_older_run():
    owner, workspace, snapshot = setup_plan()
    tracked_run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    application = start_tracking_plan(plan_run=tracked_run, actor=owner)[0]
    saved_run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    capital_url = reverse("workspace-capital", args=[workspace.pk])

    assert (
        client.post(reverse("planner-run-clear", args=[workspace.pk, saved_run.pk])).status_code
        == 200
    )
    assert client.get(capital_url).data["planned"] == "15000.00"
    assert client.get(capital_url).data["available"] == "35000.00"
    cancel_application(application=application, actor=owner)
    assert client.get(capital_url).data["planned"] == "0.00"
