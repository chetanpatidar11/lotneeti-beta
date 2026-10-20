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


def defer_automatic_for_reuse(
    *,
    decision: str,
    selected: bool,
    reason: str,
    values: dict,
    earlier_selected: list[dict],
    at: datetime,
) -> tuple[bool, str]:
    """Delay later automatic picks while an earlier selected IPO uses the same funding window."""
    if decision != "DEFAULT" or not selected:
        return selected, reason
    india = ZoneInfo("Asia/Kolkata")
    for earlier in earlier_selected:
        if earlier is values or earlier["close_date"] >= values["close_date"]:
            continue
        if selection_status(earlier, at=at) not in {"OPEN", "UPCOMING"}:
            continue
        start_date = values["open_date"]
        if earlier["allotment_date"] <= start_date:
            wait_until = datetime.combine(start_date, time.min, tzinfo=india)
        else:
            wait_until = datetime.combine(earlier["close_date"], time(17), tzinfo=india)
        if at < wait_until:
            return False, "WAITING_FOR_FUND_REUSE"
    return selected, reason


def resolve_ipo_choices(
    *,
    candidates: list[tuple[str, dict, str, Decimal | None]],
    threshold: Decimal | None,
    issue_types: tuple[str, ...],
    at: datetime,
) -> dict[str, tuple[bool, str]]:
    """Apply the same automatic selection timing in IPO and planner views."""
    has_open = has_open_auto_ipo(
        [values for _, values, _, _ in candidates], issue_types=issue_types, at=at
    )
    initial = {}
    for ipo_id, values, decision, percent in candidates:
        initial[ipo_id] = select_ipo(
            decision=decision,
            gmp_percent=percent,
            threshold=threshold,
            issue_type=values["issue_type"],
            auto_issue_types=issue_types,
            status=selection_status(values, at=at),
            allow_upcoming=not has_open,
        )
    chosen = []
    resolved = {}
    for ipo_id, values, decision, _ in sorted(
        candidates, key=lambda item: (item[1]["close_date"], item[0])
    ):
        selected, reason = defer_automatic_for_reuse(
            decision=decision,
            selected=initial[ipo_id][0],
            reason=initial[ipo_id][1],
            values=values,
            earlier_selected=chosen,
            at=at,
        )
        resolved[ipo_id] = (selected, reason)
        if selected:
            chosen.append(values)
    return resolved


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
