"""Feasible Retail wallets, with own-name funding preferred."""

from funding.policy import resolve_cross_funding_policy
from planner.cash import PlannedAllocation, cash_at_cutoff, expected_release_at
from planner.coverage import CoverageRow, WalletChoice
from planner.dto import (
    ApplicantInput,
    IPOInput,
    PlannerSnapshot,
    RollingUsageInput,
    application_cutoff,
)
from planner.owner_reserve import cross_fundable_cash
from planner.quotes import Quote, minimum_shni_quote
from planner.rolling import RollingLimitTracker


def _choose_wallet(
    snapshot: PlannerSnapshot,
    ipo: IPOInput,
    applicant: ApplicantInput,
    quote: Quote,
    rows: tuple[CoverageRow, ...],
    *,
    shni: bool,
) -> WalletChoice | None:
    ipo_by_id = {item.id: item for item in snapshot.ipos}
    allocations = tuple(
        PlannedAllocation(
            id=f"{row.ipo_id}:{row.applicant_id}",
            bank_id=row.bank_id,
            amount=row.amount,
            cutoff_at=application_cutoff(ipo_by_id[row.ipo_id], row.category),
            release_at=expected_release_at(
                ipo_by_id[row.ipo_id].allotment_date,
                application_cutoff(ipo_by_id[row.ipo_id], row.category).tzinfo,
            ),
        )
        for row in rows
        if row.ipo_id in ipo_by_id and row.amount > 0
    )
    rolling = RollingLimitTracker(
        snapshot.rolling_usage
        + tuple(
            RollingUsageInput(
                id=f"planned:{row.ipo_id}:{row.applicant_id}",
                bank_id=row.bank_id,
                upi_id=row.upi_id,
                amount=row.amount,
                submitted_at=application_cutoff(ipo_by_id[row.ipo_id], row.category),
                cancelled=False,
            )
            for row in rows
            if row.ipo_id in ipo_by_id and row.amount > 0
        )
    )
    existing = {
        (item.ipo_id, item.applicant_id)
        for item in snapshot.existing_applications
        if not item.cancelled
    }
    preference_rank = {}
    for item in snapshot.funding_preferences:
        if item.beneficiary_id == applicant.id and item.enabled:
            preference_rank[item.bank_id] = min(
                item.priority, preference_rank.get(item.bank_id, item.priority)
            )
    candidates = []
    at = application_cutoff(ipo, "SHNI" if shni else "RETAIL")
    release_at = expected_release_at(ipo.allotment_date, at.tzinfo)
    minimum_shni_amount = minimum_shni_quote(ipo.upper_price, ipo.lot_size).amount
    for bank in snapshot.banks:
        if not bank.active or (
            bank.restricted_applicant_id is not None
            and bank.restricted_applicant_id != applicant.id
        ):
            continue
        same_owner = bank.owner_id == applicant.id
        policy = resolve_cross_funding_policy(
            platform_default=snapshot.config.platform_cross_funding_policy,
            bank_policy=bank.cross_funding_policy,
            workspace_policy=snapshot.config.workspace_cross_funding_policy,
            plan_override=snapshot.config.plan_cross_funding_override,
            same_owner=same_owner,
        )
        if not policy.allowed_for_automation:
            continue
        cash = cash_at_cutoff(
            bank=bank,
            cutoff=at,
            blocks=snapshot.cash_blocks,
            allocations=allocations,
            recurring_debits=snapshot.recurring_debits,
        )
        if cash.raw_available < quote.amount:
            continue
        owner = next((item for item in snapshot.applicants if item.id == bank.owner_id), None)
        owner_ipos = (
            tuple(
                item
                for item in snapshot.ipos
                if item.selected
                and (item.id, bank.owner_id) not in existing
                and any(
                    demat.active and demat.applicant_id == bank.owner_id
                    for demat in snapshot.demats
                )
            )
            if owner is not None and owner.active
            else ()
        )
        covered = frozenset(row.ipo_id for row in rows if row.applicant_id == bank.owner_id)
        owner_safe = (
            same_owner
            or cross_fundable_cash(
                bank=bank,
                at=at,
                release_at=release_at,
                owner_ipos=owner_ipos,
                covered_ipo_ids=covered,
                blocks=snapshot.cash_blocks,
                allocations=allocations,
                recurring_debits=snapshot.recurring_debits,
            )
            >= quote.amount
        )
        for upi in snapshot.upis:
            if upi.bank_id != bank.id or not upi.active or not upi.verified:
                continue
            limit_check = rolling.check(upi=upi, amount=quote.amount, at=at, config=snapshot.config)
            if not limit_check.allowed:
                continue
            upi_count_limit = (
                upi.count_limit_override
                if upi.count_limit_override is not None
                else snapshot.config.upi_count_limit
            )
            upi_amount_limit = (
                upi.amount_limit_override
                if upi.amount_limit_override is not None
                else snapshot.config.upi_amount_limit
            )
            count_headroom = upi_count_limit - limit_check.upi_count_after
            amount_headroom = upi_amount_limit - limit_check.upi_amount_after
            if snapshot.config.bank_level_enforcement:
                count_headroom = min(
                    count_headroom, snapshot.config.bank_count_limit - limit_check.bank_count_after
                )
                amount_headroom = min(
                    amount_headroom,
                    snapshot.config.bank_amount_limit - limit_check.bank_amount_after,
                )
            warnings = policy.warnings
            if not owner_safe:
                warnings += ("OWNER_RESERVE_TRADEOFF",)
            category_ranking = (
                (cash.raw_available - quote.amount, -count_headroom, -amount_headroom)
                if shni
                else (
                    cash.raw_available >= minimum_shni_amount,
                    -count_headroom,
                    -amount_headroom,
                    cash.raw_available,
                )
            )
            candidates.append(
                (
                    (
                        not same_owner,
                        not owner_safe,
                        bank.id not in preference_rank,
                        preference_rank.get(bank.id, 0),
                        upi.holder_id != applicant.id,
                        *category_ranking,
                        bank.id,
                        upi.id,
                    ),
                    WalletChoice(bank.id, upi.id, warnings),
                )
            )
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def choose_retail_wallet(
    snapshot: PlannerSnapshot,
    ipo: IPOInput,
    applicant: ApplicantInput,
    quote: Quote,
    rows: tuple[CoverageRow, ...],
) -> WalletChoice | None:
    return _choose_wallet(snapshot, ipo, applicant, quote, rows, shni=False)


def choose_shni_wallet(
    snapshot: PlannerSnapshot,
    ipo: IPOInput,
    applicant: ApplicantInput,
    quote: Quote,
    rows: tuple[CoverageRow, ...],
) -> WalletChoice | None:
    return _choose_wallet(snapshot, ipo, applicant, quote, rows, shni=True)
