from django.db import transaction

from accounts.models import User, Workspace, WorkspaceMembership
from core.audit import record_event
from core.beta_events import record_beta_event
from core.models import BetaEvent


@transaction.atomic
def create_workspace(*, name: str, owner: User) -> Workspace:
    workspace = Workspace.objects.create(name=name, owner=owner)
    WorkspaceMembership.objects.create(
        workspace=workspace, user=owner, role=WorkspaceMembership.Role.OWNER
    )
    record_event(
        action="workspace.created",
        target=workspace,
        actor=owner,
        workspace=workspace,
        metadata={"role": WorkspaceMembership.Role.OWNER},
    )
    record_beta_event(workspace=workspace, event_type=BetaEvent.Type.ACTIVATED)
    return workspace


@transaction.atomic
def ensure_personal_workspace(*, owner: User) -> Workspace:
    locked_owner = User.objects.select_for_update().get(pk=owner.pk)
    membership = (
        WorkspaceMembership.objects.filter(user=locked_owner)
        .select_related("workspace")
        .order_by("workspace__created_at", "workspace_id")
        .first()
    )
    if membership:
        return membership.workspace
    return create_workspace(name="Personal", owner=locked_owner)
