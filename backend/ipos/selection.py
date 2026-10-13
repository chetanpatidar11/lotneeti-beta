"""Pure draft IPO selection rule; a manual decision always wins."""

from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo


def selection_status(values: dict, *, at: datetime) -> str:
    status = values["status"]
    if status in {"OPEN", "UPCOMING"}:
        india = ZoneInfo("Asia/Kolkata")
        close_at = datetime.combine(values["close_date"], time(17), tzinfo=india)
        if at >= close_at:
            return "CLOSED"
        if at.astimezone(india).date() < values["open_date"]:
            return "UPCOMING"
        return "OPEN"
    return status


def has_open_auto_ipo(values: list[dict], *, issue_types: tuple[str, ...], at: datetime) -> bool:
    return any(
        item["issue_type"] in issue_types and selection_status(item, at=at) == "OPEN"
        for item in values
    )


def select_ipo(
    *,
    decision: str,
    gmp_percent: Decimal | None,
    threshold: Decimal | None,
    issue_type: str | None = None,
    auto_issue_types: tuple[str, ...] = ("MAINBOARD",),
    status: str | None = None,
    allow_upcoming: bool = True,
) -> tuple[bool, str]:
    if decision == "APPLY":
        return True, "MANUAL_APPLY"
    if decision == "SKIP":
        return False, "MANUAL_SKIP"
    if decision != "DEFAULT":
        raise ValueError(f"Unknown IPO decision: {decision}")
    if issue_type is not None and issue_type not in auto_issue_types:
        return False, "ISSUE_TYPE_EXCLUDED"
    if status == "UPCOMING" and not allow_upcoming:
        return False, "OPEN_IPO_AVAILABLE"
    if status is not None and status not in {"OPEN", "UPCOMING"}:
        return False, "IPO_NOT_OPEN"
    if threshold is None:
        return False, "THRESHOLD_NOT_SET"
    if gmp_percent is None:
        return False, "GMP_UNAVAILABLE"
    if gmp_percent < threshold:
        return False, "BELOW_GMP_THRESHOLD"
    return True, "GMP_THRESHOLD"
