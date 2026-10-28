import calendar
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from core.audit import record_event
from funding.models import RecurringDebit, RecurringDebitOccurrence
from funding.services import remove_money

MAX_SCHEDULES_PER_RUN = 50
MAX_OCCURRENCES_PER_SCHEDULE = 10
MAX_OCCURRENCES_PER_RUN = 100


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
        # Rotate processed schedules behind untouched ones, including old backlogs.
        .order_by("updated_at", "id")
        .values_list("pk", flat=True)[:MAX_SCHEDULES_PER_RUN]
    )
    posted = 0
    processed = 0
    for schedule_id in schedule_ids:
        for _ in range(MAX_OCCURRENCES_PER_SCHEDULE):
            if processed >= MAX_OCCURRENCES_PER_RUN:
                return posted
            # Commit each occurrence so no schedule holds a bank for its backlog.
            with transaction.atomic():
                schedule = (
                    RecurringDebit.objects.select_for_update()
                    .select_related("bank")
                    .filter(pk=schedule_id, archived_at__isnull=True)
                    .first()
                )
                if schedule is None or not schedule.active or schedule.next_due_date > today:
                    break
                processed += 1
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
