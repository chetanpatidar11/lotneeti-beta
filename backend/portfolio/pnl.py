"""Exact realized results from actual allotment cost and recorded sale proceeds."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

PAISE = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class RealizedResult:
    gross_proceeds: Decimal
    ipo_cost: Decimal
    charges: Decimal
    realized_profit: Decimal
    roi_percent: Decimal | None


def realized_results(sales) -> dict:
    """Allocate cost by cumulative sold shares so a full exit uses exact actual cost."""
    by_application = {}
    for sale in sales:
        by_application.setdefault(sale.application_id, []).append(sale)
    results = {}
    for items in by_application.values():
        sold = 0
        allocated_cost = Decimal("0.00")
        for sale in sorted(items, key=lambda item: (item.recorded_at, str(item.pk))):
            application = sale.application
            sold += sale.quantity
            cumulative_cost = (
                application.actual_cost * Decimal(sold) / Decimal(application.allotted_quantity)
            ).quantize(PAISE, rounding=ROUND_HALF_UP)
            cost = cumulative_cost - allocated_cost
            allocated_cost = cumulative_cost
            proceeds = (Decimal(sale.quantity) * sale.price_per_share).quantize(PAISE)
            profit = proceeds - cost - sale.charges
            roi = (profit * 100 / cost).quantize(PAISE, rounding=ROUND_HALF_UP) if cost else None
            results[sale.pk] = RealizedResult(proceeds, cost, sale.charges, profit, roi)
    return results
