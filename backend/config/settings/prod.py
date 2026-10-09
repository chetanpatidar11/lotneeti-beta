import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(f"Required environment variable {name} is not set")
    return value


SECRET_KEY = required_env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = [host.strip() for host in required_env("DJANGO_ALLOWED_HOSTS").split(",")]
FRONTEND_BASE_URL = required_env("FRONTEND_BASE_URL")
DEFAULT_FROM_EMAIL = required_env("DEFAULT_FROM_EMAIL")
EMAIL_DELIVERY = os.environ.get("EMAIL_DELIVERY", "smtp").lower()
if EMAIL_DELIVERY == "ses":
    EMAIL_BACKEND = "accounts.ses_email.SESEmailBackend"
    AWS_SES_REGION = required_env("AWS_SES_REGION")
elif EMAIL_DELIVERY == "smtp":
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = required_env("EMAIL_HOST")
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = required_env("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = required_env("EMAIL_HOST_PASSWORD")
else:
    raise ImproperlyConfigured("EMAIL_DELIVERY must be ses or smtp")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": required_env("POSTGRES_DB"),
        "USER": required_env("POSTGRES_USER"),
        "PASSWORD": required_env("POSTGRES_PASSWORD"),
        "HOST": required_env("POSTGRES_HOST"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"sslmode": os.environ.get("POSTGRES_SSLMODE", "require")},
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": required_env("REDIS_URL"),
    }
}
RATE_LIMIT_TRUSTED_PROXY_IPS = {"127.0.0.1", "::1"}

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"safe_json": {"()": "core.observability.SafeJSONFormatter"}},
    "handlers": {"stdout": {"class": "logging.StreamHandler", "formatter": "safe_json"}},
    "loggers": {
        "lotneeti": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["stdout"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["stdout"], "level": "WARNING", "propagate": False},
    },
}
