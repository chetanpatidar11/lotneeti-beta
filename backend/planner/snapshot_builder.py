"""Build a tenant-scoped frozen planner snapshot from current ORM records."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from applications.models import Application
from core.crypto import decrypt_value
from funding.models import (
    BankAccount,
    FundingPreference,
    RecurringDebit,
    UPIHandle,
    upi_hash_for_workspace,
)
from investors.models import DematAccount, Investor
from ipos.gmp_effective import latest_selection_gmp
from ipos.models import IPOUserDecision
from ipos.overrides import effective_ipo_values, published_ipos
from ipos.public_serializers import gmp_percent
from ipos.selection import resolve_ipo_choices
from planner.cash import expected_release_at
from planner.dto import (
    ApplicantInput,
    BankInput,
    CashBlockInput,
    DematInput,
    ExistingApplicationInput,
    FundingPreferenceInput,
    IPOInput,
    PlannerConfig,
    PlannerSnapshot,
    RecurringDebitInput,
    RollingUsageInput,
    UPIInput,
)
from planner.engine import PLANNER_VERSION
from planner.policies import bank_policy, platform_policy


def build_snapshot(
    *,
    workspace,
    ipo_ids: frozenset[str] | None = None,
    plan_cross_funding_override: str = "DEFAULT",
    as_of: datetime | None = None,
) -> PlannerSnapshot:
    if plan_cross_funding_override not in {"DEFAULT", "ALLOW", "WARN", "DISALLOW"}:
        raise ValidationError("Invalid plan cross-funding policy")
    now = as_of or timezone.now()
    platform_policy_value = platform_policy(at=now)
    zone = ZoneInfo(settings.TIME_ZONE)
    decisions = {
        str(item.ipo_id): item
        for item in IPOUserDecision.objects.filter(workspace=workspace).order_by("ipo_id")
    }
    ipos = list(published_ipos().order_by("id"))
    effective_values = {ipo.pk: effective_ipo_values(ipo) for ipo in ipos}
    issue_types = tuple(workspace.auto_select_issue_types or ["MAINBOARD"])
    selection_candidates = []
    current_gmp_by_ipo = {}
    for ipo in ipos:
        effective = effective_values[ipo.pk]
        latest = latest_selection_gmp(ipo, at=now)
        current_gmp = (
            gmp_percent(latest.value_per_share, effective["upper_price"]) if latest else None
        )
        current_gmp_by_ipo[str(ipo.pk)] = current_gmp
        decision = decisions.get(str(ipo.pk))
        selection_candidates.append(
            (
                str(ipo.pk),
                effective,
                decision.decision if decision else IPOUserDecision.Decision.DEFAULT,
                current_gmp,
            )
        )
    choices = resolve_ipo_choices(
        candidates=selection_candidates,
        threshold=workspace.auto_select_gmp_percent,
        issue_types=issue_types,
        at=now,
    )
    selected_ipos = []
    for ipo in ipos:
        effective = effective_values[ipo.pk]
        current_gmp = current_gmp_by_ipo[str(ipo.pk)]
        decision = decisions.get(str(ipo.pk))
        selected, _ = choices[str(ipo.pk)]
        if not selected:
            continue
        retail_cutoff = datetime.combine(effective["close_date"], time(17), tzinfo=zone)
        if retail_cutoff < now:
            continue
        if ipo_ids is not None and str(ipo.pk) not in ipo_ids:
            continue
        selected_ipos.append(
            IPOInput(
                id=str(ipo.pk),
                selected=True,
                gmp_percent=current_gmp,
                upper_price=effective["upper_price"],
                lot_size=effective["lot_size"],
                cutoff_at=retail_cutoff,
                allotment_date=effective["allotment_date"],
                mode=decision.mode if decision else IPOUserDecision.Mode.RETAIL_ONLY,
                shni_cutoff_at=datetime.combine(effective["close_date"], time(16), tzinfo=zone),
            )
        )
    if ipo_ids is not None and ipo_ids != {ipo.id for ipo in selected_ipos}:
        raise ValidationError("Requested IPOs must be published, selected and open for planning")

    investors = list(Investor.objects.filter(workspace=workspace, is_deleted=False).order_by("id"))
    demats = DematAccount.objects.filter(investor__workspace=workspace).order_by("id")
    banks = list(BankAccount.objects.filter(workspace=workspace).order_by("id"))
    upis = list(UPIHandle.objects.filter(bank__workspace=workspace).order_by("id"))
    own_active_banks = {
        bank.pk: bank.owner_id for bank in banks if bank.active and not bank.is_placeholder
    }
    usable_upis = {
        upi.handle_lookup_hash
        for upi in upis
        if upi.active and upi.verified and upi.bank_id in own_active_banks
    }
    ready_payment_investors = {
        upi.holder_id
        for upi in upis
        if upi.active and upi.verified and own_active_banks.get(upi.bank_id) == upi.holder_id
    }
    ready_payment_investors.update(
        investor.pk
        for investor in investors
        if investor.payment_hint_ciphertext
        and upi_hash_for_workspace(
            workspace.pk,
            decrypt_value(investor.payment_hint_ciphertext, purpose="payment-hint"),
        )
        in usable_upis
    )
    preferences = FundingPreference.objects.filter(beneficiary__workspace=workspace).order_by("id")
    schedules = RecurringDebit.objects.filter(
        bank__workspace=workspace, active=True, archived_at__isnull=True
    ).order_by("id")
    applications = list(
        Application.objects.filter(workspace=workspace).select_related("ipo").order_by("id")
    )
    return PlannerSnapshot(
        as_of=now,
        config=PlannerConfig(
            version=PLANNER_VERSION,
            platform_cross_funding_policy=platform_policy_value,
            workspace_cross_funding_policy=workspace.cross_funding_policy,
            plan_cross_funding_override=plan_cross_funding_override,
        ),
        ipos=tuple(selected_ipos),
        applicants=tuple(
            ApplicantInput(
                str(item.pk),
                item.planning_priority,
                item.active
                and (not item.payment_setup_pending or item.pk in ready_payment_investors),
            )
            for item in investors
        ),
        demats=tuple(
            DematInput(str(item.pk), str(item.investor_id), item.active) for item in demats
        ),
        banks=tuple(
            BankInput(
                id=str(item.pk),
                owner_id=str(item.owner_id),
                balance=item.current_balance,
                active=item.active and not item.is_placeholder,
                cross_funding_policy=bank_policy(item, at=now),
                restricted_applicant_id=(
                    str(item.restricted_investor_id) if item.restricted_investor_id else None
                ),
            )
            for item in banks
        ),
        upis=tuple(
            UPIInput(
                id=str(item.pk),
                bank_id=str(item.bank_id),
                holder_id=str(item.holder_id),
                active=item.active,
                verified=item.verified,
                count_limit_override=item.count_limit_override,
                amount_limit_override=item.amount_limit_override,
            )
            for item in upis
        ),
        funding_preferences=tuple(
            FundingPreferenceInput(
                str(item.beneficiary_id), str(item.bank_id), item.priority, item.enabled
            )
            for item in preferences
        ),
        recurring_debits=tuple(
            RecurringDebitInput(
                id=str(item.pk),
                bank_id=str(item.bank_id),
                amount=item.amount,
                frequency=item.frequency,
                start_date=item.start_date,
                next_due_date=item.next_due_date,
                end_date=item.end_date,
                active=item.active,
            )
            for item in schedules
        ),
        cash_blocks=tuple(
            CashBlockInput(
                id=str(item.pk),
                bank_id=str(item.bank_id),
                amount=item.amount,
                blocked_at=item.blocked_at or item.submitted_at,
                release_at=expected_release_at(item.ipo.allotment_date, zone),
            )
            for item in applications
            if item.status in {Application.Status.SUBMITTED, Application.Status.BLOCKED}
            and (item.blocked_at or item.submitted_at) is not None
        ),
        rolling_usage=tuple(
            RollingUsageInput(
                id=str(item.pk),
                bank_id=str(item.bank_id),
                upi_id=str(item.upi_id),
                amount=item.amount,
                submitted_at=item.submitted_at,
                cancelled=item.status == Application.Status.CANCELLED,
            )
            for item in applications
            if item.submitted_at is not None
        ),
        existing_applications=tuple(
            ExistingApplicationInput(
                id=str(item.pk),
                ipo_id=str(item.ipo_id),
                applicant_id=str(item.applicant_id),
                cancelled=item.status == Application.Status.CANCELLED,
            )
            for item in applications
        ),
    )
