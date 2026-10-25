from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from test_quota_planning import setup_quota

from applications.models import Application
from funding.models import UPIHandle
from planner.models import PlanRun


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status", ["PLANNED", "SUBMITTED", "BLOCKED", "NOT_ALLOTTED", "ALLOTTED", "CANCELLED"]
)
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_resaved_plan_reserves_each_tracked_lane_once_and_keeps_shareholder_separate(status):
    _, workspace, _, _, _, client = setup_quota(count=1, eligible_count=1, balance="600000")
    rows = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json").data[
        "rows"
    ]
    save_url = reverse("planner-run-create", args=[workspace.pk])
    assert client.post(save_url, {"rows": rows}, format="json").status_code == 201
    first = PlanRun.objects.first()
    originals = list(first.rows.values())
    public = first.rows.get(category="RETAIL")
    tracked = client.post(
        reverse("application-start-tracking", args=[workspace.pk, first.pk]),
        {"row_ids": [str(public.pk)], "record_only": True},
        format="json",
    )
    assert tracked.status_code == 201 and len(tracked.data) == 1
    item = Application.objects.get()

    def action(name, **data):
        return client.post(
            reverse("application-action", args=[workspace.pk, item.pk, name]),
            {"record_only": True, **data},
            format="json",
        )

    if status in {"BLOCKED", "NOT_ALLOTTED", "ALLOTTED"}:
        assert action("block").status_code == 200
    if status == "SUBMITTED":
        assert action("submit").status_code == 200
    if status == "NOT_ALLOTTED":
        assert action("not-allotted").status_code == 200
    if status == "ALLOTTED":
        assert action("allotted", quantity=150, actual_cost="15000.00").status_code == 200
    if status == "CANCELLED":
        assert action("cancel").status_code == 200
    item.refresh_from_db()
    assert item.status == status

    for lots in (2, 3):
        edited = [row | {"lots": lots, "amount": str(Decimal("15000.00") * lots)} for row in rows]
        saved = client.post(save_url, {"rows": edited}, format="json")
        assert saved.status_code == 201
        latest = PlanRun.objects.first()
        assert latest.pk != first.pk
        expected_planned = Decimal("15000.00") * lots  # Latest shareholder row remains separate.
        if status in {"PLANNED", "SUBMITTED"}:
            expected_planned += Decimal("15000.00")
        elif status == "CANCELLED":
            expected_planned *= 2  # A new public row may replace a cancelled earlier application.
        expected_blocked = Decimal("15000.00") if status == "BLOCKED" else Decimal("0.00")
        expected_balance = Decimal("585000.00") if status == "ALLOTTED" else Decimal("600000.00")
        capital = client.get(reverse("workspace-capital", args=[workspace.pk])).data
        assert Decimal(capital["planned"]) == expected_planned
        assert Decimal(capital["blocked"]) == expected_blocked
        assert Decimal(capital["balance"]) == expected_balance
        assert (
            Decimal(capital["available"]) == expected_balance - expected_blocked - expected_planned
        )
        listed = client.get(reverse("application-list", args=[workspace.pk])).data
        saved_rows = [row for row in listed if row["is_plan_row"]]
        assert len(saved_rows) == (2 if status == "CANCELLED" else 1)
        assert "SHARE" in {row["category"] for row in saved_rows}
    assert list(first.rows.values()) == originals
    item.refresh_from_db()
    assert item.lots == 1 and item.amount == Decimal("15000.00") and item.status == status


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_resaving_keeps_tracked_bank_and_lot_edits_instead_of_reserving_old_mapping():
    _, workspace, investors, _, _, client = setup_quota(count=2, eligible_count=1, balance="600000")
    rows = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json").data[
        "rows"
    ]
    save_url = reverse("planner-run-create", args=[workspace.pk])
    assert client.post(save_url, {"rows": rows}, format="json").status_code == 201
    first = PlanRun.objects.first()
    public = first.rows.get(category="RETAIL", applicant_ref=str(investors[0].pk))
    assert (
        client.post(
            reverse("application-start-tracking", args=[workspace.pk, first.pk]),
            {"row_ids": [str(public.pk)], "record_only": True},
            format="json",
        ).status_code
        == 201
    )
    item = Application.objects.get()
    upi = UPIHandle.objects.get(bank__owner=investors[1])
    edited = client.post(
        reverse("application-action", args=[workspace.pk, item.pk, "edit"]),
        {
            "category": "SHNI",
            "lots": 14,
            "bank": str(upi.bank_id),
            "upi": str(upi.pk),
            "record_only": True,
        },
        format="json",
    )
    assert edited.status_code == 200
    rows = [
        row | {"lots": 2, "amount": "30000.00"} if row["category"] == "SHARE" else row
        for row in rows
    ]
    assert client.post(save_url, {"rows": rows}, format="json").status_code == 201
    capital = client.get(reverse("workspace-capital", args=[workspace.pk])).data
    assert capital["planned"] == "255000.00"  # Edited sHNI + other Retail + latest shareholder.
    assert capital["available"] == "945000.00"
    assert capital["by_bank"][str(upi.bank_id)]["planned"] == "225000.00"
    item.refresh_from_db()
    assert item.bank_id == upi.bank_id and item.lots == 14 and item.category == "SHNI"
