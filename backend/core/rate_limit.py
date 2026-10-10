"""Small fixed-window limits for high-cost and authentication routes."""

import hashlib
import hmac
import ipaddress
import time

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse


def _scope(request):
    path = request.path_info
    method = request.method
    if (
        path in {"/api/v1/auth/register/", "/api/v1/auth/password/reset/start/"}
        and method == "POST"
    ):
        return "auth_start"
    if (
        path in {"/api/v1/auth/register/verify/", "/api/v1/auth/password/reset/complete/"}
        and method == "POST"
    ):
        return "auth_verify"
    if path == "/api/v1/auth/password/login/" and method == "POST":
        return "auth_password"
    if path == "/admin/login/" and method == "POST":
        return "admin_login"
    if path.startswith("/admin/") or path.startswith("/api/v1/platform/"):
        return "admin"
    if path.startswith("/api/v1/workspaces/"):
        if "/imports/" in path and method != "GET":
            return "import"
        if "/exports/" in path:
            return "export"
        if "/planner/" in path and method in {"POST", "PATCH"}:
            return "planner"
    return None


def _client_ip(request):
    remote = request.META.get("REMOTE_ADDR", "")
    forwarded = request.META.get("HTTP_X_REAL_IP", "")
    if remote in settings.RATE_LIMIT_TRUSTED_PROXY_IPS and forwarded:
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    try:
        return str(ipaddress.ip_address(remote))
    except ValueError:
        return "unknown"


class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.RATE_LIMIT_ENABLED:
            return self.get_response(request)
        scope = _scope(request)
        if scope is None:
            return self.get_response(request)
        limit, window = settings.RATE_LIMIT_RULES[scope]
        user = getattr(request, "user", None)
        identity = (
            f"user:{user.pk}"
            if scope not in {"auth_start", "auth_verify", "auth_password", "admin_login"}
            and user is not None
            and user.is_authenticated
            else f"ip:{_client_ip(request)}"
        )
        now = int(time.time())
        bucket = now // window
        digest = hmac.new(
            settings.SECRET_KEY.encode(), f"{scope}:{identity}".encode(), hashlib.sha256
        ).hexdigest()
        key = f"rl:{scope}:{digest}:{bucket}"
        try:
            if cache.add(key, 1, timeout=window + 1):
                count = 1
            else:
                count = cache.incr(key)
        except ValueError:
            # The previous bucket can expire between add and incr.
            cache.add(key, 1, timeout=window + 1)
            count = 1
        if count > limit:
            response = JsonResponse(
                {"detail": "Too many requests. Please try again shortly."}, status=429
            )
            response["Retry-After"] = str(window - now % window)
            return response
        return self.get_response(request)
