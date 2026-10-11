"""Pure draft IPO selection rule; a manual decision always wins."""

from decimal import Decimal


def select_ipo(
    *,
    decision: str,
    gmp_percent: Decimal | None,
    threshold: Decimal | None,
    issue_type: str | None = None,
    auto_issue_types: tuple[str, ...] = ("MAINBOARD",),
) -> tuple[bool, str]:
    if decision == "APPLY":
        return True, "MANUAL_APPLY"
    if decision == "SKIP":
        return False, "MANUAL_SKIP"
    if decision != "DEFAULT":
        raise ValueError(f"Unknown IPO decision: {decision}")
    if issue_type is not None and issue_type not in auto_issue_types:
        return False, "ISSUE_TYPE_EXCLUDED"
    if threshold is None or gmp_percent is None:
        return False, "NO_AUTO_SELECTION"
    return gmp_percent >= threshold, "GMP_THRESHOLD"
