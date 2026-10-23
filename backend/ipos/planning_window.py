"""IPO selection availability for planning, separate from exchange application hours."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.utils import timezone

INDIA_TIME_ZONE = ZoneInfo("Asia/Kolkata")


def planning_window(
    *, status: str, close_date: date, now: datetime | None = None
) -> tuple[bool, bool]:
    """Return (available, planning_only) for the IPO's closing-day plan grace period."""
    instant = now or timezone.now()
    local_now = instant.astimezone(INDIA_TIME_ZONE)
    today = local_now.date()

    if status in {"OPEN", "UPCOMING"} and close_date >= today:
        available = True
    else:
        available = status == "CLOSED" and close_date == today

    if not available:
        return False, False

    application_cutoff = datetime.combine(close_date, time(17), tzinfo=INDIA_TIME_ZONE)
    planning_only = status == "CLOSED" or local_now >= application_cutoff
    return True, planning_only
