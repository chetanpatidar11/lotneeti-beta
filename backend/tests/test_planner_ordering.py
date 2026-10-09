from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

from planner.dto import IPOInput
from planner.ordering import selected_ipo_order

IST = timezone(timedelta(hours=5, minutes=30))


def ipo(id, *, gmp="25.00", day=3, selected=True, cutoff=None):
    return IPOInput(
        id=id,
        selected=selected,
        gmp_percent=Decimal(gmp) if gmp is not None else None,
        upper_price=Decimal("100.00"),
        lot_size=150,
        cutoff_at=cutoff or datetime(2026, 10, day, 17, tzinfo=IST),
        allotment_date=date(2026, 10, 9),
        mode="RETAIL_ONLY",
    )


def test_is007_higher_gmp_precedes_earlier_cutoff_including_manual_selection():
    earlier = ipo("earlier", gmp="22.00", day=3)
    higher = ipo("higher", gmp="35.00", day=4)
    unselected = ipo("unselected", gmp="50.00", day=2, selected=False)
    assert selected_ipo_order((earlier, unselected, higher)) == (higher, earlier)


def test_is008_equal_gmp_uses_earlier_cutoff():
    later = ipo("later", day=4)
    earlier = ipo("earlier", day=3)
    assert selected_ipo_order((later, earlier)) == (earlier, later)


def test_is009_equal_gmp_and_instant_uses_stable_id_regardless_of_input_order():
    first = ipo("a")
    second = ipo("b", cutoff=datetime(2026, 10, 3, 11, 30, tzinfo=UTC))
    assert selected_ipo_order((second, first)) == (first, second)
    assert selected_ipo_order((first, second)) == (first, second)


def test_unknown_gmp_is_last_and_keeps_cutoff_id_order():
    known = ipo("known", gmp="0.00", day=4)
    unknown = ipo("unknown", gmp=None, day=3)
    assert selected_ipo_order((unknown, known)) == (known, unknown)
