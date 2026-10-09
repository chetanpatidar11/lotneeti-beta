from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import create_workspace
from core.models import AuditEvent
from ipos.gmp_effective import resolve_gmp
from ipos.gmp_overrides import resume_observation_auto, set_observation_override
from ipos.gmp_policy import current_gmp_policy, update_gmp_policy
from ipos.models import IPO, GMPObservation, GMPProviderState
from ipos.provider_health import set_provider_enabled, set_provider_override
from planner.snapshot_builder import build_snapshot


def make_ipo():
    today = date.today()
    return IPO.objects.create(
        issuer_name="Synthetic Market Ltd",
        issue_type=IPO.IssueType.MAINBOARD,
        lower_price=Decimal("100.00"),
        upper_price=Decimal("100.00"),
        lot_size=150,
        open_date=today,
        close_date=today + timedelta(days=3),
        allotment_date=today + timedelta(days=7),
        status=IPO.Status.OPEN,
        publication_state=IPO.PublicationState.PUBLISHED,
        source_key="synthetic-fixture",
        source_record_id="synthetic-consensus-001",
    )


def observe(ipo, source, value, at):
    return GMPObservation.objects.create(
        ipo=ipo,
        source_key=source,
        value_per_share=Decimal(value),
        observed_at=at,
    )


@pytest.mark.django_db
def test_median_uses_one_latest_fresh_enabled_observation_per_source_and_keeps_history():
    now = timezone.now()
    ipo = make_ipo()
    observe(ipo, "alpha", "99.00", now - timedelta(hours=3))
    first = observe(ipo, "alpha", "10.00", now - timedelta(hours=1))
    second = observe(ipo, "beta", "15.00", now - timedelta(hours=2))
    observe(ipo, "stale", "40.00", now - timedelta(hours=25))
    observe(ipo, "disabled", "90.00", now - timedelta(minutes=5))
    GMPProviderState.objects.create(provider_key="disabled", enabled=False)

    result = resolve_gmp(ipo, at=now)
    assert result.effective.value_per_share == Decimal("12.50")
    assert result.source_count == 2
    assert result.minimum == Decimal("10.00")
    assert result.maximum == Decimal("15.00")
    assert result.median == Decimal("12.50")
    assert result.latest_observed_at == first.observed_at
    assert result.source_conflict is True
    assert result.stale_source_keys == ("stale",)
    assert {item.pk for item in result.fresh_observations} == {first.pk, second.pk}
    assert GMPObservation.objects.filter(ipo=ipo).count() == 5

    member = User.objects.create_user(email="member@example.test")
    api = APIClient()
    api.force_authenticate(member)
    public = api.get(reverse("ipo-detail", args=[ipo.pk]))
    assert public.data["current_gmp"] == "12.50"
    assert public.data["gmp_source_count"] == 2
    assert public.data["gmp_minimum"] == "10.00"
    assert public.data["gmp_maximum"] == "15.00"
    assert public.data["gmp_median"] == "12.50"
    assert public.data["gmp_source_conflict"] is True
    assert public.data["gmp_stale_source_count"] == 1
    history = api.get(reverse("ipo-gmp-history", args=[ipo.pk])).data
    assert len(history) == 5
    assert {row["id"] for row in history if row["included_in_consensus"]} == {
        str(first.pk),
        str(second.pk),
    }
    assert next(row for row in history if row["source_key"] == "disabled")["enabled"] is False
    assert next(row for row in history if row["source_key"] == "stale")["fresh"] is False
    assert (
        next(row for row in history if row["source_key"] == "alpha" and row["id"] == str(first.pk))[
            "source_value_per_share"
        ]
        == "10.00"
    )


@pytest.mark.django_db
def test_exact_freshness_and_conflict_boundaries_are_editable():
    now = timezone.now()
    ipo = make_ipo()
    ipo.upper_price = Decimal("105.00")
    ipo.save()
    observe(ipo, "alpha", "10.00", now - timedelta(hours=24))
    observe(ipo, "beta", "15.25", now - timedelta(hours=1))
    policy = current_gmp_policy()
    assert policy.freshness_hours == 24
    assert policy.conflict_threshold_percent_points == Decimal("5.00")
    result = resolve_gmp(ipo, at=now)
    assert result.source_count == 1
    assert result.source_conflict is False
    assert result.effective.value_per_share == Decimal("15.25")

    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    update_gmp_policy(
        freshness_hours=25,
        conflict_threshold_percent_points="5.00",
        reason="Founder beta review",
        actor=founder,
    )
    result = resolve_gmp(ipo, at=now)
    assert result.source_count == 2
    assert result.source_conflict is True
    assert result.effective.value_per_share == Decimal("12.625")

    update_gmp_policy(
        freshness_hours=25,
        conflict_threshold_percent_points="5.01",
        reason="Founder beta review",
        actor=founder,
    )
    assert resolve_gmp(ipo, at=now).source_conflict is False
    assert AuditEvent.objects.filter(action="gmp.policy_updated").count() == 2


@pytest.mark.django_db
def test_observation_correction_precedes_provider_value_and_disabled_source_cannot_win():
    now = timezone.now()
    ipo = make_ipo()
    first = observe(ipo, "alpha", "10.00", now - timedelta(hours=1))
    second = observe(ipo, "beta", "20.00", now - timedelta(hours=1))
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    set_observation_override(
        observation=second,
        value_per_share="30.00",
        expires_at=now + timedelta(hours=48),
        reason="Founder notice correction",
        actor=founder,
    )
    set_provider_override(
        provider_key="alpha",
        value_per_share="25.00",
        expires_at=now + timedelta(hours=48),
        reason="Founder provider correction",
        actor=founder,
    )
    assert resolve_gmp(ipo, at=now).effective.value_per_share == Decimal("30.00")
    set_provider_enabled(
        provider_key="beta", enabled=False, reason="Provider under review", actor=founder
    )
    result = resolve_gmp(ipo, at=now)
    assert result.effective.value_per_share == Decimal("25.00")
    assert result.source_count == 1
    assert result.source_conflict is False
    assert resolve_gmp(ipo, at=now + timedelta(hours=25)).effective is None
    assert first.value_per_share == Decimal("10.00")


@pytest.mark.django_db
def test_active_founder_correction_overrides_median_but_not_source_conflict():
    now = timezone.now()
    ipo = make_ipo()
    first = observe(ipo, "alpha", "10.00", now - timedelta(hours=1))
    observe(ipo, "beta", "20.00", now - timedelta(hours=1))
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    set_observation_override(
        observation=first,
        value_per_share="30.00",
        expires_at=now + timedelta(hours=2),
        reason="Founder reviewed source notice",
        actor=founder,
    )
    result = resolve_gmp(ipo, at=now)
    assert result.effective.value_per_share == Decimal("30.00")
    assert result.effective.corrected is True
    assert result.source_conflict is True
    assert first.value_per_share == Decimal("10.00")
    resume_observation_auto(observation=first, actor=founder)
    assert resolve_gmp(ipo, at=now).effective.value_per_share == Decimal("15.00")


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="WARN")
def test_stale_gmp_does_not_auto_select_or_enter_planner_snapshot():
    now = timezone.now()
    ipo = make_ipo()
    observe(ipo, "alpha", "40.00", now - timedelta(hours=25))
    member = User.objects.create_user(email="member@example.test")
    workspace = create_workspace(name="Synthetic family", owner=member)
    workspace.auto_select_gmp_percent = Decimal("20.00")
    workspace.save()
    api = APIClient()
    api.force_authenticate(member)
    public = api.get(reverse("ipo-detail", args=[ipo.pk]))
    assert public.data["current_gmp"] is None
    assert public.data["gmp_data_state"] == "STALE"
    assert (
        api.get(reverse("workspace-ipo-decision-list", args=[workspace.pk])).data[0]["selected"]
        is False
    )
    assert build_snapshot(workspace=workspace, as_of=now).ipos == ()


@pytest.mark.django_db
def test_founder_policy_and_exception_pages_require_mfa_and_show_review_state():
    now = timezone.now()
    ipo = make_ipo()
    observe(ipo, "alpha", "10.00", now - timedelta(hours=1))
    observe(ipo, "beta", "15.00", now - timedelta(hours=1))
    founder = User.objects.create_superuser(email="founder@example.test", password="synthetic")
    staff = Client()
    staff.force_login(founder)
    policy_url = reverse("founder_admin:gmp-policy")
    exceptions_url = reverse("founder_admin:ipo-exceptions")
    assert staff.get(policy_url).status_code == 302
    assert staff.get(exceptions_url).status_code == 302
    session = staff.session
    session["admin_mfa_verified"] = True
    session.save()
    assert b"GMP source conflict" in staff.get(exceptions_url).content
    response = staff.post(
        policy_url,
        {
            "freshness_hours": "48",
            "conflict_threshold_percent_points": "6.00",
            "reason": "Founder beta review",
        },
    )
    assert response.status_code == 302
    assert current_gmp_policy().freshness_hours == 48
    assert b"GMP source conflict" not in staff.get(exceptions_url).content
    assert AuditEvent.objects.filter(action="gmp.policy_updated", actor=founder).exists()
