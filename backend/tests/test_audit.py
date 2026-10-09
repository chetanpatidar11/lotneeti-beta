import pytest
from django.core.exceptions import ValidationError

from accounts.models import User
from accounts.services import create_workspace
from core.audit import record_event
from core.models import AuditEvent


@pytest.mark.django_db
def test_audit_service_records_actor_object_action_metadata_and_time():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    event = AuditEvent.objects.get(action="workspace.created")

    assert event.actor == owner
    assert event.workspace == workspace
    assert event.object_type == "accounts.Workspace"
    assert event.object_id == str(workspace.pk)
    assert event.metadata == {"role": "OWNER"}
    assert event.created_at is not None


@pytest.mark.django_db
def test_audit_event_rejects_sensitive_metadata_and_mutation():
    user = User.objects.create_user(email="user@example.test")
    with pytest.raises(ValidationError):
        record_event(action="auth.test", target=user, actor=user, metadata={"raw_pan": "SYNTHETIC"})

    event = record_event(action="auth.test", target=user, actor=user, metadata={"method": "TEST"})
    event.metadata = {"method": "CHANGED"}
    with pytest.raises(ValueError):
        event.save()
    with pytest.raises(ValueError):
        event.delete()
