from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from core.rate_limit import RateLimitMiddleware


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@override_settings(
    RATE_LIMIT_ENABLED=True,
    RATE_LIMIT_RULES={
        "auth_start": (2, 60),
        "auth_verify": (2, 60),
        "auth_password": (2, 60),
        "admin_login": (2, 60),
        "admin": (2, 60),
        "import": (2, 60),
        "export": (2, 60),
        "planner": (2, 60),
    },
    RATE_LIMIT_TRUSTED_PROXY_IPS={"127.0.0.1"},
)
def test_sensitive_routes_are_limited_and_retry_after_is_returned():
    factory = RequestFactory()
    middleware = RateLimitMiddleware(lambda request: HttpResponse(status=204))
    routes = [
        ("post", "/api/v1/auth/register/"),
        ("post", "/api/v1/auth/register/verify/"),
        ("post", "/api/v1/auth/password/login/"),
        ("post", "/api/v1/auth/password/reset/start/"),
        ("post", "/api/v1/auth/password/reset/complete/"),
        ("post", "/admin/login/"),
        ("get", "/admin/"),
        ("get", "/api/v1/platform/"),
        ("post", "/api/v1/workspaces/abc/imports/"),
        ("post", "/api/v1/workspaces/abc/planner/preview/"),
        ("post", "/api/v1/workspaces/abc/planner/runs/abc/exports/"),
        ("get", "/api/v1/workspaces/abc/planner/runs/abc/exports/def/download/"),
    ]
    for method, path in routes:
        cache.clear()
        statuses = []
        for _ in range(3):
            request = getattr(factory, method)(path, REMOTE_ADDR="198.51.100.12")
            request.user = SimpleNamespace(pk=7, is_authenticated=True)
            response = middleware(request)
            statuses.append(response.status_code)
        assert statuses == [204, 204, 429], path
        assert 1 <= int(response["Retry-After"]) <= 60


@override_settings(
    RATE_LIMIT_ENABLED=True,
    RATE_LIMIT_RULES={"auth_start": (1, 60), "planner": (1, 60)},
    RATE_LIMIT_TRUSTED_PROXY_IPS={"127.0.0.1"},
)
def test_trusted_proxy_ip_and_user_isolation_ignore_untrusted_forwarding():
    factory = RequestFactory()
    middleware = RateLimitMiddleware(lambda request: HttpResponse(status=204))

    def call(path, ip, forwarded, user_id=None):
        request = factory.post(path, REMOTE_ADDR=ip, HTTP_X_REAL_IP=forwarded)
        request.user = SimpleNamespace(pk=user_id, is_authenticated=user_id is not None)
        return middleware(request).status_code

    auth = "/api/v1/auth/register/"
    assert call(auth, "127.0.0.1", "198.51.100.1") == 204
    assert call(auth, "127.0.0.1", "198.51.100.1") == 429
    assert call(auth, "127.0.0.1", "198.51.100.2") == 204
    assert call(auth, "203.0.113.5", "198.51.100.3") == 204
    assert call(auth, "203.0.113.5", "198.51.100.4") == 429

    planner = "/api/v1/workspaces/abc/planner/preview/"
    assert call(planner, "198.51.100.1", "", 10) == 204
    assert call(planner, "198.51.100.2", "", 10) == 429
    assert call(planner, "198.51.100.1", "", 11) == 204


@pytest.mark.django_db
@override_settings(
    RATE_LIMIT_ENABLED=True,
    RATE_LIMIT_RULES={"auth_start": (1, 60)},
)
def test_registration_endpoint_returns_429_after_limit(client):
    first = client.post(
        "/api/v1/auth/register/",
        data={"email": "rate-limit@example.invalid", "password": "Safe test password 284!"},
        content_type="application/json",
        REMOTE_ADDR="192.0.2.10",
        HTTP_ORIGIN="http://127.0.0.1:3000",
    )
    second = client.post(
        "/api/v1/auth/register/",
        data={"email": "rate-limit@example.invalid", "password": "Safe test password 284!"},
        content_type="application/json",
        REMOTE_ADDR="192.0.2.10",
        HTTP_ORIGIN="http://127.0.0.1:3000",
    )
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json() == {"detail": "Too many requests. Please try again shortly."}
