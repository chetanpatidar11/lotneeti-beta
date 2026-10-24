from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from core.models import AuditEvent
from funding.models import BalanceChange, BankAccount, UPIHandle
from funding.serializers import BankAccountSerializer
from tests.test_banks import synthetic_investor


def fixture_bank():
    user = User.objects.create_user(email="holder-sync@example.test")
    workspace = create_workspace(name="Synthetic", owner=user)
    first = synthetic_investor(workspace)
    second = synthetic_investor(workspace, "TESTX0002A")
    bank = BankAccount(
        workspace=workspace,
        owner=first,
        bank_name="Synthetic Bank",
        current_balance=Decimal("50000"),
    )
    bank.set_account_number("SYNTHETIC-ACCOUNT-ONE")
    bank.save()
    handles = []
    for index, active in enumerate([True, False]):
        upi = UPIHandle(
            bank=bank,
            holder=first,
            active=active,
            count_limit_override=4,
            amount_limit_override=Decimal("200000"),
        )
        upi.set_handle(f"synthetic{index}@exampleupi")
        upi.save()
        handles.append(upi)
    client = APIClient()
    client.force_authenticate(user)
    return user, workspace, first, second, bank, handles, client


@pytest.mark.django_db
@pytest.mark.parametrize("imported", [False, True])
def test_bank_holder_edit_moves_all_linked_upis_and_preserves_identifiers_limits_and_balance(
    imported,
):
    user, workspace, first, second, bank, handles, client = fixture_bank()
    bank.is_imported_reference = imported
    bank.save()
    other = BankAccount(workspace=workspace, owner=first, bank_name="Other Bank")
    other.set_account_number("SYNTHETIC-ACCOUNT-TWO")
    other.save()
    unrelated = UPIHandle(bank=other, holder=first)
    unrelated.set_handle("unrelated@exampleupi")
    unrelated.save()
    originals = [(upi.handle_ciphertext, upi.handle_lookup_hash, upi.active) for upi in handles]
    result = client.patch(
        reverse("bank-detail", args=[workspace.pk, bank.pk]), {"owner": str(second.pk)}
    )
    assert result.status_code == 200
    bank.refresh_from_db()
    assert bank.owner == second and bank.current_balance == Decimal("50000")
    assert bank.is_imported_reference == imported
    for upi, original in zip(handles, originals, strict=True):
        upi.refresh_from_db()
        assert upi.holder == second and upi.bank == bank
        assert (upi.handle_ciphertext, upi.handle_lookup_hash, upi.active) == original
        assert upi.count_limit_override == 4 and upi.amount_limit_override == Decimal("200000")
    unrelated.refresh_from_db()
    assert unrelated.holder == first
    assert not BalanceChange.objects.exists()
    events = AuditEvent.objects.filter(action="upi.holder_synced")
    assert events.count() == 2
    assert all(event.actor == user and event.workspace == workspace for event in events)
    assert {
        row["holder"] for row in client.get(reverse("upi-list", args=[workspace.pk, bank.pk])).data
    } == {second.pk}
    assert (
        client.patch(
            reverse("bank-detail", args=[workspace.pk, bank.pk]), {"owner": str(second.pk)}
        ).status_code
        == 200
    )
    assert events.count() == 2


@pytest.mark.django_db
def test_explicit_same_holder_save_repairs_stale_upis_but_unrelated_edits_do_not_reassign():
    _, workspace, first, second, bank, handles, client = fixture_bank()
    bank.owner = second
    bank.save()
    url = reverse("bank-detail", args=[workspace.pk, bank.pk])
    assert client.patch(url, {"bank_name": "Renamed"}).status_code == 200
    assert set(bank.upis.values_list("holder_id", flat=True)) == {first.pk}
    assert client.patch(url, {"owner": str(second.pk)}).status_code == 200
    assert set(bank.upis.values_list("holder_id", flat=True)) == {second.pk}
    assert bank.upis.count() == len(handles)


@pytest.mark.django_db
def test_holder_change_rejects_inactive_or_other_workspace_owners_and_viewers():
    user, workspace, first, second, bank, _, client = fixture_bank()
    other = create_workspace(name="Other", owner=user)
    outside = synthetic_investor(other)
    second.active = False
    second.save()
    url = reverse("bank-detail", args=[workspace.pk, bank.pk])
    for investor in [second, outside]:
        assert client.patch(url, {"owner": str(investor.pk)}).status_code == 400
    viewer = User.objects.create_user(email="viewer-sync@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    client.force_authenticate(viewer)
    assert client.patch(url, {"owner": str(first.pk)}).status_code == 403
    bank.refresh_from_db()
    assert bank.owner == first
    assert set(bank.upis.values_list("holder_id", flat=True)) == {first.pk}
    assert not AuditEvent.objects.filter(action="upi.holder_synced").exists()


@pytest.mark.django_db
def test_bank_and_upi_holder_changes_roll_back_together_on_failure():
    user, workspace, first, second, bank, _, _ = fixture_bank()
    serializer = BankAccountSerializer(
        bank,
        data={"owner": str(second.pk)},
        partial=True,
        context={"workspace": workspace, "request": SimpleNamespace(user=user)},
    )
    serializer.is_valid(raise_exception=True)
    with patch(
        "funding.serializers.record_event", side_effect=RuntimeError("Synthetic audit failure")
    ):
        with pytest.raises(RuntimeError, match="Synthetic audit failure"):
            serializer.save()
    bank.refresh_from_db()
    assert bank.owner == first
    assert set(bank.upis.values_list("holder_id", flat=True)) == {first.pk}
