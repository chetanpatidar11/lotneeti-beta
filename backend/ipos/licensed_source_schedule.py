"""Licensed provider refresh slots with persisted duplicate-request protection."""

from django.db import transaction
from django.utils import timezone

from ipos.models import IPOProviderSyncState


def licensed_refresh_slot(at=None):
    local = timezone.localtime(at or timezone.now())
    if local.hour == 0 and local.minute == 1:
        return local.replace(second=0, microsecond=0)
    if 9 <= local.hour <= 19 and local.minute == 0:
        return local.replace(second=0, microsecond=0)
    return None


def reserve_refresh_slot(provider_key: str, *, at=None):
    slot = licensed_refresh_slot(at)
    if slot is None:
        return {
            "status": "OUTSIDE_SCHEDULE",
            "provider": provider_key,
            "requested": 0,
            "reason": "Licensed refresh slots are 12:01 AM and hourly from 9 AM through 7 PM IST.",
        }, None

    with transaction.atomic():
        state, _ = IPOProviderSyncState.objects.get_or_create(source_key=provider_key)
        state = IPOProviderSyncState.objects.select_for_update().get(pk=state.pk)
        previous = timezone.localtime(state.last_attempt_at) if state.last_attempt_at else None
        if previous and (previous.date(), previous.hour) == (slot.date(), slot.hour):
            return {
                "status": "RATE_LIMITED",
                "provider": provider_key,
                "requested": 0,
                "reason": "This provider has already been requested in this licensed refresh slot.",
            }, None
        state.last_attempt_at = slot
        state.last_status = "RUNNING"
        state.last_safe_error = ""
        state.save(update_fields=["last_attempt_at", "last_status", "last_safe_error"])
    return None, state
