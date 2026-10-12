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
def test_one_form_creates_account_without_email_then_signs_in_for_30_days():
    client = APIClient(HTTP_ORIGIN=FRONTEND_ORIGIN)
    credentials = {"email": "New@Example.Test", "password": "Safe test password 284!"}
    created = client.post(reverse("password-login"), credentials)
    assert created.status_code == 200
    assert created.data["email"] == "new@example.test"
    user = User.objects.get(email="new@example.test")
    assert user.email_verified_at is None
    assert user.check_password(credentials["password"])
    assert len(mail.outbox) == 0
    assert AuditEvent.objects.filter(action="auth.account_created", actor=user).exists()
    assert client.get(reverse("me")).status_code == 200
    assert client.session.get_expiry_age() > 29 * 24 * 60 * 60
    assert client.post(reverse("session-refresh")).status_code == 204
    assert int(client.cookies["sessionid"]["max-age"]) >= 29 * 24 * 60 * 60
    assert client.post(reverse("logout")).status_code == 204
    assert client.post(reverse("password-login"), credentials).status_code == 200
    assert User.objects.count() == 1
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_existing_account_wrong_password_does_not_create_or_change_account():
    user = User.objects.create_user(email="person@example.test", password="Old safe password 284!")
    client = APIClient(HTTP_ORIGIN=FRONTEND_ORIGIN)
    response = client.post(
        reverse("password-login"),
        {"email": "person@example.test", "password": "Wrong password 284!"},
    )
    assert response.status_code == 400
    assert response.data == {"detail": "Email or password is incorrect."}
    assert User.objects.count() == 1
    user.refresh_from_db()
    assert user.check_password("Old safe password 284!")
    assert client.get(reverse("me")).status_code == 403
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_register_alias_uses_same_account_entry_without_verification_email():
    client = APIClient(HTTP_ORIGIN=FRONTEND_ORIGIN)
    response = client.post(
        reverse("register"), {"email": "person@example.test", "password": "Safe test password 284!"}
    )
    assert response.status_code == 200
    assert client.get(reverse("me")).status_code == 200
    assert User.objects.count() == 1
    assert EmailLoginToken.objects.count() == 0
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_password_reset_response_does_not_disclose_account_and_recovers_old_magic_user():
    user = User.objects.create_user(email="old@example.test")
    client = APIClient(HTTP_ORIGIN=FRONTEND_ORIGIN)
    missing = client.post(reverse("password-reset-start"), {"email": "missing@example.test"})
    present = client.post(reverse("password-reset-start"), {"email": user.email})
    assert missing.status_code == present.status_code == 200
    assert missing.data == present.data
    assert len(mail.outbox) == 1
    token = token_from_email()
    assert (
        client.post(
            reverse("password-reset-complete"),
            {"token": token, "password": "New safe password 284!"},
        ).status_code
        == 200
    )
    user.refresh_from_db()
    assert user.check_password("New safe password 284!")


@pytest.mark.django_db
def test_password_reset_delivery_failure_keeps_generic_response(monkeypatch):
    User.objects.create_user(email="person@example.test", password="Safe test password 284!")

    def failed_send(*args, **kwargs):
        raise RuntimeError("mail unavailable")

    monkeypatch.setattr("accounts.auth.send_mail", failed_send)
    client = APIClient(HTTP_ORIGIN=FRONTEND_ORIGIN)
    missing = client.post(reverse("password-reset-start"), {"email": "missing@example.test"})
    present = client.post(reverse("password-reset-start"), {"email": "person@example.test"})
    assert missing.status_code == present.status_code == 200
    assert missing.data == present.data
    assert EmailLoginToken.objects.count() == 0


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
def test_password_login_rejects_founder_but_allows_unverified_members():
    client = APIClient(HTTP_ORIGIN=FRONTEND_ORIGIN)
    founder = User.objects.create_superuser(
        email="founder@example.test", password="Safe test password 284!"
    )
    founder.email_verified_at = timezone.now()
    founder.save(update_fields=["email_verified_at"])
    unverified = User.objects.create_user(
        email="pending@example.test", password="Safe test password 284!"
    )
    assert (
        client.post(
            reverse("password-login"),
            {"email": founder.email, "password": "Safe test password 284!"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            reverse("password-login"),
            {"email": unverified.email, "password": "Safe test password 284!"},
        ).status_code
        == 200
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
