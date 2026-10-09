import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import login
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import EmailLoginToken, User
from core.audit import record_event

TOKEN_LIFETIME = timedelta(minutes=15)
REQUEST_COOLDOWN = timedelta(minutes=1)


def request_email_login(email: str) -> None:
    normalized_email = email.strip().lower()
    now = timezone.now()
    if EmailLoginToken.objects.filter(
        email=normalized_email, created_at__gte=now - REQUEST_COOLDOWN
    ).exists():
        return

    # Platform administration uses its own MFA flow; email links are for workspace access.
    if User.objects.filter(email=normalized_email, is_founder_admin=True).exists():
        return

    token = secrets.token_urlsafe(32)
    EmailLoginToken.objects.create(
        email=normalized_email,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=now + TOKEN_LIFETIME,
    )
    link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/auth/verify?{urlencode({'token': token})}"
    send_mail(
        "Sign in to LotNeeti",
        f"Open this link to sign in. It expires in 15 minutes:\n\n{link}\n",
        settings.DEFAULT_FROM_EMAIL,
        [normalized_email],
    )


@transaction.atomic
def consume_email_login(request, token: str) -> User:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    record = EmailLoginToken.objects.select_for_update().filter(token_hash=token_hash).first()
    if record is None or record.used_at is not None or record.expires_at <= timezone.now():
        raise ValidationError({"token": "This sign-in link has expired or was already used."})

    user, _ = User.objects.get_or_create(email=record.email)
    if not user.is_active or user.is_founder_admin:
        raise ValidationError({"token": "This sign-in link cannot be used."})

    record.used_at = timezone.now()
    record.save(update_fields=["used_at"])
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)
    record_event(
        action="auth.email_login", target=user, actor=user, metadata={"method": "EMAIL_LINK"}
    )
    return user
