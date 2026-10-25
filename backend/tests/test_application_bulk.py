from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from test_quota_planning import setup_quota

from applications.models import Application
from core.models import AuditEvent
from funding.models import BankAccount
from planner.models import PlanRun


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["submit", "block"])
@pytest.mark.parametrize("mode", ["RETAIL_ONLY", "SHNI_PREFERRED", "BHNI_PREFERRED"])
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_bulk_submit_and_block_preserve_upi_and_asba_mappings(mode, action):
    # Also run on PostgreSQL: SQLite ignores row locks and cannot detect illegal
    # FOR UPDATE locks on the optional UPI's outer join.
    _, workspace, _, _, decision, client = setup_quota(count=2, eligible_count=2, balance="1250000")
    decision.mode = mode
    decision.save()
    rows = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json").data[
        "rows"
    ]
    rows = [row | ({"upi": None} if row["category"] == "BHNI" else {}) for row in rows]
    saved = client.post(
        reverse("planner-run-create", args=[workspace.pk]), {"rows": rows}, format="json"
    )
    assert saved.status_code == 201 and saved.data["status"] == "READY", saved.data
    run = PlanRun.objects.get()
    originals = list(run.rows.values())
    tracked = client.post(
        reverse("application-start-tracking", args=[workspace.pk, run.pk]),
        {"record_only": True},
        format="json",
    )
    assert tracked.status_code == 201 and len(tracked.data) == 4
    public_category = {
        "RETAIL_ONLY": "RETAIL",
        "SHNI_PREFERRED": "SHNI",
        "BHNI_PREFERRED": "BHNI",
    }[mode]
    assert {item["category"] for item in tracked.data} == {public_category, "SHARE"}
    ids = [item["id"] for item in tracked.data]
    mappings = {item["id"]: (item["bank"], item["upi"]) for item in tracked.data}
    balances = list(BankAccount.objects.order_by("pk").values_list("pk", "current_balance"))
    if action == "block":
        # One already Submitted plus three Planned rows must block together.
        response = client.post(
            reverse("application-action", args=[workspace.pk, ids[0], "submit"]),
            {"record_only": True},
            format="json",
        )
        assert response.status_code == 200
    bulk = reverse("application-bulk", args=[workspace.pk])
    response = client.post(bulk, {"action": action, "ids": ids, "record_only": True}, format="json")
    expected_status = "SUBMITTED" if action == "submit" else "BLOCKED"
    assert response.status_code == 200 and len(response.data) == len(ids)
    assert all(item["status"] == expected_status for item in response.data)
    assert {item["id"]: (item["bank"], item["upi"]) for item in response.data} == mappings
    if action == "submit":
        response = client.post(
            bulk, {"action": "block", "ids": ids, "record_only": True}, format="json"
        )
        assert response.status_code == 200
    assert all(item["submitted_at"] and item["blocked_at"] for item in response.data)
    assert Application.objects.filter(status="BLOCKED").count() == 4
    assert AuditEvent.objects.filter(action="application.submitted").count() == 4
    assert AuditEvent.objects.filter(action="application.blocked").count() == 4
    assert Application.objects.filter(category="BHNI", upi__isnull=True).count() == (
        2 if mode == "BHNI_PREFERRED" else 0
    )
    first = Application.objects.get(pk=ids[0])
    edited = client.post(
        reverse("application-action", args=[workspace.pk, first.pk, "edit"]),
        {
            "category": first.category,
            "lots": first.lots + 1 if first.category != "SHARE" else 1,
            "bank": str(first.bank_id),
            "upi": str(first.upi_id) if first.upi_id else None,
            "record_only": True,
        },
        format="json",
    )
    assert edited.status_code == 200 and edited.data["status"] == "BLOCKED"
    assert Decimal(edited.data["amount"]) > 0
    assert list(run.rows.values()) == originals
    assert list(BankAccount.objects.order_by("pk").values_list("pk", "current_balance")) == balances
