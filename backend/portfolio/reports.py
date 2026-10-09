"""Workspace, IPO and investor realized sale summaries."""

from decimal import ROUND_HALF_UP, Decimal

from portfolio.pnl import PAISE, realized_results


def _empty_totals():
    return {
        "gross_proceeds": Decimal("0.00"),
        "ipo_cost": Decimal("0.00"),
        "charges": Decimal("0.00"),
        "realized_profit": Decimal("0.00"),
    }


def _add(totals, result):
    totals["gross_proceeds"] += result.gross_proceeds
    totals["ipo_cost"] += result.ipo_cost
    totals["charges"] += result.charges
    totals["realized_profit"] += result.realized_profit


def _display(totals):
    cost = totals["ipo_cost"]
    return {
        **{
            key: str(totals[key])
            for key in ("gross_proceeds", "ipo_cost", "charges", "realized_profit")
        },
        "roi_percent": str(
            (totals["realized_profit"] * 100 / cost).quantize(PAISE, rounding=ROUND_HALF_UP)
        )
        if cost
        else None,
    }


def profit_report(sales, *, from_date=None, to_date=None):
    """Allocate costs across all sales, then filter by sale date for a period."""
    results = realized_results(sales)
    total = _empty_totals()
    by_ipo = {}
    by_investor = {}
    count = 0
    for sale in sales:
        if (from_date and sale.sold_on < from_date) or (to_date and sale.sold_on > to_date):
            continue
        count += 1
        result = results[sale.pk]
        _add(total, result)
        ipo_id = str(sale.application.ipo_id)
        if ipo_id not in by_ipo:
            by_ipo[ipo_id] = {
                "id": ipo_id,
                "name": sale.application.ipo.issuer_name,
                **_empty_totals(),
            }
        _add(by_ipo[ipo_id], result)
        investor_id = str(sale.application.applicant_id)
        if investor_id not in by_investor:
            by_investor[investor_id] = {
                "id": investor_id,
                "name": sale.application.applicant.name,
                **_empty_totals(),
            }
        _add(by_investor[investor_id], result)
    return {
        "sale_count": count,
        "workspace": _display(total),
        "by_ipo": [
            {"id": item["id"], "name": item["name"], **_display(item)}
            for item in sorted(by_ipo.values(), key=lambda item: (item["name"], item["id"]))
        ],
        "by_investor": [
            {"id": item["id"], "name": item["name"], **_display(item)}
            for item in sorted(by_investor.values(), key=lambda item: (item["name"], item["id"]))
        ],
    }
