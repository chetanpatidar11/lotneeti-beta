"""Exercise the public workspace APIs with a realistic-sized synthetic portfolio."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_preview_api import setup_workspace

from funding.models import BalanceChange, BankAccount, UPIHandle
from investors.models import DematAccount, Investor
from ipos.models import IPO


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_ten_synthetic_accounts_and_issues_cover_workspace_data_surfaces():
    owner, workspace, _, selected_ipo, _ = setup_workspace()
    for index in range(2, 11):
        investor = Investor(
            workspace=workspace,
            name=f"Synthetic Investor {index:02d}",
            planning_priority=index,
        )
        investor.set_pan(f"TESTX{index:04d}A")
        investor.save()
        demat = DematAccount(
            investor=investor,
            depository="CDSL" if index % 2 else "NSDL",
        )
        demat.set_dp_id(f"DEMO-DP-{index:04d}")
        demat.set_client_id(f"DEMO-CLIENT-{index:04d}")
        demat.save()
        bank = BankAccount(
            workspace=workspace,
            owner=investor,
            bank_name=f"Synthetic Bank {index:02d}",
            current_balance=Decimal("50000.00"),
        )
        bank.set_account_number(f"DEMO-ACCOUNT-{index:04d}")
        bank.save()
        upi = UPIHandle(bank=bank, holder=investor, verified=True)
        upi.set_handle(f"synthetic{index:02d}@upi.test")
        upi.save()
        BalanceChange.objects.create(
            bank=bank,
            operation=BalanceChange.Operation.SET,
            old_balance=0,
            delta=Decimal("50000.00"),
            new_balance=Decimal("50000.00"),
            actor=owner,
            note="Synthetic opening balance",
        )

    client = APIClient()
    client.force_authenticate(owner)
    investors = client.get(reverse("investor-list", args=[workspace.pk]))
    banks = client.get(reverse("bank-list", args=[workspace.pk]))
    assert investors.status_code == banks.status_code == 200
    assert len(investors.data) == len(banks.data) == 10
    assert all("TESTX" not in str(row) for row in investors.data)
    assert all("DEMO-ACCOUNT" not in str(row) for row in banks.data)

    preview = client.post(reverse("planner-preview", args=[workspace.pk]), {}, format="json")
    assert preview.status_code == 200
    assert preview.data["status"] == "READY"
    assert len(preview.data["rows"]) == 10
    assert {row["ipo"] for row in preview.data["rows"]} == {str(selected_ipo.pk)}
    assert client.get(reverse("workspace-capital", args=[workspace.pk])).status_code == 200

    for index in range(2, 11):
        IPO.objects.create(
            issuer_name=f"Synthetic Issue {index:02d}",
            issue_type="MAINBOARD" if index % 2 else "SME",
            lower_price=Decimal("100.00"),
            upper_price=Decimal("100.00"),
            lot_size=100,
            open_date=date(2030, 10, 1) + timedelta(days=index),
            close_date=date(2030, 10, 4) + timedelta(days=index),
            allotment_date=date(2030, 10, 9) + timedelta(days=index),
            status="UPCOMING" if index % 2 else "CLOSED",
            publication_state="PUBLISHED",
            source_key="manual",
            source_record_id=f"synthetic-smoke-{index}",
        )
    issues = client.get(reverse("ipo-list"))
    assert issues.status_code == 200
    assert len(issues.data) == 10
    assert client.get(reverse("application-list", args=[workspace.pk])).status_code == 200
    assert client.get(reverse("profit-report", args=[workspace.pk])).status_code == 200
