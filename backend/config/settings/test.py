import os

from .base import *  # noqa: F403

ACTIVE_IPO_SOURCE = None

SECRET_KEY = "test-only-not-a-secret"
LOCAL_PREVIEW_AUTH_ENABLED = os.environ.get("LOTNEETI_LOCAL_PREVIEW_AUTH") == "1"
ALLOWED_HOSTS = ["testserver", "127.0.0.1", "localhost"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("LOTNEETI_TEST_DB", ":memory:"),
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
RATE_LIMIT_ENABLED = False

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
EMAIL_BACKEND = os.environ.get(
    "LOTNEETI_TEST_EMAIL_BACKEND", "django.core.mail.backends.locmem.EmailBackend"
)
EMAIL_FILE_PATH = os.environ.get("LOTNEETI_TEST_EMAIL_FILE_PATH", "/private/tmp/lotneeti-mail")
