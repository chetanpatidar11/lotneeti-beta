import pytest
from django.core.exceptions import ValidationError

from accounts.models import User
from accounts.services import create_workspace
from funding.models import BankAccount, FundingPreference
from investors.models import Investor


def investor(workspace, name, pan):
    person = Investor(workspace=workspace, name=name)
    person.set_pan(pan)
    person.save()
    return person


def bank(workspace, owner, name, number):
    account = BankAccount(workspace=workspace, owner=owner, bank_name=name)
    account.set_account_number(number)
    account.save()
    return account


@pytest.mark.django_db
def test_funding_preferences_are_ordered_and_disabled_entries_are_skipped():
    user = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=user)
    beneficiary = investor(workspace, "Mother", "TESTX0001A")
    funder = investor(workspace, "Wife", "TESTX0002B")
    first_bank = bank(workspace, funder, "Demo HDFC", "DEMO-ACCOUNT-0001")
    second_bank = bank(workspace, funder, "Demo SBI", "DEMO-ACCOUNT-0002")
    FundingPreference.objects.create(beneficiary=beneficiary, bank=second_bank, priority=2)
    FundingPreference.objects.create(beneficiary=beneficiary, bank=first_bank, priority=1)

    assert list(
        FundingPreference.objects.enabled_for(beneficiary).values_list("bank_id", flat=True)
    ) == [first_bank.pk, second_bank.pk]
    first = FundingPreference.objects.get(beneficiary=beneficiary, bank=first_bank)
    first.enabled = False
    first.save(update_fields=["enabled", "updated_at"])
    assert list(
        FundingPreference.objects.enabled_for(beneficiary).values_list("bank_id", flat=True)
    ) == [second_bank.pk]


@pytest.mark.django_db
def test_preferred_bank_cannot_belong_to_another_workspace():
    user = User.objects.create_user(email="owner@example.test")
    first = create_workspace(name="First", owner=user)
    second = create_workspace(name="Second", owner=user)
    beneficiary = investor(first, "Mother", "TESTX0001A")
    funder = investor(second, "Wife", "TESTX0002B")
    other_bank = bank(second, funder, "Demo HDFC", "DEMO-ACCOUNT-0001")

    with pytest.raises(ValidationError):
        FundingPreference.objects.create(beneficiary=beneficiary, bank=other_bank, priority=1)
