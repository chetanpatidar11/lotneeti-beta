from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import EmailLoginToken, User, Workspace, WorkspaceMembership
from core.models import AuditEvent

FRONTEND_ORIGIN = "http://127.0.0.1:3000"


def token_from_email():
    link = mail.outbox[-1].body.splitlines()[-1]
    return parse_qs(urlparse(link).query)["token"][0]


@pytest.mark.django_db
def test_registration_verifies_email_once_then_password_sign_in_keeps_session():
    client = APIClient(HTTP_ORIGIN=FRONTEND_ORIGIN)
    start = client.post(
        reverse("register"), {"email": "New@Example.Test", "password": "Safe test password 284!"}
    )

    assert start.status_code == 200
    assert len(mail.outbox) == 1
    assert User.objects.count() == 0
    token = token_from_email()
    assert token not in EmailLoginToken.objects.get().token_hash

    assert (
        client.post(
            reverse("password-login"),
            {"email": "new@example.test", "password": "Safe test password 284!"},
        ).status_code
        == 400
    )
    verify = client.post(reverse("register-verify"), {"token": token})

    assert verify.status_code == 200
    assert verify.data["email"] == "new@example.test"
    assert AuditEvent.objects.get(action="auth.email_verified").actor.email == "new@example.test"
    assert User.objects.get(email="new@example.test").email_verified_at is not None
    assert client.get(reverse("me")).status_code == 200
    assert client.session.get_expiry_age() > 29 * 24 * 60 * 60
    assert client.post(reverse("session-refresh")).status_code == 204
    assert int(client.cookies["sessionid"]["max-age"]) >= 29 * 24 * 60 * 60
    assert client.post(reverse("register-verify"), {"token": token}).status_code == 400
    assert client.post(reverse("logout")).status_code == 204
    assert client.get(reverse("me")).status_code == 403
    assert (
        client.post(
            reverse("password-login"),
            {"email": "NEW@example.test", "password": "Safe test password 284!"},
        ).status_code
        == 200
    )
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_expired_verification_link_cannot_sign_in():
    client = APIClient(HTTP_ORIGIN=FRONTEND_ORIGIN)
    client.post(
        reverse("register"), {"email": "person@example.test", "password": "Safe test password 284!"}
    )
    token = token_from_email()
    EmailLoginToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

    assert client.post(reverse("register-verify"), {"token": token}).status_code == 400
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_repeat_request_is_throttled_and_founder_link_is_not_sent():
    client = APIClient(HTTP_ORIGIN=FRONTEND_ORIGIN)
    start = reverse("register")
    data = {"email": "person@example.test", "password": "Safe test password 284!"}
    client.post(start, data)
    client.post(start, data)
    assert len(mail.outbox) == 1

    User.objects.create_superuser(email="founder@example.test", password="test-password")
    response = client.post(
        start, {"email": "founder@example.test", "password": "Safe test password 284!"}
    )
    assert response.status_code == 200
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_existing_magic_link_user_can_set_password_after_email_verification():
    user = User.objects.create_user(email="existing@example.test")
    client = APIClient(HTTP_ORIGIN=FRONTEND_ORIGIN)
    assert (
        client.post(
            reverse("register"), {"email": user.email, "password": "New safe password 284!"}
        ).status_code
        == 200
    )
    token = token_from_email()
    assert client.post(reverse("register-verify"), {"token": token}).status_code == 200
    user.refresh_from_db()
    assert user.check_password("New safe password 284!")
    assert user.email_verified_at is not None


@pytest.mark.django_db
def test_password_reset_is_one_time_and_invalidates_old_password():
    user = User.objects.create_user(email="person@example.test", password="Old safe password 284!")
    user.email_verified_at = timezone.now()
    user.save(update_fields=["email_verified_at"])
    client = APIClient(HTTP_ORIGIN=FRONTEND_ORIGIN)
    assert client.post(reverse("password-reset-start"), {"email": user.email}).status_code == 200
    token = token_from_email()
    assert (
        client.post(
            reverse("password-reset-complete"),
            {"token": token, "password": "New safe password 284!"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            reverse("password-reset-complete"),
            {"token": token, "password": "Other safe password 284!"},
        ).status_code
        == 400
    )
    client.post(reverse("logout"))
    assert (
        client.post(
            reverse("password-login"), {"email": user.email, "password": "Old safe password 284!"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            reverse("password-login"), {"email": user.email, "password": "New safe password 284!"}
        ).status_code
        == 200
    )


@pytest.mark.django_db
def test_password_login_rejects_founder_and_unverified_accounts():
    client = APIClient(HTTP_ORIGIN=FRONTEND_ORIGIN)
    founder = User.objects.create_superuser(
        email="founder@example.test", password="Safe test password 284!"
    )
    founder.email_verified_at = timezone.now()
    founder.save(update_fields=["email_verified_at"])
    unverified = User.objects.create_user(
        email="pending@example.test", password="Safe test password 284!"
    )
    for email in (founder.email, unverified.email):
        assert (
            client.post(
                reverse("password-login"), {"email": email, "password": "Safe test password 284!"}
            ).status_code
            == 400
        )


@pytest.mark.django_db
def test_registration_rejects_cross_site_requests_without_sending_email():
    client = APIClient()
    data = {"email": "person@example.test", "password": "Safe test password 284!"}
    assert (
        client.post(reverse("register"), data, HTTP_ORIGIN="https://other.example").status_code
        == 403
    )
    assert client.post(reverse("register"), data).status_code == 403
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_local_preview_login_is_opt_in_and_creates_only_a_local_workspace():
    client = APIClient()
    url = reverse("local-preview-login")
    origin = "http://127.0.0.1:3000"
    assert client.post(url, HTTP_ORIGIN=origin, HTTP_HOST="127.0.0.1:8000").status_code == 404

    with override_settings(LOCAL_PREVIEW_AUTH_ENABLED=True, FRONTEND_BASE_URL=origin):
        response = client.post(
            url, HTTP_ORIGIN=origin, HTTP_HOST="127.0.0.1:8000", REMOTE_ADDR="127.0.0.1"
        )
        assert response.status_code == 200
        assert response.data["email"] == "local-preview@lotneeti.test"
        assert client.get(reverse("me")).status_code == 200
        user = User.objects.get(email="local-preview@lotneeti.test")
        assert user.has_usable_password() is False
        assert not user.is_staff and not user.is_founder_admin and not user.is_superuser
        assert Workspace.objects.count() == 1
        assert WorkspaceMembership.objects.get(user=user).role == WorkspaceMembership.Role.OWNER
        assert client.post(url, HTTP_ORIGIN=origin, HTTP_HOST="127.0.0.1:8000").status_code == 200
        assert Workspace.objects.count() == 1


@pytest.mark.django_db
def test_local_preview_login_rejects_nonlocal_requests_and_wrong_origin():
    client = APIClient()
    url = reverse("local-preview-login")
    origin = "http://127.0.0.1:3000"
    with override_settings(LOCAL_PREVIEW_AUTH_ENABLED=True, FRONTEND_BASE_URL=origin):
        assert (
            client.post(
                url, HTTP_ORIGIN=origin, HTTP_HOST="127.0.0.1:8000", REMOTE_ADDR="203.0.113.2"
            ).status_code
            == 404
        )
        assert (
            client.post(
                url, HTTP_ORIGIN="http://example.test", HTTP_HOST="127.0.0.1:8000"
            ).status_code
            == 404
        )
    assert User.objects.count() == 0
