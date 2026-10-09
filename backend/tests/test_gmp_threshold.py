from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from core.models import AuditEvent


@pytest.mark.django_db
def test_founder_workspace_can_set_twenty_percent_without_platform_default():
    founder = User.objects.create_user(email="founder@example.test")
    first = create_workspace(name="Founder", owner=founder)
    second = create_workspace(name="Other", owner=founder)
    assert first.auto_select_gmp_percent is None
    assert second.auto_select_gmp_percent is None
    client = APIClient()
    client.force_authenticate(founder)
    url = reverse("workspace-detail", args=[first.pk])

    response = client.patch(url, {"auto_select_gmp_percent": "20.00"})
    assert response.status_code == 200
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.auto_select_gmp_percent == Decimal("20.00")
    assert second.auto_select_gmp_percent is None
    assert AuditEvent.objects.filter(action="workspace.updated", workspace=first).count() == 1
    assert client.patch(url, {"auto_select_gmp_percent": None}, format="json").status_code == 200
    first.refresh_from_db()
    assert first.auto_select_gmp_percent is None


@pytest.mark.django_db
def test_only_owner_can_change_auto_select_threshold():
    owner = User.objects.create_user(email="owner@example.test")
    operator = User.objects.create_user(email="operator@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    WorkspaceMembership.objects.create(workspace=workspace, user=operator, role="OPERATOR")
    client = APIClient()
    client.force_authenticate(operator)
    assert (
        client.patch(
            reverse("workspace-detail", args=[workspace.pk]), {"auto_select_gmp_percent": "20.00"}
        ).status_code
        == 403
    )
