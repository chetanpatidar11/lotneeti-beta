import pytest

from accounts.models import User
from accounts.services import create_workspace
from core.feature_flags import is_enabled, set_flag
from core.models import AuditEvent


@pytest.mark.django_db
def test_workspace_flag_overrides_platform_default_and_falls_back_after_removal():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)

    assert is_enabled("IMPORT_PREVIEW", workspace=workspace) is False
    set_flag(key="IMPORT_PREVIEW", enabled=True, actor=owner)
    assert is_enabled("IMPORT_PREVIEW", workspace=workspace) is True

    workspace_flag = set_flag(key="IMPORT_PREVIEW", enabled=False, workspace=workspace, actor=owner)
    assert is_enabled("IMPORT_PREVIEW", workspace=workspace) is False
    workspace_flag.delete()
    assert is_enabled("IMPORT_PREVIEW", workspace=workspace) is True
    assert AuditEvent.objects.filter(action="feature_flag.updated", actor=owner).count() == 2


@pytest.mark.django_db
def test_unknown_flag_uses_explicit_default_without_creating_state():
    assert is_enabled("UNKNOWN", default=True) is True
    assert is_enabled("UNKNOWN", default=False) is False
