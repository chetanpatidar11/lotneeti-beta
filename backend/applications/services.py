"""Workspace-authorized application tracking and mandate transitions."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import Workspace, WorkspaceMembership
from applications.models import Application
from core.audit import record_event
from core.beta_events import record_beta_event
from core.models import BetaEvent
from funding.models import BalanceChange, BankAccount, UPIHandle
from investors.models import DematAccount, Investor
from ipos.models import IPO
from planner.export_readiness import assert_exportable_plan


def _require_writer(workspace, actor):
    if not WorkspaceMembership.objects.filter(
        workspace=workspace,
        user=actor,
        role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
    ).exists():
        raise ValidationError("This member cannot update applications")


@transaction.atomic
def start_tracking_plan(*, plan_run, actor) -> tuple[Application, ...]:
    workspace = Workspace.objects.select_for_update().get(pk=plan_run.workspace_id)
    _require_writer(workspace, actor)
    assert_exportable_plan(plan_run)
    tracked = []
    for row in plan_run.rows.all():
        ipo = IPO.objects.get(pk=row.ipo_ref)
        applicant = Investor.objects.get(
            pk=row.applicant_ref, workspace=workspace, is_deleted=False
        )
        demat = DematAccount.objects.get(pk=row.demat_ref, investor__workspace=workspace)
        bank = BankAccount.objects.get(pk=row.bank_ref, workspace=workspace)
        upi = UPIHandle.objects.get(pk=row.upi_ref, bank__workspace=workspace)
        existing = (
            Application.objects.filter(workspace=workspace, ipo=ipo, applicant=applicant)
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
            metadata={"status": application.status},
        )
    return tuple(tracked)


@transaction.atomic
def edit_application(
    *, application: Application, actor, category: str, lots: int, bank_id, upi_id
) -> Application:
    item = (
        Application.objects.select_for_update()
        .select_related("ipo", "bank", "upi")
        .get(pk=application.pk)
    )
    _require_writer(item.workspace, actor)
    if item.status not in {Application.Status.PLANNED, Application.Status.SUBMITTED}:
        raise ValidationError("Only planned or submitted applications can be edited")
    if category not in {"RETAIL", "SHNI"} or type(lots) is not int or lots < 1:
        raise ValidationError("Choose a valid category and number of lots")
    if category == "RETAIL" and lots != 1:
        raise ValidationError("Retail applications use one lot")
    bank = BankAccount.objects.filter(
        pk=bank_id, workspace=item.workspace, active=True, is_placeholder=False
    ).first()
    if bank is None:
        raise ValidationError("Choose an active bank account in this workspace")
    upi = UPIHandle.objects.filter(pk=upi_id, bank=bank, active=True, verified=True).first()
    if upi is None:
        raise ValidationError("Choose an active UPI linked to that bank")
    amount = (item.amount / item.lots * lots).quantize(Decimal("0.01"))
    if category == "SHNI" and amount <= Decimal("200000.00"):
        raise ValidationError("sHNI applications must be above ₹2,00,000")
    if (category, lots, bank.pk, upi.pk) == (item.category, item.lots, item.bank_id, item.upi_id):
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
    if amount + other_commitments > bank.current_balance:
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
    item.edited_at = timezone.now()
    item.save(update_fields=["category", "lots", "amount", "bank", "upi", "edited_at"])
    record_event(
        action="application.edited",
        target=item,
        actor=actor,
        workspace=item.workspace,
        metadata={
            "before": before,
            "after": {
                "category": category,
                "lots": lots,
                "amount": str(amount),
                "bank_id": str(bank.pk),
                "upi_id": str(upi.pk),
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


@transaction.atomic
def mark_submitted(*, application: Application, actor) -> Application:
    item = Application.objects.select_for_update().get(pk=application.pk)
    _require_writer(item.workspace, actor)
    if item.status != Application.Status.PLANNED:
        raise ValidationError("Only a planned application can be marked submitted")
    item.status = Application.Status.SUBMITTED
    item.submitted_at = timezone.now()
    item.save(update_fields=["status", "submitted_at"])
    record_event(
        action="application.submitted",
        target=item,
        actor=actor,
        workspace=item.workspace,
        metadata={"status": item.status},
    )
    return item


@transaction.atomic
def mark_blocked(*, application: Application, actor) -> Application:
    item = Application.objects.select_for_update().get(pk=application.pk)
    _require_writer(item.workspace, actor)
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
        metadata={"status": item.status},
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
