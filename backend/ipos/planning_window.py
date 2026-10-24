"""IPO selection availability for planning, separate from exchange application hours."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.utils import timezone

INDIA_TIME_ZONE = ZoneInfo("Asia/Kolkata")


def planning_window(
    *, status: str, close_date: date, now: datetime | None = None
) -> tuple[bool, bool]:
    """Return manual availability and whether the IPO is limited to record plans."""
    if status not in {"OPEN", "UPCOMING", "CLOSED", "ALLOTMENT", "LISTED"}:
        return False, False

    instant = now or timezone.now()
    application_cutoff = datetime.combine(close_date, time(17), tzinfo=INDIA_TIME_ZONE)
    planning_only = status in {"CLOSED", "ALLOTMENT", "LISTED"} or instant >= application_cutoff
    return True, planning_only
