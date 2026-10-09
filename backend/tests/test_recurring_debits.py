from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from accounts.models import User
from accounts.services import create_workspace
from funding.models import BankAccount, RecurringDebit
from investors.models import Investor


@pytest.mark.django_db
def test_recurring_debit_stores_schedule_and_pause_state():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    investor = Investor(workspace=workspace, name="Synthetic")
    investor.set_pan("TESTX0001A")
    investor.save()
    bank = BankAccount(workspace=workspace, owner=investor, bank_name="Demo Bank")
    bank.set_account_number("DEMO-ACCOUNT-0001")
    bank.save()

    debit = RecurringDebit.objects.create(
        bank=bank,
        name="Home Loan EMI",
        amount=Decimal("8500.00"),
        frequency=RecurringDebit.Frequency.MONTHLY,
        start_date=date(2026, 10, 5),
        next_due_date=date(2026, 10, 5),
    )
    debit.active = False
    debit.save(update_fields=["active", "updated_at"])
    debit.refresh_from_db()

    assert debit.bank == bank
    assert debit.next_due_date == date(2026, 10, 5)
    assert debit.active is False


@pytest.mark.django_db
def test_recurring_debit_rejects_invalid_amount_and_dates():
    debit = RecurringDebit(
        name="Synthetic EMI",
        amount=Decimal("0.00"),
        frequency=RecurringDebit.Frequency.MONTHLY,
        start_date=date(2026, 10, 5),
        next_due_date=date(2026, 10, 4),
        end_date=date(2026, 10, 3),
    )
    with pytest.raises(ValidationError) as exc:
        debit.clean()
    assert set(exc.value.message_dict) == {"amount", "next_due_date", "end_date"}
