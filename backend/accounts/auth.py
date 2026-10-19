import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from accounts.models import EmailLoginToken, User
from core.audit import record_event

TOKEN_LIFETIME = timedelta(minutes=15)
REQUEST_COOLDOWN = timedelta(minutes=1)
MAX_CODE_ATTEMPTS = 5
INVALID_LINK = {"token": "This link has expired or was already used."}
INVALID_CODE = {"code": "The code is incorrect or has expired. Request a new code if needed."}
logger = logging.getLogger(__name__)


class EmailDeliveryUnavailable(APIException):
    status_code = 503
    default_detail = "Verification email is temporarily unavailable. Please try again."
    default_code = "email_delivery_unavailable"


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


def _code_hash(email: str, purpose: str, code: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), f"{purpose}:{email}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def _send_code(email: str, *, purpose: str, subject: str, password_hash: str = "") -> bool:
    now = timezone.now()
    if EmailLoginToken.objects.filter(
        email=email, purpose=purpose, created_at__gte=now - REQUEST_COOLDOWN
    ).exists():
        return True
    code = f"{secrets.randbelow(1_000_000):06d}"
    record = EmailLoginToken.objects.create(
        email=email,
        token_hash=_code_hash(email, purpose, code),
        purpose=purpose,
        pending_password_hash=password_hash,
        expires_at=now + TOKEN_LIFETIME,
    )
    try:
        sent = send_mail(
            subject,
            f"Your LotNeeti verification code is {code}. It expires in 15 minutes. "
            "If you did not request it, ignore this email.\n",
            settings.DEFAULT_FROM_EMAIL,
            [email],
        )
        if sent != 1:
            raise RuntimeError("Mail backend did not accept the verification email")
    except Exception:
        record.delete()
        logger.exception("Account code email delivery failed")
        return False
    return True


def _consume_code(email: str, code: str, purpose: str) -> EmailLoginToken:
    email = normalized_email(email)
    record = (
        EmailLoginToken.objects.select_for_update()
        .filter(email=email, purpose=purpose, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if (
        record is None
        or record.expires_at <= timezone.now()
        or record.failed_attempts >= MAX_CODE_ATTEMPTS
    ):
        raise ValidationError(INVALID_CODE)
    if not hmac.compare_digest(record.token_hash, _code_hash(email, purpose, code)):
        record.failed_attempts += 1
        record.save(update_fields=["failed_attempts"])
        return None
    return record


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
    if not _workspace_user(user) or user.has_usable_password() or not record.pending_password_hash:
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


def request_registration(email: str, password: str) -> bool:
    email = normalized_email(email)
    if User.objects.filter(email=email).exists():
        return False
    _validate_password(password, User(email=email))
    sent = _send_code(
        email,
        purpose=EmailLoginToken.Purpose.VERIFY,
        subject="Verify your LotNeeti account",
        password_hash=make_password(password),
    )
    if not sent:
        raise EmailDeliveryUnavailable()
    return True


@transaction.atomic
def verify_registration_code(request, email: str, code: str) -> User | None:
    record = _consume_code(email, code, EmailLoginToken.Purpose.VERIFY)
    if record is None:
        return None
    if User.objects.filter(email=record.email).exists() or not record.pending_password_hash:
        raise ValidationError(INVALID_CODE)
    user = User.objects.create(
        email=record.email, password=record.pending_password_hash, email_verified_at=timezone.now()
    )
    record.used_at = timezone.now()
    record.pending_password_hash = ""
    record.save(update_fields=["used_at", "pending_password_hash"])
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)
    record_event(action="auth.email_verified", target=user, actor=user)
    return user


@transaction.atomic
def login_with_password(request, email: str, password: str) -> User:
    email = normalized_email(email)
    user = User.objects.filter(email=email).first()
    if user is None:
        raise ValidationError({"detail": "Email or password is incorrect."})
    user = authenticate(request, email=email, password=password)
    if not _workspace_user(user):
        raise ValidationError({"detail": "Email or password is incorrect."})
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)
    record_event(
        action="auth.password_login",
        target=user,
        actor=user,
    )
    return user


@transaction.atomic
def request_password_reset(email: str) -> None:
    email = normalized_email(email)
    user = User.objects.filter(email=email).first()
    if not _workspace_user(user):
        return
    _send_code(
        email,
        purpose=EmailLoginToken.Purpose.RESET,
        subject="Reset your LotNeeti password",
    )


@transaction.atomic
def complete_password_reset_code(request, email: str, code: str, password: str) -> User | None:
    record = _consume_code(email, code, EmailLoginToken.Purpose.RESET)
    if record is None:
        return None
    user = User.objects.select_for_update().filter(email=record.email).first()
    if not _workspace_user(user):
        raise ValidationError(INVALID_CODE)
    _validate_password(password, user)
    user.set_password(password)
    user.save(update_fields=["password"])
    record.used_at = timezone.now()
    record.save(update_fields=["used_at"])
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)
    record_event(action="auth.password_reset", target=user, actor=user)
    return user


@transaction.atomic
def complete_password_reset(request, token: str, password: str) -> User:
    record = _consume_token(token, EmailLoginToken.Purpose.RESET)
    user = User.objects.select_for_update().filter(email=record.email).first()
    if not _workspace_user(user):
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
