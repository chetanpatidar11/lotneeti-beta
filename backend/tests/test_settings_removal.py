from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from applications.models import Application
from core.models import AuditEvent
from funding.models import (
    ArchivedBalanceChange,
    BalanceChange,
    BankAccount,
    RecurringDebit,
    UPIHandle,
)
from investors.models import DematAccount, Investor
from planner.models import PlanRun
from planner.persistence import create_plan_run


def create_investor(workspace, name, pan):
    investor = Investor(workspace=workspace, name=name)
    investor.set_pan(pan)
    investor.save()
    return investor


def create_bank(workspace, investor, number, balance=Decimal("0.00")):
    bank = BankAccount(
        workspace=workspace,
        owner=investor,
        bank_name="Synthetic Bank",
        current_balance=balance,
    )
    bank.set_account_number(number)
    bank.save()
    return bank


def selection_url(workspace):
    return reverse("settings-items", args=[workspace.pk])


@pytest.mark.django_db
def test_bulk_investor_removal_archives_linked_accounts_and_can_be_restored():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Synthetic", owner=owner)
    first = create_investor(workspace, "First", "TESTX0001A")
    second = create_investor(workspace, "Second", "TESTX0002B")
    demat = DematAccount(investor=first, depository="CDSL")
    demat.set_dp_id("DEMO-DP-0001")
    demat.set_client_id("DEMO-CLIENT-0001")
    demat.save()
    bank = create_bank(workspace, first, "DEMO-ACCOUNT-0001")
    upi = UPIHandle(bank=bank, holder=first)
    upi.set_handle("synthetic@upi.test")
    upi.save()
    BalanceChange.objects.create(
        bank=bank,
        operation=BalanceChange.Operation.SET,
        old_balance=0,
        delta=0,
        new_balance=0,
        actor=owner,
    )
    client = APIClient()
    client.force_authenticate(owner)
    url = selection_url(workspace)

    removed = client.post(
        url,
        {"kind": "investor", "action": "remove", "ids": [str(first.pk), str(second.pk)]},
        format="json",
    )
    assert removed.status_code == 200
    assert removed.data["updated"] == 2
    for item in (first, second, demat, bank, upi):
        item.refresh_from_db()
        assert item.active is False
    assert BalanceChange.objects.filter(bank=bank).count() == 1
    assert AuditEvent.objects.filter(action="investor.removed", workspace=workspace).count() == 2
    for action in ("demat.removed", "bank.removed", "upi.removed"):
        assert AuditEvent.objects.filter(action=action, workspace=workspace).count() == 1

    assert (
        client.post(
            url, {"kind": "bank", "action": "restore", "ids": [str(bank.pk)]}, format="json"
        ).status_code
        == 400
    )
    restored = client.post(
        url,
        {"kind": "investor", "action": "restore", "ids": [str(first.pk)]},
        format="json",
    )
    assert restored.status_code == 200
    first.refresh_from_db()
    assert first.active is True
    bank.refresh_from_db()
    assert bank.active is False  # Child choices stay removed until explicitly restored.
    for kind, identifier in (("bank", bank.pk), ("demat", demat.pk), ("upi", upi.pk)):
        response = client.post(
            url, {"kind": kind, "action": "restore", "ids": [str(identifier)]}, format="json"
        )
        assert response.status_code == 200
    assert BankAccount.objects.get(pk=bank.pk).active is True
    assert DematAccount.objects.get(pk=demat.pk).active is True
    assert UPIHandle.objects.get(pk=upi.pk).active is True


@pytest.mark.django_db
def test_settings_deactivate_activate_and_permanent_delete_are_distinct():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Synthetic", owner=owner)
    investor = create_investor(workspace, "First", "TESTX0001A")
    demat = DematAccount(investor=investor, depository="CDSL")
    demat.set_dp_id("")
    demat.set_client_id("DEMO-CLIENT-0001")
    demat.save()
    bank = create_bank(workspace, investor, "DEMO-ACCOUNT-0001")
    BalanceChange.objects.create(
        bank=bank,
        operation=BalanceChange.Operation.SET,
        old_balance=0,
        delta=0,
        new_balance=0,
        actor=owner,
        note="Opening balance",
    )
    upi = UPIHandle(bank=bank, holder=investor)
    upi.set_handle("synthetic@upi.test")
    upi.save()
    client = APIClient()
    client.force_authenticate(owner)
    url = selection_url(workspace)
    for action, active in (("deactivate", False), ("activate", True)):
        response = client.post(
            url, {"kind": "investor", "action": action, "ids": [str(investor.pk)]}, format="json"
        )
        assert response.status_code == 200
        investor.refresh_from_db()
        assert investor.active is active
    deleted = client.post(
        url, {"kind": "investor", "action": "delete", "ids": [str(investor.pk)]}, format="json"
    )
    assert deleted.status_code == 200
    assert not Investor.objects.filter(pk=investor.pk).exists()
    assert not DematAccount.objects.filter(pk=demat.pk).exists()
    assert not BankAccount.objects.filter(pk=bank.pk).exists()
    assert not UPIHandle.objects.filter(pk=upi.pk).exists()
    assert not BalanceChange.objects.filter(bank_id=bank.pk).exists()
    assert AuditEvent.objects.filter(action="investor.deleted", workspace=workspace).exists()


@pytest.mark.django_db
def test_permanent_bank_delete_keeps_balance_history_and_is_workspace_scoped():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Synthetic", owner=owner)
    investor = create_investor(workspace, "First", "TESTX0001A")
    first = create_bank(workspace, investor, "DEMO-ACCOUNT-0001")
    second = create_bank(workspace, investor, "DEMO-ACCOUNT-0002")
    BalanceChange.objects.create(
        bank=second,
        operation=BalanceChange.Operation.ADD,
        old_balance=0,
        delta=10,
        new_balance=10,
        actor=owner,
    )
    BalanceChange.objects.create(
        bank=second,
        operation=BalanceChange.Operation.REMOVE,
        old_balance=10,
        delta=-10,
        new_balance=0,
        actor=owner,
    )
    client = APIClient()
    client.force_authenticate(owner)
    response = client.post(
        selection_url(workspace),
        {
            "kind": "bank",
            "action": "delete",
            "ids": [str(first.pk), str(second.pk)],
        },
        format="json",
    )
    assert response.status_code == 200
    assert BankAccount.objects.filter(pk__in=[first.pk, second.pk]).count() == 0
    assert BalanceChange.objects.filter(bank_id=second.pk).count() == 0
    assert (
        ArchivedBalanceChange.objects.filter(workspace=workspace, bank_ref=second.pk).count() == 2
    )
    history = client.get(reverse("bank-balance-history", args=[workspace.pk, second.pk]))
    assert history.status_code == 200
    assert [row["operation"] for row in history.data] == ["REMOVE", "ADD"]
    archive = client.get(reverse("archived-bank-history-list", args=[workspace.pk]))
    assert archive.status_code == 200
    assert archive.data[0]["account_masked"] == "••••0002"
    outsider = User.objects.create_user(email="outsider@example.test")
    client.force_authenticate(outsider)
    assert (
        client.get(reverse("bank-balance-history", args=[workspace.pk, second.pk])).status_code
        == 403
    )


@pytest.mark.django_db
def test_bank_with_recorded_nonzero_balance_can_be_deleted_without_losing_history():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Synthetic", owner=owner)
    investor = create_investor(workspace, "First", "TESTX0001A")
    bank = create_bank(workspace, investor, "DEMO-ACCOUNT-0003", Decimal("250.00"))
    BalanceChange.objects.create(
        bank=bank,
        operation=BalanceChange.Operation.SET,
        old_balance=0,
        delta=250,
        new_balance=250,
        actor=owner,
        note="Opening balance",
    )
    client = APIClient()
    client.force_authenticate(owner)
    deleted = client.post(
        selection_url(workspace),
        {"kind": "bank", "action": "delete", "ids": [str(bank.pk)]},
        format="json",
    )
    assert deleted.status_code == 200
    assert not BankAccount.objects.filter(pk=bank.pk).exists()
    history = client.get(reverse("bank-balance-history", args=[workspace.pk, bank.pk]))
    assert history.data[0]["balance"] == "250.00"


@pytest.mark.django_db
def test_deleting_investor_archives_linked_bank_history():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Synthetic", owner=owner)
    investor = create_investor(workspace, "First", "TESTX0001A")
    bank = create_bank(workspace, investor, "DEMO-ACCOUNT-0004", Decimal("500.00"))
    BalanceChange.objects.create(
        bank=bank,
        operation=BalanceChange.Operation.ADD,
        old_balance=0,
        delta=500,
        new_balance=500,
        actor=owner,
    )
    client = APIClient()
    client.force_authenticate(owner)
    response = client.post(
        selection_url(workspace),
        {"kind": "investor", "action": "delete", "ids": [str(investor.pk)]},
        format="json",
    )
    assert response.status_code == 200
    assert not Investor.objects.filter(pk=investor.pk).exists()
    assert not BankAccount.objects.filter(pk=bank.pk).exists()
    history = client.get(reverse("bank-balance-history", args=[workspace.pk, bank.pk]))
    assert history.status_code == 200
    assert history.data[0]["balance"] == "500.00"


@pytest.mark.django_db
def test_deleting_investor_keeps_saved_plan_snapshot():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    investor_id = snapshot.applicants[0].id
    bank_id = snapshot.banks[0].id
    BalanceChange.objects.create(
        bank_id=bank_id,
        operation=BalanceChange.Operation.SET,
        old_balance=0,
        delta=50000,
        new_balance=50000,
        actor=owner,
    )
    client = APIClient()
    client.force_authenticate(owner)
    response = client.post(
        selection_url(workspace),
        {"kind": "investor", "action": "delete", "ids": [investor_id]},
        format="json",
    )
    assert response.status_code == 200
    assert not Investor.objects.filter(pk=investor_id).exists()
    assert PlanRun.objects.filter(pk=run.pk).exists()
    assert run.rows.filter(applicant_ref=investor_id, bank_ref=bank_id).exists()
    assert ArchivedBalanceChange.objects.filter(bank_ref=bank_id).exists()


@pytest.mark.django_db
def test_bank_bulk_removal_is_atomic_when_balance_or_payment_is_active():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Synthetic", owner=owner)
    investor = create_investor(workspace, "First", "TESTX0001A")
    first = create_bank(workspace, investor, "DEMO-ACCOUNT-0001")
    second = create_bank(workspace, investor, "DEMO-ACCOUNT-0002", Decimal("100.00"))
    client = APIClient()
    client.force_authenticate(owner)
    url = selection_url(workspace)
    payload = {"kind": "bank", "action": "remove", "ids": [str(first.pk), str(second.pk)]}

    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert BankAccount.objects.filter(pk__in=[first.pk, second.pk], active=True).count() == 2

    second.current_balance = Decimal("0.00")
    second.save(update_fields=["current_balance"])
    schedule = RecurringDebit.objects.create(
        bank=second,
        name="Synthetic payment",
        amount=Decimal("50.00"),
        frequency=RecurringDebit.Frequency.MONTHLY,
        start_date="2026-10-01",
        next_due_date="2026-10-01",
    )
    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert BankAccount.objects.filter(pk__in=[first.pk, second.pk], active=True).count() == 2

    schedule.active = False
    schedule.save(update_fields=["active"])
    response = client.post(url, payload, format="json")
    assert response.status_code == 200
    assert response.data["updated"] == 2
    assert BankAccount.objects.filter(pk__in=[first.pk, second.pk], active=False).count() == 2


@pytest.mark.django_db
def test_open_application_prevents_removal_of_its_investor_and_accounts():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    assert (
        client.post(
            reverse("application-start-tracking", args=[workspace.pk, run.pk]), {}
        ).status_code
        == 201
    )
    application = Application.objects.get()
    url = selection_url(workspace)
    BankAccount.objects.filter(pk=application.bank_id).update(current_balance=0)

    for kind, identifier in (
        ("investor", application.applicant_id),
        ("demat", application.demat_id),
        ("bank", application.bank_id),
        ("upi", application.upi_id),
    ):
        response = client.post(
            url, {"kind": kind, "action": "remove", "ids": [str(identifier)]}, format="json"
        )
        assert response.status_code == 400
        assert "open applications" in str(response.data)
    deleted_bank = client.post(
        url,
        {"kind": "bank", "action": "delete", "ids": [str(application.bank_id)]},
        format="json",
    )
    assert deleted_bank.status_code == 400
    assert BankAccount.objects.filter(pk=application.bank_id).exists()


@pytest.mark.django_db
def test_removal_is_workspace_scoped_and_viewers_cannot_remove():
    owner = User.objects.create_user(email="owner@example.test")
    viewer = User.objects.create_user(email="viewer@example.test")
    outsider = User.objects.create_user(email="outsider@example.test")
    first = create_workspace(name="First", owner=owner)
    second = create_workspace(name="Second", owner=owner)
    WorkspaceMembership.objects.create(
        workspace=first, user=viewer, role=WorkspaceMembership.Role.VIEWER
    )
    own = create_investor(first, "Own", "TESTX0001A")
    foreign = create_investor(second, "Other", "TESTX0002B")
    url = selection_url(first)
    payload = {"kind": "investor", "action": "remove", "ids": [str(own.pk)]}
    client = APIClient()

    client.force_authenticate(viewer)
    assert client.post(url, payload, format="json").status_code == 403
    client.force_authenticate(outsider)
    assert client.post(url, payload, format="json").status_code == 403
    client.force_authenticate(owner)
    response = client.post(
        url,
        {"kind": "investor", "action": "remove", "ids": [str(own.pk), str(foreign.pk)]},
        format="json",
    )
    assert response.status_code == 404
    own.refresh_from_db()
    foreign.refresh_from_db()
    assert own.active is True and foreign.active is True
    assert (
        client.post(
            url, {"kind": "investor", "action": "remove", "ids": []}, format="json"
        ).status_code
        == 400
    )
