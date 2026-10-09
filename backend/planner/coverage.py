"""Baseline one-lot Retail coverage in IPO and applicant priority order."""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from planner.dto import ApplicantInput, IPOInput, PlannerSnapshot
from planner.ordering import selected_ipo_order
from planner.quotes import Quote, retail_quote


@dataclass(frozen=True, slots=True)
class WalletChoice:
    bank_id: str
    upi_id: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanReason:
    code: str
    message: str
    data: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class CoverageRow:
    ipo_id: str
    applicant_id: str
    category: str
    lots: int
    amount: Decimal
    demat_id: str
    bank_id: str
    upi_id: str
    warnings: tuple[str, ...] = ()
    locked: bool = False
    blocking_reasons: tuple[str, ...] = ()
    reasons: tuple[PlanReason, ...] = ()


@dataclass(frozen=True, slots=True)
class UncoveredApplicant:
    ipo_id: str
    applicant_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class CoverageResult:
    rows: tuple[CoverageRow, ...]
    uncovered: tuple[UncoveredApplicant, ...]


WalletSelector = Callable[
    [PlannerSnapshot, IPOInput, ApplicantInput, Quote, tuple[CoverageRow, ...]], WalletChoice | None
]


def baseline_retail_coverage(
    snapshot: PlannerSnapshot,
    choose_wallet: WalletSelector,
    initial_rows: tuple[CoverageRow, ...] = (),
) -> CoverageResult:
    rows: list[CoverageRow] = list(initial_rows)
    uncovered: list[UncoveredApplicant] = []
    existing = {
        (app.ipo_id, app.applicant_id)
        for app in snapshot.existing_applications
        if not app.cancelled
    }
    locked = {(row.ipo_id, row.applicant_id) for row in snapshot.locked_rows}
    seen = existing | locked | {(row.ipo_id, row.applicant_id) for row in initial_rows}
    for ipo in selected_ipo_order(snapshot.ipos):
        for applicant in sorted(snapshot.applicants, key=lambda item: (item.priority, item.id)):
            key = (ipo.id, applicant.id)
            if not applicant.active or key in seen:
                continue
            if ipo.mode == "CUSTOM":
                uncovered.append(
                    UncoveredApplicant(ipo.id, applicant.id, "CUSTOM_CATEGORY_REQUIRED")
                )
                continue
            demats = sorted(
                (
                    demat
                    for demat in snapshot.demats
                    if demat.applicant_id == applicant.id and demat.active
                ),
                key=lambda demat: demat.id,
            )
            if not demats:
                uncovered.append(UncoveredApplicant(ipo.id, applicant.id, "NO_ACTIVE_DEMAT"))
                continue
            quote = retail_quote(ipo.upper_price, ipo.lot_size)
            wallet = choose_wallet(snapshot, ipo, applicant, quote, tuple(rows))
            if wallet is None:
                uncovered.append(UncoveredApplicant(ipo.id, applicant.id, "NO_FEASIBLE_WALLET"))
                continue
            rows.append(
                CoverageRow(
                    ipo_id=ipo.id,
                    applicant_id=applicant.id,
                    category="RETAIL",
                    lots=quote.lots,
                    amount=quote.amount,
                    demat_id=demats[0].id,
                    bank_id=wallet.bank_id,
                    upi_id=wallet.upi_id,
                    warnings=wallet.warnings,
                )
            )
            seen.add(key)
    return CoverageResult(tuple(rows), tuple(uncovered))
