from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from core.models import AuditEvent
from ipos.models import IPO, GMPObservation
from planner.snapshot_builder import build_snapshot


@pytest.mark.django_db
def test_founder_workspace_can_set_twenty_percent_without_platform_default():
    founder = User.objects.create_user(email="founder@example.test")
    first = create_workspace(name="Founder", owner=founder)
    second = create_workspace(name="Other", owner=founder)
    assert first.auto_select_enabled is False
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


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="WARN")
def test_automatic_issue_types_default_to_mainboard_and_manual_apply_still_wins():
    owner = User.objects.create_user(email="types@example.test")
    workspace = create_workspace(name="Types", owner=owner)
    workspace.auto_select_enabled = True
    workspace.auto_select_gmp_percent = Decimal("20.00")
    workspace.save()
    today = timezone.localdate()
    issues = []
    for issue_type in (IPO.IssueType.MAINBOARD, IPO.IssueType.SME):
        ipo = IPO.objects.create(
            issuer_name=f"Synthetic {issue_type}",
            issue_type=issue_type,
            lower_price=Decimal("100.00"),
            upper_price=Decimal("100.00"),
            lot_size=100,
            open_date=today,
            close_date=today + timedelta(days=3),
            allotment_date=today + timedelta(days=7),
            status=IPO.Status.OPEN,
            publication_state=IPO.PublicationState.PUBLISHED,
            source_key="synthetic-fixture",
            source_record_id=issue_type,
        )
        GMPObservation.objects.create(
            ipo=ipo,
            source_key="synthetic",
            value_per_share=Decimal("30.00"),
            observed_at=timezone.now() - timedelta(minutes=5),
        )
        issues.append(ipo)
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("workspace-detail", args=[workspace.pk])
    decisions_url = reverse("workspace-ipo-decision-list", args=[workspace.pk])

    assert workspace.auto_select_issue_types == ["MAINBOARD"]
    assert {row["ipo"]: row["selected"] for row in client.get(decisions_url).data} == {
        str(issues[0].pk): True,
        str(issues[1].pk): False,
    }
    assert {item.id for item in build_snapshot(workspace=workspace).ipos} == {str(issues[0].pk)}

    assert (
        client.patch(
            url, {"auto_select_issue_types": ["MAINBOARD", "SME"]}, format="json"
        ).status_code
        == 200
    )
    workspace.refresh_from_db()
    assert all(row["selected"] for row in client.get(decisions_url).data)
    selected_ids = {item.id for item in build_snapshot(workspace=workspace).ipos}
    assert selected_ids == {str(ipo.pk) for ipo in issues}

    assert client.patch(url, {"auto_select_issue_types": ["SME"]}, format="json").status_code == 200
    workspace.refresh_from_db()
    assert {row["ipo"]: row["selected"] for row in client.get(decisions_url).data} == {
        str(issues[0].pk): False,
        str(issues[1].pk): True,
    }
    assert (
        client.patch(
            reverse("workspace-ipo-decision-detail", args=[workspace.pk, issues[0].pk]),
            {"decision": "APPLY"},
            format="json",
        ).data["selected"]
        is True
    )
    selected_ids = {item.id for item in build_snapshot(workspace=workspace).ipos}
    assert selected_ids == {str(ipo.pk) for ipo in issues}
    for invalid in ([], ["SME", "SME"], ["UNKNOWN"]):
        assert (
            client.patch(url, {"auto_select_issue_types": invalid}, format="json").status_code
            == 400
        )


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="WARN")
def test_upcoming_is_automatic_only_when_no_open_eligible_ipo_exists():
    owner = User.objects.create_user(email="fallback@example.test")
    workspace = create_workspace(name="Fallback", owner=owner)
    workspace.auto_select_enabled = True
    workspace.auto_select_gmp_percent = Decimal("20.00")
    workspace.save()
    today = timezone.localdate()
    issues = []
    for status in (IPO.Status.OPEN, IPO.Status.UPCOMING):
        ipo = IPO.objects.create(
            issuer_name=f"Synthetic {status}",
            issue_type=IPO.IssueType.MAINBOARD,
            lower_price=Decimal("100.00"),
            upper_price=Decimal("100.00"),
            lot_size=100,
            open_date=today if status == IPO.Status.OPEN else today + timedelta(days=1),
            close_date=today + timedelta(days=4),
            allotment_date=today + timedelta(days=8),
            status=status,
            publication_state=IPO.PublicationState.PUBLISHED,
            source_key="synthetic-fixture",
            source_record_id=status,
        )
        GMPObservation.objects.create(
            ipo=ipo,
            source_key="synthetic",
            value_per_share=Decimal("30.00"),
            observed_at=timezone.now() - timedelta(minutes=5),
        )
        issues.append(ipo)
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("workspace-ipo-decision-list", args=[workspace.pk])

    assert {row["ipo"]: row["selected"] for row in client.get(url).data} == {
        str(issues[0].pk): True,
        str(issues[1].pk): False,
    }
    assert {item.id for item in build_snapshot(workspace=workspace).ipos} == {str(issues[0].pk)}

    issues[0].publication_state = IPO.PublicationState.ARCHIVED
    issues[0].save(update_fields=["publication_state"])
    assert {row["ipo"]: row["selected"] for row in client.get(url).data} == {
        str(issues[1].pk): True,
    }
    assert {item.id for item in build_snapshot(workspace=workspace).ipos} == {str(issues[1].pk)}


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="WARN")
def test_automatic_selection_requires_explicit_enable_and_keeps_manual_choices():
    from tests.test_ipo_decisions import make_ipo

    owner = User.objects.create_user(email="disabled-auto@example.test")
    workspace = create_workspace(name="Synthetic", owner=owner)
    workspace.auto_select_gmp_percent = Decimal("1.00")
    workspace.save()
    ipo = make_ipo()
    GMPObservation.objects.create(
        ipo=ipo,
        source_key="synthetic",
        value_per_share=Decimal("30.00"),
        observed_at=timezone.now(),
    )
    client = APIClient()
    client.force_authenticate(owner)
    settings_url = reverse("workspace-detail", args=[workspace.pk])
    choices_url = reverse("workspace-ipo-decision-list", args=[workspace.pk])
    assert client.get(choices_url).data[0]["reason"] == "AUTOMATIC_DISABLED"
    assert not build_snapshot(workspace=workspace).ipos
    assert (
        client.patch(settings_url, {"auto_select_enabled": True}, format="json").status_code == 200
    )
    workspace.refresh_from_db()
    assert client.get(choices_url).data[0]["selected"] is True
    assert len(build_snapshot(workspace=workspace).ipos) == 1
    client.patch(
        reverse("workspace-ipo-decision-detail", args=[workspace.pk, ipo.pk]), {"decision": "APPLY"}
    )
    client.patch(settings_url, {"auto_select_enabled": False}, format="json")
    workspace.refresh_from_db()
    assert client.get(choices_url).data[0]["reason"] == "MANUAL_APPLY"
    assert len(build_snapshot(workspace=workspace).ipos) == 1
