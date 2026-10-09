import pytest

from accounts.services import create_workspace
from core.beta_events import record_beta_event
from core.models import BetaEvent


@pytest.mark.django_db
def test_activation_event_is_workspace_scoped_without_payload(django_user_model):
    owner = django_user_model.objects.create_user(email="beta-event@example.invalid")
    workspace = create_workspace(name="Synthetic beta workspace", owner=owner)
    event = BetaEvent.objects.get(workspace=workspace)
    assert event.event_type == BetaEvent.Type.ACTIVATED
    assert set(field.name for field in BetaEvent._meta.fields) == {
        "id",
        "workspace",
        "event_type",
        "created_at",
    }
    with pytest.raises(ValueError, match="Unknown beta event"):
        record_beta_event(workspace=workspace, event_type="PAN_EXPORTED")
