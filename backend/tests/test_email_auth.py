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


def token_from_email():
    link = mail.outbox[-1].body.splitlines()[-1]
    return parse_qs(urlparse(link).query)["token"][0]


@pytest.mark.django_db
def test_email_link_creates_user_and_persistent_session_once():
    client = APIClient()
    start = client.post(reverse("email-login-start"), {"email": "New@Example.Test"})

    assert start.status_code == 200
    assert len(mail.outbox) == 1
    assert User.objects.count() == 0
    token = token_from_email()
    assert token not in EmailLoginToken.objects.get().token_hash

    verify = client.post(reverse("email-login-verify"), {"token": token})

    assert verify.status_code == 200
    assert verify.data["email"] == "new@example.test"
    assert AuditEvent.objects.get(action="auth.email_login").actor.email == "new@example.test"
    assert client.get(reverse("me")).status_code == 200
    assert client.session.get_expiry_age() > 29 * 24 * 60 * 60
    assert client.post(reverse("email-login-verify"), {"token": token}).status_code == 400
    assert client.post(reverse("logout")).status_code == 204
    assert client.get(reverse("me")).status_code == 403


@pytest.mark.django_db
def test_expired_link_cannot_sign_in():
    client = APIClient()
    client.post(reverse("email-login-start"), {"email": "person@example.test"})
    token = token_from_email()
    EmailLoginToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

    assert client.post(reverse("email-login-verify"), {"token": token}).status_code == 400
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_repeat_request_is_throttled_and_founder_link_is_not_sent():
    client = APIClient()
    start = reverse("email-login-start")
    client.post(start, {"email": "person@example.test"})
    client.post(start, {"email": "person@example.test"})
    assert len(mail.outbox) == 1

    User.objects.create_superuser(email="founder@example.test", password="test-password")
    response = client.post(start, {"email": "founder@example.test"})
    assert response.status_code == 200
    assert len(mail.outbox) == 1


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
