"""Preserve selected manual locks and surface their current feasibility."""

from collections import Counter
from decimal import Decimal

from funding.policy import resolve_cross_funding_policy
from planner.cash import PlannedAllocation, cash_at_cutoff, expected_release_at
from planner.coverage import CoverageResult, CoverageRow
from planner.dto import PlannerSnapshot, RollingUsageInput, application_cutoff
from planner.rolling import RollingLimitTracker


def locked_coverage(snapshot: PlannerSnapshot) -> CoverageResult:
    ipos = {ipo.id: ipo for ipo in snapshot.ipos if ipo.selected}
    applicants = {applicant.id: applicant for applicant in snapshot.applicants}
    demats = {demat.id: demat for demat in snapshot.demats}
    banks = {bank.id: bank for bank in snapshot.banks}
    upis = {upi.id: upi for upi in snapshot.upis}
    selected = tuple(
        sorted(
            (row for row in snapshot.locked_rows if row.ipo_id in ipos),
            key=lambda row: (row.ipo_id, row.applicant_id, row.id),
        )
    )
    duplicate_counts = Counter((row.ipo_id, row.applicant_id) for row in selected)
    existing = {
        (app.ipo_id, app.applicant_id)
        for app in snapshot.existing_applications
        if not app.cancelled
    }
    rows = []
    for locked in selected:
        ipo = ipos[locked.ipo_id]
        applicant = applicants.get(locked.applicant_id)
        demat = demats.get(locked.demat_id)
        bank = banks.get(locked.bank_id)
        upi = upis.get(locked.upi_id)
        reasons = []
        warnings = ()
        key = (locked.ipo_id, locked.applicant_id)
        if duplicate_counts[key] > 1 or key in existing:
            reasons.append("DUPLICATE_APPLICANT_IPO")
        if applicant is None or not applicant.active:
            reasons.append("APPLICANT_INACTIVE")
        if demat is None or not demat.active or demat.applicant_id != locked.applicant_id:
            reasons.append("INVALID_DEMAT")
        if bank is None or not bank.active:
            reasons.append("INVALID_BANK")
        elif bank.restricted_applicant_id not in (None, locked.applicant_id):
            reasons.append("BANK_PAN_RESTRICTED")
        if upi is None or not upi.active or not upi.verified or upi.bank_id != locked.bank_id:
            reasons.append("INVALID_UPI")
        if locked.category not in {"RETAIL", "SHNI"} or locked.lots < 1:
            reasons.append("INVALID_CATEGORY")
        else:
            expected_amount = ipo.upper_price * ipo.lot_size * locked.lots
            if locked.amount != expected_amount or locked.amount <= 0:
                reasons.append("INVALID_AMOUNT")
            if locked.category == "RETAIL" and locked.lots != 1:
                reasons.append("INVALID_CATEGORY")
            if locked.category == "SHNI" and locked.amount <= Decimal("200000.00"):
                reasons.append("INVALID_CATEGORY")
        if bank is not None and applicant is not None:
            policy = resolve_cross_funding_policy(
                platform_default=snapshot.config.platform_cross_funding_policy,
                bank_policy=bank.cross_funding_policy,
                workspace_policy=snapshot.config.workspace_cross_funding_policy,
                plan_override=snapshot.config.plan_cross_funding_override,
                locked_row=True,
                same_owner=bank.owner_id == applicant.id,
            )
            warnings = policy.warnings
            reasons.extend(policy.blocking_reasons)
        other_locks = tuple(row for row in selected if row.id != locked.id and row.ipo_id in ipos)
        allocations = tuple(
            PlannedAllocation(
                id=row.id,
                bank_id=row.bank_id,
                amount=row.amount,
                cutoff_at=application_cutoff(ipos[row.ipo_id], row.category),
                release_at=expected_release_at(
                    ipos[row.ipo_id].allotment_date,
                    application_cutoff(ipos[row.ipo_id], row.category).tzinfo,
                ),
            )
            for row in other_locks
            if row.amount > 0
        )
        if bank is not None and locked.amount > 0:
            available = cash_at_cutoff(
                bank=bank,
                cutoff=application_cutoff(ipo, locked.category),
                blocks=snapshot.cash_blocks,
                allocations=allocations,
                recurring_debits=snapshot.recurring_debits,
            ).raw_available
            if available < locked.amount:
                reasons.append("INSUFFICIENT_BALANCE")
        if upi is not None and locked.amount > 0:
            tracker = RollingLimitTracker(
                snapshot.rolling_usage
                + tuple(
                    RollingUsageInput(
                        id=f"locked:{row.id}",
                        bank_id=row.bank_id,
                        upi_id=row.upi_id,
                        amount=row.amount,
                        submitted_at=application_cutoff(ipos[row.ipo_id], row.category),
                        cancelled=False,
                    )
                    for row in other_locks
                    if row.amount > 0
                )
            )
            reasons.extend(
                tracker.check(
                    upi=upi,
                    amount=locked.amount,
                    at=application_cutoff(ipo, locked.category),
                    config=snapshot.config,
                ).blocking_reasons
            )
        if reasons:
            reasons.append("LOCKED_ROW_INFEASIBLE")
        rows.append(
            CoverageRow(
                ipo_id=locked.ipo_id,
                applicant_id=locked.applicant_id,
                category=locked.category,
                lots=locked.lots,
                amount=locked.amount,
                demat_id=locked.demat_id,
                bank_id=locked.bank_id,
                upi_id=locked.upi_id,
                warnings=warnings,
                locked=True,
                blocking_reasons=tuple(dict.fromkeys(reasons)),
            )
        )
    return CoverageResult(tuple(rows), ())
