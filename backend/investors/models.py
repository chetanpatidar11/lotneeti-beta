import uuid

from django.core.validators import MinValueValidator
from django.db import models

from core.crypto import decrypt_value, encrypt_value, lookup_hash


def pan_hash_for_workspace(workspace_id, normalized_pan: str) -> str:
    return lookup_hash(f"{workspace_id}:{normalized_pan}", purpose="pan")


class Investor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace", on_delete=models.CASCADE, related_name="investors"
    )
    name = models.CharField(max_length=120)
    pan_ciphertext = models.TextField()
    pan_lookup_hash = models.CharField(max_length=64)
    planning_priority = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1)]
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "pan_lookup_hash"], name="unique_workspace_pan"
            )
        ]

    def __str__(self):
        return self.name

    def set_pan(self, pan: str) -> None:
        normalized = pan.strip().upper()
        self.pan_ciphertext = encrypt_value(normalized, purpose="pan")
        self.pan_lookup_hash = pan_hash_for_workspace(self.workspace_id, normalized)

    @property
    def pan_masked(self) -> str:
        pan = decrypt_value(self.pan_ciphertext, purpose="pan")
        return f"******{pan[-4:]}"


class DematAccount(models.Model):
    class Depository(models.TextChoices):
        CDSL = "CDSL", "CDSL"
        NSDL = "NSDL", "NSDL"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investor = models.ForeignKey(Investor, on_delete=models.CASCADE, related_name="demats")
    depository = models.CharField(max_length=4, choices=Depository.choices)
    dp_id_ciphertext = models.TextField()
    client_id_ciphertext = models.TextField()
    broker = models.CharField(max_length=120, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.depository} demat for {self.investor.name}"

    def set_dp_id(self, value: str) -> None:
        self.dp_id_ciphertext = encrypt_value(value.strip(), purpose="demat")

    def set_client_id(self, value: str) -> None:
        self.client_id_ciphertext = encrypt_value(value.strip(), purpose="demat")

    @property
    def dp_id_masked(self) -> str:
        value = decrypt_value(self.dp_id_ciphertext, purpose="demat")
        return f"••••{value[-4:]}"

    @property
    def client_id_masked(self) -> str:
        value = decrypt_value(self.client_id_ciphertext, purpose="demat")
        return f"••••{value[-4:]}"


class AccountImportBatch(models.Model):
    class Status(models.TextChoices):
        PREVIEWED = "PREVIEWED", "Previewed"
        CONFIRMED = "CONFIRMED", "Confirmed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace", on_delete=models.CASCADE, related_name="account_imports"
    )
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="account_imports"
    )
    source_filename = models.CharField(max_length=255)
    source_hash = models.CharField(max_length=64)
    rows_ciphertext = models.TextField()
    row_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PREVIEWED)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.source_filename} ({self.status})"
