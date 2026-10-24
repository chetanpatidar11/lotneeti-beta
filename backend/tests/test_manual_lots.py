from dataclasses import replace
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_preview_api import setup_workspace
from test_planner_validate_api import edited_row

from applications.models import Application
from funding.models import BankAccount
from planner.audit import audit_plan
from planner.coverage import baseline_retail_coverage
from planner.dto import BankInput
from planner.locks import locked_coverage
from planner.models import PlanRun
from planner.repair import _rows_feasible
from planner.upgrades import upgrade_retail_to_shni
from planner.wallets import choose_retail_wallet


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_manual_retail_lots_validate_lock_replan_save_track_and_edit():
    owner, workspace, investor, ipo, _ = setup_workspace()
    client = APIClient()
    client.force_authenticate(owner)
    preview_url = reverse("planner-preview", args=[workspace.pk])
    assert client.post(preview_url, {}, format="json").data["rows"][0]["lots"] == 1
    row = edited_row(investor, ipo) | {"lots": 3, "locked": True}
    validated = client.post(
        reverse("planner-validate", args=[workspace.pk]), {"rows": [row]}, format="json"
    )
    assert validated.status_code == 200
    assert validated.data["status"] == "READY"
    assert validated.data["rows"][0]["amount"] == "45000.00"
    replanned = client.post(
        preview_url, {"locked_rows": [row | {"amount": "45000.00"}]}, format="json"
    )
    assert replanned.status_code == 200
    assert replanned.data["status"] == "READY"
    assert len(replanned.data["rows"]) == 1
    assert replanned.data["rows"][0]["lots"] == 3
    assert replanned.data["rows"][0]["amount"] == "45000.00"
    saved = client.post(
        reverse("planner-run-create", args=[workspace.pk]), {"rows": [row]}, format="json"
    )
    assert saved.status_code == 201
    run = PlanRun.objects.get()
    assert run.rows.get().lots == 3
    assert (
        client.post(
            reverse("application-start-tracking", args=[workspace.pk, run.pk]), {}
        ).status_code
        == 201
    )
    application = Application.objects.get()
    assert application.amount == Decimal("45000.00")
    assert (
        client.post(
            reverse("application-action", args=[workspace.pk, application.pk, "submit"]), {}
        ).status_code
        == 200
    )
    edit_url = reverse("application-action", args=[workspace.pk, application.pk, "edit"])
    payload = {
        "category": "RETAIL",
        "bank": str(application.bank_id),
        "upi": str(application.upi_id),
    }
    changed = client.post(edit_url, payload | {"lots": 2}, format="json")
    assert changed.status_code == 200
    assert changed.data["amount"] == "30000.00"
    assert changed.data["lots"] == 2
    assert changed.data["status"] == "SUBMITTED"
    failed = client.post(edit_url, payload | {"lots": 4}, format="json")
    assert failed.status_code == 409
    assert "Balance" in str(failed.data)
    application.refresh_from_db()
    assert application.lots == 2
    assert application.bank.current_balance == Decimal("50000.00")


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
@pytest.mark.parametrize(
    "lots,category,ready",
    [(20, "RETAIL", True), (21, "RETAIL", False), (20, "SHNI", False), (21, "SHNI", True)],
)
def test_manual_category_amount_boundaries(lots, category, ready):
    owner, workspace, investor, ipo, _ = setup_workspace()
    ipo.lot_size = 100
    ipo.save()
    BankAccount.objects.filter(workspace=workspace).update(current_balance=Decimal("500000.00"))
    client = APIClient()
    client.force_authenticate(owner)
    row = edited_row(investor, ipo) | {"lots": lots, "category": category}
    result = client.post(
        reverse("planner-validate", args=[workspace.pk]), {"rows": [row]}, format="json"
    )
    assert result.status_code == 200
    assert (result.data["status"] == "READY") is ready
    assert ("INVALID_CATEGORY" not in result.data["rows"][0]["blocking_reasons"]) is ready


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
@pytest.mark.parametrize("lots", [0, -1, 1.5, ""])
def test_manual_lots_require_a_positive_whole_number(lots):
    owner, workspace, investor, ipo, _ = setup_workspace()
    client = APIClient()
    client.force_authenticate(owner)
    result = client.post(
        reverse("planner-validate", args=[workspace.pk]),
        {"rows": [edited_row(investor, ipo) | {"lots": lots}]},
        format="json",
    )
    assert result.status_code == 400


def test_manual_multilot_locks_pass_audit_and_repair_without_automatic_upgrade():
    from test_planner_locks import locked, snapshot

    data = snapshot(locked_rows=(locked(lots=2, amount=Decimal("30000.00")),))
    initial = locked_coverage(data)
    assert initial.rows[0].blocking_reasons == ()
    assert audit_plan(data, initial.rows, reported_planned_total=Decimal("30000.00")).issues == ()
    assert _rows_feasible(data, initial.rows)
    baseline = baseline_retail_coverage(data, choose_retail_wallet, initial.rows)
    assert upgrade_retail_to_shni(data, baseline).rows == initial.rows
    large = replace(
        data,
        banks=(BankInput("bank-1", "wife", Decimal("500000"), True, "DEFAULT"),),
        locked_rows=(locked(lots=14, amount=Decimal("210000")),),
    )
    rejected = locked_coverage(large)
    assert "INVALID_CATEGORY" in rejected.rows[0].blocking_reasons
    assert not _rows_feasible(large, rejected.rows)
