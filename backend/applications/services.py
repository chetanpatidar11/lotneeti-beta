"""Workspace-authorized application tracking and mandate transitions."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from accounts.models import Workspace, WorkspaceMembership
from applications.models import Application
from applications.quota_rules import validate_quota_mapping
from core.audit import record_event
from core.beta_events import record_beta_event
from core.models import BetaEvent
from funding.models import BalanceChange, BankAccount, UPIHandle
from investors.models import DematAccount, Investor
from ipos.models import IPO
from planner.dto import PlannerConfig, RollingUsageInput, UPIInput
from planner.engine import PLANNER_VERSION
from planner.export_readiness import assert_exportable_plan
from planner.models import PlanRun
from planner.policies import bank_policy
from planner.rolling import RollingLimitTracker


def _require_writer(workspace, actor):
    if not WorkspaceMembership.objects.filter(
        workspace=workspace,
        user=actor,
        role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
    ).exists():
        raise ValidationError("This member cannot update applications")


@transaction.atomic
def start_tracking_plan(
    *, plan_run, actor, row_ids=None, record_only=False
) -> tuple[Application, ...]:
    workspace = Workspace.objects.select_for_update().get(pk=plan_run.workspace_id)
    _require_writer(workspace, actor)
    if record_only:
        plan_run = PlanRun.objects.select_for_update().get(pk=plan_run.pk, workspace=workspace)
        if plan_run.status not in {PlanRun.Status.READY, PlanRun.Status.BLOCKED}:
            raise ValidationError("This saved plan is no longer available")
        if PlanRun.objects.filter(workspace=workspace).first().pk != plan_run.pk:
            raise ValidationError("This plan is no longer current. Refresh Applications.")
    else:
        assert_exportable_plan(plan_run, allow_record_only=True)
    rows = list(plan_run.rows.all())
    requested = set(row_ids) if row_ids is not None else None
    eligible = [
        row
        for row in rows
        if plan_run.reserved_ipo_ids is None or row.ipo_ref in plan_run.reserved_ipo_ids
    ]
    if requested is not None and requested != {row.pk for row in eligible if row.pk in requested}:
        raise ValidationError("One or more planned applications are unavailable")
    tracked = []
    for row in eligible:
        if requested is not None and row.pk not in requested:
            continue
        if record_only:
            recordable_warnings = {
                "CASH_OVERSPEND",
                "INSUFFICIENT_BALANCE",
                "UPI_LIMIT_EXCEEDED",
                "BANK_LIMIT_EXCEEDED",
                "CROSS_FUNDING_DISALLOWED",
                "LOCKED_ROW_INFEASIBLE",
            }
            if set(row.blocking_reasons) - recordable_warnings:
                raise ValidationError(
                    "Correct the application's account, category or eligibility details "
                    "before recording it"
                )
        ipo = IPO.objects.get(pk=row.ipo_ref)
        applicant = Investor.objects.get(
            pk=row.applicant_ref, workspace=workspace, is_deleted=False
        )
        demat = DematAccount.objects.get(pk=row.demat_ref, investor__workspace=workspace)
        bank = BankAccount.objects.get(pk=row.bank_ref, workspace=workspace)
        upi = (
            UPIHandle.objects.get(pk=row.upi_ref, bank__workspace=workspace)
            if row.upi_ref
            else None
        )
        validate_quota_mapping(
            workspace=workspace,
            ipo=ipo,
            applicant_id=applicant.pk,
            category=row.category,
            lots=row.lots,
            amount=row.amount,
            bank=bank,
            upi=upi,
        )
        existing = (
            Application.objects.filter(workspace=workspace, ipo=ipo, applicant=applicant)
            .filter(Q(category="SHARE") if row.category == "SHARE" else ~Q(category="SHARE"))
            .exclude(status=Application.Status.CANCELLED)
            .first()
        )
        if existing is None and Application.objects.filter(plan_row=row).exists():
            raise ValidationError(
                "This plan row was cancelled. Create a new plan before tracking it again"
            )
        if existing is not None:
            if existing.plan_row_id != row.pk:
                raise ValidationError(
                    "This applicant already has a tracked application for this IPO"
                )
            tracked.append(existing)
            continue
        application = Application.objects.create(
            workspace=workspace,
            plan_row=row,
            ipo=ipo,
            applicant=applicant,
            demat=demat,
            bank=bank,
            upi=upi,
            category=row.category,
            lots=row.lots,
            amount=row.amount,
        )
        tracked.append(application)
        record_event(
            action="application.tracking_started",
            target=application,
            actor=actor,
            workspace=workspace,
            metadata={
                "status": application.status,
                "record_only": record_only,
                "plan_warnings": row.blocking_reasons if record_only else [],
            },
        )
    return tuple(tracked)


@transaction.atomic
def edit_application(
    *, application: Application, actor, category: str, lots: int, bank_id, upi_id, record_only=False
) -> Application:
    item = (
        Application.objects.select_for_update()
        .select_related("ipo", "bank", "upi")
        .get(pk=application.pk)
    )
    _require_writer(item.workspace, actor)
    allowed = {Application.Status.PLANNED, Application.Status.SUBMITTED}
    if record_only:
        allowed.add(Application.Status.BLOCKED)
    if item.status not in allowed:
        raise ValidationError("Only planned or submitted applications can be edited")
    if category not in {"RETAIL", "SHNI", "SHARE", "BHNI"} or type(lots) is not int or lots < 1:
        raise ValidationError("Choose a valid category and number of lots")
    if (category == "SHARE") != (item.category == "SHARE"):
        raise ValidationError(
            "Keep shareholder and public applications separate; add quota rows in a new plan"
        )
    bank = BankAccount.objects.filter(
        pk=bank_id, workspace=item.workspace, active=True, is_placeholder=False
    ).first()
    if bank is None:
        raise ValidationError("Choose an active bank account in this workspace")
    if not record_only and bank.owner_id != item.applicant_id and bank_policy(bank) == "DISALLOW":
        raise ValidationError("This bank cannot fund another investor's application")
    upi = (
        UPIHandle.objects.filter(pk=upi_id, bank=bank, active=True, verified=True).first()
        if upi_id
        else None
    )
    if upi is None and category != "BHNI":
        raise ValidationError("Choose an active UPI linked to that bank")
    amount = (item.amount / item.lots * lots).quantize(Decimal("0.01"))
    if category == "RETAIL" and amount > Decimal("200000.00"):
        raise ValidationError("Retail applications cannot exceed ₹2,00,000. Choose sHNI.")
    if category == "SHNI" and amount <= Decimal("200000.00"):
        raise ValidationError("sHNI applications must be above ₹2,00,000")
    validate_quota_mapping(
        workspace=item.workspace,
        ipo=item.ipo,
        applicant_id=item.applicant_id,
        category=category,
        lots=lots,
        amount=amount,
        bank=bank,
        upi=upi,
    )
    if category == "SHNI" and amount > Decimal("1000000"):
        raise ValidationError("Choose bHNI for an amount above ₹10,00,000")
    if (category, lots, bank.pk, upi.pk if upi else None) == (
        item.category,
        item.lots,
        item.bank_id,
        item.upi_id,
    ):
        return item
    other_commitments = Application.objects.filter(
        workspace=item.workspace,
        bank=bank,
        status__in=(
            Application.Status.PLANNED,
            Application.Status.SUBMITTED,
            Application.Status.BLOCKED,
        ),
    ).exclude(pk=item.pk).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    if not record_only and amount + other_commitments > bank.current_balance:
        raise ValidationError("Bank Balance is below the updated application amount")
    before = {
        "category": item.category,
        "lots": item.lots,
        "amount": str(item.amount),
        "bank_id": str(item.bank_id),
        "upi_id": str(item.upi_id),
    }
    item.category = category
    item.lots = lots
    item.amount = amount
    item.bank = bank
    item.upi = upi
    warnings = []
    if record_only:
        if amount + other_commitments > bank.current_balance:
            warnings.append("Bank Balance is below the updated application amount")
        if bank.owner_id != item.applicant_id and bank_policy(bank) == "DISALLOW":
            warnings.append("This bank is restricted to own-account funding")
    if item.status in {Application.Status.SUBMITTED, Application.Status.BLOCKED}:
        warnings.extend(_assert_submission_limits(item, allow_warnings=record_only))
    item.edited_at = timezone.now()
    item.save(update_fields=["category", "lots", "amount", "bank", "upi", "edited_at"])
    record_event(
        action="application.edited",
        target=item,
        actor=actor,
        workspace=item.workspace,
        metadata={
            "record_only": record_only,
            "warnings": warnings,
            "before": before,
            "after": {
                "category": category,
                "lots": lots,
                "amount": str(amount),
                "bank_id": str(bank.pk),
                "upi_id": str(upi.pk) if upi else "",
            },
        },
    )
    return item


@transaction.atomic
def cancel_application(*, application: Application, actor) -> Application:
    item = Application.objects.select_for_update().get(pk=application.pk)
    _require_writer(item.workspace, actor)
    if item.status not in {
        Application.Status.PLANNED,
        Application.Status.SUBMITTED,
        Application.Status.BLOCKED,
    }:
        raise ValidationError("Only planned, submitted or blocked applications can be cancelled")
    previous_status = item.status
    item.status = Application.Status.CANCELLED
    item.cancelled_at = timezone.now()
    item.save(update_fields=["status", "cancelled_at"])
    record_event(
        action="application.cancelled",
        target=item,
        actor=actor,
        workspace=item.workspace,
        metadata={"previous_status": previous_status},
    )
    return item


def _assert_submission_limits(item, *, exclude_id=None, allow_warnings=False):
    locked_bank = BankAccount.objects.select_for_update().get(pk=item.bank_id)
    item.bank = locked_bank
    if item.category == "BHNI":
        validate_quota_mapping(
            workspace=item.workspace,
            ipo=item.ipo,
            applicant_id=item.applicant_id,
            category=item.category,
            lots=item.lots,
            amount=item.amount,
            bank=item.bank,
            upi=None,
        )
        other = Application.objects.filter(
            bank_id=item.bank_id, status__in=("PLANNED", "SUBMITTED", "BLOCKED")
        ).exclude(pk=item.pk).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        if item.amount + other > item.bank.current_balance:
            message = "Bank Balance is below the ASBA amount after other applications"
            if allow_warnings:
                return [message]
            raise ValidationError(message)
        return []
    validate_quota_mapping(
        workspace=item.workspace,
        ipo=item.ipo,
        applicant_id=item.applicant_id,
        category=item.category,
        lots=item.lots,
        amount=item.amount,
        bank=item.bank,
        upi=item.upi,
    )
    upi = UPIHandle.objects.get(pk=item.upi_id)
    now = timezone.now()
    config = PlannerConfig(PLANNER_VERSION, "DISALLOW", "DEFAULT")
    usage = (
        Application.objects.filter(
            bank_id=item.bank_id, submitted_at__gt=now - timedelta(hours=24), submitted_at__lte=now
        )
        .exclude(status=Application.Status.CANCELLED)
        .exclude(category="BHNI")
        .exclude(pk=exclude_id or item.pk)
    )
    check = RollingLimitTracker(
        tuple(
            RollingUsageInput(
                str(event.pk),
                str(event.bank_id),
                str(event.upi_id),
                event.amount,
                event.submitted_at,
                False,
            )
            for event in usage
        )
    ).check(
        upi=UPIInput(
            str(upi.pk),
            str(upi.bank_id),
            str(upi.holder_id),
            upi.active,
            upi.verified,
            upi.count_limit_override,
            upi.amount_limit_override,
        ),
        amount=item.amount,
        at=now,
        config=config,
    )
    if not check.allowed:
        message = (
            "This bank or UPI has reached its application limit. Retail and sHNI share "
            "six applications in a rolling 24 hours; the configured amount limit also applies."
        )
        if allow_warnings:
            return [message]
        raise ValidationError(message)
    return []


@transaction.atomic
def mark_submitted(*, application: Application, actor, record_only=False) -> Application:
    item = Application.objects.select_for_update().get(pk=application.pk)
    _require_writer(item.workspace, actor)
    if item.status != Application.Status.PLANNED:
        raise ValidationError("Only a planned application can be marked submitted")
    warnings = []
    if item.bank.owner_id != item.applicant_id and bank_policy(item.bank) == "DISALLOW":
        if not record_only:
            raise ValidationError("This bank cannot fund another investor's application")
        warnings.append("This bank is restricted to own-account funding")
    warnings.extend(_assert_submission_limits(item, allow_warnings=record_only))
    item.status = Application.Status.SUBMITTED
    item.submitted_at = timezone.now()
    item.save(update_fields=["status", "submitted_at"])
    record_event(
        action="application.submitted",
        target=item,
        actor=actor,
        workspace=item.workspace,
        metadata={"status": item.status, "record_only": record_only, "warnings": warnings},
    )
    return item


@transaction.atomic
def mark_blocked(*, application: Application, actor, record_only=False) -> Application:
    item = Application.objects.select_for_update().get(pk=application.pk)
    _require_writer(item.workspace, actor)
    if record_only and item.status == Application.Status.PLANNED:
        item = mark_submitted(application=item, actor=actor, record_only=True)
    if item.status != Application.Status.SUBMITTED:
        raise ValidationError("Only a submitted application can be marked blocked")
    item.status = Application.Status.BLOCKED
    item.blocked_at = timezone.now()
    item.expected_release_date = item.ipo.allotment_date + timedelta(days=1)
    item.save(update_fields=["status", "blocked_at", "expected_release_date"])
    record_event(
        action="application.blocked",
        target=item,
        actor=actor,
        workspace=item.workspace,
        metadata={"status": item.status, "record_only": record_only},
    )
    return item


@transaction.atomic
def mark_not_allotted(*, application: Application, actor) -> Application:
    item = Application.objects.select_for_update().get(pk=application.pk)
    _require_writer(item.workspace, actor)
    if item.status != Application.Status.BLOCKED:
        raise ValidationError("Only a blocked application can be marked Not Allotted")
    item.status = Application.Status.NOT_ALLOTTED
    item.result_at = timezone.now()
    item.save(update_fields=["status", "result_at"])
    record_event(
        action="application.not_allotted",
        target=item,
        actor=actor,
        workspace=item.workspace,
        metadata={"status": item.status},
    )
    return item


@transaction.atomic
def mark_allotted(
    *, application: Application, actor, quantity: int, actual_cost: Decimal
) -> Application:
    item = Application.objects.select_for_update().select_related("ipo").get(pk=application.pk)
    _require_writer(item.workspace, actor)
    if item.status != Application.Status.BLOCKED:
        raise ValidationError("Only a blocked application can be marked Allotted")
    if type(quantity) is not int or quantity < 1 or quantity > item.lots * item.ipo.lot_size:
        raise ValidationError("Allotted quantity must fit the application lots")
    if actual_cost <= 0 or actual_cost > item.amount:
        raise ValidationError("Actual cost must be positive and no more than the blocked amount")
    bank = BankAccount.objects.select_for_update().get(pk=item.bank_id)
    if bank.current_balance < actual_cost:
        raise ValidationError("Bank Balance is below the actual allotment cost")
    old_balance = bank.current_balance
    bank.current_balance -= actual_cost
    bank.save(update_fields=["current_balance", "updated_at"])
    change = BalanceChange.objects.create(
        bank=bank,
        operation=BalanceChange.Operation.ALLOTMENT,
        old_balance=old_balance,
        delta=-actual_cost,
        new_balance=bank.current_balance,
        note=f"IPO allotment: {item.ipo.issuer_name}",
        actor=actor,
    )
    item.status = Application.Status.ALLOTTED
    item.allotted_quantity = quantity
    item.actual_cost = actual_cost
    item.result_at = timezone.now()
    item.save(update_fields=["status", "allotted_quantity", "actual_cost", "result_at"])
    record_event(
        action="application.allotted",
        target=item,
        actor=actor,
        workspace=item.workspace,
        metadata={"quantity": quantity, "cost": str(actual_cost)},
    )
    record_event(
        action="balance.allotment_debited",
        target=change,
        actor=actor,
        workspace=item.workspace,
    )
    record_beta_event(workspace=item.workspace, event_type=BetaEvent.Type.ALLOTMENT_RECORDED)
    return item
