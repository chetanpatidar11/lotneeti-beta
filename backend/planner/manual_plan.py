"""Recheck the exact rows a member reviewed before saving or exporting."""

from dataclasses import replace
from decimal import Decimal

from django.core.exceptions import ValidationError

from funding.policy import resolve_cross_funding_policy
from planner.audit import audit_plan
from planner.cash import PlannedAllocation, expected_release_at
from planner.coverage import CoverageRow
from planner.dto import application_cutoff
from planner.owner_reserve import cross_fundable_cash


def review_manual_rows(snapshot, edited_rows):
    selected = {ipo.id: ipo for ipo in snapshot.ipos}
    applicants = {item.id: item for item in snapshot.applicants}
    banks = {item.id: item for item in snapshot.banks}
    rows = []
    for item in edited_rows:
        ipo_id = str(item["ipo"])
        applicant_id = str(item["applicant"])
        bank_id = str(item["bank"])
        ipo = selected.get(ipo_id)
        if ipo is None:
            raise ValidationError("A row refers to an unselected IPO.")
        amount = item.get("amount", ipo.upper_price * ipo.lot_size * item["lots"])
        bank = banks.get(bank_id)
        applicant = applicants.get(applicant_id)
        warnings = ()
        if bank is not None and applicant is not None:
            warnings = resolve_cross_funding_policy(
                platform_default=snapshot.config.platform_cross_funding_policy,
                bank_policy=bank.cross_funding_policy,
                workspace_policy=snapshot.config.workspace_cross_funding_policy,
                plan_override=snapshot.config.plan_cross_funding_override,
                locked_row=item["locked"],
                same_owner=bank.owner_id == applicant.id,
            ).warnings
        rows.append(
            CoverageRow(
                ipo_id=ipo_id,
                applicant_id=applicant_id,
                category=item["category"],
                lots=item["lots"],
                amount=amount,
                demat_id=str(item["demat"]),
                bank_id=bank_id,
                upi_id=str(item["upi"]),
                locked=item["locked"],
                warnings=warnings,
            )
        )
    for index, row in enumerate(rows):
        bank = banks.get(row.bank_id)
        if bank is None or bank.owner_id == row.applicant_id:
            continue
        ipo = selected[row.ipo_id]
        owner = applicants.get(bank.owner_id)
        owner_ipos = (
            tuple(
                item
                for item in snapshot.ipos
                if item.selected
                and any(
                    demat.active and demat.applicant_id == bank.owner_id
                    for demat in snapshot.demats
                )
            )
            if owner is not None and owner.active
            else ()
        )
        other_rows = [other for other_index, other in enumerate(rows) if other_index != index]
        allocations = tuple(
            PlannedAllocation(
                id=f"{other.ipo_id}:{other.applicant_id}",
                bank_id=other.bank_id,
                amount=other.amount,
                cutoff_at=application_cutoff(selected[other.ipo_id], other.category),
                release_at=expected_release_at(
                    selected[other.ipo_id].allotment_date,
                    application_cutoff(selected[other.ipo_id], other.category).tzinfo,
                ),
            )
            for other in other_rows
            if other.amount > 0
        )
        at = application_cutoff(ipo, row.category)
        if (
            cross_fundable_cash(
                bank=bank,
                at=at,
                release_at=expected_release_at(ipo.allotment_date, at.tzinfo),
                owner_ipos=owner_ipos,
                covered_ipo_ids=frozenset(
                    other.ipo_id for other in other_rows if other.applicant_id == bank.owner_id
                ),
                blocks=snapshot.cash_blocks,
                allocations=allocations,
                recurring_debits=snapshot.recurring_debits,
            )
            < row.amount
        ):
            rows[index] = replace(row, warnings=(*row.warnings, "OWNER_RESERVE_TRADEOFF"))
    total = sum((row.amount for row in rows), Decimal("0.00"))
    audit = audit_plan(snapshot, tuple(rows), reported_planned_total=total)
    return tuple(rows), audit
