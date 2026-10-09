from importlib import import_module

from django.test import Client, override_settings
from django.urls import reverse


def test_production_settings_require_https_and_secure_cookies(monkeypatch):
    synthetic_env = {
        "DJANGO_SECRET_KEY": "synthetic-settings-check-only",
        "DJANGO_ALLOWED_HOSTS": "testserver",
        "FRONTEND_BASE_URL": "https://app.example.test",
        "DEFAULT_FROM_EMAIL": "noreply@example.test",
        "EMAIL_HOST": "smtp.example.test",
        "EMAIL_HOST_USER": "synthetic-user",
        "EMAIL_HOST_PASSWORD": "synthetic-value",
        "POSTGRES_DB": "synthetic-db",
        "POSTGRES_USER": "synthetic-user",
        "POSTGRES_PASSWORD": "synthetic-value",
        "POSTGRES_HOST": "db.example.test",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
    }
    for name, value in synthetic_env.items():
        monkeypatch.setenv(name, value)
    prod = import_module("config.settings.prod")
    assert prod.LOCAL_PREVIEW_AUTH_ENABLED is False
    assert prod.SECURE_SSL_REDIRECT is True
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.SESSION_COOKIE_HTTPONLY is True
    assert prod.CSRF_COOKIE_SECURE is True
    assert prod.SECURE_HSTS_SECONDS > 0
    assert prod.SECURE_CONTENT_TYPE_NOSNIFF is True
    assert prod.X_FRAME_OPTIONS == "DENY"

    with override_settings(
        SECURE_SSL_REDIRECT=prod.SECURE_SSL_REDIRECT,
        SECURE_HSTS_SECONDS=prod.SECURE_HSTS_SECONDS,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=prod.SECURE_HSTS_INCLUDE_SUBDOMAINS,
        SECURE_CONTENT_TYPE_NOSNIFF=prod.SECURE_CONTENT_TYPE_NOSNIFF,
        X_FRAME_OPTIONS=prod.X_FRAME_OPTIONS,
        SESSION_COOKIE_SECURE=prod.SESSION_COOKIE_SECURE,
        SESSION_COOKIE_HTTPONLY=prod.SESSION_COOKIE_HTTPONLY,
        CSRF_COOKIE_SECURE=prod.CSRF_COOKIE_SECURE,
    ):
        client = Client()
        insecure = client.get(reverse("api-v1-health"))
        assert insecure.status_code == 301
        assert insecure["Location"].startswith("https://")
        secure = client.get(reverse("api-v1-health"), secure=True)
        assert secure.status_code == 200
        assert secure["Strict-Transport-Security"].startswith("max-age=")
        assert secure["X-Content-Type-Options"] == "nosniff"
        assert secure["X-Frame-Options"] == "DENY"
        client.get(reverse("founder_admin:login"), secure=True)
        assert client.cookies["csrftoken"]["secure"] is True
