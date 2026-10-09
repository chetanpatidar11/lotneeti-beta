from collections.abc import Mapping

from django.core.exceptions import ValidationError
from django.db.models import Model

from core.models import AuditEvent

FORBIDDEN_METADATA_KEYS = (
    "account",
    "bank_number",
    "email",
    "otp",
    "pan",
    "password",
    "pin",
    "secret",
    "token",
    "upi",
)


def record_event(
    *,
    action: str,
    target: Model,
    actor=None,
    workspace=None,
    metadata: Mapping | None = None,
) -> AuditEvent:
    safe_metadata = dict(metadata or {})
    if any(
        forbidden in str(key).lower()
        for key in safe_metadata
        for forbidden in FORBIDDEN_METADATA_KEYS
    ):
        raise ValidationError("Sensitive values do not belong in audit metadata")
    if len(action) > 100 or not action:
        raise ValidationError("Invalid audit action")

    return AuditEvent.objects.create(
        actor=actor,
        workspace=workspace,
        object_type=target._meta.label,
        object_id=str(target.pk),
        action=action,
        metadata=safe_metadata,
    )
