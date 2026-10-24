from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from test_quota_planning import setup_quota

from accounts.models import User, WorkspaceMembership
from applications.models import Application
from core.models import AuditEvent
from funding.models import BankAccount
from planner.export_readiness import assert_exportable_plan
from planner.models import PlanRun


def warning_plan():
    owner, workspace, _, _, _, client = setup_quota()
    rows = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json").data[
        "rows"
    ]
    changed = [row | {"bank": rows[0]["bank"], "upi": rows[0]["upi"]} for row in rows]
    saved = client.post(
        reverse("planner-run-create", args=[workspace.pk]), {"rows": changed}, format="json"
    )
    assert saved.status_code == 201 and saved.data["status"] == "BLOCKED"
    return owner, workspace, client, PlanRun.objects.get()


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_record_only_all_23_warning_rows_can_be_blocked_edited_resulted_and_cancelled():
    owner, workspace, client, run = warning_plan()
    originals = list(run.rows.values())
    balances = list(BankAccount.objects.values_list("pk", "current_balance"))
    track = reverse("application-start-tracking", args=[workspace.pk, run.pk])
    assert client.post(track, {}, format="json").status_code == 409
    tracked = client.post(track, {"record_only": True}, format="json")
    assert tracked.status_code == 201 and len(tracked.data) == 23
    first = Application.objects.get(pk=tracked.data[0]["id"])

    # Direct Planned -> Blocked records both timestamps and events atomically.
    def action(item, name):
        return reverse("application-action", args=[workspace.pk, item.pk, name])

    assert client.post(action(first, "block"), {}, format="json").status_code == 409
    blocked = client.post(action(first, "block"), {"record_only": True}, format="json")
    assert blocked.status_code == 200 and blocked.data["status"] == "BLOCKED"
    assert blocked.data["submitted_at"] and blocked.data["blocked_at"]
    assert (
        client.post(action(first, "block"), {"record_only": True}, format="json").status_code == 409
    )
    remaining = [item["id"] for item in tracked.data[1:]]
    bulk = reverse("application-bulk", args=[workspace.pk])
    response = client.post(
        bulk, {"action": "block", "ids": remaining, "record_only": True}, format="json"
    )
    assert response.status_code == 200 and len(response.data) == 22
    assert Application.objects.filter(status="BLOCKED").count() == 23
    assert AuditEvent.objects.filter(action="application.submitted").count() == 23
    assert AuditEvent.objects.filter(action="application.blocked").count() == 23
    assert (
        AuditEvent.objects.filter(
            action="application.submitted", metadata__record_only=True
        ).count()
        == 23
    )
    assert any(
        event.metadata["warnings"]
        for event in AuditEvent.objects.filter(action="application.submitted")
    )
    assert list(BankAccount.objects.values_list("pk", "current_balance")) == balances
    first.refresh_from_db()
    edited = client.post(
        action(first, "edit"),
        {
            "category": first.category,
            "lots": 2,
            "bank": str(first.bank_id),
            "upi": str(first.upi_id),
            "record_only": True,
        },
        format="json",
    )
    assert edited.status_code == 200 and edited.data["status"] == "BLOCKED"
    assert edited.data["lots"] == 2 and edited.data["amount"] == "30000.00"
    assert (
        client.get(reverse("workspace-capital", args=[workspace.pk])).data["blocked"]
        == "1800000.00"
    )
    first.refresh_from_db()
    result = client.post(action(first, "not-allotted"), {}, format="json")
    assert result.status_code == 200 and result.data["status"] == "NOT_ALLOTTED"
    cancelled = client.post(
        bulk, {"action": "cancel", "ids": remaining, "record_only": True}, format="json"
    )
    assert cancelled.status_code == 200
    assert client.get(reverse("workspace-capital", args=[workspace.pk])).data["blocked"] == "0.00"
    assert list(run.rows.values()) == originals
    run.refresh_from_db()
    assert run.status == "BLOCKED" and run.audit_issues
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        assert_exportable_plan(run)


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_record_only_is_explicit_scoped_and_cannot_revive_cleared_or_cancelled_rows():
    owner, workspace, client, run = warning_plan()
    track = reverse("application-start-tracking", args=[workspace.pk, run.pk])
    viewer = User.objects.create_user(email="record-viewer@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    client.force_authenticate(viewer)
    assert client.post(track, {"record_only": True}, format="json").status_code == 403
    outsider = User.objects.create_user(email="record-outsider@example.test")
    client.force_authenticate(outsider)
    assert client.post(track, {"record_only": True}, format="json").status_code == 404
    client.force_authenticate(owner)
    assert client.post(track, {"record_only": "invalid"}, format="json").status_code == 400
    row = run.rows.first()
    tracked = client.post(track, {"row_ids": [str(row.pk)], "record_only": True}, format="json")
    assert tracked.status_code == 201
    item = Application.objects.get()
    cancel = reverse("application-action", args=[workspace.pk, item.pk, "cancel"])
    assert client.post(cancel, {}, format="json").status_code == 200
    assert (
        client.post(
            track, {"row_ids": [str(row.pk)], "record_only": True}, format="json"
        ).status_code
        == 409
    )
    block = reverse("application-action", args=[workspace.pk, item.pk, "block"])
    assert client.post(block, {"record_only": True}, format="json").status_code == 409
    run.status = "CLEARED"
    run.save(update_fields=["status"])
    assert client.post(track, {"record_only": True}, format="json").status_code == 409


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_recording_keeps_structural_mapping_and_quota_errors_blocked():
    _, workspace, _, _, _, client = setup_quota(count=1, eligible_count=1)
    rows = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json").data[
        "rows"
    ]
    rows[0]["amount"] = "1.00"
    saved = client.post(
        reverse("planner-run-create", args=[workspace.pk]), {"rows": rows}, format="json"
    )
    assert saved.data["status"] == "BLOCKED"
    run = PlanRun.objects.get()
    response = client.post(
        reverse("application-start-tracking", args=[workspace.pk, run.pk]),
        {"record_only": True},
        format="json",
    )
    assert response.status_code == 409 and Application.objects.count() == 0


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_manual_asba_block_can_record_low_current_balance_without_changing_it():
    _, workspace, _, _, decision, client = setup_quota(count=1, eligible_count=0, balance="1250000")
    decision.shareholder_preferred = False
    decision.mode = "BHNI_PREFERRED"
    decision.save()
    rows = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json").data[
        "rows"
    ]
    for row in rows:
        row["upi"] = None
    assert (
        client.post(
            reverse("planner-run-create", args=[workspace.pk]), {"rows": rows}, format="json"
        ).status_code
        == 201
    )
    run = PlanRun.objects.get()
    BankAccount.objects.filter(workspace=workspace).update(current_balance=Decimal("1"))
    tracked = client.post(
        reverse("application-start-tracking", args=[workspace.pk, run.pk]),
        {"record_only": True},
        format="json",
    )
    assert tracked.status_code == 201
    item = Application.objects.get()
    blocked = client.post(
        reverse("application-action", args=[workspace.pk, item.pk, "block"]),
        {"record_only": True},
        format="json",
    )
    assert blocked.status_code == 200 and blocked.data["status"] == "BLOCKED"
    assert BankAccount.objects.get(workspace=workspace).current_balance == Decimal("1")


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_manual_bulk_block_rolls_back_both_timestamps_and_audits_if_one_row_is_cancelled():
    _, workspace, client, run = warning_plan()
    rows = list(run.rows.all())[:2]
    tracked = client.post(
        reverse("application-start-tracking", args=[workspace.pk, run.pk]),
        {"row_ids": [str(row.pk) for row in rows], "record_only": True},
        format="json",
    )
    assert tracked.status_code == 201
    items = list(Application.objects.order_by("pk"))
    assert (
        client.post(
            reverse("application-action", args=[workspace.pk, items[1].pk, "cancel"]),
            {},
            format="json",
        ).status_code
        == 200
    )
    response = client.post(
        reverse("application-bulk", args=[workspace.pk]),
        {"ids": [str(item.pk) for item in items], "action": "block", "record_only": True},
        format="json",
    )
    assert response.status_code == 409
    items[0].refresh_from_db()
    assert items[0].status == "PLANNED"
    assert items[0].submitted_at is None and items[0].blocked_at is None
    assert not AuditEvent.objects.filter(
        action__in=["application.submitted", "application.blocked"]
    ).exists()


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_manual_recording_rejects_superseded_plan_even_without_specific_rows():
    _, workspace, client, run = warning_plan()
    old = run.pk
    payload = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json").data
    assert (
        client.post(
            reverse("planner-run-create", args=[workspace.pk]),
            {"rows": payload["rows"]},
            format="json",
        ).status_code
        == 201
    )
    result = client.post(
        reverse("application-start-tracking", args=[workspace.pk, old]),
        {"record_only": True},
        format="json",
    )
    assert result.status_code == 409 and Application.objects.count() == 0
