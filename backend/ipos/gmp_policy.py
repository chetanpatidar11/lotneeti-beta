"""Read and audit the Founder-editable GMP beta policy."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from core.audit import record_event
from ipos.models import GMPPolicy


def current_gmp_policy() -> GMPPolicy:
    policy, _ = GMPPolicy.objects.get_or_create(pk=1)
    return policy


@transaction.atomic
def update_gmp_policy(*, freshness_hours, conflict_threshold_percent_points, reason, actor):
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise ValidationError("A reason of up to 500 characters is required")
    policy = GMPPolicy.objects.select_for_update().filter(pk=1).first() or GMPPolicy(pk=1)
    before = {
        "freshness_hours": policy.freshness_hours,
        "conflict_threshold_percent_points": str(policy.conflict_threshold_percent_points),
    }
    try:
        policy.freshness_hours = int(freshness_hours)
        policy.conflict_threshold_percent_points = Decimal(str(conflict_threshold_percent_points))
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValidationError("Enter valid GMP policy values") from exc
    policy.updated_by = actor
    policy.full_clean()
    policy.save()
    record_event(
        action="gmp.policy_updated",
        target=policy,
        actor=actor,
        metadata={
            "before": before,
            "after": {
                "freshness_hours": policy.freshness_hours,
                "conflict_threshold_percent_points": str(policy.conflict_threshold_percent_points),
            },
            "reason": reason,
        },
    )
    return policy
