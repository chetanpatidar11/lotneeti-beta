"""Exact whole-lot quote sizes for Planner v2."""

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

SHNI_THRESHOLD = Decimal("200000.00")


@dataclass(frozen=True, slots=True)
class Quote:
    lots: int
    amount: Decimal


def _lot_amount(upper_price: Decimal, lot_size: int) -> Decimal:
    if not isinstance(upper_price, Decimal) or upper_price <= 0:
        raise ValueError("Upper price must be a positive decimal")
    if upper_price != upper_price.quantize(Decimal("0.01")):
        raise ValueError("Upper price must have at most two decimal places")
    if type(lot_size) is not int or lot_size < 1:
        raise ValueError("Lot size must be a positive whole number")
    return upper_price * lot_size


def retail_quote(upper_price: Decimal, lot_size: int) -> Quote:
    return Quote(lots=1, amount=_lot_amount(upper_price, lot_size))


def minimum_shni_quote(upper_price: Decimal, lot_size: int) -> Quote:
    lot_amount = _lot_amount(upper_price, lot_size)
    lots = int((SHNI_THRESHOLD / lot_amount).to_integral_value(rounding=ROUND_FLOOR)) + 1
    return Quote(lots=lots, amount=lot_amount * lots)
