from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from test_plan_export_api import FakeStorage
from test_planner_preview_api import setup_workspace

from funding.models import BankAccount, UPIHandle
from investors.models import DematAccount, Investor
from planner.models import PlanRun


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_ee006_two_edited_locked_rows_export_the_exact_reviewed_mappings(monkeypatch):
    owner, workspace, first, ipo, _ = setup_workspace()
    first_demat = DematAccount.objects.get(investor=first)
    alternate = BankAccount(
        workspace=workspace,
        owner=first,
        bank_name="Alternate Synthetic Bank",
        current_balance=Decimal("25000.00"),
    )
    alternate.set_account_number("DEMO-ACCOUNT-ALT1")
    alternate.save()
    alternate_upi = UPIHandle(bank=alternate, holder=first, verified=True)
    alternate_upi.set_handle("alternate@upi.test")
    alternate_upi.save()
    second = Investor(workspace=workspace, name="Second Synthetic")
    second.set_pan("TESTX0002B")
    second.save()
    second_demat = DematAccount(investor=second, depository="NSDL")
    second_demat.set_dp_id("DEMO-DP-002")
    second_demat.set_client_id("DEMO-CLIENT-002")
    second_demat.save()
    second_bank = BankAccount(
        workspace=workspace,
        owner=second,
        bank_name="Second Synthetic Bank",
        current_balance=Decimal("230000.00"),
    )
    second_bank.set_account_number("DEMO-ACCOUNT-0002")
    second_bank.save()
    second_upi = UPIHandle(bank=second_bank, holder=second, verified=True)
    second_upi.set_handle("second@upi.test")
    second_upi.save()
    rows = [
        {
            "ipo": str(ipo.pk),
            "applicant": str(first.pk),
            "category": "RETAIL",
            "lots": 1,
            "demat": str(first_demat.pk),
            "bank": str(alternate.pk),
            "upi": str(alternate_upi.pk),
            "locked": True,
        },
        {
            "ipo": str(ipo.pk),
            "applicant": str(second.pk),
            "category": "SHNI",
            "lots": 14,
            "demat": str(second_demat.pk),
            "bank": str(second_bank.pk),
            "upi": str(second_upi.pk),
            "locked": True,
        },
    ]
    client = APIClient()
    client.force_authenticate(owner)
    validated = client.post(
        reverse("planner-validate", args=[workspace.pk]), {"rows": rows}, format="json"
    )
    assert validated.status_code == 200
    assert validated.data["status"] == "READY"
    storage = FakeStorage()
    monkeypatch.setattr("exports.views.get_export_storage", lambda: storage)
    saved = client.post(
        reverse("planner-run-create", args=[workspace.pk]),
        {"rows": validated.data["rows"]},
        format="json",
    )
    assert saved.status_code == 201
    assert saved.data["status"] == "READY"
    run = PlanRun.objects.get(pk=saved.data["id"])
    assert {
        (row.applicant_ref, row.category, row.bank_ref, row.amount) for row in run.rows.all()
    } == {
        (str(first.pk), "RETAIL", str(alternate.pk), Decimal("15000.00")),
        (str(second.pk), "SHNI", str(second_bank.pk), Decimal("210000.00")),
    }
    assert all(row.locked for row in run.rows.all())
    exported = client.post(reverse("plan-export-create", args=[workspace.pk, run.pk]), {})
    assert exported.status_code == 201
    data = next(iter(storage.objects.values())).decode()
    assert "TESTX0001A" in data and "TESTX0002B" in data
    assert "DEMO-ACCOUNT-ALT1" in data and "DEMO-ACCOUNT-0002" in data
    assert "210000.00" in data and "15000.00" in data
