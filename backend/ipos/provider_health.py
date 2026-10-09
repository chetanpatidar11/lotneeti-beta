"""Audited provider health and temporary GMP source controls."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.audit import record_event
from ipos.models import GMPProviderState


def get_provider_state(provider_key: str) -> GMPProviderState:
    key = provider_key.strip()
    if not key or len(key) > 80:
        raise ValidationError("A provider key is required")
    state, _ = GMPProviderState.objects.get_or_create(provider_key=key)
    return state


@transaction.atomic
def record_provider_success(*, provider_key: str, observed_at=None) -> GMPProviderState:
    state = get_provider_state(provider_key)
    state.last_success_at = observed_at or timezone.now()
    state.save(update_fields=["last_success_at", "updated_at"])
    return state


@transaction.atomic
def record_provider_failure(*, provider_key: str, error: Exception, observed_at=None):
    state = get_provider_state(provider_key)
    state.last_error_at = observed_at or timezone.now()
    state.last_error_type = type(error).__name__[:120]
    state.save(update_fields=["last_error_at", "last_error_type", "updated_at"])
    return state


@transaction.atomic
def set_provider_enabled(*, provider_key: str, enabled: bool, reason: str, actor):
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise ValidationError("A reason of up to 500 characters is required")
    state = get_provider_state(provider_key)
    state.enabled = bool(enabled)
    state.save(update_fields=["enabled", "updated_at"])
    record_event(
        action="gmp.provider_enabled" if state.enabled else "gmp.provider_disabled",
        target=state,
        actor=actor,
        metadata={"provider": state.provider_key, "reason": reason},
    )
    return state


@transaction.atomic
def set_provider_override(*, provider_key: str, value_per_share, expires_at, reason: str, actor):
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise ValidationError("A reason of up to 500 characters is required")
    if expires_at is None or expires_at <= timezone.now():
        raise ValidationError("Override expiry must be in the future")
    value = GMPProviderState._meta.get_field("override_value_per_share").clean(
        value_per_share, None
    )
    state = get_provider_state(provider_key)
    state.override_value_per_share = value
    state.override_expires_at = expires_at
    state.override_reason = reason
    state.override_set_by = actor
    state.save(
        update_fields=[
            "override_value_per_share",
            "override_expires_at",
            "override_reason",
            "override_set_by",
            "updated_at",
        ]
    )
    record_event(
        action="gmp.provider_override_set",
        target=state,
        actor=actor,
        metadata={"provider": state.provider_key, "expires_at": expires_at.isoformat()},
    )
    return state


@transaction.atomic
def clear_provider_override(*, provider_key: str, actor):
    state = get_provider_state(provider_key)
    state.override_value_per_share = None
    state.override_expires_at = None
    state.override_reason = ""
    state.override_set_by = None
    state.save(
        update_fields=[
            "override_value_per_share",
            "override_expires_at",
            "override_reason",
            "override_set_by",
            "updated_at",
        ]
    )
    record_event(
        action="gmp.provider_override_cleared",
        target=state,
        actor=actor,
        metadata={"provider": state.provider_key},
    )
    return state


def active_provider_override(state: GMPProviderState, *, at=None):
    if (
        state.override_value_per_share is None
        or state.override_expires_at is None
        or state.override_expires_at <= (at or timezone.now())
    ):
        return None
    return Decimal(state.override_value_per_share)
