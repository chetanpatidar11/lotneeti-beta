"""Replay proposed rows from a frozen snapshot without optimizer counters."""

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from funding.policy import resolve_cross_funding_policy
from planner.cash import PlannedAllocation, cash_at_cutoff, expected_release_at
from planner.coverage import CoverageRow
from planner.dto import PlannerSnapshot, RollingUsageInput, application_cutoff
from planner.rolling import RollingLimitTracker


@dataclass(frozen=True, slots=True)
class AuditIssue:
    code: str
    ipo_id: str = ""
    applicant_id: str = ""
    message: str = ""


@dataclass(frozen=True, slots=True)
class AuditResult:
    valid: bool
    issues: tuple[AuditIssue, ...]
    planned_total: Decimal


def audit_plan(
    snapshot: PlannerSnapshot,
    rows: tuple[CoverageRow, ...],
    *,
    reported_planned_total: Decimal,
) -> AuditResult:
    issues: list[AuditIssue] = []
    ipo_by_id = {ipo.id: ipo for ipo in snapshot.ipos if ipo.selected}
    applicant_by_id = {applicant.id: applicant for applicant in snapshot.applicants}
    demat_by_id = {demat.id: demat for demat in snapshot.demats}
    bank_by_id = {bank.id: bank for bank in snapshot.banks}
    upi_by_id = {upi.id: upi for upi in snapshot.upis}
    existing = {
        (item.ipo_id, item.applicant_id)
        for item in snapshot.existing_applications
        if not item.cancelled
    }
    counts = Counter((row.ipo_id, row.applicant_id) for row in rows)
    for ipo_id, applicant_id in sorted(counts):
        if counts[(ipo_id, applicant_id)] > 1 or (ipo_id, applicant_id) in existing:
            issues.append(
                AuditIssue(
                    "DUPLICATE_APPLICANT_IPO",
                    ipo_id,
                    applicant_id,
                    "An applicant can have only one application for an IPO.",
                )
            )

    for locked in sorted(
        snapshot.locked_rows, key=lambda row: (row.ipo_id, row.applicant_id, row.id)
    ):
        if locked.ipo_id not in ipo_by_id:
            continue
        matches = [
            row
            for row in rows
            if row.ipo_id == locked.ipo_id and row.applicant_id == locked.applicant_id
        ]
        if (
            len(matches) != 1
            or not matches[0].locked
            or any(
                getattr(matches[0], field) != getattr(locked, field)
                for field in ("category", "lots", "amount", "demat_id", "bank_id", "upi_id")
            )
        ):
            issues.append(
                AuditIssue(
                    "LOCKED_ROW_CHANGED",
                    locked.ipo_id,
                    locked.applicant_id,
                    "A locked application was changed or removed.",
                )
            )

    allocations = tuple(
        PlannedAllocation(
            id=f"{index}:{row.ipo_id}:{row.applicant_id}",
            bank_id=row.bank_id,
            amount=row.amount,
            cutoff_at=application_cutoff(ipo_by_id[row.ipo_id], row.category),
            release_at=expected_release_at(
                ipo_by_id[row.ipo_id].allotment_date,
                application_cutoff(ipo_by_id[row.ipo_id], row.category).tzinfo,
            ),
        )
        for index, row in enumerate(rows)
        if row.ipo_id in ipo_by_id and row.amount > 0
    )
    plan_usage = tuple(
        RollingUsageInput(
            id=f"audit:{index}:{row.ipo_id}:{row.applicant_id}",
            bank_id=row.bank_id,
            upi_id=row.upi_id,
            amount=row.amount,
            submitted_at=application_cutoff(ipo_by_id[row.ipo_id], row.category),
            cancelled=False,
        )
        for index, row in enumerate(rows)
        if row.ipo_id in ipo_by_id and row.amount > 0
    )
    for index, row in sorted(
        enumerate(rows), key=lambda pair: (pair[1].ipo_id, pair[1].applicant_id, pair[0])
    ):

        def issue(
            code: str,
            message: str,
            ipo_id: str = row.ipo_id,
            applicant_id: str = row.applicant_id,
        ) -> None:
            issues.append(AuditIssue(code, ipo_id, applicant_id, message))

        ipo = ipo_by_id.get(row.ipo_id)
        applicant = applicant_by_id.get(row.applicant_id)
        demat = demat_by_id.get(row.demat_id)
        bank = bank_by_id.get(row.bank_id)
        upi = upi_by_id.get(row.upi_id)
        if ipo is None:
            issue("IPO_NOT_SELECTED", "This IPO is not selected for the plan.")
            continue
        if applicant is None or not applicant.active:
            issue("APPLICANT_INACTIVE", "This applicant is inactive or missing.")
        if demat is None or not demat.active or demat.applicant_id != row.applicant_id:
            issue("INVALID_DEMAT", "This demat cannot be used by the applicant.")
        if bank is None or not bank.active:
            issue("INVALID_BANK", "This bank account is inactive or missing.")
        elif bank.restricted_applicant_id not in (None, row.applicant_id):
            issue("BANK_PAN_RESTRICTED", "This bank account is restricted to another applicant.")
        if upi is None or not upi.active or not upi.verified or upi.bank_id != row.bank_id:
            issue("INVALID_UPI", "This UPI cannot be used with this bank account.")
        if row.category not in {"RETAIL", "SHNI"} or type(row.lots) is not int or row.lots < 1:
            issue("INVALID_CATEGORY", "Choose a valid category and whole-lot amount.")
        else:
            expected_amount = ipo.upper_price * ipo.lot_size * row.lots
            if row.amount != expected_amount or row.amount <= 0:
                issue("INVALID_AMOUNT", "The application amount does not match its lots.")
            if row.category == "RETAIL" and row.lots != 1:
                issue("INVALID_CATEGORY", "Retail applications use exactly one lot.")
            if row.category == "SHNI" and row.amount <= Decimal("200000.00"):
                issue("INVALID_CATEGORY", "sHNI applications must exceed ₹2,00,000.")
        if row.locked and row.blocking_reasons:
            issue("LOCKED_ROW_INFEASIBLE", "A locked mapping has a blocking issue.")
        if bank is not None and applicant is not None:
            policy = resolve_cross_funding_policy(
                platform_default=snapshot.config.platform_cross_funding_policy,
                bank_policy=bank.cross_funding_policy,
                workspace_policy=snapshot.config.workspace_cross_funding_policy,
                plan_override=snapshot.config.plan_cross_funding_override,
                locked_row=row.locked,
                same_owner=bank.owner_id == applicant.id,
            )
            if not policy.allowed_for_automation:
                issue("CROSS_FUNDING_DISALLOWED", "This bank cannot fund the applicant.")
        if bank is not None and row.amount > 0:
            others = tuple(item for item in allocations if not item.id.startswith(f"{index}:"))
            if (
                cash_at_cutoff(
                    bank=bank,
                    cutoff=application_cutoff(ipo, row.category),
                    blocks=snapshot.cash_blocks,
                    allocations=others,
                    recurring_debits=snapshot.recurring_debits,
                ).raw_available
                < row.amount
            ):
                issue("CASH_OVERSPEND", "This bank does not have enough money at the cutoff.")
        if upi is not None and row.amount > 0:
            other_usage = tuple(
                item for item in plan_usage if not item.id.startswith(f"audit:{index}:")
            )
            rolling = RollingLimitTracker(snapshot.rolling_usage + other_usage).check(
                upi=upi,
                amount=row.amount,
                at=application_cutoff(ipo, row.category),
                config=snapshot.config,
            )
            for reason in rolling.blocking_reasons:
                issue(reason, "The rolling application limit is exceeded.")

    total = sum((row.amount for row in rows), Decimal("0.00"))
    if reported_planned_total != total:
        issues.append(
            AuditIssue("PLANNED_TOTAL_MISMATCH", message="Planned does not match the plan rows.")
        )
    return AuditResult(valid=not issues, issues=tuple(issues), planned_total=total)
