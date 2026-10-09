"""Bounded, all-or-nothing Retail rehome for a failed sHNI upgrade."""

from dataclasses import replace
from itertools import combinations

from funding.policy import resolve_cross_funding_policy
from planner.cash import PlannedAllocation, cash_at_cutoff, expected_release_at
from planner.coverage import CoverageResult, CoverageRow
from planner.dto import PlannerSnapshot, RollingUsageInput, application_cutoff
from planner.manual_plan import review_manual_rows
from planner.ordering import selected_ipo_order
from planner.quotes import minimum_shni_quote, retail_quote
from planner.rolling import RollingLimitTracker
from planner.wallets import choose_retail_wallet, choose_shni_wallet

MAX_REHOME_ROWS = 2


def _rows_feasible(snapshot: PlannerSnapshot, rows: tuple[CoverageRow, ...]) -> bool:
    ipo_by_id = {ipo.id: ipo for ipo in snapshot.ipos}
    applicant_by_id = {applicant.id: applicant for applicant in snapshot.applicants}
    bank_by_id = {bank.id: bank for bank in snapshot.banks}
    upi_by_id = {upi.id: upi for upi in snapshot.upis}
    demat_by_id = {demat.id: demat for demat in snapshot.demats}
    if len({(row.ipo_id, row.applicant_id) for row in rows}) != len(rows):
        return False
    for index, row in enumerate(rows):
        ipo = ipo_by_id.get(row.ipo_id)
        applicant = applicant_by_id.get(row.applicant_id)
        bank = bank_by_id.get(row.bank_id)
        upi = upi_by_id.get(row.upi_id)
        demat = demat_by_id.get(row.demat_id)
        if any(item is None for item in (ipo, applicant, bank, upi, demat)):
            return False
        if (
            not applicant.active
            or not bank.active
            or not upi.active
            or not upi.verified
            or upi.bank_id != bank.id
            or not demat.active
            or demat.applicant_id != applicant.id
            or (
                bank.restricted_applicant_id is not None
                and bank.restricted_applicant_id != applicant.id
            )
        ):
            return False
        if row.blocking_reasons or row.category not in {"RETAIL", "SHNI"}:
            return False
        expected_amount = ipo.upper_price * ipo.lot_size * row.lots
        if row.lots < 1 or row.amount != expected_amount:
            return False
        if row.category == "RETAIL" and row.lots != 1:
            return False
        if row.category == "SHNI" and row.amount <= 200000:
            return False
        if not resolve_cross_funding_policy(
            platform_default=snapshot.config.platform_cross_funding_policy,
            bank_policy=bank.cross_funding_policy,
            workspace_policy=snapshot.config.workspace_cross_funding_policy,
            plan_override=snapshot.config.plan_cross_funding_override,
            same_owner=bank.owner_id == applicant.id,
        ).allowed_for_automation:
            return False
        others = tuple(other for other_index, other in enumerate(rows) if other_index != index)
        allocations = tuple(
            PlannedAllocation(
                id=f"{other.ipo_id}:{other.applicant_id}",
                bank_id=other.bank_id,
                amount=other.amount,
                cutoff_at=application_cutoff(ipo_by_id[other.ipo_id], other.category),
                release_at=expected_release_at(
                    ipo_by_id[other.ipo_id].allotment_date,
                    application_cutoff(ipo_by_id[other.ipo_id], other.category).tzinfo,
                ),
            )
            for other in others
        )
        if (
            cash_at_cutoff(
                bank=bank,
                cutoff=application_cutoff(ipo, row.category),
                blocks=snapshot.cash_blocks,
                allocations=allocations,
                recurring_debits=snapshot.recurring_debits,
            ).raw_available
            < row.amount
        ):
            return False
        tracker = RollingLimitTracker(
            snapshot.rolling_usage
            + tuple(
                RollingUsageInput(
                    id=f"planned:{other.ipo_id}:{other.applicant_id}",
                    bank_id=other.bank_id,
                    upi_id=other.upi_id,
                    amount=other.amount,
                    submitted_at=application_cutoff(ipo_by_id[other.ipo_id], other.category),
                    cancelled=False,
                )
                for other in others
            )
        )
        if not tracker.check(
            upi=upi,
            amount=row.amount,
            at=application_cutoff(ipo, row.category),
            config=snapshot.config,
        ).allowed:
            return False
    return True


def try_rehome_for_shni(
    snapshot: PlannerSnapshot,
    coverage: CoverageResult,
    *,
    ipo_id: str,
    applicant_id: str,
    max_moves: int = MAX_REHOME_ROWS,
) -> CoverageResult:
    if not 0 <= max_moves <= MAX_REHOME_ROWS:
        raise ValueError("Rehome limit is outside the configured bound")
    ipo_by_id = {ipo.id: ipo for ipo in snapshot.ipos}
    applicant_by_id = {applicant.id: applicant for applicant in snapshot.applicants}
    ipo = ipo_by_id[ipo_id]
    applicant = applicant_by_id[applicant_id]
    if ipo.mode not in {"RETAIL_PLUS_SHNI", "SHNI_PREFERRED"}:
        return coverage
    target = next(
        (
            row
            for row in coverage.rows
            if row.ipo_id == ipo_id
            and row.applicant_id == applicant_id
            and row.category == "RETAIL"
        ),
        None,
    )
    if target is None or target.locked:
        return coverage
    quote = minimum_shni_quote(ipo.upper_price, ipo.lot_size)
    for bank_id in sorted({row.bank_id for row in coverage.rows if row != target}):
        movable = sorted(
            (
                row
                for row in coverage.rows
                if row != target
                and row.category == "RETAIL"
                and not row.locked
                and row.bank_id == bank_id
            ),
            key=lambda row: (row.ipo_id, row.applicant_id),
        )
        for count in range(1, min(max_moves, len(movable)) + 1):
            for displaced in combinations(movable, count):
                removed = {target, *displaced}
                trial = [row for row in coverage.rows if row not in removed]
                wallet = choose_shni_wallet(snapshot, ipo, applicant, quote, tuple(trial))
                if wallet is None:
                    continue
                upgraded = replace(
                    target,
                    category="SHNI",
                    lots=quote.lots,
                    amount=quote.amount,
                    bank_id=wallet.bank_id,
                    upi_id=wallet.upi_id,
                    warnings=wallet.warnings,
                )
                trial.append(upgraded)
                replacements = {(target.ipo_id, target.applicant_id): upgraded}
                for row in displaced:
                    row_ipo = ipo_by_id[row.ipo_id]
                    row_applicant = applicant_by_id[row.applicant_id]
                    row_quote = retail_quote(row_ipo.upper_price, row_ipo.lot_size)
                    destination = choose_retail_wallet(
                        snapshot, row_ipo, row_applicant, row_quote, tuple(trial)
                    )
                    if destination is None:
                        break
                    moved = replace(
                        row,
                        bank_id=destination.bank_id,
                        upi_id=destination.upi_id,
                        warnings=destination.warnings,
                    )
                    trial.append(moved)
                    replacements[(row.ipo_id, row.applicant_id)] = moved
                else:
                    if not any(
                        replacements[(row.ipo_id, row.applicant_id)].bank_id != row.bank_id
                        for row in displaced
                    ):
                        continue
                    candidate = tuple(
                        replacements.get((row.ipo_id, row.applicant_id), row)
                        for row in coverage.rows
                    )
                    if _rows_feasible(snapshot, candidate):
                        return CoverageResult(candidate, coverage.uncovered)
    return coverage


def repair_shni_upgrades(snapshot: PlannerSnapshot, coverage: CoverageResult) -> CoverageResult:
    result = coverage
    applicants = {item.id: item for item in snapshot.applicants}
    for ipo in selected_ipo_order(snapshot.ipos):
        if ipo.mode not in {"RETAIL_PLUS_SHNI", "SHNI_PREFERRED"}:
            continue
        candidates = sorted(
            (
                row
                for row in result.rows
                if row.ipo_id == ipo.id and row.category == "RETAIL" and not row.locked
            ),
            key=lambda row: (applicants[row.applicant_id].priority, row.applicant_id),
        )
        for row in candidates:
            result = try_rehome_for_shni(
                snapshot, result, ipo_id=ipo.id, applicant_id=row.applicant_id
            )
    return result


def owner_affinity_cleanup(snapshot: PlannerSnapshot, coverage: CoverageResult) -> CoverageResult:
    """Swap equal-timeline wallets only when more applicants use their own bank."""
    rows = list(coverage.rows)
    ipos = {ipo.id: ipo for ipo in snapshot.ipos}
    banks = {bank.id: bank for bank in snapshot.banks}

    def timeline(row: CoverageRow):
        ipo = ipos[row.ipo_id]
        cutoff = application_cutoff(ipo, row.category)
        return cutoff, expected_release_at(ipo.allotment_date, cutoff.tzinfo)

    while True:
        changed = False
        indices = sorted(
            range(len(rows)),
            key=lambda index: (
                rows[index].ipo_id,
                rows[index].applicant_id,
                rows[index].bank_id,
                rows[index].upi_id,
            ),
        )
        for first, second in combinations(indices, 2):
            left, right = rows[first], rows[second]
            if (
                left.locked
                or right.locked
                or left.bank_id == right.bank_id
                or left.amount != right.amount
                or timeline(left) != timeline(right)
            ):
                continue
            before = int(banks[left.bank_id].owner_id == left.applicant_id) + int(
                banks[right.bank_id].owner_id == right.applicant_id
            )
            after = int(banks[right.bank_id].owner_id == left.applicant_id) + int(
                banks[left.bank_id].owner_id == right.applicant_id
            )
            if after <= before:
                continue
            candidate = rows.copy()
            candidate[first] = replace(
                left, bank_id=right.bank_id, upi_id=right.upi_id, warnings=()
            )
            candidate[second] = replace(
                right, bank_id=left.bank_id, upi_id=left.upi_id, warnings=()
            )
            if not _rows_feasible(snapshot, tuple(candidate)):
                continue
            reviewed, audit = review_manual_rows(
                snapshot,
                [
                    {
                        "ipo": row.ipo_id,
                        "applicant": row.applicant_id,
                        "category": row.category,
                        "lots": row.lots,
                        "amount": row.amount,
                        "demat": row.demat_id,
                        "bank": row.bank_id,
                        "upi": row.upi_id,
                        "locked": row.locked,
                    }
                    for row in candidate
                ],
            )
            if not audit.valid:
                continue
            rows = [
                replace(row, warnings=reviewed[index].warnings)
                for index, row in enumerate(candidate)
            ]
            changed = True
            break
        if not changed:
            return CoverageResult(tuple(rows), coverage.uncovered)
