from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from test_plan_export_api import FakeStorage
from test_planner_preview_api import setup_workspace

from applications.models import Application
from core.models import BetaEvent
from funding.models import BankAccount, UPIHandle


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_m05_ipo_to_locked_export_block_partial_allotment_sale_and_profit(monkeypatch):
    owner, workspace, investor, ipo, decision = setup_workspace()
    decision.decision = "DEFAULT"
    decision.save(update_fields=["decision", "updated_at"])
    client = APIClient()
    client.force_authenticate(owner)
    decision_url = reverse("workspace-ipo-decision-detail", args=[workspace.pk, ipo.pk])
    selected = client.patch(decision_url, {"decision": "APPLY"}, format="json")
    assert selected.status_code == 200
    assert selected.data["selected"] is True

    preview = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json")
    assert preview.status_code == 200
    assert preview.data["status"] == "READY"
    assert len(preview.data["rows"]) == 1
    proposed = preview.data["rows"][0]
    assert proposed["applicant"] == str(investor.pk)

    alternate = BankAccount(
        workspace=workspace,
        owner=investor,
        bank_name="Alternate Synthetic Bank",
        current_balance=Decimal("50000.00"),
    )
    alternate.set_account_number("DEMO-ACCOUNT-ALT1")
    alternate.save()
    alternate_upi = UPIHandle(bank=alternate, holder=investor, verified=True)
    alternate_upi.set_handle("alternate@upi.test")
    alternate_upi.save()
    edited = proposed | {"bank": str(alternate.pk), "upi": str(alternate_upi.pk), "locked": True}
    validated = client.post(
        reverse("planner-validate", args=[workspace.pk]),
        {"rows": [edited]},
        format="json",
    )
    assert validated.status_code == 200
    assert validated.data["status"] == "READY"
    reviewed = validated.data["rows"][0]
    assert reviewed["bank"] == str(alternate.pk) and reviewed["locked"] is True
    assert reviewed["amount"] == "15000.00"
    storage = FakeStorage()
    monkeypatch.setattr("exports.views.get_export_storage", lambda: storage)
    saved = client.post(
        reverse("planner-run-create", args=[workspace.pk]),
        {"rows": [reviewed]},
        format="json",
    )
    assert saved.status_code == 201 and saved.data["status"] == "READY"
    run_id = saved.data["id"]
    exported = client.post(reverse("plan-export-create", args=[workspace.pk, run_id]), {})
    assert exported.status_code == 201
    exported_csv = next(iter(storage.objects.values()))
    assert b"DEMO-ACCOUNT-ALT1" in exported_csv
    assert b"TESTX0001A" in exported_csv

    tracked = client.post(reverse("application-start-tracking", args=[workspace.pk, run_id]), {})
    assert tracked.status_code == 201 and len(tracked.data) == 1
    application = Application.objects.get(pk=tracked.data[0]["id"])
    for action in ("submit", "block"):
        transition = client.post(
            reverse("application-action", args=[workspace.pk, application.pk, action]), {}
        )
        assert transition.status_code == 200
    blocked = client.get(reverse("workspace-capital", args=[workspace.pk])).data
    assert blocked["blocked"] == "15000.00"
    assert blocked["balance"] == "100000.00"
    allotted = client.post(
        reverse("application-action", args=[workspace.pk, application.pk, "allotted"]),
        {"quantity": 50, "actual_cost": "5000.00"},
        format="json",
    )
    assert allotted.status_code == 200
    assert client.get(reverse("workspace-capital", args=[workspace.pk])).data["blocked"] == "0.00"
    assert BankAccount.objects.get(pk=alternate.pk).current_balance == Decimal("45000.00")

    sold = client.post(
        reverse("sale-list", args=[workspace.pk]),
        {
            "application": str(application.pk),
            "quantity": 50,
            "price_per_share": "120.00",
            "sold_on": "2030-10-20",
            "charges": "50.00",
        },
        format="json",
    )
    assert sold.status_code == 201
    assert sold.data["gross_proceeds"] == "6000.00"
    assert sold.data["ipo_cost"] == "5000.00"
    assert sold.data["realized_profit"] == "950.00"
    assert sold.data["roi_percent"] == "19.00"
    summary = client.get(reverse("profit-report", args=[workspace.pk])).data
    assert summary["workspace"]["realized_profit"] == "950.00"
    assert summary["by_ipo"][0]["name"] == ipo.issuer_name
    assert summary["by_investor"][0]["name"] == investor.name
    events = list(
        BetaEvent.objects.filter(workspace=workspace).values_list("event_type", flat=True)
    )
    assert events.count(BetaEvent.Type.PLAN_GENERATED) == 1
    assert events.count(BetaEvent.Type.PLAN_EDITED) == 1
    assert events.count(BetaEvent.Type.EXPORT_GENERATED) == 1
    assert events.count(BetaEvent.Type.ALLOTMENT_RECORDED) == 1
    assert events.count(BetaEvent.Type.PNL_COMPLETED) == 1
    assert not any(hasattr(event, "metadata") for event in BetaEvent.objects.all())
