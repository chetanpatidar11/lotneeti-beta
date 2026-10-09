import base64
import hashlib
import hmac

from cryptography.fernet import Fernet
from django.conf import settings


def _cipher(purpose: str) -> Fernet:
    key = hashlib.sha256(f"{settings.SECRET_KEY}:lotneeti:{purpose}:v1".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_value(value: str, *, purpose: str) -> str:
    return _cipher(purpose).encrypt(value.encode()).decode()


def decrypt_value(value: str, *, purpose: str) -> str:
    return _cipher(purpose).decrypt(value.encode()).decode()


def lookup_hash(value: str, *, purpose: str) -> str:
    key = f"{settings.SECRET_KEY}:lotneeti:{purpose}:lookup:v1".encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()
