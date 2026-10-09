import calendar
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from core.audit import record_event
from funding.models import RecurringDebit, RecurringDebitOccurrence
from funding.services import remove_money


def next_occurrence_date(schedule: RecurringDebit, due_date: date) -> date:
    if schedule.frequency == RecurringDebit.Frequency.DAILY:
        return due_date + timedelta(days=1)
    if schedule.frequency == RecurringDebit.Frequency.WEEKLY:
        return due_date + timedelta(days=7)
    if schedule.frequency == RecurringDebit.Frequency.MONTHLY:
        year = due_date.year + (due_date.month == 12)
        month = due_date.month % 12 + 1
        day = min(schedule.start_date.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    raise ValueError("Unsupported recurring payment frequency")


def post_due_recurring_debits(*, as_of: date | None = None) -> int:
    today = as_of or timezone.localdate()
    schedule_ids = list(
        RecurringDebit.objects.filter(
            active=True, archived_at__isnull=True, next_due_date__lte=today
        )
        .order_by("next_due_date", "id")
        .values_list("pk", flat=True)
    )
    posted = 0
    for schedule_id in schedule_ids:
        with transaction.atomic():
            schedule = (
                RecurringDebit.objects.select_for_update()
                .select_related("bank")
                .get(pk=schedule_id)
            )
            while schedule.active and schedule.next_due_date <= today:
                due_date = schedule.next_due_date
                if schedule.end_date is not None and due_date > schedule.end_date:
                    schedule.active = False
                    schedule.save(update_fields=["active", "updated_at"])
                    break

                if not RecurringDebitOccurrence.objects.filter(
                    recurring_debit=schedule, due_date=due_date
                ).exists():
                    change = remove_money(
                        bank=schedule.bank,
                        amount=schedule.amount,
                        actor=None,
                        note=f"Scheduled payment: {schedule.name}",
                    )
                    occurrence = RecurringDebitOccurrence.objects.create(
                        recurring_debit=schedule,
                        due_date=due_date,
                        balance_change=change,
                    )
                    record_event(
                        action="recurring_debit.posted",
                        target=occurrence,
                        workspace=schedule.bank.workspace,
                    )
                    posted += 1

                schedule.next_due_date = next_occurrence_date(schedule, due_date)
                if schedule.end_date is not None and schedule.next_due_date > schedule.end_date:
                    schedule.active = False
                schedule.save(update_fields=["next_due_date", "active", "updated_at"])
    return posted
