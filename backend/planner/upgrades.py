"""Replace baseline Retail rows with minimum valid sHNI rows when feasible."""

from dataclasses import replace

from planner.coverage import CoverageResult
from planner.dto import PlannerSnapshot
from planner.ordering import selected_ipo_order
from planner.quotes import minimum_shni_quote
from planner.wallets import choose_shni_wallet


def upgrade_retail_to_shni(snapshot: PlannerSnapshot, coverage: CoverageResult) -> CoverageResult:
    rows = list(coverage.rows)
    applicants = {item.id: item for item in snapshot.applicants}
    for ipo in selected_ipo_order(snapshot.ipos):
        if ipo.mode not in {"RETAIL_PLUS_SHNI", "SHNI_PREFERRED"}:
            continue
        quote = minimum_shni_quote(ipo.upper_price, ipo.lot_size)
        while True:
            changed = False
            indices = sorted(
                (
                    index
                    for index, row in enumerate(rows)
                    if row.ipo_id == ipo.id and row.category == "RETAIL" and not row.locked
                ),
                key=lambda index: (
                    applicants[rows[index].applicant_id].priority,
                    rows[index].applicant_id,
                ),
            )
            for index in indices:
                row = rows[index]
                applicant = applicants[row.applicant_id]
                others = tuple(
                    current for current_index, current in enumerate(rows) if current_index != index
                )
                wallet = choose_shni_wallet(snapshot, ipo, applicant, quote, others)
                if wallet is None:
                    continue
                rows[index] = replace(
                    row,
                    category="SHNI",
                    lots=quote.lots,
                    amount=quote.amount,
                    bank_id=wallet.bank_id,
                    upi_id=wallet.upi_id,
                    warnings=wallet.warnings,
                )
                changed = True
            if ipo.mode != "SHNI_PREFERRED" or not changed:
                break
    return CoverageResult(tuple(rows), coverage.uncovered)
