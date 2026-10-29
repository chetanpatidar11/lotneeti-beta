import csv
from io import StringIO

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User, WorkspaceMembership
from core.models import AuditEvent
from planner.models import PlanRun
from planner.persistence import create_plan_run


@pytest.mark.django_db
@pytest.mark.parametrize("format_id", ["demat_csv", "quota_csv"])
def test_direct_csv_without_s3_has_exact_bytes_private_headers_and_reserves_ipo(format_id):
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    run.reserved_ipo_ids = []
    run.save(update_fields=["reserved_ipo_ids"])
    client = APIClient()
    client.force_authenticate(owner)
    ipo_id = snapshot.ipos[0].id
    response = client.post(
        reverse("plan-export-create", args=[workspace.pk, run.pk]),
        {"format_id": format_id, "ipo_id": ipo_id, "delivery": "download"},
        format="json",
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Cache-Control"] == "private, no-store"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert 'attachment; filename="' in response["Content-Disposition"]
    assert "synthetic-industries-" in response["Content-Disposition"]
    rows = list(csv.reader(StringIO(response.content.decode())))
    assert len(rows) == 2
    assert "TESTX0001A" in rows[1] and "demo@upi.test" in rows[1]
    run.refresh_from_db()
    assert run.reserved_ipo_ids == [ipo_id]
    audit = AuditEvent.objects.get(action="planner.export.downloaded", workspace=workspace)
    from hashlib import sha256

    assert audit.metadata["content_sha256"] == sha256(response.content).hexdigest()
    assert "TESTX0001A" not in str(audit.metadata)


@pytest.mark.django_db
def test_direct_csv_denies_viewers_outsiders_anonymous_and_blocked_plans():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    url = reverse("plan-export-create", args=[workspace.pk, run.pk])
    payload = {"format_id": "demat_csv", "ipo_id": snapshot.ipos[0].id, "delivery": "download"}
    client = APIClient()
    assert client.post(url, payload, format="json").status_code == 403
    for role, status in [("VIEWER", 403), ("outsider", 404), ("OPERATOR", 200)]:
        user = User.objects.create_user(email=f"{role.lower()}@example.test")
        if role != "outsider":
            WorkspaceMembership.objects.create(workspace=workspace, user=user, role=role)
        client.force_authenticate(user)
        assert client.post(url, payload, format="json").status_code == status
    client.force_authenticate(owner)
    run.status = PlanRun.Status.BLOCKED
    run.reserved_ipo_ids = []
    run.save(update_fields=["status", "reserved_ipo_ids"])
    assert client.post(url, payload, format="json").status_code == 409
    run.refresh_from_db()
    assert run.reserved_ipo_ids == []


@pytest.mark.django_db
def test_direct_csv_rejects_other_ipo_without_reserving_funds():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    run.reserved_ipo_ids = []
    run.save(update_fields=["reserved_ipo_ids"])
    client = APIClient()
    client.force_authenticate(owner)
    response = client.post(
        reverse("plan-export-create", args=[workspace.pk, run.pk]),
        {"format_id": "demat_csv", "ipo_id": "not-in-plan", "delivery": "download"},
        format="json",
    )
    assert response.status_code == 409
    run.refresh_from_db()
    assert run.reserved_ipo_ids == []
    assert not AuditEvent.objects.filter(action="planner.export.downloaded").exists()
