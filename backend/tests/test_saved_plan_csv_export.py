import csv
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from test_planner_persistence import setup_plan

from accounts.models import User, WorkspaceMembership
from exports.services import export_saved_plan
from planner.models import PlanRun
from planner.persistence import create_plan_run


@pytest.mark.django_db
def test_valid_saved_plan_exports_stable_csv_with_authorized_values():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    first = export_saved_plan(plan_run=run, actor=owner)
    second = export_saved_plan(plan_run=run, actor=owner)
    assert first == second
    assert first.format_id == "generic_csv"
    parsed = list(csv.reader(StringIO(first.data.decode("utf-8"))))
    assert len(parsed) == 2
    assert parsed[1] == [
        "Synthetic",
        "TESTX0001A",
        "CDSL",
        "1",
        "DEMO-CLIENT-001",
        "demo@upi.test",
        "DEMO-ACCOUNT-0001",
    ]


@pytest.mark.django_db
def test_blocked_plan_and_viewer_cannot_export_saved_csv():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    viewer = User.objects.create_user(email="viewer@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    with pytest.raises(ValidationError, match="cannot export"):
        export_saved_plan(plan_run=run, actor=viewer)
    run.status = PlanRun.Status.BLOCKED
    run.save(update_fields=["status"])
    with pytest.raises(ValidationError, match="blocking plan issues"):
        export_saved_plan(plan_run=run, actor=owner)
