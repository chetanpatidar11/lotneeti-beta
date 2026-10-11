"""Pure draft IPO selection rule; a manual decision always wins."""

from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo


def selection_status(values: dict, *, at: datetime) -> str:
    status = values["status"]
    if status in {"OPEN", "UPCOMING"}:
        close_at = datetime.combine(values["close_date"], time(17), tzinfo=ZoneInfo("Asia/Kolkata"))
        if at >= close_at:
            return "CLOSED"
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
    if status is not None and status != "OPEN" and not (status == "UPCOMING" and allow_upcoming):
        return False, "NOT_OPEN_FOR_AUTO_SELECTION"
    if threshold is None or gmp_percent is None:
        return False, "NO_AUTO_SELECTION"
    return gmp_percent >= threshold, "GMP_THRESHOLD"
