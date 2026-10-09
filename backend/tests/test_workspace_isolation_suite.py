from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User
from accounts.services import create_workspace
from applications.models import Application
from funding.models import BankAccount, RecurringDebit, UPIHandle
from investors.models import DematAccount, Investor
from planner.persistence import create_plan_run


def _account_tree(workspace, suffix):
    investor = Investor(workspace=workspace, name=f"Synthetic {suffix}")
    investor.set_pan(f"TESTX000{suffix}A")
    investor.save()
    demat = DematAccount(investor=investor, depository="CDSL")
    demat.set_dp_id(f"DP-{suffix}")
    demat.set_client_id(f"CLIENT-{suffix}")
    demat.save()
    bank = BankAccount(workspace=workspace, owner=investor, bank_name=f"Bank {suffix}")
    bank.set_account_number(f"DEMO-ACCOUNT-{suffix}")
    bank.save()
    upi = UPIHandle(bank=bank, holder=investor)
    upi.set_handle(f"synthetic{suffix}@upi.test")
    upi.save()
    recurring = RecurringDebit.objects.create(
        bank=bank,
        name="Scheduled payment",
        amount=Decimal("100.00"),
        frequency="MONTHLY",
        start_date=date(2030, 1, 1),
        next_due_date=date(2030, 1, 1),
    )
    return investor, demat, bank, upi, recurring


@pytest.mark.django_db
def test_member_of_two_workspaces_cannot_substitute_nested_resource_ids():
    owner = User.objects.create_user(email="scope-owner@example.test")
    first = create_workspace(name="First", owner=owner)
    second = create_workspace(name="Second", owner=owner)
    first_investor, _, first_bank, _, _ = _account_tree(first, "1")
    second_investor, second_demat, second_bank, second_upi, second_recurring = _account_tree(
        second, "2"
    )
    client = APIClient()
    client.force_authenticate(owner)
    blocked_paths = (
        reverse("investor-detail", args=[first.pk, second_investor.pk]),
        reverse("demat-detail", args=[first.pk, first_investor.pk, second_demat.pk]),
        reverse("bank-detail", args=[first.pk, second_bank.pk]),
        reverse("upi-detail", args=[first.pk, first_bank.pk, second_upi.pk]),
        reverse("recurring-debit-detail", args=[first.pk, first_bank.pk, second_recurring.pk]),
        reverse("bank-balance-history", args=[first.pk, second_bank.pk]),
    )
    for path in blocked_paths:
        assert client.get(path).status_code == 404, path
    for path in blocked_paths[:5]:
        assert client.patch(path, {"active": False}, format="json").status_code == 404, path
    assert (
        client.post(
            reverse("bank-add-money", args=[first.pk, second_bank.pk]),
            {"amount": "100.00"},
            format="json",
        ).status_code
        == 404
    )
    assert (
        client.post(
            reverse("funding-preference-list", args=[first.pk, first_investor.pk]),
            {"bank": str(second_bank.pk), "priority": 1},
            format="json",
        ).status_code
        == 400
    )
    second_investor.refresh_from_db()
    second_bank.refresh_from_db()
    assert second_investor.active is True
    assert second_bank.active is True
    assert second_bank.current_balance == Decimal("0.00")


@pytest.mark.django_db
def test_planner_application_export_and_sale_ids_cannot_cross_workspace_path():
    owner, second, snapshot = setup_plan()
    first = create_workspace(name="Other owned workspace", owner=owner)
    run = create_plan_run(workspace=second, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    assert (
        client.post(
            reverse("application-start-tracking", args=[first.pk, run.pk]), {}, format="json"
        ).status_code
        == 404
    )
    assert (
        client.post(
            reverse("plan-export-create", args=[first.pk, run.pk]), {}, format="json"
        ).status_code
        == 404
    )
    client.post(reverse("application-start-tracking", args=[second.pk, run.pk]), {})
    application = Application.objects.get(workspace=second)
    assert (
        client.post(
            reverse("application-action", args=[first.pk, application.pk, "submit"]),
            {},
            format="json",
        ).status_code
        == 404
    )
    assert (
        client.post(
            reverse("sale-list", args=[first.pk]),
            {
                "application": str(application.pk),
                "quantity": 1,
                "price_per_share": "100.00",
                "sold_on": "2030-10-10",
            },
            format="json",
        ).status_code
        == 404
    )
    application.refresh_from_db()
    assert application.status == Application.Status.PLANNED
