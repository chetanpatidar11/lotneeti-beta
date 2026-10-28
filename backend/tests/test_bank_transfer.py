from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from core.models import AuditEvent
from funding.models import ArchivedBalanceChange, BalanceChange, BankAccount
from funding.services import transfer_money
from investors.models import Investor
from investors.settings_views import _archive_bank_balance_history


def make_bank(workspace, investor, suffix, balance="0.00", active=True):
    bank = BankAccount(
        workspace=workspace,
        owner=investor,
        bank_name=f"Synthetic Bank {suffix}",
        current_balance=Decimal(balance),
        active=active,
    )
    bank.set_account_number(f"SYNTHETIC-ACCOUNT-{suffix}")
    bank.save()
    return bank


def setup_transfer():
    owner = User.objects.create_user(email="transfer-owner@example.test")
    workspace = create_workspace(name="Synthetic transfer workspace", owner=owner)
    investor = Investor(workspace=workspace, name="Synthetic Investor")
    investor.set_pan("TESTX0001A")
    investor.save()
    source = make_bank(workspace, investor, "001", "500.00")
    destination = make_bank(workspace, investor, "002", "100.00")
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("bank-transfer", args=[workspace.pk])
    return owner, workspace, investor, source, destination, client, url


@pytest.mark.django_db
def test_transfer_updates_both_balances_and_records_matching_statement_entries():
    owner, workspace, _, source, destination, client, url = setup_transfer()

    response = client.post(
        url,
        {
            "source_bank": str(source.pk),
            "destination_bank": str(destination.pk),
            "amount": "175.25",
            "note": "Moved to second account",
        },
    )

    assert response.status_code == 201
    assert response.data["source_balance"] == "324.75"
    assert response.data["destination_balance"] == "275.25"
    source.refresh_from_db()
    destination.refresh_from_db()
    assert source.current_balance == Decimal("324.75")
    assert destination.current_balance == Decimal("275.25")
    changes = list(BalanceChange.objects.filter(transfer_id=response.data["transfer_id"]))
    assert len(changes) == 2
    outgoing = next(change for change in changes if change.bank_id == source.pk)
    incoming = next(change for change in changes if change.bank_id == destination.pk)
    assert (outgoing.operation, outgoing.old_balance, outgoing.delta, outgoing.new_balance) == (
        BalanceChange.Operation.TRANSFER_OUT,
        Decimal("500.00"),
        Decimal("-175.25"),
        Decimal("324.75"),
    )
    assert (incoming.operation, incoming.old_balance, incoming.delta, incoming.new_balance) == (
        BalanceChange.Operation.TRANSFER_IN,
        Decimal("100.00"),
        Decimal("175.25"),
        Decimal("275.25"),
    )
    assert all(
        change.note == "Moved to second account" and change.actor == owner for change in changes
    )
    assert destination.bank_name in outgoing.counterparty_label
    assert source.bank_name in incoming.counterparty_label
    assert (
        AuditEvent.objects.filter(
            action__startswith="balance.transferred", workspace=workspace
        ).count()
        == 2
    )

    statement = client.get(reverse("workspace-balance-statement", args=[workspace.pk]))
    assert statement.status_code == 200
    assert statement.data["total"] == 2
    assert {row["operation"] for row in statement.data["results"]} == {
        "TRANSFER_OUT",
        "TRANSFER_IN",
    }
    assert {row["transfer_id"] for row in statement.data["results"]} == {
        response.data["transfer_id"]
    }


@pytest.mark.django_db
def test_transfer_rejects_invalid_accounts_and_amount_without_partial_change():
    owner, workspace, investor, source, destination, client, url = setup_transfer()
    outsider = User.objects.create_user(email="transfer-outsider@example.test")
    other_workspace = create_workspace(name="Other transfer workspace", owner=outsider)
    other_investor = Investor(workspace=other_workspace, name="Other Investor")
    other_investor.set_pan("TESTX0002A")
    other_investor.save()
    other_bank = make_bank(other_workspace, other_investor, "003")
    valid = {
        "source_bank": str(source.pk),
        "destination_bank": str(destination.pk),
        "amount": "100.00",
    }

    for payload, expected in (
        ({**valid, "destination_bank": str(source.pk)}, 400),
        ({**valid, "amount": "0"}, 400),
        ({**valid, "amount": "500.01"}, 400),
        ({**valid, "destination_bank": str(other_bank.pk)}, 404),
    ):
        assert client.post(url, payload).status_code == expected

    destination.active = False
    destination.save(update_fields=["active"])
    assert client.post(url, valid).status_code == 400
    destination.active = True
    destination.is_placeholder = True
    destination.save(update_fields=["active", "is_placeholder"])
    assert client.post(url, valid).status_code == 400

    viewer = User.objects.create_user(email="transfer-viewer@example.test")
    WorkspaceMembership.objects.create(
        workspace=workspace, user=viewer, role=WorkspaceMembership.Role.VIEWER
    )
    client.force_authenticate(viewer)
    assert client.post(url, valid).status_code == 403
    client.force_authenticate(outsider)
    assert client.post(url, valid).status_code == 403
    source.refresh_from_db()
    destination.refresh_from_db()
    assert source.current_balance == Decimal("500.00")
    assert destination.current_balance == Decimal("100.00")
    assert BalanceChange.objects.filter(bank__workspace=workspace).count() == 0


@pytest.mark.django_db
def test_optional_description_is_saved_for_each_balance_action():
    _, workspace, _, source, _, client, _ = setup_transfer()
    for action, amount in (("add", "20.00"), ("remove", "10.00"), ("set", "450.00")):
        response = client.post(
            reverse(
                f"bank-{action}-money" if action != "set" else "bank-set-balance",
                args=[workspace.pk, source.pk],
            ),
            {"amount": amount, "note": f"Synthetic {action} note"},
        )
        assert response.status_code == 201
        assert BalanceChange.objects.get(pk=response.data["id"]).note == f"Synthetic {action} note"


@pytest.mark.django_db
def test_transfer_rolls_back_both_banks_if_history_audit_fails(monkeypatch):
    owner, workspace, _, source, destination, _, _ = setup_transfer()
    calls = 0

    def fail_second_audit(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Synthetic audit failure")

    monkeypatch.setattr("funding.services.record_event", fail_second_audit)
    with pytest.raises(RuntimeError, match="Synthetic audit failure"):
        transfer_money(
            source=source,
            destination=destination,
            amount=Decimal("50.00"),
            actor=owner,
        )
    source.refresh_from_db()
    destination.refresh_from_db()
    assert source.current_balance == Decimal("500.00")
    assert destination.current_balance == Decimal("100.00")
    assert BalanceChange.objects.filter(bank__workspace=workspace).count() == 0


@pytest.mark.django_db
def test_transfer_details_remain_in_deleted_bank_history():
    _, workspace, _, source, destination, client, url = setup_transfer()
    response = client.post(
        url,
        {
            "source_bank": str(source.pk),
            "destination_bank": str(destination.pk),
            "amount": "25.00",
            "note": "Synthetic archive note",
        },
    )
    assert response.status_code == 201
    _archive_bank_balance_history(source, workspace)
    archived = ArchivedBalanceChange.objects.get(bank_ref=source.pk)
    assert str(archived.transfer_id) == response.data["transfer_id"]
    assert destination.bank_name in archived.counterparty_label
    assert archived.note == "Synthetic archive note"


@pytest.mark.django_db
def test_statement_resolves_full_transfer_details_for_all_workspace_members():
    from funding.models import UPIHandle

    owner, workspace, investor, source, destination, client, _ = setup_transfer()
    upi = UPIHandle(bank=destination, holder=investor)
    upi.set_handle("synthetic.destination@exampleupi")
    upi.save()
    transfer_money(source=source, destination=destination, amount=Decimal("10"), actor=owner)
    url = reverse("workspace-balance-statement", args=[workspace.pk])
    row = next(row for row in client.get(url).data["results"] if row["operation"] == "TRANSFER_OUT")
    assert "synthetic.destination@exampleupi" in row["counterparty_label"]
    assert "SYNTHETIC-ACCOUNT-002" in row["counterparty_label"]
    viewer = User.objects.create_user(email="masked-transfer@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    client.force_authenticate(viewer)
    row = next(row for row in client.get(url).data["results"] if row["operation"] == "TRANSFER_OUT")
    assert "synthetic.destination@exampleupi" in row["counterparty_label"]
    assert "SYNTHETIC-ACCOUNT-002" in row["counterparty_label"]
    assert "••••@exampleupi" not in row["counterparty_label"]
