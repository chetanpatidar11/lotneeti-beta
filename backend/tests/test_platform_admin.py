from urllib.parse import parse_qs, urlparse

import pyotp
import pytest
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import create_workspace
from core.models import AuditEvent
from funding.models import BankAccount
from investors.models import Investor
from platform_admin.models import AdminTOTPDevice
from platform_admin.totp import enroll_admin, verify_admin_code


def secret_from_uri(uri):
    return parse_qs(urlparse(uri).query)["secret"][0]


@pytest.mark.django_db
def test_founder_admin_can_access_separate_platform_controls():
    founder = User.objects.create_superuser(email="founder@example.test", password="test-password")
    create_workspace(name="Founder's workspace", owner=founder)
    uri = enroll_admin(founder)
    site = Client()
    login_response = site.post(
        reverse("founder_admin:login"),
        {
            "email": founder.email,
            "password": "test-password",
            "code": pyotp.TOTP(secret_from_uri(uri)).now(),
        },
    )

    assert login_response.status_code == 302
    assert AuditEvent.objects.filter(action="admin.login", actor=founder).count() == 1
    assert site.get(reverse("platform-overview")).json() == {"users": 1, "workspaces": 1}
    index = site.get(reverse("founder_admin:index"))
    assert index.status_code == 200
    for model_path in (
        "ipos_ipo_changelist",
        "ipos_gmpobservation_changelist",
        "accounts_user_changelist",
        "planner_planrun_changelist",
        "core_auditevent_changelist",
        "core_betaevent_changelist",
    ):
        url = reverse(f"founder_admin:{model_path}")
        assert url.encode() in index.content
        assert site.get(url).status_code == 200
    assert reverse("founder_admin:support-workspaces").encode() in index.content


@pytest.mark.django_db
def test_support_lookup_shows_redacted_counts_and_requires_founder_mfa():
    founder = User.objects.create_superuser(email="founder@example.test", password="test-password")
    workspace = create_workspace(name="Synthetic support workspace", owner=founder)
    investor = Investor(workspace=workspace, name="Synthetic person")
    investor.set_pan("TESTX0001A")
    investor.save()
    bank = BankAccount(workspace=workspace, owner=investor, bank_name="Synthetic Bank")
    bank.set_account_number("DEMO-ACCOUNT-0001")
    bank.save()
    url = reverse("founder_admin:support-workspaces")
    site = Client()
    site.force_login(founder)
    assert site.get(url, {"q": "Synthetic support"}).status_code == 302
    session = site.session
    session["admin_mfa_verified"] = True
    session.save()

    response = site.get(url, {"q": "Synthetic support"})
    assert response.status_code == 200
    assert str(workspace.pk).encode() in response.content
    assert b"Investors: 1" in response.content
    assert b"Banks: 1" in response.content
    for sensitive in (b"TESTX0001A", b"DEMO-ACCOUNT-0001", founder.email.encode()):
        assert sensitive not in response.content
    assert site.get(url, {"q": str(workspace.pk)}).status_code == 200
    assert AuditEvent.objects.filter(action="admin.support_lookup", actor=founder).count() == 2
    assert all(
        set(event.metadata) == {"result_count"}
        for event in AuditEvent.objects.filter(action="admin.support_lookup")
    )


@pytest.mark.django_db
def test_workspace_owner_does_not_gain_platform_access_even_if_staff():
    owner = User.objects.create_user(email="owner@example.test", is_staff=True)
    create_workspace(name="Owner workspace", owner=owner)
    api = APIClient()
    api.force_authenticate(owner)
    site = Client()
    site.force_login(owner)

    assert api.get(reverse("platform-overview")).status_code == 403
    assert site.get(reverse("founder_admin:index")).status_code == 302


@pytest.mark.django_db
def test_founder_flag_without_staff_status_is_not_enough():
    user = User.objects.create_user(email="flagged@example.test", is_founder_admin=True)
    api = APIClient()
    api.force_authenticate(user)

    assert api.get(reverse("platform-overview")).status_code == 403


@pytest.mark.django_db
def test_founder_password_without_valid_totp_cannot_enter_staff_site():
    founder = User.objects.create_superuser(email="founder@example.test", password="test-password")
    enroll_admin(founder)
    site = Client()
    login_url = reverse("founder_admin:login")

    assert (
        site.post(login_url, {"email": founder.email, "password": "test-password"}).status_code
        == 200
    )
    assert (
        site.post(
            login_url, {"email": founder.email, "password": "test-password", "code": "000000"}
        ).status_code
        == 200
    )
    assert site.get(reverse("founder_admin:index")).status_code == 302
    assert site.get(reverse("platform-overview")).status_code == 403


@pytest.mark.django_db
def test_totp_secret_is_encrypted_and_code_cannot_be_replayed():
    founder = User.objects.create_superuser(email="founder@example.test", password="test-password")
    uri = enroll_admin(founder)
    secret = secret_from_uri(uri)
    device = AdminTOTPDevice.objects.get(user=founder)
    code = pyotp.TOTP(secret).now()

    assert secret not in device.secret_ciphertext
    assert verify_admin_code(founder, code)
    assert not verify_admin_code(founder, code)


@pytest.mark.django_db
def test_staff_login_requires_csrf_token():
    founder = User.objects.create_superuser(email="founder@example.test", password="test-password")
    uri = enroll_admin(founder)
    site = Client(enforce_csrf_checks=True)
    login_url = reverse("founder_admin:login")

    assert site.post(login_url, {}).status_code == 403
    assert site.get(login_url).status_code == 200
    response = site.post(
        login_url,
        {
            "email": founder.email,
            "password": "test-password",
            "code": pyotp.TOTP(secret_from_uri(uri)).now(),
            "csrfmiddlewaretoken": site.cookies["csrftoken"].value,
        },
    )
    assert response.status_code == 302
