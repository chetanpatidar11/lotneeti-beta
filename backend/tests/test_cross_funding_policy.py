import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from funding.policy import resolve_cross_funding_policy


@pytest.mark.parametrize(
    ("layers", "policy", "source"),
    [
        ({}, "ALLOW", "platform"),
        ({"bank_policy": "WARN"}, "WARN", "bank"),
        ({"bank_policy": "ALLOW", "workspace_policy": "DISALLOW"}, "DISALLOW", "workspace"),
        ({"workspace_policy": "DISALLOW", "plan_override": "ALLOW"}, "ALLOW", "plan"),
        ({"bank_policy": "DISALLOW", "workspace_policy": "ALLOW"}, "DISALLOW", "bank"),
        ({"bank_policy": "DISALLOW", "plan_override": "ALLOW"}, "DISALLOW", "bank"),
    ],
)
def test_effective_policy_follows_layers_with_bank_prohibition(layers, policy, source):
    decision = resolve_cross_funding_policy(platform_default="ALLOW", **layers)
    assert (decision.policy, decision.source) == (policy, source)
    assert decision.allowed_for_automation is (policy != "DISALLOW")
    assert "CROSS_FUNDING" in decision.warnings


def test_warning_own_account_and_locked_row_context():
    warning = resolve_cross_funding_policy(platform_default="WARN")
    assert warning.warnings == ("CROSS_FUNDING", "CROSS_FUNDING_POLICY_WARNING")
    own = resolve_cross_funding_policy(platform_default="DISALLOW", same_owner=True)
    assert own.allowed_for_automation is True
    assert own.warnings == ()
    locked = resolve_cross_funding_policy(
        platform_default="ALLOW", workspace_policy="DISALLOW", locked_row=True
    )
    assert locked.allowed_for_automation is False
    assert locked.keep_locked_row is True
    assert locked.blocking_reasons == ("CROSS_FUNDING_DISALLOWED",)


def test_policy_requires_known_values():
    with pytest.raises(ValueError):
        resolve_cross_funding_policy(platform_default="DEFAULT")
    with pytest.raises(ValueError):
        resolve_cross_funding_policy(platform_default="ALLOW", plan_override="MAYBE")


@pytest.mark.django_db
def test_only_workspace_owner_can_set_workspace_cross_funding_preference():
    owner = User.objects.create_user(email="owner@example.test")
    operator = User.objects.create_user(email="operator@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    WorkspaceMembership.objects.create(workspace=workspace, user=operator, role="OPERATOR")
    url = reverse("workspace-detail", args=[workspace.pk])
    client = APIClient()
    client.force_authenticate(operator)
    assert client.patch(url, {"cross_funding_policy": "ALLOW"}).status_code == 403
    client.force_authenticate(owner)
    result = client.patch(url, {"cross_funding_policy": "DISALLOW"})
    assert result.status_code == 200
    assert result.data["cross_funding_policy"] == "DISALLOW"
    workspace.refresh_from_db()
    assert workspace.cross_funding_policy == "DISALLOW"
