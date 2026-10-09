from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from test_ipos import issue

from accounts.models import User
from accounts.services import create_workspace
from core.models import AuditEvent
from ipos.gmp_effective import latest_effective_gmp
from ipos.models import IPO, GMPObservation, GMPObservationOverride
from ipos.providers import ManualGMPProvider


@pytest.mark.django_db
def test_mfa_gmp_editor_corrects_source_with_expiry_and_public_projection():
    founder = User.objects.create_superuser(email="founder@example.invalid", password="test")
    member = User.objects.create_user(email="member@example.invalid")
    workspace = create_workspace(name="Synthetic workspace", owner=member)
    workspace.auto_select_gmp_percent = Decimal("20.00")
    workspace.save()
    ipo = issue(publication_state=IPO.PublicationState.PUBLISHED)
    ipo.save()
    observation = GMPObservation.objects.create(
        ipo=ipo,
        source_key="synthetic",
        value_per_share=Decimal("10.00"),
        observed_at=timezone.now() - timedelta(hours=1),
    )
    staff = Client()
    staff.force_login(founder)
    detail_url = reverse("founder_admin:gmp-observation-detail", args=[observation.pk])
    assert staff.get(detail_url).status_code == 302
    session = staff.session
    session["admin_mfa_verified"] = True
    session.save()
    assert staff.get(reverse("founder_admin:gmp-observations")).status_code == 200
    expiry = timezone.localtime(timezone.now() + timedelta(hours=2))
    response = staff.post(
        detail_url,
        {
            "action": "set",
            "value_per_share": "25.00",
            "expires_at": expiry.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M"),
            "reason": "Verified exchange notice",
        },
    )
    assert response.status_code == 302
    observation.refresh_from_db()
    assert observation.value_per_share == Decimal("10.00")
    assert latest_effective_gmp(ipo).value_per_share == Decimal("25.00")

    api = APIClient()
    api.force_authenticate(member)
    public = api.get(reverse("ipo-detail", args=[ipo.pk]))
    assert public.data["current_gmp"] == "25.00"
    assert public.data["current_gmp_percent"] == "23.81"
    history = api.get(reverse("ipo-gmp-history", args=[ipo.pk]))
    assert history.data[0]["value_per_share"] == "25.00"
    decision = api.get(reverse("workspace-ipo-decision-list", args=[workspace.pk]))
    assert decision.data[0]["selected"] is True

    page = staff.get(detail_url)
    assert b"Source value" in page.content
    assert b"Effective value" in page.content
    assert b"Verified exchange notice" in page.content
    assert staff.post(detail_url, {"action": "resume"}).status_code == 302
    assert latest_effective_gmp(ipo).value_per_share == Decimal("10.00")
    assert (
        GMPObservationOverride.objects.filter(
            observation=observation, resumed_at__isnull=True
        ).count()
        == 0
    )
    assert AuditEvent.objects.filter(action="gmp.observation_override_set").exists()
    assert AuditEvent.objects.filter(action="gmp.observation_override_resumed").exists()


@pytest.mark.django_db
def test_disabled_provider_is_excluded_from_effective_latest_value():
    ipo = issue(publication_state=IPO.PublicationState.PUBLISHED)
    ipo.save()
    observation = ManualGMPProvider().record(
        ipo=ipo,
        value_per_share=Decimal("10.00"),
        observed_at=timezone.now() - timedelta(hours=1),
    )
    from ipos.provider_health import set_provider_enabled

    founder = User.objects.create_superuser(email="founder@example.invalid", password="test")
    set_provider_enabled(
        provider_key=observation.source_key,
        enabled=False,
        reason="Synthetic provider test",
        actor=founder,
    )
    assert latest_effective_gmp(ipo) is None
