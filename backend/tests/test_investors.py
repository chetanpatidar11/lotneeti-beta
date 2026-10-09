import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from core.models import AuditEvent
from investors.models import Investor, pan_hash_for_workspace

SYNTHETIC_PAN = "TESTX0001A"


@pytest.mark.django_db
def test_owner_can_create_edit_and_deactivate_investor_with_masked_pan():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    list_url = reverse("investor-list", args=[workspace.pk])

    created = client.post(
        list_url, {"name": "Synthetic Person", "pan": SYNTHETIC_PAN, "planning_priority": 2}
    )
    assert created.status_code == 201
    assert created.data["pan_masked"] == "******001A"
    assert "pan" not in created.data
    investor = Investor.objects.get(pk=created.data["id"])
    assert SYNTHETIC_PAN not in investor.pan_ciphertext
    assert investor.pan_lookup_hash != SYNTHETIC_PAN

    detail_url = reverse("investor-detail", args=[workspace.pk, investor.pk])
    updated = client.patch(detail_url, {"planning_priority": 1, "active": False})
    assert updated.status_code == 200
    investor.refresh_from_db()
    assert investor.planning_priority == 1
    assert investor.active is False
    assert AuditEvent.objects.filter(action__startswith="investor.", actor=owner).count() == 2


@pytest.mark.django_db
def test_duplicate_pan_rejected_within_workspace_but_allowed_in_another():
    owner = User.objects.create_user(email="owner@example.test")
    first = create_workspace(name="First", owner=owner)
    second = create_workspace(name="Second", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)

    assert (
        client.post(
            reverse("investor-list", args=[first.pk]), {"name": "A", "pan": SYNTHETIC_PAN}
        ).status_code
        == 201
    )
    duplicate = client.post(
        reverse("investor-list", args=[first.pk]), {"name": "B", "pan": SYNTHETIC_PAN.lower()}
    )
    assert duplicate.status_code == 400
    assert (
        client.post(
            reverse("investor-list", args=[second.pk]), {"name": "C", "pan": SYNTHETIC_PAN}
        ).status_code
        == 201
    )
    first_investor = Investor.objects.get(workspace=first)
    second_investor = Investor.objects.get(workspace=second)
    assert first_investor.pan_lookup_hash != second_investor.pan_lookup_hash
    assert first_investor.pan_lookup_hash == pan_hash_for_workspace(first.pk, SYNTHETIC_PAN)


@pytest.mark.django_db
def test_pan_edit_updates_encrypted_value_and_duplicate_index():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    list_url = reverse("investor-list", args=[workspace.pk])
    created = client.post(list_url, {"name": "A", "pan": SYNTHETIC_PAN})
    second_pan = "TESTX0002B"
    detail_url = reverse("investor-detail", args=[workspace.pk, created.data["id"]])

    response = client.patch(detail_url, {"pan": second_pan.lower()})

    assert response.status_code == 200
    assert response.data["pan_masked"] == "******002B"
    investor = Investor.objects.get(pk=created.data["id"])
    assert investor.pan_lookup_hash == pan_hash_for_workspace(workspace.pk, second_pan)
    assert SYNTHETIC_PAN not in investor.pan_ciphertext
    assert second_pan not in investor.pan_ciphertext
    assert client.post(list_url, {"name": "B", "pan": SYNTHETIC_PAN}).status_code == 201


@pytest.mark.django_db
def test_investor_access_is_scoped_and_viewer_is_read_only():
    owner = User.objects.create_user(email="owner@example.test")
    viewer = User.objects.create_user(email="viewer@example.test")
    outsider = User.objects.create_user(email="outsider@example.test")
    workspace = create_workspace(name="Private", owner=owner)
    WorkspaceMembership.objects.create(
        workspace=workspace, user=viewer, role=WorkspaceMembership.Role.VIEWER
    )
    investor = Investor(workspace=workspace, name="Synthetic", planning_priority=1)
    investor.set_pan(SYNTHETIC_PAN)
    investor.save()
    detail_url = reverse("investor-detail", args=[workspace.pk, investor.pk])
    list_url = reverse("investor-list", args=[workspace.pk])
    client = APIClient()

    client.force_authenticate(outsider)
    assert client.get(list_url).status_code == 403
    assert client.get(detail_url).status_code == 403
    assert client.patch(detail_url, {"name": "Changed"}).status_code == 403

    client.force_authenticate(viewer)
    assert client.get(detail_url).status_code == 200
    assert client.patch(detail_url, {"name": "Changed"}).status_code == 403
    assert client.post(list_url, {"name": "New", "pan": "TESTX0002B"}).status_code == 403
