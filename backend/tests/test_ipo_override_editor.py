from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from test_ipos import issue

from accounts.models import User
from accounts.services import create_workspace
from core.models import AuditEvent
from ipos.models import GMPObservation, IPOFieldOverride
from planner.snapshot_builder import build_snapshot


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="WARN")
def test_staff_override_editor_requires_mfa_and_drives_public_and_planner_values():
    founder = User.objects.create_superuser(email="founder@example.invalid", password="test")
    member = User.objects.create_user(email="member@example.invalid")
    workspace = create_workspace(name="Synthetic workspace", owner=member)
    workspace.auto_select_gmp_percent = Decimal("20.00")
    workspace.save()
    today = timezone.localdate()
    ipo = issue(
        publication_state="DRAFT",
        status="OPEN",
        open_date=today - timedelta(days=1),
        close_date=today + timedelta(days=2),
        allotment_date=today + timedelta(days=5),
        listing_date=today + timedelta(days=7),
    )
    ipo.save()
    GMPObservation.objects.create(
        ipo=ipo,
        source_key="synthetic",
        value_per_share=Decimal("25.00"),
        observed_at=timezone.now() - timedelta(hours=1),
    )
    staff = Client()
    staff.force_login(founder)
    detail_url = reverse("founder_admin:ipo-override-detail", args=[ipo.pk])
    assert staff.get(detail_url).status_code == 302
    session = staff.session
    session["admin_mfa_verified"] = True
    session.save()
    assert staff.get(reverse("founder_admin:ipo-overrides")).status_code == 200

    for field_name, value in (
        ("publication_state", "PUBLISHED"),
        ("upper_price", "125.00"),
        ("lot_size", "200"),
    ):
        response = staff.post(
            detail_url,
            {"action": "set", "field_name": field_name, "value": value, "reason": "Notice review"},
        )
        assert response.status_code == 302
    page = staff.get(detail_url)
    assert page.status_code == 200
    assert b"Source value" in page.content
    assert b"Effective value" in page.content
    assert b"Notice review" in page.content
    assert b"Resume auto" in page.content
    ipo.refresh_from_db()
    assert ipo.publication_state == "DRAFT"
    assert ipo.upper_price == Decimal("105.00")
    assert ipo.lot_size == 140

    client = APIClient()
    client.force_authenticate(member)
    public = client.get(reverse("ipo-detail", args=[ipo.pk]))
    assert public.status_code == 200
    assert public.data["upper_price"] == "125.00"
    assert public.data["lot_size"] == 200
    assert public.data["current_gmp_percent"] == "20.00"
    assert client.get(reverse("ipo-gmp-history", args=[ipo.pk])).data[0]["percent"] == "20.00"
    decision = client.get(reverse("workspace-ipo-decision-list", args=[workspace.pk]))
    assert decision.data[0]["selected"] is True
    snapshot = build_snapshot(workspace=workspace, as_of=timezone.now())
    assert snapshot.ipos[0].upper_price == Decimal("125.00")
    assert snapshot.ipos[0].lot_size == 200
    assert len(snapshot.ipos) == 1

    assert (
        staff.post(
            detail_url,
            {"action": "resume", "field_name": "publication_state"},
        ).status_code
        == 302
    )
    assert client.get(reverse("ipo-detail", args=[ipo.pk])).status_code == 404
    assert IPOFieldOverride.objects.filter(ipo=ipo, resumed_at__isnull=True).count() == 2
    assert AuditEvent.objects.filter(action__startswith="ipo.override_").count() == 4


@pytest.mark.django_db
def test_editor_rejects_invalid_change_without_recording_it():
    founder = User.objects.create_superuser(email="founder@example.invalid", password="test")
    ipo = issue()
    ipo.save()
    staff = Client()
    staff.force_login(founder)
    session = staff.session
    session["admin_mfa_verified"] = True
    session.save()
    detail_url = reverse("founder_admin:ipo-override-detail", args=[ipo.pk])
    response = staff.post(
        detail_url,
        {"action": "set", "field_name": "lower_price", "value": "200", "reason": "Bad"},
    )
    assert response.status_code == 200
    assert b"Upper price must be at least the lower price" in response.content
    assert IPOFieldOverride.objects.count() == 0
