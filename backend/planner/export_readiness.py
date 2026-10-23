"""Fail closed before converting a saved plan into an external file."""

from django.core.exceptions import ValidationError

from funding.models import BankAccount
from funding.restrictions import restricted_bank_names
from planner.models import PlanRun
from planner.plan_window import stored_snapshot_is_planning_only
from planner.policies import bank_policy


def assert_exportable_plan(
    plan_run: PlanRun, *, ipo_id: str | None = None, allow_record_only: bool = False
) -> None:
    if (
        plan_run.status != PlanRun.Status.READY
        or plan_run.audit_issues
        or plan_run.rows.filter(blocking_reasons__isnull=False)
        .exclude(blocking_reasons=[])
        .exists()
    ):
        raise ValidationError("Resolve blocking plan issues before export")
    if not allow_record_only and stored_snapshot_is_planning_only(plan_run.input_snapshot):
        raise ValidationError(
            "This IPO is closed. Closing-day plans are for record keeping and cannot be exported."
        )
    assert_current_bank_funding_rules(plan_run, ipo_id=ipo_id)


def assert_current_bank_funding_rules(plan_run: PlanRun, *, ipo_id: str | None = None) -> None:
    """Reject new use of saved cross-funded mappings after a bank rule changes."""
    rows = plan_run.rows.all()
    if ipo_id is not None:
        rows = rows.filter(ipo_ref=ipo_id)
    mappings = list(rows.values_list("bank_ref", "applicant_ref"))
    banks = {
        str(bank.pk): bank
        for bank in BankAccount.objects.filter(
            workspace=plan_run.workspace, pk__in={bank_id for bank_id, _ in mappings}
        )
    }
    restricted_names = restricted_bank_names()
    for bank_id, applicant_id in mappings:
        bank = banks.get(bank_id)
        if bank is None:
            continue
        if (
            str(bank.owner_id) != applicant_id
            and bank_policy(bank, restricted_names=restricted_names) == "DISALLOW"
        ):
            raise ValidationError(
                "This bank no longer allows cross-funding. Re-plan before exporting."
            )
