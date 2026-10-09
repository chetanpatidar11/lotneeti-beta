"""Audited corrections for individual GMP observations."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.audit import record_event
from ipos.models import GMPObservation, GMPObservationOverride


@transaction.atomic
def set_observation_override(
    *, observation: GMPObservation, value_per_share, expires_at, reason: str, actor
):
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise ValidationError("A reason of up to 500 characters is required")
    if expires_at is None or expires_at <= timezone.now():
        raise ValidationError("Override expiry must be in the future")
    locked = GMPObservation.objects.select_for_update().get(pk=observation.pk)
    value = GMPObservationOverride._meta.get_field("value_per_share").clean(value_per_share, locked)
    now = timezone.now()
    GMPObservationOverride.objects.filter(observation=locked, resumed_at__isnull=True).update(
        resumed_at=now, resumed_by=actor
    )
    override = GMPObservationOverride.objects.create(
        observation=locked,
        value_per_share=value,
        expires_at=expires_at,
        reason=reason,
        created_by=actor,
    )
    record_event(
        action="gmp.observation_override_set",
        target=override,
        actor=actor,
        metadata={"source_key": locked.source_key, "expires_at": expires_at.isoformat()},
    )
    return override


@transaction.atomic
def resume_observation_auto(*, observation: GMPObservation, actor):
    locked = GMPObservation.objects.select_for_update().get(pk=observation.pk)
    override = GMPObservationOverride.objects.filter(
        observation=locked, resumed_at__isnull=True
    ).first()
    if override is None:
        raise ValidationError("This observation is already automatic")
    override.resumed_at = timezone.now()
    override.resumed_by = actor
    override.save(update_fields=["resumed_at", "resumed_by"])
    record_event(
        action="gmp.observation_override_resumed",
        target=override,
        actor=actor,
        metadata={"source_key": locked.source_key},
    )
    return override
