"""Effective-dated planner policy resolution and audited edits."""

from datetime import datetime

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.audit import record_event
from planner.models import PlannerPolicy

POLICY_VALUES = frozenset(PlannerPolicy.Policy.values)


def _active_queryset(*, scope: str, bank=None, at=None):
    moment = at or timezone.now()
    return PlannerPolicy.objects.filter(
        scope=scope,
        bank=bank if scope == PlannerPolicy.Scope.BANK else None,
        effective_from__lte=moment,
    ).filter(Q(effective_until__isnull=True) | Q(effective_until__gt=moment))


def platform_policy(*, at=None):
    current = _active_queryset(scope=PlannerPolicy.Scope.GLOBAL, at=at).first()
    if current is not None:
        return current.policy
    configured = getattr(settings, "PLANNER_PLATFORM_CROSS_FUNDING_POLICY", None)
    if configured not in POLICY_VALUES:
        raise ImproperlyConfigured("Set a concrete planner platform cross-funding policy")
    return configured


def bank_policy(bank, *, at=None):
    current = _active_queryset(scope=PlannerPolicy.Scope.BANK, bank=bank, at=at).first()
    return current.policy if current is not None else bank.cross_funding_policy


@transaction.atomic
def set_policy(
    *,
    scope: str,
    policy: str,
    effective_from: datetime,
    effective_until: datetime | None,
    reason: str,
    actor,
    bank=None,
):
    if scope not in PlannerPolicy.Scope.values:
        raise ValidationError("Unknown planner policy scope")
    if policy not in POLICY_VALUES:
        raise ValidationError("Unknown planner policy")
    if scope == PlannerPolicy.Scope.GLOBAL and bank is not None:
        raise ValidationError("Global policies cannot target a bank")
    if scope == PlannerPolicy.Scope.BANK and bank is None:
        raise ValidationError("Bank policies require a bank")
    if timezone.is_naive(effective_from):
        raise ValidationError("Policy start must include a timezone")
    if effective_until is not None:
        if timezone.is_naive(effective_until):
            raise ValidationError("Policy end must include a timezone")
        if effective_until <= effective_from:
            raise ValidationError("Policy end must be after its start")
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise ValidationError("A reason of up to 500 characters is required")
    overlap = PlannerPolicy.objects.filter(
        scope=scope,
        bank=bank if scope == PlannerPolicy.Scope.BANK else None,
        effective_from__lt=(effective_until or datetime.max.replace(tzinfo=effective_from.tzinfo)),
    ).filter(Q(effective_until__isnull=True) | Q(effective_until__gt=effective_from))
    if overlap.exists():
        raise ValidationError("Policy dates overlap an existing policy")
    policy_record = PlannerPolicy.objects.create(
        scope=scope,
        bank=bank if scope == PlannerPolicy.Scope.BANK else None,
        policy=policy,
        effective_from=effective_from,
        effective_until=effective_until,
        reason=reason,
        created_by=actor,
    )
    record_event(
        action="planner.policy_set",
        target=policy_record,
        actor=actor,
        metadata={
            "scope": scope,
            "policy": policy,
            "bank_id": str(bank.pk) if bank is not None else None,
            "effective_from": effective_from.isoformat(),
            "effective_until": effective_until.isoformat() if effective_until else None,
        },
    )
    return policy_record
