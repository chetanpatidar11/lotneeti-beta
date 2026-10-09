"""Ordered plain-language explanations for automatic plan rows."""

from dataclasses import replace

from planner.coverage import CoverageResult, CoverageRow, PlanReason
from planner.dto import PlannerSnapshot


def explain_row(snapshot: PlannerSnapshot, row: CoverageRow) -> tuple[PlanReason, ...]:
    if row.locked:
        return ()
    applicants = {item.id: item for item in snapshot.applicants}
    banks = {item.id: item for item in snapshot.banks}
    applicant = applicants[row.applicant_id]
    bank = banks[row.bank_id]
    reasons = [
        PlanReason(
            "APPLICANT_PRIORITY",
            f"Applicant priority {applicant.priority}.",
            (("priority", str(applicant.priority)),),
        )
    ]
    if bank.owner_id == applicant.id:
        reasons.append(PlanReason("OWN_FUNDING", "Uses this applicant's own bank account."))
    else:
        reasons.append(PlanReason("OWN_WALLET_UNAVAILABLE", "Own funding was unavailable."))
        preferences = sorted(
            (
                item
                for item in snapshot.funding_preferences
                if item.beneficiary_id == applicant.id and item.bank_id == bank.id and item.enabled
            ),
            key=lambda item: (item.priority, item.bank_id),
        )
        if preferences:
            rank = preferences[0].priority
            reasons.append(
                PlanReason(
                    "PREFERRED_CROSS_FUNDER",
                    f"Uses preferred funding bank {rank}.",
                    (("priority", str(rank)), ("bank_id", bank.id)),
                )
            )
        else:
            reasons.append(
                PlanReason("OTHER_CROSS_FUNDER", "Uses another permitted funding account.")
            )
        if "OWNER_RESERVE_TRADEOFF" in row.warnings:
            reasons.append(
                PlanReason(
                    "OWNER_CASH_CONFLICT",
                    "This may leave the bank owner short for another selected IPO.",
                )
            )
        else:
            reasons.append(
                PlanReason(
                    "OWNER_CASH_PROTECTED",
                    "The bank owner's selected IPO money remains protected.",
                )
            )
    if row.category == "SHNI":
        reasons.append(PlanReason("MINIMUM_SHNI", "Uses the minimum whole-lot sHNI amount."))
    reasons.append(PlanReason("ROLLING_LIMIT_ROOM", "Bank and UPI application limits have room."))
    return tuple(reasons)


def explain_rows(snapshot: PlannerSnapshot, coverage: CoverageResult) -> CoverageResult:
    return CoverageResult(
        rows=tuple(
            row if row.locked else replace(row, reasons=explain_row(snapshot, row))
            for row in coverage.rows
        ),
        uncovered=coverage.uncovered,
    )
