"""Pure draft IPO selection rule; a manual decision always wins."""

from decimal import Decimal


def select_ipo(
    *, decision: str, gmp_percent: Decimal | None, threshold: Decimal | None
) -> tuple[bool, str]:
    if decision == "APPLY":
        return True, "MANUAL_APPLY"
    if decision == "SKIP":
        return False, "MANUAL_SKIP"
    if decision != "DEFAULT":
        raise ValueError(f"Unknown IPO decision: {decision}")
    if threshold is None or gmp_percent is None:
        return False, "NO_AUTO_SELECTION"
    return gmp_percent >= threshold, "GMP_THRESHOLD"
