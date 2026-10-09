from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from accounts.services import create_workspace
from core.models import AuditEvent
from funding.models import BankAccount
from investors.models import Investor
from planner.models import PlannerPolicy
from planner.policies import bank_policy, platform_policy, set_policy


def synthetic_bank():
    owner = User.objects.create_user(email="owner@example.invalid")
    workspace = create_workspace(name="Synthetic workspace", owner=owner)
    investor = Investor(workspace=workspace, name="Synthetic investor")
    investor.set_pan("TESTX0001A")
    investor.save()
    bank = BankAccount(workspace=workspace, owner=investor, bank_name="Synthetic Bank")
    bank.set_account_number("DEMO-ACCOUNT-0001")
    bank.save()
    return owner, bank


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_effective_dated_global_and_bank_policies_are_audited_and_resolved():
    founder, bank = synthetic_bank()
    start = timezone.now() + timedelta(minutes=1)
    global_policy = set_policy(
        scope="GLOBAL",
        policy="DISALLOW",
        effective_from=start,
        effective_until=None,
        reason="Synthetic platform rule",
        actor=founder,
    )
    bank_start = start + timedelta(minutes=1)
    bank_override = set_policy(
        scope="BANK",
        policy="WARN",
        bank=bank,
        effective_from=bank_start,
        effective_until=None,
        reason="Synthetic bank exception",
        actor=founder,
    )
    assert platform_policy(at=start + timedelta(seconds=1)) == "DISALLOW"
    assert bank_policy(bank, at=bank_start + timedelta(seconds=1)) == "WARN"
    assert global_policy.bank_id is None
    assert bank_override.bank_id == bank.pk
    assert AuditEvent.objects.filter(action="planner.policy_set").count() == 2
    event = AuditEvent.objects.filter(action="planner.policy_set").first()
    assert set(event.metadata) == {
        "scope",
        "policy",
        "bank_id",
        "effective_from",
        "effective_until",
    }
    with pytest.raises(ValidationError):
        set_policy(
            scope="GLOBAL",
            policy="WARN",
            effective_from=start + timedelta(minutes=2),
            effective_until=None,
            reason="Overlap",
            actor=founder,
        )


@pytest.mark.django_db
def test_mfa_policy_editor_requires_reason_and_shows_history():
    founder = User.objects.create_superuser(email="founder@example.invalid", password="test")
    staff = Client()
    staff.force_login(founder)
    url = reverse("founder_admin:planner-policies")
    assert staff.get(url).status_code == 302
    session = staff.session
    session["admin_mfa_verified"] = True
    session.save()
    assert staff.get(url).status_code == 200
    start = timezone.localtime(timezone.now() + timedelta(hours=1))
    response = staff.post(
        url,
        {
            "scope": "GLOBAL",
            "policy": "WARN",
            "effective_from": start.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M"),
            "reason": "Founder policy review",
        },
    )
    assert response.status_code == 302
    assert PlannerPolicy.objects.get().policy == "WARN"
    assert b"Founder policy review" in staff.get(url).content
    invalid = staff.post(
        url,
        {
            "scope": "GLOBAL",
            "policy": "ALLOW",
            "effective_from": start.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M"),
            "reason": "",
        },
    )
    assert invalid.status_code == 200
    assert PlannerPolicy.objects.count() == 1
