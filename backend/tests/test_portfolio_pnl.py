from decimal import Decimal
from types import SimpleNamespace

from portfolio.pnl import realized_results


def test_split_sales_allocate_exact_actual_cost_without_rounding_drift():
    application = SimpleNamespace(actual_cost=Decimal("100.00"), allotted_quantity=3)
    sales = [
        SimpleNamespace(
            pk=index,
            application_id="app",
            application=application,
            quantity=1,
            price_per_share=Decimal("40.00"),
            charges=Decimal("0.00"),
            recorded_at=index,
        )
        for index in (1, 2, 3)
    ]
    results = realized_results(list(reversed(sales)))
    assert [results[index].ipo_cost for index in (1, 2, 3)] == [
        Decimal("33.33"),
        Decimal("33.34"),
        Decimal("33.33"),
    ]
    assert sum((result.ipo_cost for result in results.values()), Decimal("0")) == Decimal("100.00")
    assert sum((result.realized_profit for result in results.values()), Decimal("0")) == Decimal(
        "20.00"
    )


def test_roi_is_unavailable_when_tiny_partial_sale_has_zero_allocated_cost():
    application = SimpleNamespace(actual_cost=Decimal("0.01"), allotted_quantity=100)
    sale = SimpleNamespace(
        pk=1,
        application_id="app",
        application=application,
        quantity=1,
        price_per_share=Decimal("1.00"),
        charges=Decimal("0.00"),
        recorded_at=1,
    )
    assert realized_results([sale])[1].roi_percent is None
