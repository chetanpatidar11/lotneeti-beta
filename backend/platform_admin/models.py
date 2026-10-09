from django.conf import settings
from django.db import models


class AdminTOTPDevice(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="admin_totp_device"
    )
    secret_ciphertext = models.TextField()
    last_used_counter = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Admin authenticator for user {self.user_id}"
