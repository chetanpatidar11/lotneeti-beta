from ipaddress import ip_address
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import login, logout
from django.http import Http404
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.auth import consume_email_login, request_email_login
from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from core.audit import record_event


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=32, max_length=256)


class EmailLoginStartView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_email_login(serializer.validated_data["email"])
        return Response({"message": "If this address can sign in, an email is on its way."})


class EmailLoginVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = consume_email_login(request, serializer.validated_data["token"])
        return Response({"id": user.pk, "email": user.email}, status=status.HTTP_200_OK)


class LocalPreviewLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not settings.LOCAL_PREVIEW_AUTH_ENABLED:
            raise Http404
        try:
            remote_is_local = ip_address(request.META.get("REMOTE_ADDR", "")).is_loopback
        except ValueError:
            remote_is_local = False
        frontend_url = urlparse(settings.FRONTEND_BASE_URL)
        if (
            not remote_is_local
            or urlparse(f"http://{request.get_host()}").hostname
            not in {"localhost", "127.0.0.1", "::1"}
            or frontend_url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or request.headers.get("origin") != settings.FRONTEND_BASE_URL.rstrip("/")
        ):
            raise Http404

        email = "local-preview@lotneeti.test"
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(email=email)
        if not user.is_active or user.is_founder_admin or user.is_staff or user.is_superuser:
            raise Http404
        if not WorkspaceMembership.objects.filter(user=user).exists():
            create_workspace(name="Local Preview", owner=user)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        record_event(action="auth.local_preview_login", target=user, actor=user)
        return Response({"id": user.pk, "email": user.email})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"id": request.user.pk, "email": request.user.email})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
