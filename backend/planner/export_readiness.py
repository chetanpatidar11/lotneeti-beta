"""Fail closed before converting a saved plan into an external file."""

from django.core.exceptions import ValidationError

from planner.models import PlanRun


def assert_exportable_plan(plan_run: PlanRun) -> None:
    if (
        plan_run.status != PlanRun.Status.READY
        or plan_run.audit_issues
        or plan_run.rows.filter(blocking_reasons__isnull=False)
        .exclude(blocking_reasons=[])
        .exists()
    ):
        raise ValidationError("Resolve blocking plan issues before export")
