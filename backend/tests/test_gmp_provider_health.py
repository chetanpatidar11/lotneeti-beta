from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from core.models import AuditEvent
from ipos.models import GMPProviderState
from ipos.provider_health import (
    active_provider_override,
    get_provider_state,
    record_provider_failure,
    record_provider_success,
    set_provider_enabled,
    set_provider_override,
)


@pytest.mark.django_db
def test_provider_health_records_success_and_redacted_failure_type():
    success_at = timezone.now() - timedelta(minutes=5)
    state = record_provider_success(provider_key="synthetic", observed_at=success_at)
    state = record_provider_failure(
        provider_key="synthetic",
        error=RuntimeError("secret source response"),
        observed_at=success_at,
    )
    assert state.last_success_at == success_at
    assert state.last_error_at == success_at
    assert state.last_error_type == "RuntimeError"
    assert "secret" not in state.last_error_type


@pytest.mark.django_db
def test_founder_mfa_provider_editor_controls_status_override_and_expiry():
    founder = User.objects.create_superuser(email="founder@example.invalid", password="test")
    state = get_provider_state("synthetic")
    staff = Client()
    staff.force_login(founder)
    detail_url = reverse("founder_admin:gmp-provider-detail", args=[state.provider_key])
    assert staff.get(detail_url).status_code == 302
    session = staff.session
    session["admin_mfa_verified"] = True
    session.save()
    assert staff.get(reverse("founder_admin:gmp-providers")).status_code == 200

    response = staff.post(detail_url, {"action": "disable", "reason": "Provider incident review"})
    assert response.status_code == 302, response.content.decode()
    state.refresh_from_db()
    assert state.enabled is False
    expires = timezone.now() + timedelta(hours=2)
    response = staff.post(
        detail_url,
        {
            "action": "override",
            "value_per_share": "12.50",
            "expires_at": timezone.localtime(expires)
            .replace(second=0, microsecond=0)
            .strftime("%Y-%m-%dT%H:%M"),
            "reason": "Founder verified notice",
        },
    )
    assert response.status_code == 302, response.content.decode()
    state.refresh_from_db()
    assert state.override_value_per_share == Decimal("12.50")
    assert active_provider_override(state) == Decimal("12.50")
    assert state.override_set_by == founder
    assert AuditEvent.objects.filter(action="gmp.provider_disabled").exists()
    event = AuditEvent.objects.get(action="gmp.provider_override_set")
    assert set(event.metadata) == {"provider", "expires_at"}
    assert b"secret source response" not in staff.get(detail_url).content

    assert staff.post(detail_url, {"action": "clear"}).status_code == 302
    state.refresh_from_db()
    assert active_provider_override(state) is None


@pytest.mark.django_db
def test_provider_override_requires_future_expiry_and_reason():
    founder = User.objects.create_superuser(email="founder@example.invalid", password="test")
    with pytest.raises(ValidationError):
        set_provider_override(
            provider_key="synthetic",
            value_per_share="10",
            expires_at=timezone.now() - timedelta(minutes=1),
            reason="reason",
            actor=founder,
        )
    with pytest.raises(ValidationError):
        set_provider_enabled(provider_key="synthetic", enabled=False, reason="", actor=founder)
    assert GMPProviderState.objects.count() == 0
