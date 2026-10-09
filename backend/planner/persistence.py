"""Transactional, tenant-scoped storage for generated plan proposals."""

from dataclasses import asdict
from hashlib import sha256

from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import WorkspaceMembership
from core.audit import record_event
from funding.models import BankAccount, UPIHandle
from investors.models import DematAccount, Investor
from ipos.models import IPO
from planner.audit import AuditResult
from planner.coverage import CoverageRow
from planner.dto import PlannerSnapshot, canonical_json
from planner.engine import PLANNER_VERSION, generate_proposal
from planner.models import PlanRow, PlanRun


def _verify_scope(workspace, snapshot: PlannerSnapshot) -> None:
    checks = (
        (
            {item.id for item in snapshot.applicants},
            Investor.objects.filter(workspace=workspace),
            "applicants",
        ),
        (
            {item.id for item in snapshot.demats},
            DematAccount.objects.filter(investor__workspace=workspace),
            "demats",
        ),
        (
            {item.id for item in snapshot.banks},
            BankAccount.objects.filter(workspace=workspace),
            "banks",
        ),
        (
            {item.id for item in snapshot.upis},
            UPIHandle.objects.filter(bank__workspace=workspace),
            "UPIs",
        ),
        ({item.id for item in snapshot.ipos}, IPO.objects.all(), "IPOs"),
    )
    for ids, queryset, label in checks:
        if (
            ids
            and set(str(pk) for pk in queryset.filter(pk__in=ids).values_list("pk", flat=True))
            != ids
        ):
            raise ValidationError(f"Planner snapshot contains unknown or out-of-workspace {label}")
    bank_ids = {item.id for item in snapshot.banks}
    upi_ids = {item.id for item in snapshot.upis}
    applicant_ids = {item.id for item in snapshot.applicants}
    if any(item.bank_id not in bank_ids for item in snapshot.cash_blocks):
        raise ValidationError("Cash block bank is outside the snapshot")
    if any(
        item.bank_id not in bank_ids or item.upi_id not in upi_ids
        for item in snapshot.rolling_usage
    ):
        raise ValidationError("Rolling usage is outside the snapshot")
    if any(item.bank_id not in bank_ids for item in snapshot.recurring_debits):
        raise ValidationError("Scheduled payment bank is outside the snapshot")
    if any(
        item.bank_id not in bank_ids or item.beneficiary_id not in applicant_ids
        for item in snapshot.funding_preferences
    ):
        raise ValidationError("Funding preference is outside the snapshot")


@transaction.atomic
def create_plan_run(*, workspace, snapshot: PlannerSnapshot, actor=None) -> PlanRun:
    if (
        actor is not None
        and not WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=actor,
            role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
        ).exists()
    ):
        raise ValidationError("This member cannot generate a plan for the workspace")
    _verify_scope(workspace, snapshot)
    proposal = generate_proposal(snapshot)
    plan_run = PlanRun.objects.create(
        workspace=workspace,
        generated_by=actor,
        planner_version=proposal.planner_version,
        settings_version=proposal.settings_version,
        input_snapshot_hash=proposal.input_snapshot_hash,
        output_hash=proposal.output_hash,
        input_snapshot=canonical_json(snapshot),
        status=PlanRun.Status.READY if proposal.audit.valid else PlanRun.Status.BLOCKED,
        planned_total=proposal.audit.planned_total,
        audit_issues=[asdict(issue) for issue in proposal.audit.issues],
        uncovered=[asdict(item) for item in proposal.coverage.uncovered],
    )
    PlanRow.objects.bulk_create(
        [
            PlanRow(
                plan_run=plan_run,
                position=position,
                ipo_ref=row.ipo_id,
                applicant_ref=row.applicant_id,
                category=row.category,
                lots=row.lots,
                amount=row.amount,
                demat_ref=row.demat_id,
                bank_ref=row.bank_id,
                upi_ref=row.upi_id,
                locked=row.locked,
                warnings=list(row.warnings),
                blocking_reasons=list(row.blocking_reasons),
                reasons=[asdict(reason) for reason in row.reasons],
            )
            for position, row in enumerate(proposal.coverage.rows)
        ]
    )
    record_event(
        action="planner.run.generated",
        target=plan_run,
        actor=actor,
        workspace=workspace,
        metadata={"status": plan_run.status, "row_count": len(proposal.coverage.rows)},
    )
    return plan_run


@transaction.atomic
def create_reviewed_plan_run(
    *,
    workspace,
    snapshot: PlannerSnapshot,
    rows: tuple[CoverageRow, ...],
    audit: AuditResult,
    actor,
) -> PlanRun:
    if not WorkspaceMembership.objects.filter(
        workspace=workspace,
        user=actor,
        role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
    ).exists():
        raise ValidationError("This member cannot save a plan for the workspace")
    _verify_scope(workspace, snapshot)
    refs = (
        ({row.applicant_id for row in rows}, {item.id for item in snapshot.applicants}),
        ({row.demat_id for row in rows}, {item.id for item in snapshot.demats}),
        ({row.bank_id for row in rows}, {item.id for item in snapshot.banks}),
        ({row.upi_id for row in rows}, {item.id for item in snapshot.upis}),
    )
    if any(not used <= known for used, known in refs):
        raise ValidationError("A plan mapping is outside this workspace")
    if audit.planned_total != sum((row.amount for row in rows), 0):
        raise ValidationError("Plan total differs from reviewed rows")
    input_text = canonical_json((snapshot, rows))
    plan_run = PlanRun.objects.create(
        workspace=workspace,
        generated_by=actor,
        planner_version=PLANNER_VERSION,
        settings_version=f"sha256:{sha256(canonical_json(snapshot.config).encode()).hexdigest()}",
        input_snapshot_hash=sha256(input_text.encode()).hexdigest(),
        output_hash=sha256(canonical_json((PLANNER_VERSION, rows, audit)).encode()).hexdigest(),
        input_snapshot=input_text,
        status=PlanRun.Status.READY if audit.valid else PlanRun.Status.BLOCKED,
        planned_total=audit.planned_total,
        audit_issues=[asdict(issue) for issue in audit.issues],
        uncovered=[],
    )
    issues_by_row = {}
    for issue in audit.issues:
        issues_by_row.setdefault((issue.ipo_id, issue.applicant_id), []).append(issue.code)
    PlanRow.objects.bulk_create(
        [
            PlanRow(
                plan_run=plan_run,
                position=position,
                ipo_ref=row.ipo_id,
                applicant_ref=row.applicant_id,
                category=row.category,
                lots=row.lots,
                amount=row.amount,
                demat_ref=row.demat_id,
                bank_ref=row.bank_id,
                upi_ref=row.upi_id,
                locked=row.locked,
                warnings=list(row.warnings),
                blocking_reasons=issues_by_row.get((row.ipo_id, row.applicant_id), []),
                reasons=[asdict(reason) for reason in row.reasons],
            )
            for position, row in enumerate(rows)
        ]
    )
    record_event(
        action="planner.run.reviewed",
        target=plan_run,
        actor=actor,
        workspace=workspace,
        metadata={"status": plan_run.status, "row_count": len(rows)},
    )
    return plan_run
