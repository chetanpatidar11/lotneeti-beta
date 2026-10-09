from decimal import Decimal

import pytest

from planner.quotes import minimum_shni_quote, retail_quote


def test_qc001_retail_is_exactly_one_lot():
    quote = retail_quote(Decimal("100.00"), 150)
    assert quote.lots == 1
    assert quote.amount == Decimal("15000.00")


def test_qc002_minimum_shni_is_smallest_whole_lot_above_threshold():
    quote = minimum_shni_quote(Decimal("100.00"), 150)
    assert quote.lots == 14
    assert quote.amount == Decimal("210000.00")
    assert quote.amount - Decimal("15000.00") <= Decimal("200000.00")


def test_qc003_one_lot_can_already_be_shni_and_exact_threshold_is_not_enough():
    assert minimum_shni_quote(Decimal("1500.00"), 150).lots == 1
    exact = minimum_shni_quote(Decimal("2000.00"), 100)
    assert exact.lots == 2
    assert exact.amount == Decimal("400000.00")


@pytest.mark.parametrize(
    ("price", "lot_size"),
    [(Decimal("0.00"), 150), (Decimal("100.001"), 150), (Decimal("100.00"), 0)],
)
def test_invalid_quote_inputs_fail_closed(price, lot_size):
    with pytest.raises(ValueError):
        retail_quote(price, lot_size)
