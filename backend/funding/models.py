import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from core.crypto import decrypt_value, encrypt_value, lookup_hash


def account_hash_for_workspace(workspace_id, account_number: str) -> str:
    return lookup_hash(f"{workspace_id}:{account_number}", purpose="bank-account")


class BankFundingRestriction(models.Model):
    """Founder-managed bank names whose accounts cannot fund other investors."""

    name = models.CharField(max_length=120, unique=True)
    aliases = models.TextField(blank=True, help_text="One alternative bank name per line.")
    active = models.BooleanField(default=True)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class BankAccount(models.Model):
    class CrossFundingPolicy(models.TextChoices):
        DEFAULT = "DEFAULT", "Use workspace setting"
        ALLOW = "ALLOW", "Allow"
        WARN = "WARN", "Warn"
        DISALLOW = "DISALLOW", "Disallow"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace", on_delete=models.CASCADE, related_name="banks"
    )
    owner = models.ForeignKey("investors.Investor", on_delete=models.PROTECT, related_name="banks")
    bank_name = models.CharField(max_length=120)
    account_ciphertext = models.TextField()
    account_lookup_hash = models.CharField(max_length=64)
    current_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    cross_funding_policy = models.CharField(
        max_length=8, choices=CrossFundingPolicy.choices, default=CrossFundingPolicy.DEFAULT
    )
    restricted_investor = models.ForeignKey(
        "investors.Investor",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="restricted_banks",
    )
    active = models.BooleanField(default=True)
    is_placeholder = models.BooleanField(default=False)
    is_imported_reference = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "account_lookup_hash"], name="unique_workspace_bank_account"
            )
        ]

    def __str__(self):
        return f"{self.bank_name} for {self.owner.name}"

    def set_account_number(self, value: str) -> None:
        normalized = value.strip()
        self.account_ciphertext = encrypt_value(normalized, purpose="bank-account")
        self.account_lookup_hash = account_hash_for_workspace(self.workspace_id, normalized)

    @property
    def account_masked(self) -> str:
        value = decrypt_value(self.account_ciphertext, purpose="bank-account")
        return f"••••{value[-4:]}"


class BalanceChange(models.Model):
    class Operation(models.TextChoices):
        ADD = "ADD", "Add Money"
        REMOVE = "REMOVE", "Remove Money"
        SET = "SET", "Set Balance"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer out"
        TRANSFER_IN = "TRANSFER_IN", "Transfer in"
        ALLOTMENT = "ALLOTMENT", "Allotment cost"

    bank = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="balance_changes")
    operation = models.CharField(max_length=12, choices=Operation.choices)
    old_balance = models.DecimalField(max_digits=14, decimal_places=2)
    delta = models.DecimalField(max_digits=14, decimal_places=2)
    new_balance = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    transfer_id = models.UUIDField(null=True, blank=True, db_index=True)
    counterparty_label = models.CharField(max_length=180, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.operation} on bank {self.bank_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Balance history cannot be changed")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Balance history cannot be deleted")


class ArchivedBalanceChange(models.Model):
    """Immutable balance history retained after an unused bank account is deleted."""

    workspace = models.ForeignKey("accounts.Workspace", on_delete=models.PROTECT)
    bank_ref = models.UUIDField()
    bank_name = models.CharField(max_length=120)
    account_masked = models.CharField(max_length=20)
    source_change_id = models.PositiveBigIntegerField()
    operation = models.CharField(max_length=12, choices=BalanceChange.Operation.choices)
    old_balance = models.DecimalField(max_digits=14, decimal_places=2)
    delta = models.DecimalField(max_digits=14, decimal_places=2)
    new_balance = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    transfer_id = models.UUIDField(null=True, blank=True, db_index=True)
    counterparty_label = models.CharField(max_length=180, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "source_change_id"],
                name="unique_archived_balance_change",
            )
        ]
        ordering = ["-created_at", "-source_change_id"]

    def __str__(self):
        return f"{self.operation} on deleted bank {self.bank_ref}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Archived balance history cannot be changed")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Archived balance history cannot be deleted")


def upi_hash_for_workspace(workspace_id, normalized_handle: str) -> str:
    return lookup_hash(f"{workspace_id}:{normalized_handle}", purpose="upi")


class UPIHandle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bank = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name="upis")
    holder = models.ForeignKey("investors.Investor", on_delete=models.PROTECT, related_name="upis")
    handle_ciphertext = models.TextField()
    handle_lookup_hash = models.CharField(max_length=64)
    active = models.BooleanField(default=True)
    verified = models.BooleanField(default=True)
    count_limit_override = models.PositiveSmallIntegerField(null=True, blank=True)
    amount_limit_override = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["handle_lookup_hash"], name="unique_upi_handle_lookup")
        ]

    def __str__(self):
        return f"UPI for {self.holder.name}"

    def set_handle(self, value: str) -> None:
        normalized = value.strip().lower()
        self.handle_ciphertext = encrypt_value(normalized, purpose="upi")
        self.handle_lookup_hash = upi_hash_for_workspace(self.bank.workspace_id, normalized)

    @property
    def handle(self) -> str:
        return decrypt_value(self.handle_ciphertext, purpose="upi")

    @property
    def handle_masked(self) -> str:
        handle = decrypt_value(self.handle_ciphertext, purpose="upi")
        _, provider = handle.rsplit("@", 1)
        return f"••••@{provider}"


class RecurringDebit(models.Model):
    class Frequency(models.TextChoices):
        DAILY = "DAILY", "Daily"
        WEEKLY = "WEEKLY", "Weekly"
        MONTHLY = "MONTHLY", "Monthly"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bank = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name="recurring_debits")
    name = models.CharField(max_length=120)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    frequency = models.CharField(max_length=7, choices=Frequency.choices)
    start_date = models.DateField()
    next_due_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if self.amount is not None and self.amount <= 0:
            errors["amount"] = "Amount must be greater than zero."
        if self.start_date and self.next_due_date and self.next_due_date < self.start_date:
            errors["next_due_date"] = "Next date cannot be before the start date."
        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "End date cannot be before the start date."
        if errors:
            raise ValidationError(errors)


class RecurringDebitOccurrence(models.Model):
    recurring_debit = models.ForeignKey(
        RecurringDebit, on_delete=models.PROTECT, related_name="occurrences"
    )
    due_date = models.DateField()
    balance_change = models.OneToOneField(BalanceChange, on_delete=models.PROTECT)
    posted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["recurring_debit", "due_date"], name="unique_recurring_occurrence"
            )
        ]

    def __str__(self):
        return f"{self.recurring_debit.name} on {self.due_date}"


class FundingPreferenceQuerySet(models.QuerySet):
    def enabled_for(self, beneficiary):
        return self.filter(beneficiary=beneficiary, enabled=True).order_by("priority", "bank_id")


class FundingPreference(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    beneficiary = models.ForeignKey(
        "investors.Investor", on_delete=models.CASCADE, related_name="funding_preferences"
    )
    bank = models.ForeignKey(
        BankAccount, on_delete=models.CASCADE, related_name="beneficiary_preferences"
    )
    priority = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = FundingPreferenceQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["beneficiary", "bank"], name="unique_beneficiary_funding_bank"
            )
        ]

    def __str__(self):
        return f"{self.beneficiary.name} prefers {self.bank.bank_name}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        if self.beneficiary_id and self.bank_id:
            if self.beneficiary.workspace_id != self.bank.workspace_id:
                raise ValidationError("Funding bank and beneficiary must share a workspace")
