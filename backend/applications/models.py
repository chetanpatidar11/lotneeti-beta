"""A submitted IPO application keeps the exact reviewed mapping."""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Application(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        SUBMITTED = "SUBMITTED", "Submitted"
        BLOCKED = "BLOCKED", "Blocked"
        ALLOTTED = "ALLOTTED", "Allotted"
        NOT_ALLOTTED = "NOT_ALLOTTED", "Not allotted"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace", on_delete=models.PROTECT, related_name="applications"
    )
    plan_row = models.OneToOneField(
        "planner.PlanRow", on_delete=models.PROTECT, related_name="application"
    )
    ipo = models.ForeignKey("ipos.IPO", on_delete=models.PROTECT, related_name="applications")
    applicant = models.ForeignKey(
        "investors.Investor", on_delete=models.PROTECT, related_name="applications"
    )
    demat = models.ForeignKey(
        "investors.DematAccount", on_delete=models.PROTECT, related_name="applications"
    )
    bank = models.ForeignKey(
        "funding.BankAccount", on_delete=models.PROTECT, related_name="applications"
    )
    upi = models.ForeignKey(
        "funding.UPIHandle",
        on_delete=models.PROTECT,
        related_name="applications",
        null=True,
        blank=True,
    )
    category = models.CharField(max_length=8)
    lots = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    planned_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    blocked_at = models.DateTimeField(null=True, blank=True)
    result_at = models.DateTimeField(null=True, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    expected_release_date = models.DateField(null=True, blank=True)
    allotted_quantity = models.PositiveIntegerField(null=True, blank=True)
    actual_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    shares_credited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-planned_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "ipo", "applicant"],
                condition=~Q(status="CANCELLED") & ~Q(category="SHARE"),
                name="unique_active_public_ipo_applicant",
            ),
            models.UniqueConstraint(
                fields=["workspace", "ipo", "applicant"],
                condition=~Q(status="CANCELLED") & Q(category="SHARE"),
                name="unique_active_share_ipo_applicant",
            ),
        ]

    def __str__(self):
        return f"{self.applicant_id} application for {self.ipo_id}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        if not all(
            (
                self.workspace_id,
                self.plan_row_id,
                self.ipo_id,
                self.applicant_id,
                self.demat_id,
                self.bank_id,
            )
        ):
            return
        if self.category == "BHNI":
            if self.upi_id is not None or self.bank.owner_id != self.applicant_id:
                raise ValidationError(
                    "bHNI uses the applicant’s own bank ASBA account, without UPI"
                )
        elif self.upi_id is None:
            raise ValidationError("A linked UPI is required for this category")
        row = self.plan_row
        if self.edited_at is None and (
            row.plan_run.workspace_id != self.workspace_id
            or str(self.ipo_id) != row.ipo_ref
            or str(self.applicant_id) != row.applicant_ref
            or str(self.demat_id) != row.demat_ref
            or str(self.bank_id) != row.bank_ref
            or (str(self.upi_id) if self.upi_id else "") != row.upi_ref
            or self.category != row.category
            or self.lots != row.lots
            or self.amount != row.amount
        ):
            raise ValidationError("Application mapping must match its reviewed plan row")
        if (
            self.applicant.workspace_id != self.workspace_id
            or self.bank.workspace_id != self.workspace_id
            or self.demat.investor_id != self.applicant_id
            or (self.upi_id is not None and self.upi.bank_id != self.bank_id)
        ):
            raise ValidationError("Application mapping is outside its workspace")


class AllotmentCheck(models.Model):
    """A lookup is deliberately separate from the financial result transaction."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("accounts.Workspace", on_delete=models.CASCADE)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    status = models.CharField(max_length=12, default="QUEUED")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)
    started_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Allotment check {self.pk}"


class AllotmentQuery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(AllotmentCheck, on_delete=models.CASCADE, related_name="queries")
    ipo = models.ForeignKey("ipos.IPO", on_delete=models.PROTECT)
    applicant = models.ForeignKey("investors.Investor", on_delete=models.PROTECT)
    provider = models.CharField(max_length=20, blank=True)
    state = models.CharField(max_length=20, default="QUEUED")
    records_ciphertext = models.TextField(blank=True)
    identity_hash = models.CharField(max_length=64)
    checked_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "ipo", "applicant"], name="unique_allotment_query"
            )
        ]

    def __str__(self):
        return f"Allotment query {self.pk}"


class AllotmentReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.ForeignKey(AllotmentQuery, on_delete=models.CASCADE, related_name="reviews")
    application = models.ForeignKey(Application, on_delete=models.PROTECT)
    fingerprint = models.CharField(max_length=64)
    matched_index = models.PositiveIntegerField(null=True)
    recorded_at = models.DateTimeField(null=True)
    recorded_index = models.PositiveIntegerField(null=True)
    recorded_quantity = models.PositiveIntegerField(null=True)
    recorded_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["query", "application"], name="unique_allotment_review")
        ]

    def __str__(self):
        return f"Allotment review {self.pk}"
