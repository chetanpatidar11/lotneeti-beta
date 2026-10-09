import secrets
from datetime import datetime

import pyotp
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from core.crypto import decrypt_value, encrypt_value
from platform_admin.models import AdminTOTPDevice


def enroll_admin(user: User) -> str:
    if not user.is_active or not user.is_staff or not user.is_founder_admin:
        raise ValueError("A Founder Admin account is required")
    secret = pyotp.random_base32()
    AdminTOTPDevice.objects.create(
        user=user,
        secret_ciphertext=encrypt_value(secret, purpose="totp"),
    )
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="LotNeeti")


@transaction.atomic
def verify_admin_code(user: User, code: str, *, at: datetime | None = None) -> bool:
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return False
    device = AdminTOTPDevice.objects.select_for_update().filter(user=user).first()
    if device is None:
        return False

    secret = decrypt_value(device.secret_ciphertext, purpose="totp")
    totp = pyotp.TOTP(secret)
    current_counter = int((at or timezone.now()).timestamp()) // 30
    for counter in (current_counter, current_counter - 1, current_counter + 1):
        if device.last_used_counter is not None and counter <= device.last_used_counter:
            continue
        if secrets.compare_digest(totp.at(counter * 30), code):
            device.last_used_counter = counter
            device.save(update_fields=["last_used_counter"])
            return True
    return False
