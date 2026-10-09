"""Workspace-level beta milestones with no free-form or sensitive payload."""

from core.models import BetaEvent


def record_beta_event(*, workspace, event_type: BetaEvent.Type) -> BetaEvent:
    if event_type not in BetaEvent.Type.values:
        raise ValueError("Unknown beta event")
    return BetaEvent.objects.create(workspace=workspace, event_type=event_type)
