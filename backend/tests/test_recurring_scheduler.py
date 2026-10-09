from datetime import date
from decimal import Decimal

import pytest

from accounts.models import User
from accounts.services import create_workspace
from funding.models import BalanceChange, BankAccount, RecurringDebit, RecurringDebitOccurrence
from funding.recurring import next_occurrence_date, post_due_recurring_debits
from investors.models import Investor


def make_schedule(*, balance="50000.00", amount="8500.00", active=True):
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    investor = Investor(workspace=workspace, name="Synthetic")
    investor.set_pan("TESTX0001A")
    investor.save()
    bank = BankAccount(
        workspace=workspace,
        owner=investor,
        bank_name="Demo Bank",
        current_balance=Decimal(balance),
    )
    bank.set_account_number("DEMO-ACCOUNT-0001")
    bank.save()
    schedule = RecurringDebit.objects.create(
        bank=bank,
        name="Home Loan EMI",
        amount=Decimal(amount),
        frequency=RecurringDebit.Frequency.MONTHLY,
        start_date=date(2026, 10, 5),
        next_due_date=date(2026, 10, 5),
        active=active,
    )
    return bank, schedule


@pytest.mark.django_db
def test_due_emi_posts_once_and_advances_next_date():
    bank, schedule = make_schedule()

    assert post_due_recurring_debits(as_of=date(2026, 10, 5)) == 1
    assert post_due_recurring_debits(as_of=date(2026, 10, 5)) == 0

    bank.refresh_from_db()
    schedule.refresh_from_db()
    assert bank.current_balance == Decimal("41500.00")
    assert schedule.next_due_date == date(2026, 11, 5)
    occurrence = RecurringDebitOccurrence.objects.get(recurring_debit=schedule)
    assert occurrence.due_date == date(2026, 10, 5)
    assert occurrence.balance_change.delta == Decimal("-8500.00")
    assert occurrence.balance_change.operation == BalanceChange.Operation.REMOVE


@pytest.mark.django_db
def test_paused_emi_does_not_post_and_edited_amount_is_used_when_resumed():
    bank, schedule = make_schedule(active=False)
    assert post_due_recurring_debits(as_of=date(2026, 10, 5)) == 0
    schedule.amount = Decimal("9000.00")
    schedule.active = True
    schedule.save(update_fields=["amount", "active"])

    assert post_due_recurring_debits(as_of=date(2026, 10, 5)) == 1
    bank.refresh_from_db()
    assert bank.current_balance == Decimal("41000.00")


@pytest.mark.django_db
def test_missed_monthly_occurrences_catch_up_once_and_respect_end_date():
    bank, schedule = make_schedule()
    schedule.end_date = date(2026, 11, 5)
    schedule.save(update_fields=["end_date"])

    assert post_due_recurring_debits(as_of=date(2026, 12, 1)) == 2
    assert post_due_recurring_debits(as_of=date(2026, 12, 1)) == 0
    bank.refresh_from_db()
    schedule.refresh_from_db()
    assert bank.current_balance == Decimal("33000.00")
    assert schedule.active is False
    assert RecurringDebitOccurrence.objects.filter(recurring_debit=schedule).count() == 2


@pytest.mark.django_db
def test_month_end_anchor_returns_after_short_month():
    _, schedule = make_schedule()
    schedule.start_date = date(2026, 1, 31)
    assert next_occurrence_date(schedule, date(2026, 1, 31)) == date(2026, 2, 28)
    assert next_occurrence_date(schedule, date(2026, 2, 28)) == date(2026, 3, 31)
