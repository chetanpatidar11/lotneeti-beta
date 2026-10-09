from django.db import transaction

from core.audit import record_event
from core.models import FeatureFlag


def is_enabled(key: str, *, workspace=None, default: bool = False) -> bool:
    """Resolve a workspace override, then the platform default."""
    if workspace is not None:
        override = FeatureFlag.objects.filter(key=key, workspace=workspace).first()
        if override is not None:
            return override.enabled
    platform_flag = FeatureFlag.objects.filter(key=key, workspace__isnull=True).first()
    return platform_flag.enabled if platform_flag is not None else default


@transaction.atomic
def set_flag(*, key: str, enabled: bool, workspace=None, actor=None) -> FeatureFlag:
    """Create or update a flag and leave a safe audit trail for privileged changes."""
    flag, _ = FeatureFlag.objects.update_or_create(
        key=key,
        workspace=workspace,
        defaults={"enabled": enabled},
    )
    record_event(
        action="feature_flag.updated",
        target=flag,
        actor=actor,
        workspace=workspace,
        metadata={
            "key": key,
            "enabled": enabled,
            "scope": "workspace" if workspace else "platform",
        },
    )
    return flag
