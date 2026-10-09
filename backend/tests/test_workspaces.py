import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace


@pytest.mark.django_db
def test_workspace_creation_adds_owner_membership():
    owner = User.objects.create_user(email="owner@example.test", password="test-password")
    client = APIClient()
    client.force_authenticate(owner)

    response = client.post(reverse("workspace-list"), {"name": "Family"})

    assert response.status_code == 201
    assert response.data["role"] == WorkspaceMembership.Role.OWNER
    assert (
        WorkspaceMembership.objects.get(workspace_id=response.data["id"], user=owner).role
        == "OWNER"
    )


@pytest.mark.django_db
def test_workspace_list_and_detail_are_scoped_to_member():
    owner = User.objects.create_user(email="owner@example.test")
    outsider = User.objects.create_user(email="outsider@example.test")
    workspace = create_workspace(name="Private", owner=owner)
    client = APIClient()
    client.force_authenticate(outsider)

    assert client.get(reverse("workspace-list")).data == []
    assert client.get(reverse("workspace-detail", args=[workspace.pk])).status_code == 404
    assert (
        client.patch(
            reverse("workspace-detail", args=[workspace.pk]), {"name": "Changed"}
        ).status_code
        == 404
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role", [WorkspaceMembership.Role.OPERATOR, WorkspaceMembership.Role.VIEWER]
)
def test_operator_and_viewer_can_read_but_cannot_change_workspace(role):
    owner = User.objects.create_user(email="owner@example.test")
    member = User.objects.create_user(email="member@example.test")
    workspace = create_workspace(name="Private", owner=owner)
    WorkspaceMembership.objects.create(workspace=workspace, user=member, role=role)
    client = APIClient()
    client.force_authenticate(member)
    url = reverse("workspace-detail", args=[workspace.pk])

    assert client.get(url).status_code == 200
    assert client.patch(url, {"name": "Changed"}).status_code == 403
    workspace.refresh_from_db()
    assert workspace.name == "Private"


@pytest.mark.django_db
def test_owner_can_rename_workspace():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Original", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)

    response = client.patch(reverse("workspace-detail", args=[workspace.pk]), {"name": "Renamed"})

    assert response.status_code == 200
    workspace.refresh_from_db()
    assert workspace.name == "Renamed"
