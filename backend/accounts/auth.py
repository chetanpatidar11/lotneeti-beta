import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import EmailLoginToken, User
from core.audit import record_event

TOKEN_LIFETIME = timedelta(minutes=15)
REQUEST_COOLDOWN = timedelta(minutes=15)
INVALID_LINK = {"token": "This link has expired or was already used."}


def normalized_email(email: str) -> str:
    return email.strip().lower()


def _validate_password(password: str, user: User) -> None:
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise ValidationError({"password": exc.messages}) from exc


def _workspace_user(user: User | None) -> bool:
    return bool(
        user
        and user.is_active
        and not (user.is_staff or user.is_superuser or user.is_founder_admin)
    )


def _send_token(
    email: str, *, purpose: str, subject: str, path: str, password_hash: str = ""
) -> None:
    now = timezone.now()
    if EmailLoginToken.objects.filter(
        email=email, purpose=purpose, created_at__gte=now - REQUEST_COOLDOWN
    ).exists():
        return
    token = secrets.token_urlsafe(32)
    EmailLoginToken.objects.create(
        email=email,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        purpose=purpose,
        pending_password_hash=password_hash,
        expires_at=now + TOKEN_LIFETIME,
    )
    link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}{path}?{urlencode({'token': token})}"
    send_mail(
        subject,
        f"Open this one-time LotNeeti link within 15 minutes:\n\n{link}\n",
        settings.DEFAULT_FROM_EMAIL,
        [email],
    )


@transaction.atomic
def request_registration(email: str, password: str) -> None:
    email = normalized_email(email)
    user = User.objects.filter(email=email).first()
    _validate_password(password, user or User(email=email))
    if user and (
        not _workspace_user(user)
        or (user.email_verified_at is not None and user.has_usable_password())
    ):
        return
    _send_token(
        email,
        purpose=EmailLoginToken.Purpose.VERIFY,
        subject="Verify your LotNeeti email",
        path="/auth/verify",
        password_hash=make_password(password),
    )


def _consume_token(token: str, purpose: str) -> EmailLoginToken:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    record = (
        EmailLoginToken.objects.select_for_update()
        .filter(token_hash=token_hash, purpose=purpose)
        .first()
    )
    if record is None or record.used_at is not None or record.expires_at <= timezone.now():
        raise ValidationError(INVALID_LINK)
    return record


@transaction.atomic
def consume_registration(request, token: str) -> User:
    record = _consume_token(token, EmailLoginToken.Purpose.VERIFY)
    user, _ = User.objects.select_for_update().get_or_create(
        email=record.email, defaults={"password": make_password(None)}
    )
    if (
        not _workspace_user(user)
        or (user.email_verified_at is not None and user.has_usable_password())
        or not record.pending_password_hash
    ):
        raise ValidationError(INVALID_LINK)
    user.password = record.pending_password_hash
    user.email_verified_at = timezone.now()
    user.save(update_fields=["password", "email_verified_at"])
    record.used_at = timezone.now()
    record.pending_password_hash = ""
    record.save(update_fields=["used_at", "pending_password_hash"])
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)
    record_event(action="auth.email_verified", target=user, actor=user)
    return user


def login_with_password(request, email: str, password: str) -> User:
    user = authenticate(request, email=normalized_email(email), password=password)
    if not _workspace_user(user) or user.email_verified_at is None:
        raise ValidationError({"detail": "Email or password is incorrect."})
    login(request, user)
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)
    record_event(action="auth.password_login", target=user, actor=user)
    return user


@transaction.atomic
def request_password_reset(email: str) -> None:
    email = normalized_email(email)
    user = User.objects.filter(email=email).first()
    if (
        not _workspace_user(user)
        or user.email_verified_at is None
        or not user.has_usable_password()
    ):
        return
    _send_token(
        email,
        purpose=EmailLoginToken.Purpose.RESET,
        subject="Reset your LotNeeti password",
        path="/auth/reset",
    )


@transaction.atomic
def complete_password_reset(request, token: str, password: str) -> User:
    record = _consume_token(token, EmailLoginToken.Purpose.RESET)
    user = User.objects.select_for_update().filter(email=record.email).first()
    if not _workspace_user(user) or user.email_verified_at is None:
        raise ValidationError(INVALID_LINK)
    _validate_password(password, user)
    user.set_password(password)
    user.save(update_fields=["password"])
    record.used_at = timezone.now()
    record.save(update_fields=["used_at"])
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)
    record_event(action="auth.password_reset", target=user, actor=user)
    return user
